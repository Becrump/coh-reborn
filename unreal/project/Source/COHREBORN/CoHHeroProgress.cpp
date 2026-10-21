#include "CoHHeroProgress.h"
#include "CoHPowers.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Net/UnrealNetwork.h"

UCoHHeroProgress::UCoHHeroProgress()
{
	SetIsReplicatedByDefault(true);
}

void UCoHHeroProgress::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(UCoHHeroProgress, Hero);
	DOREPLIFETIME(UCoHHeroProgress, bHasRecord);
}

UCoHHeroProgress* UCoHHeroProgress::Of(const AActor* A) { return A ? A->FindComponentByClass<UCoHHeroProgress>() : nullptr; }
UCoHPowerComponent* UCoHHeroProgress::Powers() const { return UCoHPowerComponent::Of(GetOwner()); }

void UCoHHeroProgress::Say(const FString& Text, FLinearColor Colour) const
{
	UE_LOG(LogTemp, Log, TEXT("CoH hero %s: %s"), *Hero.Name, *Text);
	if (UCoHPowerComponent* P = Powers()) P->MulticastText(Text, Colour);
}

bool UCoHHeroProgress::LoadHeroFile(const FString& File)
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!R || GetOwnerRole() != ROLE_Authority) return false;
	FCoHHeroRecord H;
	if (!R->LoadHero(File, H)) return false;
	Hero = H;
	bHasRecord = true;
	SaveFile = FPaths::GetCleanFilename(File).Replace(TEXT(".json"), TEXT("")) + TEXT("_save.json");
	Apply(true);
	UE_LOG(LogTemp, Log, TEXT("CoH hero: %s, %s level %d (%d XP), %s / %s, %d picks, preset %s"), *Hero.Name, *Hero.Class, Hero.Level, Hero.XP,
		*Hero.Primary, *Hero.Secondary, Hero.Picks.Num(), *Hero.Preset);
	return true;
}

void UCoHHeroProgress::Apply(bool bRefillTray)
{
	UCoHPowerComponent* P = Powers();
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	const UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
	if (!P || !R || !DB) return;
	P->DisplayName = Hero.Name;
	P->SetClassAndLevel(Hero.Class, Hero.Level);
	// owned: the picks plus the free auto-issued powers for this level
	TArray<FName> Owned;
	for (const FCoHHeroPick& Pk : Hero.Picks) Owned.AddUnique(Pk.Power);
	for (const FName& A : R->AutoPowers(Hero)) Owned.AddUnique(A);
	P->Owned = Owned;
	// the tray: bought powers in order, then the inherent click / toggle powers
	// (Brawl, Sprint, Rest); passives (Defiance, Fitness) run on their own
	if (P->Tray.Num() < 10) P->Tray.SetNum(10);
	if (bRefillTray) for (FName& T : P->Tray) T = NAME_None;
	for (const FName& Id : Owned)
	{
		const FCoHPowerDef* Def = DB->FindPower(Id);
		if (!Def || Def->Type == TEXT("kAuto") || P->Tray.Contains(Id)) continue;
		const int32 Free = P->Tray.IndexOfByKey(NAME_None);
		if (Free == INDEX_NONE) break;
		P->Tray[Free] = Id;
	}
}

int32 UCoHHeroProgress::XPLevel() const
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	return R ? R->XPLevel(Hero.XP) : Hero.Level;
}

int32 UCoHHeroProgress::PicksOpen() const
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	return R && bHasRecord ? FMath::Max(0, R->PicksAllowed(Hero.Level) - Hero.Picks.Num()) : 0;
}

void UCoHHeroProgress::XPBar(int32& Into, int32& Span) const
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	Into = 0; Span = 1;
	if (!R || !R->HasRewards()) return;
	const int32 Lv = FMath::Min(XPLevel(), 49);
	const int32 Base = R->XPFor(Lv), Next = R->XPFor(Lv + 1);
	Into = Hero.XP - Base; Span = FMath::Max(1, Next - Base);
}

TArray<FName> UCoHHeroProgress::Options() const
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	return R && bHasRecord ? R->Options(Hero) : TArray<FName>();
}

void UCoHHeroProgress::Award(int32 XP, int32 Influence)
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!R || !bHasRecord || GetOwnerRole() != ROLE_Authority) return;
	const int32 DebtBefore = Hero.Debt, XPBefore = Hero.XP, LvBefore = XPLevel();
	R->GiveXP(Hero, XP);
	Hero.Influence += Influence;
	const int32 Paid = DebtBefore - Hero.Debt;
	FString Msg = FString::Printf(TEXT("+%d XP"), Hero.XP - XPBefore);
	if (Paid > 0) Msg += FString::Printf(TEXT("  (%d to debt)"), Paid);
	if (Influence > 0) Msg += FString::Printf(TEXT("  +%d influence"), Influence);
	Say(Msg, FLinearColor(0.55f, 0.85f, 1.f));
	if (XPLevel() > LvBefore) Say(FString::Printf(TEXT("LEVEL UP! You can train to level %d (press L)"), XPLevel()), FLinearColor(1.f, 0.85f, 0.2f));
	Save();
}

void UCoHHeroProgress::OnDefeatedByVillains()
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!R || !bHasRecord || GetOwnerRole() != ROLE_Authority) return;
	const int32 Added = R->Defeated(Hero);
	if (Added > 0) Say(FString::Printf(TEXT("Defeated: %d XP debt"), Added), FLinearColor(0.7f, 0.3f, 1.f));
	Save();
}

void UCoHHeroProgress::AddInspiration(FName Inspiration)
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!R || Inspiration.IsNone() || GetOwnerRole() != ROLE_Authority) return;
	const FIntPoint Tray = R->InspirationTray(Hero.Level);
	if (Hero.Inspirations.Num() >= Tray.X * Tray.Y) { Say(TEXT("Inspiration tray full"), FLinearColor::White); return; }
	Hero.Inspirations.Add(Inspiration);
	FString Short = Inspiration.ToString();
	int32 Dot; if (Short.FindLastChar(TEXT('.'), Dot)) Short = Short.Mid(Dot + 1);
	Say(TEXT("Inspiration: ") + Short.Replace(TEXT("_"), TEXT(" ")), FLinearColor(0.9f, 0.6f, 1.f));
}

void UCoHHeroProgress::Train() { ServerTrain(); }
void UCoHHeroProgress::Pick(FName Power) { ServerPick(Power); }
void UCoHHeroProgress::UseInspiration(int32 Index) { ServerUseInspiration(Index); }

void UCoHHeroProgress::ServerTrain_Implementation()
{
	if (!CanTrain()) { Say(TEXT("Not enough XP to train"), FLinearColor::White); return; }
	// one level per visit to the trainer, as in the original
	Hero.Level = FMath::Min(Hero.Level + 1, 50);
	Apply(false);
	FString Msg = FString::Printf(TEXT("Trained to level %d"), Hero.Level);
	if (PicksOpen() > 0) Msg += TEXT(": choose a new power (P)");
	Say(Msg, FLinearColor(1.f, 0.85f, 0.2f));
	Save();
}

void UCoHHeroProgress::ServerPick_Implementation(FName Power)
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!R || !bHasRecord) return;
	if (PicksOpen() <= 0) { Say(TEXT("No power pick open"), FLinearColor::White); return; }
	// the server checks every pick against the original rules
	const int32 N = Hero.Picks.Num();
	const int32 At = FMath::Max(R->PickLevel(N), 1);
	const FString Why = R->CanPick(Hero, Power, At, N);
	if (!Why.IsEmpty()) { Say(TEXT("Can't take that power: ") + Why, FLinearColor(1, 0.4f, 0.4f)); return; }
	Hero.Picks.Add({ Hero.Level, Power });
	Apply(false);
	Say(TEXT("New power: ") + Power.ToString().Mid(Power.ToString().Find(TEXT("."), ESearchCase::IgnoreCase, ESearchDir::FromEnd) + 1).Replace(TEXT("_"), TEXT(" ")), FLinearColor(1.f, 0.85f, 0.2f));
	Save();
}

void UCoHHeroProgress::ServerUseInspiration_Implementation(int32 Index)
{
	if (!Hero.Inspirations.IsValidIndex(Index)) return;
	const FName P = Hero.Inspirations[Index];
	Hero.Inspirations.RemoveAt(Index);
	if (UCoHPowerComponent* C = Powers()) C->UseFreePower(P);
}

void UCoHHeroProgress::Save() const
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (R && bHasRecord && !SaveFile.IsEmpty()) R->SaveHero(SaveFile, Hero);
}

void UCoHHeroProgress::RewardDefeat(UCoHPowerComponent* Victim, const FString& Rank, const FString& Group)
{
	const UCoHGameRules* R = UCoHGameRules::Get(Victim);
	if (!Victim || !R || !R->HasRewards() || Victim->GetOwnerRole() != ROLE_Authority) return;
	float Total = 0.f;
	for (const auto& KV : Victim->DamageBy) Total += KV.Value;
	if (Total <= 0.f) return;
	const FVector Where = Victim->GetOwner()->GetActorLocation();
	UCoHHeroProgress* Top = nullptr; float TopDamage = 0.f; bool bTopItems = false;
	for (const auto& KV : Victim->DamageBy)
	{
		AActor* Who = KV.Key.Get();
		UCoHHeroProgress* H = Of(Who);
		if (!H || !H->bHasRecord || KV.Value <= 0.f) continue;
		// no kill credit past 200 ft (DIST_FOR_KILL_CREDIT)
		if (FVector::Dist(Who->GetActorLocation(), Where) > R->KillCreditFeet * 30.48f) continue;
		const TArray<FCoHAward> A = R->Defeat(Rank, Victim->Level - 1, { H->Hero.Level - 1 }, KV.Value / Total, Group);
		if (A.Num() == 0) continue;
		UE_LOG(LogTemp, Log, TEXT("CoH reward: %s level %d %s defeated -> %s (%.0f%% damage): %d XP, %d influence"), *Group, Victim->Level, *Rank,
			*H->Hero.Name, 100.f * KV.Value / Total, A[0].XP, A[0].Influence);
		H->Award(A[0].XP, A[0].Influence);
		if (KV.Value > TopDamage) { TopDamage = KV.Value; Top = H; bTopItems = A[0].bItems; }
	}
	if (Top && bTopItems) Top->AddInspiration(R->RollDrop(Rank, Victim->Level - 1, Group));
}

#include "CoHBadges.h"
#include "CoHGameRules.h"
#include "CoHHeroProgress.h"
#include "CoHPowers.h"
#include "CoHSocial.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

void UCoHBadges::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	FString File = BadgesFile;
	if (File.IsEmpty())
	{
		FString Rules;
		GConfig->GetString(TEXT("/Script/COHREBORN.CoHPowerDatabase"), TEXT("RulesDir"), Rules, GGameIni);
		if (Rules.IsEmpty()) Rules = FPaths::ProjectContentDir() / TEXT("CoH/Data/Rules");
		File = FPaths::GetPath(Rules) / TEXT("badges/badges_game.json");      // <out>/rules -> <out>/badges
	}
	FString Text;
	TSharedPtr<FJsonObject> Root;
	if (!FFileHelper::LoadFileToString(Text, *File) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH badges: no %s (tools/badges/badges_game.py): no badges"), *File);
		return;
	}
	const TArray<TSharedPtr<FJsonValue>>* Bs;
	if (Root->TryGetArrayField(TEXT("badges"), Bs))
		for (const auto& V : *Bs)
		{
			const auto O = V->AsObject();
			if (!O.IsValid()) continue;
			FCoHBadgeDef B;
			O->TryGetStringField(TEXT("id"), B.Id); O->TryGetStringField(TEXT("category"), B.Category);
			O->TryGetStringField(TEXT("title"), B.Title); O->TryGetStringField(TEXT("text"), B.Text); O->TryGetStringField(TEXT("icon"), B.Icon);
			const TArray<TSharedPtr<FJsonValue>>* R;
			if (O->TryGetArrayField(TEXT("requires"), R)) for (const auto& T : *R) B.Requires.Add(T->AsString());
			if (!B.Id.IsEmpty() && B.Requires.Num()) Badges.Add(MoveTemp(B));
		}
	const TArray<TSharedPtr<FJsonValue>>* Ss;
	if (Root->TryGetArrayField(TEXT("spots"), Ss))
		for (const auto& V : *Ss)
		{
			const auto O = V->AsObject();
			const TArray<TSharedPtr<FJsonValue>>* P;
			if (!O.IsValid() || !O->TryGetArrayField(TEXT("pos"), P) || P->Num() < 3) continue;
			FCoHBadgeSpot Sp;
			O->TryGetStringField(TEXT("name"), Sp.Name);
			Sp.Name = TEXT("visits.") + Sp.Name.ToLower();
			Sp.Pos = FVector((*P)[0]->AsNumber(), (*P)[1]->AsNumber(), (*P)[2]->AsNumber());
			Spots.Add(Sp);
		}
	UE_LOG(LogTemp, Log, TEXT("CoH badges: %d badges, %d markers"), Badges.Num(), Spots.Num());
}

UCoHBadges* UCoHBadges::Get(const UObject* WorldContext)
{
	const UWorld* W = WorldContext ? WorldContext->GetWorld() : nullptr;
	const UGameInstance* GI = W ? W->GetGameInstance() : nullptr;
	return GI ? GI->GetSubsystem<UCoHBadges>() : nullptr;
}

// ------------------------------------------------------------------ requirements
// The original's postfix expressions: numbers, stats (kills.x, visits.x,
// badgecount...), "<attr> char>" (level, type, origin...), "<badge> owned?",
// arithmetic, comparisons, eq, && || !. Anything we don't keep is 0.
namespace CoHBadgeEval
{
	struct FVal { double N = 0; FString S; bool bStr = false; };

	static int32 StatOf(const FCoHHeroRecord& H, const FString& Key)
	{
		if (Key == TEXT("badgecount")) return H.Badges.Owned.Num();
		if (Key == TEXT("influence")) return H.Influence;
		if (Key == TEXT("level")) return H.Level;
		for (const FCoHStat& S : H.Badges.Stats) if (S.Key == Key) return S.Value;
		return 0;
	}

	static bool Run(const TArray<FString>& Tokens, const FCoHHeroRecord& H)
	{
		TArray<FVal> St;
		auto Pop = [&St]() { return St.Num() ? St.Pop(EAllowShrinking::No) : FVal(); };
		auto Num = [](double X) { FVal V; V.N = X; return V; };
		for (const FString& T : Tokens)
		{
			if (T.IsNumeric()) { St.Add(Num(FCString::Atod(*T))); continue; }
			if (T == TEXT("char>"))
			{
				const FString A = Pop().S.ToLower();
				FVal V; V.bStr = true;
				if (A == TEXT("level")) { V = Num(H.Level); }
				else if (A == TEXT("type") || A == TEXT("alignment")) V.S = TEXT("hero");
				else if (A == TEXT("origin")) V.S = H.Origin;
				else if (A == TEXT("class")) V.S = H.Class;
				else if (A == TEXT("praetorianprogress")) V.S = TEXT("normal");
				St.Add(V);
				continue;
			}
			if (T == TEXT("owned?")) { const FString Id = Pop().S; St.Add(Num(H.Badges.Owned.Contains(Id) ? 1 : 0)); continue; }
			if (T == TEXT("!")) { St.Add(Num(Pop().N == 0 ? 1 : 0)); continue; }
			if (T == TEXT("+") || T == TEXT("-") || T == TEXT("*") || T == TEXT("/") || T == TEXT("%") || T == TEXT(">=") || T == TEXT("<=")
				|| T == TEXT(">") || T == TEXT("<") || T == TEXT("&&") || T == TEXT("||") || T == TEXT("eq"))
			{
				const FVal B = Pop(), A = Pop();
				double R = 0;
				if (T == TEXT("+")) R = A.N + B.N;
				else if (T == TEXT("-")) R = A.N - B.N;
				else if (T == TEXT("*")) R = A.N * B.N;
				else if (T == TEXT("/") || T == TEXT("%")) R = B.N != 0 ? A.N / B.N : 0;
				else if (T == TEXT(">=")) R = A.N >= B.N;
				else if (T == TEXT("<=")) R = A.N <= B.N;
				else if (T == TEXT(">")) R = A.N > B.N;
				else if (T == TEXT("<")) R = A.N < B.N;
				else if (T == TEXT("&&")) R = A.N != 0 && B.N != 0;
				else if (T == TEXT("||")) R = A.N != 0 || B.N != 0;
				else R = (A.bStr || B.bStr) ? A.S.Equals(B.S, ESearchCase::IgnoreCase) : A.N == B.N;
				St.Add(Num(R));
				continue;
			}
			// a name: a stat, or the argument of char> / owned? / eq
			FVal V; V.S = T; V.N = StatOf(H, T.ToLower());
			St.Add(V);
		}
		return St.Num() > 0 && St.Last().N != 0;
	}
}

bool UCoHBadges::Eval(const FCoHBadgeDef& B, const FCoHHeroRecord& Hero) const
{
	return CoHBadgeEval::Run(B.Requires, Hero);
}

void UCoHBadges::Check(AActor* Hero) const
{
	UCoHHeroProgress* P = UCoHHeroProgress::Of(Hero);
	if (!P || !P->bHasRecord || Hero->GetLocalRole() != ROLE_Authority) return;
	bool bAny = false;
	for (int32 Pass = 0; Pass < 3; ++Pass)     // a badge can complete an accolade made of badges
	{
		bool bNew = false;
		for (const FCoHBadgeDef& B : Badges)
		{
			if (P->Hero.Badges.Owned.Contains(B.Id) || !Eval(B, P->Hero)) continue;
			P->Hero.Badges.Owned.Add(B.Id);
			bNew = bAny = true;
			if (UCoHPowerComponent* C = UCoHPowerComponent::Of(Hero)) C->MulticastText(TEXT("Badge earned: ") + B.Title, FLinearColor(1.f, 0.85f, 0.2f));
			if (UCoHSocial* S = UCoHSocial::Of(Hero)) S->Tell(ECoHChat::System, FString(), FString::Printf(TEXT("You earned the %s badge. %s"), *B.Title, *B.Text));
		}
		if (!bNew) break;
	}
	if (bAny) P->Save();
}

void UCoHBadges::Grant(AActor* Hero, const FString& Id)
{
	UCoHHeroProgress* P = UCoHHeroProgress::Of(Hero);
	const UCoHBadges* B = Get(Hero);
	if (!P || !P->bHasRecord || !B || Id.IsEmpty()) return;
	const FCoHBadgeDef* Def = B->Badges.FindByPredicate([&Id](const FCoHBadgeDef& X) { return X.Id.Equals(Id, ESearchCase::IgnoreCase); });
	if (!Def) { AddStat(Hero, TEXT("token.") + Id); return; }
	if (!P->Hero.Badges.Owned.Contains(Def->Id))
	{
		P->Hero.Badges.Owned.Add(Def->Id);
		if (UCoHPowerComponent* C = UCoHPowerComponent::Of(Hero)) C->MulticastText(TEXT("Badge earned: ") + Def->Title, FLinearColor(1.f, 0.85f, 0.2f));
		if (UCoHSocial* S = UCoHSocial::Of(Hero)) S->Tell(ECoHChat::System, FString(), FString::Printf(TEXT("You earned the %s badge. %s"), *Def->Title, *Def->Text));
	}
	B->Check(Hero);      // accolades made of this badge
	P->Save();
}

void UCoHBadges::AddStat(AActor* Hero, const FString& Key, int32 Amount)
{
	UCoHHeroProgress* P = UCoHHeroProgress::Of(Hero);
	const UCoHBadges* B = Get(Hero);
	if (!P || !P->bHasRecord || !B || Key.IsEmpty()) return;
	const FString K = Key.ToLower();
	FCoHStat* S = P->Hero.Badges.Stats.FindByPredicate([&K](const FCoHStat& X) { return X.Key == K; });
	if (!S) { S = &P->Hero.Badges.Stats.AddDefaulted_GetRef(); S->Key = K; }
	S->Value += Amount;
	B->Check(Hero);
}

void UCoHBadges::OnDefeat(AActor* Hero, const FString& Group, const FString& Rank, const FString& Villain)
{
	UCoHHeroProgress* P = UCoHHeroProgress::Of(Hero);
	const UCoHBadges* B = Get(Hero);
	if (!P || !P->bHasRecord || !B) return;
	// the original counts each defeat by group, group and rank, and villain
	const FString R = Rank.Contains(TEXT("Boss")) ? TEXT("boss") : (Rank.Contains(TEXT("Lt")) || Rank.Contains(TEXT("Lieutenant"))) ? TEXT("lieutenant") : TEXT("minion");
	TArray<FString> Keys;
	if (!Group.IsEmpty()) { Keys.Add(TEXT("kills.") + Group.ToLower()); Keys.Add(TEXT("kills.") + Group.ToLower() + TEXT(".") + R); }
	if (!Villain.IsEmpty()) Keys.Add(TEXT("kills.") + Villain.ToLower());
	for (const FString& K : Keys)
	{
		FCoHStat* S = P->Hero.Badges.Stats.FindByPredicate([&K](const FCoHStat& X) { return X.Key == K; });
		if (!S) { S = &P->Hero.Badges.Stats.AddDefaulted_GetRef(); S->Key = K; }
		S->Value += 1;
	}
	B->Check(Hero);
}

FString UCoHBadges::Describe(const AActor* Hero) const
{
	const UCoHHeroProgress* P = UCoHHeroProgress::Of(Hero);
	if (!P || !P->bHasRecord) return TEXT("No hero loaded.");
	TArray<FString> Titles;
	for (const FString& Id : P->Hero.Badges.Owned)
		if (const FCoHBadgeDef* B = Badges.FindByPredicate([&Id](const FCoHBadgeDef& X) { return X.Id == Id; })) Titles.Add(B->Title);
	return FString::Printf(TEXT("%d of %d badges%s%s"), Titles.Num(), Badges.Num(), Titles.Num() ? TEXT(": ") : TEXT(""), *FString::Join(Titles, TEXT(", ")));
}

void UCoHBadges::Tick(float DeltaTime)
{
	UGameInstance* GI = GetGameInstance();
	UWorld* W = GI ? GI->GetWorld() : nullptr;
	if (!W || W->GetNetMode() == NM_Client || (NextVisitCheck -= DeltaTime) > 0.f) return;
	NextVisitCheck = 1.f;
	for (FConstPlayerControllerIterator It = W->GetPlayerControllerIterator(); It; ++It)
	{
		APawn* Pawn = It->Get() ? It->Get()->GetPawn() : nullptr;
		UCoHHeroProgress* P = UCoHHeroProgress::Of(Pawn);
		if (!P || !P->bHasRecord) continue;
		const FVector At = Pawn->GetActorLocation();
		for (const FCoHBadgeSpot& Sp : Spots)
		{
			if (FVector::DistSquared2D(Sp.Pos, At) > VisitRadius * VisitRadius || FMath::Abs(Sp.Pos.Z - At.Z) > 2000.f) continue;
			if (P->Hero.Badges.Stats.ContainsByPredicate([&Sp](const FCoHStat& X) { return X.Key == Sp.Name; })) continue;
			AddStat(Pawn, Sp.Name, 1);
		}
	}
}

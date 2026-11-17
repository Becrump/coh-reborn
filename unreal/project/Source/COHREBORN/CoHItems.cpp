#include "CoHItems.h"
#include "CoHHeroProgress.h"
#include "CoHPowers.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/SWeakWidget.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Text/STextBlock.h"

// ------------------------------------------------------------------ UCoHItems
FString FCoHBoostDef::Short() const
{
	static const TMap<FString, FString> Names = {
		{ TEXT("kDamage_Boost"), TEXT("Dmg") }, { TEXT("kAccuracy_Boost"), TEXT("Acc") }, { TEXT("kRecharge_Boost"), TEXT("Rech") },
		{ TEXT("kEnduranceDiscount_Boost"), TEXT("EndRdx") }, { TEXT("kRange_Boost"), TEXT("Range") }, { TEXT("kHeal_Boost"), TEXT("Heal") },
		{ TEXT("kHold_Boost"), TEXT("Hold") }, { TEXT("kStun_Boost"), TEXT("Stun") }, { TEXT("kSleep_Boost"), TEXT("Sleep") },
		{ TEXT("kImmobilize_Boost"), TEXT("Immob") }, { TEXT("kConfuse_Boost"), TEXT("Conf") }, { TEXT("kFear_Boost"), TEXT("Fear") },
		{ TEXT("kRes_Damage_Boost"), TEXT("ResDam") }, { TEXT("kDefense_Buff_Boost"), TEXT("DefBuf") }, { TEXT("kInterrupt_Boost"), TEXT("Intrpt") },
		{ TEXT("kRecovery_Boost"), TEXT("EndMod") }, { TEXT("kEnduranceModification_Boost"), TEXT("EndMod") }, { TEXT("kKnockback_Boost"), TEXT("KB") },
		{ TEXT("kSnare_Boost"), TEXT("Slow") }, { TEXT("kTaunt_Boost"), TEXT("Taunt") }, { TEXT("kToHit_Buff_Boost"), TEXT("ToHit") },
		{ TEXT("kToHit_DeBuff_Boost"), TEXT("ToHitDeb") }, { TEXT("kDefense_DeBuff_Boost"), TEXT("DefDeb") }, { TEXT("kRun_Boost"), TEXT("Run") },
		{ TEXT("kJump_Boost"), TEXT("Jump") }, { TEXT("kFly_Boost"), TEXT("Fly") } };
	if (const FString* N = Names.Find(Type)) return *N;
	FString S = Type; S.RemoveFromStart(TEXT("k")); S.RemoveFromEnd(TEXT("_Boost"));
	return S.Left(7);
}

void UCoHItems::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	FString File = ItemsFile;
	if (File.IsEmpty())
	{
		FString Rules;
		GConfig->GetString(TEXT("/Script/COHREBORN.CoHPowerDatabase"), TEXT("RulesDir"), Rules, GGameIni);
		if (Rules.IsEmpty()) Rules = FPaths::ProjectContentDir() / TEXT("CoH/Data/Rules");
		File = FPaths::GetPath(Rules) / TEXT("items/items_game.json");      // <out>/rules -> <out>/items
	}
	FString Text;
	TSharedPtr<FJsonObject> Root;
	if (!FFileHelper::LoadFileToString(Text, *File) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH items: no %s (tools/items/items_game.py): no enhancements"), *File);
		return;
	}
	auto Strs = [](const TSharedPtr<FJsonObject>& O, const TCHAR* K)
	{
		TArray<FString> Out; const TArray<TSharedPtr<FJsonValue>>* A;
		if (O->TryGetArrayField(K, A)) for (const auto& V : *A) { FString S; if (V->TryGetString(S)) Out.Add(S); }
		return Out;
	};
	const TSharedPtr<FJsonObject>* Bs;
	if (Root->TryGetObjectField(TEXT("boosts"), Bs))
		for (const auto& KV : (*Bs)->Values)
		{
			const auto O = KV.Value->AsObject();
			if (!O.IsValid()) continue;
			FCoHBoostDef B;
			B.Id = FString(KV.Key);
			O->TryGetStringField(TEXT("name"), B.Name); O->TryGetStringField(TEXT("grade"), B.Grade);
			O->TryGetStringField(TEXT("type"), B.Type); O->TryGetStringField(TEXT("icon"), B.Icon); O->TryGetStringField(TEXT("help"), B.Help);
			double Sc = 0; O->TryGetNumberField(TEXT("scale"), Sc); B.Scale = (float)Sc;
			FString Sched; O->TryGetStringField(TEXT("schedule"), Sched); B.bScheduleB = Sched == TEXT("B");
			B.Origins = Strs(O, TEXT("origins")); B.Attribs = Strs(O, TEXT("attribs"));
			Boosts.Add(B.Id, MoveTemp(B));
		}
	const TSharedPtr<FJsonObject>* Ss;
	if (Root->TryGetObjectField(TEXT("stores"), Ss))
		for (const auto& KV : (*Ss)->Values)
		{
			TArray<FCoHStoreItem>& L = Stores.Add(FString(KV.Key));
			for (const auto& V : KV.Value->AsArray())
			{
				const auto O = V->AsObject();
				if (!O.IsValid()) continue;
				FCoHStoreItem It; O->TryGetStringField(TEXT("boost"), It.Boost);
				double Lv = 1, Pr = 0; O->TryGetNumberField(TEXT("level"), Lv); O->TryGetNumberField(TEXT("price"), Pr);
				It.Level = (int32)Lv; It.Price = (int32)Pr;
				L.Add(It);
			}
		}
	auto Nums = [&](const TCHAR* K, TArray<float>& Out) { const TArray<TSharedPtr<FJsonValue>>* A; if (Root->TryGetArrayField(K, A)) for (const auto& V : *A) Out.Add((float)V->AsNumber()); };
	TArray<float> Sl; Nums(TEXT("slots"), Sl); for (float L : Sl) SlotLevels.Add((int32)L);
	Nums(TEXT("effect_above"), Above); Nums(TEXT("effect_below"), Below);
	UE_LOG(LogTemp, Log, TEXT("CoH items: %d enhancements, %d stores, %d slot levels"), Boosts.Num(), Stores.Num(), SlotLevels.Num());
}

UCoHItems* UCoHItems::Get(const UObject* WorldContext)
{
	const UWorld* W = WorldContext ? WorldContext->GetWorld() : nullptr;
	const UGameInstance* GI = W ? W->GetGameInstance() : nullptr;
	return GI ? GI->GetSubsystem<UCoHItems>() : nullptr;
}

int32 UCoHItems::SlotsAt(int32 Level) const
{
	int32 N = 0;
	for (int32 L : SlotLevels) if (L <= Level) ++N;
	return N;
}

bool UCoHItems::Split(const FString& Item, FString& Id, int32& Level)
{
	FString L;
	if (!Item.Split(TEXT("@"), &Id, &L)) return false;
	FString Lv = L; L.Split(TEXT("@"), &Lv, nullptr);
	Level = FMath::Max(1, FCString::Atoi(*Lv));
	return !Id.IsEmpty();
}

float UCoHItems::Strength(const FCoHBoostDef& B, int32 EnhLevel, int32 HeroLevel) const
{
	const int32 Diff = EnhLevel - HeroLevel;
	float E = 1.f;
	if (Diff > 0 && Above.Num()) E = Above[FMath::Min(Diff, Above.Num() - 1)];
	else if (Diff < 0)
	{
		if (-Diff > 3) return 0.f;      // red: too far below the hero to work
		if (Below.Num()) E = Below[FMath::Min(-Diff, Below.Num() - 1)];
	}
	return B.Scale * E;
}

float UCoHItems::Diminish(float T, bool bB)
{
	const float A = bB ? 0.4f : 0.7f, Bk = bB ? 0.5f : 0.9f, C = bB ? 0.6f : 1.0f;
	if (T <= A) return T;
	if (T <= Bk) return A + (T - A) * 0.9f;
	const float AtB = A + (Bk - A) * 0.9f;
	if (T <= C) return AtB + (T - Bk) * 0.7f;
	return AtB + (C - Bk) * 0.7f + (T - C) * 0.15f;
}

bool UCoHItems::Fits(const FCoHBoostDef& B, const FCoHPowerDef& P, const FString& Origin) const
{
	if (!P.BoostsAllowed.Contains(B.Type)) return false;
	if (B.Origins.Num() == 0 || Origin.IsEmpty()) return true;
	for (const FString& O : B.Origins) if (Origin.Contains(O) || O.Contains(Origin)) return true;
	return false;
}

FString UCoHItems::RandomDrop(const FString& Origin, int32 Level) const
{
	const FString Grade = Level < 12 ? TEXT("TO") : Level < 22 ? TEXT("DO") : TEXT("SO");
	TArray<const FCoHBoostDef*> Pool;
	for (const auto& KV : Boosts)
	{
		const FCoHBoostDef& B = KV.Value;
		if (B.Grade != Grade) continue;
		bool bOrigin = B.Origins.Num() == 0 || Origin.IsEmpty();
		for (const FString& O : B.Origins) if (Origin.Contains(O)) bOrigin = true;
		if (bOrigin) Pool.Add(&B);
	}
	if (Pool.Num() == 0) return FString();
	const int32 Lv = FMath::Clamp(Level + FMath::RandRange(-1, 2), 1, 53);
	return FString::Printf(TEXT("%s@%d"), *Pool[FMath::RandRange(0, Pool.Num() - 1)]->Id, Lv);
}

int32 UCoHItems::SellPrice(const FString& Item) const
{
	FString Id; int32 Lv = 1;
	if (!Split(Item, Id, Lv)) return 0;
	for (const auto& KV : Stores)
		for (const FCoHStoreItem& It : KV.Value)
			if (It.Boost == Id && It.Level == Lv) return FMath::Max(1, It.Price * 2 / 5);
	return 10 * Lv;
}

FString UCoHItems::Label(const FString& Item) const
{
	FString Id; int32 Lv = 1;
	if (!Split(Item, Id, Lv)) return Item;
	const FCoHBoostDef* B = Boost(Id);
	return B ? FString::Printf(TEXT("%s %s %d"), *B->Grade, *B->Short(), Lv) : Item;
}

// ------------------------------------------------------------------ the window
class SCoHEnhPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHEnhPanel) {}
		SLATE_ARGUMENT(TWeakObjectPtr<UCoHEnhancements>, Owner)
	SLATE_END_ARGS()

	void Construct(const FArguments& Args)
	{
		Owner = Args._Owner;
		ChildSlot
		[
			SNew(SOverlay)
			+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
			[
				SAssignNew(Window, SBox).WidthOverride(760).MaxDesiredHeight(640).Visibility(EVisibility::Collapsed)
				[
					SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.03f, 0.06f, 0.16f, 0.94f)).Padding(14)
					[
						SAssignNew(Body, SVerticalBox)
					]
				]
			]
		];
	}

	bool IsOpen() const { return Window.IsValid() && Window->GetVisibility() == EVisibility::Visible; }
	void Open(bool bStore) { bStoreMode = bStore; Selected = INDEX_NONE; Window->SetVisibility(EVisibility::Visible); Rebuild(); }
	void Close() { Window->SetVisibility(EVisibility::Collapsed); }

	virtual void Tick(const FGeometry& G, const double Now, const float Dt) override
	{
		SCompoundWidget::Tick(G, Now, Dt);
		if (!IsOpen()) return;
		const FString Sig = Signature();
		if (Sig != LastSig) Rebuild();
	}

private:
	TWeakObjectPtr<UCoHEnhancements> Owner;
	TSharedPtr<SBox> Window;
	TSharedPtr<SVerticalBox> Body;
	bool bStoreMode = false;
	int32 Selected = INDEX_NONE;
	FString LastSig;

	FString Signature() const
	{
		const UCoHEnhancements* E = Owner.Get();
		const FCoHBoostState* S = E ? E->State() : nullptr;
		const UCoHHeroProgress* P = E ? E->Progress() : nullptr;
		if (!S || !P) return FString();
		FString Out = FString::Printf(TEXT("%d|%d|%d|%s|"), P->Hero.Level, P->Hero.Influence, Selected, *FString::Join(S->Inventory, TEXT(",")));
		for (const FCoHPowerSlots& Ps : S->Slots) Out += Ps.Power.ToString() + TEXT(":") + FString::Join(Ps.Enh, TEXT(",")) + TEXT(";");
		if (const UCoHPowerComponent* C = E->Powers()) for (const FName& O : C->Owned) Out += O.ToString();
		return Out + E->StoreTitle + FString::FromInt(E->StoreRows.Num());
	}

	static TSharedRef<SWidget> Label(const FString& T, FLinearColor C = FLinearColor(0.85f, 0.92f, 1.f), int32 Size = 11, bool bBold = false)
	{
		return SNew(STextBlock).Text(FText::FromString(T)).ColorAndOpacity(C).Font(FCoreStyle::GetDefaultFontStyle(bBold ? "Bold" : "Regular", Size));
	}
	TSharedRef<SWidget> Button(const FString& T, TFunction<void()> Do, FLinearColor C = FLinearColor(0.2f, 0.35f, 0.6f))
	{
		return SNew(SButton).ButtonColorAndOpacity(C).ContentPadding(FMargin(6, 2))
			.OnClicked_Lambda([Do]() { Do(); return FReply::Handled(); })
			[Label(T, FLinearColor::White, 10)];
	}

	void Rebuild()
	{
		LastSig = Signature();
		Body->ClearChildren();
		UCoHEnhancements* E = Owner.Get();
		const FCoHBoostState* S = E ? E->State() : nullptr;
		const UCoHItems* I = UCoHItems::Get(E);
		const UCoHPowerComponent* C = E ? E->Powers() : nullptr;
		const UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(E);
		const UCoHHeroProgress* HP = E ? E->Progress() : nullptr;
		TSharedRef<SHorizontalBox> Head = SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(1.f)[Label(bStoreMode && E ? E->StoreTitle : FString(TEXT("Enhancements")), FLinearColor(0.55f, 0.85f, 1.f), 15, true)]
			+ SHorizontalBox::Slot().AutoWidth()[Button(TEXT("Close"), [this]() { Close(); })];
		Body->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Head];
		if (!E || !S || !I || !C || !DB || !HP) { Body->AddSlot().AutoHeight()[Label(TEXT("No hero loaded."))]; return; }
		Body->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Label(FString::Printf(TEXT("Influence %d    Slots to place: %d    %s"), HP->Hero.Influence, E->SlotsLeft(),
			Selected != INDEX_NONE ? TEXT("Click a slot to put the selected enhancement in it.") : TEXT("Pick an enhancement below, then a slot.")), FLinearColor(1.f, 0.9f, 0.55f))];
		TSharedRef<SScrollBox> Scroll = SNew(SScrollBox);
		if (bStoreMode)
		{
			for (int32 r = 0; r < E->StoreRows.Num(); ++r)
			{
				TArray<FString> Parts; E->StoreRows[r].ParseIntoArray(Parts, TEXT("@"));
				if (Parts.Num() < 3) continue;
				const FCoHBoostDef* B = I->Boost(Parts[0]);
				const FString Name = B ? FString::Printf(TEXT("%s  (level %s, %s)"), *B->Name, *Parts[1], *B->Help) : Parts[0];
				Scroll->AddSlot().Padding(0, 1)
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center)[Label(Name)]
					+ SHorizontalBox::Slot().AutoWidth()[Button(FString::Printf(TEXT("Buy %s inf"), *Parts[2]), [E, r]() { E->ServerBuy(r); }, FLinearColor(0.2f, 0.5f, 0.3f))]
				];
			}
		}
		else
		{
			for (const FName& Id : C->Owned)
			{
				const FCoHPowerDef* P = DB->FindPower(Id);
				if (!P || P->BoostsAllowed.Num() == 0) continue;
				const FCoHPowerSlots* Ps = S->Slots.FindByPredicate([&](const FCoHPowerSlots& X) { return X.Power == Id; });
				const int32 N = Ps ? FMath::Max(1, Ps->Enh.Num()) : 1;
				TSharedRef<SHorizontalBox> Row = SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[SNew(SBox).WidthOverride(200)[Label(P->Display)]];
				for (int32 k = 0; k < N; ++k)
				{
					const FString Item = Ps && Ps->Enh.IsValidIndex(k) ? Ps->Enh[k] : FString();
					const FName PowerId = Id;
					Row->AddSlot().AutoWidth().Padding(2, 0)[Button(Item.IsEmpty() ? TEXT("  empty  ") : I->Label(Item), [this, E, PowerId, k]()
					{
						if (Selected != INDEX_NONE) { E->ServerSlot(Selected, PowerId, k); Selected = INDEX_NONE; }
					}, Item.IsEmpty() ? FLinearColor(0.15f, 0.18f, 0.25f) : FLinearColor(0.25f, 0.4f, 0.7f))];
				}
				if (N < 6 && E->SlotsLeft() > 0)
				{
					const FName PowerId = Id;
					Row->AddSlot().AutoWidth().Padding(6, 0)[Button(TEXT("+ slot"), [E, PowerId]() { E->ServerAddSlot(PowerId); }, FLinearColor(0.45f, 0.4f, 0.1f))];
				}
				Scroll->AddSlot().Padding(0, 2)[Row];
			}
		}
		Body->AddSlot().FillHeight(1.f)[Scroll];
		// the enhancement tray
		Body->AddSlot().AutoHeight().Padding(0, 8, 0, 2)[Label(FString::Printf(TEXT("Enhancement tray (%d / %d)"), S->Inventory.Num(), E->TraySize), FLinearColor(0.55f, 0.85f, 1.f), 12, true)];
		TSharedRef<SWrapBox> Tray = SNew(SWrapBox).UseAllottedSize(true);
		for (int32 t = 0; t < S->Inventory.Num(); ++t)
		{
			const FString Item = S->Inventory[t];
			Tray->AddSlot().Padding(2)[Button(I->Label(Item), [this, t]() { Selected = Selected == t ? INDEX_NONE : t; Rebuild(); },
				t == Selected ? FLinearColor(0.75f, 0.55f, 0.1f) : FLinearColor(0.25f, 0.4f, 0.7f))];
		}
		Body->AddSlot().AutoHeight()[Tray];
		if (Selected != INDEX_NONE && S->Inventory.IsValidIndex(Selected))
		{
			const int32 T = Selected;
			TSharedRef<SHorizontalBox> Acts = SNew(SHorizontalBox);
			if (bStoreMode) Acts->AddSlot().AutoWidth().Padding(2)[Button(FString::Printf(TEXT("Sell for %d inf"), I->SellPrice(S->Inventory[T])), [this, E, T]() { E->ServerSell(T); Selected = INDEX_NONE; }, FLinearColor(0.2f, 0.5f, 0.3f))];
			Acts->AddSlot().AutoWidth().Padding(2)[Button(TEXT("Trash"), [this, E, T]() { E->ServerTrash(T); Selected = INDEX_NONE; }, FLinearColor(0.5f, 0.15f, 0.15f))];
			Body->AddSlot().AutoHeight().Padding(0, 4, 0, 0)[Acts];
		}
	}
};

// ------------------------------------------------------------------ UCoHEnhancements
UCoHEnhancements::UCoHEnhancements()
{
	SetIsReplicatedByDefault(true);
}

UCoHEnhancements* UCoHEnhancements::Of(const AActor* A) { return A ? A->FindComponentByClass<UCoHEnhancements>() : nullptr; }
UCoHHeroProgress* UCoHEnhancements::Progress() const { return UCoHHeroProgress::Of(GetOwner()); }
UCoHPowerComponent* UCoHEnhancements::Powers() const { return UCoHPowerComponent::Of(GetOwner()); }
const FCoHBoostState* UCoHEnhancements::State() const { const UCoHHeroProgress* P = Progress(); return P && P->bHasRecord ? &P->Hero.Boosts : nullptr; }
FCoHBoostState* UCoHEnhancements::MutableState() const { UCoHHeroProgress* P = Progress(); return P && P->bHasRecord ? &P->Hero.Boosts : nullptr; }

void UCoHEnhancements::BeginPlay()
{
	Super::BeginPlay();
	const APawn* Pawn = Cast<APawn>(GetOwner());
	if (Pawn && Pawn->IsLocallyControlled() && GEngine && GEngine->GameViewport)
	{
		Panel = SNew(SCoHEnhPanel).Owner(this);
		PanelHost = SNew(SWeakWidget).PossiblyNullContent(Panel);
		GEngine->GameViewport->AddViewportWidgetContent(PanelHost.ToSharedRef(), 9);
	}
}

void UCoHEnhancements::EndPlay(const EEndPlayReason::Type Reason)
{
	if (PanelHost.IsValid() && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(PanelHost.ToSharedRef());
	PanelHost.Reset(); Panel.Reset();
	Super::EndPlay(Reason);
}

void UCoHEnhancements::TogglePanel()
{
	if (!Panel.IsValid()) return;
	if (Panel->IsOpen()) Panel->Close(); else Panel->Open(false);
}

int32 UCoHEnhancements::SlotsLeft() const
{
	const UCoHItems* I = UCoHItems::Get(this);
	const UCoHHeroProgress* P = Progress();
	const FCoHBoostState* S = State();
	if (!I || !P || !S) return 0;
	int32 Used = 0;
	for (const FCoHPowerSlots& Ps : S->Slots) Used += FMath::Max(0, Ps.Enh.Num() - 1);
	return FMath::Max(0, I->SlotsAt(P->Hero.Level) - Used);
}

void UCoHEnhancements::Changed()
{
	if (UCoHHeroProgress* P = Progress()) { P->Apply(false); P->Save(); }
}

static void CoHEnhSay(const UCoHEnhancements* E, const FString& Text, FLinearColor C = FLinearColor(0.6f, 0.85f, 1.f))
{
	if (UCoHPowerComponent* P = E ? E->Powers() : nullptr) P->MulticastText(Text, C);
}

bool UCoHEnhancements::Give(const FString& Item, bool bSay)
{
	FCoHBoostState* S = MutableState();
	const UCoHItems* I = UCoHItems::Get(this);
	if (!S || !I || Item.IsEmpty()) return false;
	if (S->Inventory.Num() >= TraySize) { if (bSay) CoHEnhSay(this, TEXT("Enhancement tray full"), FLinearColor(1.f, 0.6f, 0.4f)); return false; }
	S->Inventory.Add(Item);
	if (bSay) CoHEnhSay(this, TEXT("Enhancement: ") + I->Label(Item));
	Changed();
	return true;
}

void UCoHEnhancements::OnVillainDefeated(AActor* Hero, int32 VillainLevel)
{
	UCoHEnhancements* E = Of(Hero);
	const UCoHItems* I = UCoHItems::Get(Hero);
	const UCoHHeroProgress* P = E ? E->Progress() : nullptr;
	if (!E || !I || !P || !P->bHasRecord || FMath::FRand() > 0.07f) return;
	E->Give(I->RandomDrop(P->Hero.Origin, FMath::Max(1, VillainLevel)));
}

void UCoHEnhancements::ServerAddSlot_Implementation(FName Power)
{
	FCoHBoostState* S = MutableState();
	const UCoHPowerComponent* C = Powers();
	if (!S || !C || !C->Owned.Contains(Power) || SlotsLeft() <= 0) return;
	FCoHPowerSlots* Ps = S->Slots.FindByPredicate([&](const FCoHPowerSlots& X) { return X.Power == Power; });
	if (!Ps) { Ps = &S->Slots.AddDefaulted_GetRef(); Ps->Power = Power; Ps->Enh.SetNum(1); }
	if (Ps->Enh.Num() >= 6) return;
	Ps->Enh.Add(FString());
	Changed();
}

void UCoHEnhancements::ServerSlot_Implementation(int32 TrayIndex, FName Power, int32 SlotIndex)
{
	FCoHBoostState* S = MutableState();
	const UCoHItems* I = UCoHItems::Get(this);
	const UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
	const UCoHPowerComponent* C = Powers();
	const UCoHHeroProgress* HP = Progress();
	if (!S || !I || !DB || !C || !HP || !S->Inventory.IsValidIndex(TrayIndex) || !C->Owned.Contains(Power)) return;
	const FString Item = S->Inventory[TrayIndex];
	FString Id; int32 Lv = 1;
	const FCoHBoostDef* B = UCoHItems::Split(Item, Id, Lv) ? I->Boost(Id) : nullptr;
	const FCoHPowerDef* P = DB->FindPower(Power);
	if (!B || !P) return;
	if (!I->Fits(*B, *P, HP->Hero.Origin)) { CoHEnhSay(this, FString::Printf(TEXT("%s can't take %s"), *P->Display, *B->Name), FLinearColor(1.f, 0.6f, 0.4f)); return; }
	if (Lv > HP->Hero.Level + 3) { CoHEnhSay(this, TEXT("That enhancement's level is too high for you"), FLinearColor(1.f, 0.6f, 0.4f)); return; }
	FCoHPowerSlots* Ps = S->Slots.FindByPredicate([&](const FCoHPowerSlots& X) { return X.Power == Power; });
	if (!Ps) { Ps = &S->Slots.AddDefaulted_GetRef(); Ps->Power = Power; Ps->Enh.SetNum(1); }
	if (!Ps->Enh.IsValidIndex(SlotIndex)) SlotIndex = Ps->Enh.IndexOfByKey(FString());
	if (!Ps->Enh.IsValidIndex(SlotIndex)) { CoHEnhSay(this, TEXT("No open slot in ") + P->Display, FLinearColor(1.f, 0.6f, 0.4f)); return; }
	Ps->Enh[SlotIndex] = Item;      // whatever was there is replaced (destroyed), as in the original
	S->Inventory.RemoveAt(TrayIndex);
	Changed();
}

void UCoHEnhancements::ServerTrash_Implementation(int32 TrayIndex)
{
	FCoHBoostState* S = MutableState();
	if (!S || !S->Inventory.IsValidIndex(TrayIndex)) return;
	S->Inventory.RemoveAt(TrayIndex);
	Changed();
}

void UCoHEnhancements::ServerSell_Implementation(int32 TrayIndex)
{
	FCoHBoostState* S = MutableState();
	const UCoHItems* I = UCoHItems::Get(this);
	UCoHHeroProgress* HP = Progress();
	if (!S || !I || !HP || OpenRows.Num() == 0 || !S->Inventory.IsValidIndex(TrayIndex)) return;
	const int32 Price = I->SellPrice(S->Inventory[TrayIndex]);
	S->Inventory.RemoveAt(TrayIndex);
	HP->Hero.Influence += Price;
	CoHEnhSay(this, FString::Printf(TEXT("Sold for %d influence"), Price));
	Changed();
}

void UCoHEnhancements::ServerBuy_Implementation(int32 Row)
{
	UCoHHeroProgress* HP = Progress();
	if (!HP || !OpenRows.IsValidIndex(Row)) return;
	TArray<FString> Parts; OpenRows[Row].ParseIntoArray(Parts, TEXT("@"));
	if (Parts.Num() < 3) return;
	const int32 Price = FCString::Atoi(*Parts[2]);
	if (HP->Hero.Influence < Price) { CoHEnhSay(this, TEXT("Not enough influence"), FLinearColor(1.f, 0.6f, 0.4f)); return; }
	const FCoHBoostState* S = State();
	if (!S || S->Inventory.Num() >= TraySize) { CoHEnhSay(this, TEXT("Enhancement tray full"), FLinearColor(1.f, 0.6f, 0.4f)); return; }
	HP->Hero.Influence -= Price;
	Give(Parts[0] + TEXT("@") + Parts[1]);
}

void UCoHEnhancements::OpenStore(const TArray<FString>& StoreIds, const FString& Title)
{
	const UCoHItems* I = UCoHItems::Get(this);
	const UCoHHeroProgress* HP = Progress();
	if (!I || !HP) return;
	const int32 Lv = HP->Hero.Level;
	TArray<FString> Rows;
	for (const FString& Sid : StoreIds)
		if (const TArray<FCoHStoreItem>* L = I->Stores.Find(Sid))
			for (const FCoHStoreItem& It : *L)
			{
				const FCoHBoostDef* B = I->Boost(It.Boost);
				if (!B || It.Level < Lv - 2 || It.Level > Lv + 3) continue;     // around the hero's level, as the store's list scrolls
				bool bOrigin = B->Origins.Num() == 0 || HP->Hero.Origin.IsEmpty();
				for (const FString& O : B->Origins) if (HP->Hero.Origin.Contains(O)) bOrigin = true;
				if (!bOrigin) continue;
				Rows.AddUnique(FString::Printf(TEXT("%s@%d@%d"), *It.Boost, It.Level, It.Price));
			}
	Rows.Sort();
	if (Rows.Num() > 120) Rows.SetNum(120);
	OpenRows = Rows;
	ClientShowStore(Title, Rows);
}

void UCoHEnhancements::ClientShowStore_Implementation(const FString& Title, const TArray<FString>& Rows)
{
	StoreTitle = Title;
	StoreRows = Rows;
	if (Panel.IsValid()) Panel->Open(true);
}

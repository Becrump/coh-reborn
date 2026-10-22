#include "CoHGameRules.h"
#include "CoHPowers.h"
#include "Animation/AnimSequenceBase.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Engine/GameInstance.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

static constexpr int32 MaxLevel = 50;
static constexpr float FeetToCm = 30.48f;

// ------------------------------------------------------------------ json helpers
static bool ReadJson(const FString& Path, TSharedPtr<FJsonValue>& Out)
{
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *Path))
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH game rules: missing %s"), *Path);
		return false;
	}
	return FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Out) && Out.IsValid();
}
static FString S(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
{
	const TSharedPtr<FJsonValue> V = O.IsValid() ? O->TryGetField(K) : nullptr;
	if (!V.IsValid() || V->IsNull()) return FString();
	if (V->Type == EJson::Number) return FString::SanitizeFloat(V->AsNumber());
	if (V->Type == EJson::Array) { const auto& A = V->AsArray(); return A.Num() ? A[0]->AsString() : FString(); }
	return V->AsString();
}
static double N(const TSharedPtr<FJsonObject>& O, const TCHAR* K, double D = 0)
{
	const TSharedPtr<FJsonValue> V = O.IsValid() ? O->TryGetField(K) : nullptr;
	if (!V.IsValid() || V->IsNull()) return D;
	if (V->Type == EJson::Number) return V->AsNumber();
	if (V->Type == EJson::Boolean) return V->AsBool() ? 1 : 0;
	if (V->Type == EJson::String) return FCString::Atod(*V->AsString());
	return D;
}
static bool B(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
{
	const TSharedPtr<FJsonValue> V = O.IsValid() ? O->TryGetField(K) : nullptr;
	if (!V.IsValid() || V->IsNull()) return false;
	if (V->Type == EJson::Boolean) return V->AsBool();
	if (V->Type == EJson::Number) return V->AsNumber() != 0;
	return !V->AsString().IsEmpty();
}
/** A string, a list of strings / numbers, or null -> tokens. */
static TArray<FString> Tokens(const TSharedPtr<FJsonValue>& V)
{
	TArray<FString> Out;
	if (!V.IsValid() || V->IsNull()) return Out;
	if (V->Type == EJson::Array)
		for (const auto& E : V->AsArray()) Out.Add(E->Type == EJson::Number ? FString::SanitizeFloat(E->AsNumber()) : E->AsString());
	else if (V->Type == EJson::Number) Out.Add(FString::SanitizeFloat(V->AsNumber()));
	else Out.Add(V->AsString());
	return Out;
}
static TArray<FString> L(const TSharedPtr<FJsonObject>& O, const TCHAR* K) { return Tokens(O.IsValid() ? O->TryGetField(K) : nullptr); }
static TArray<int32> Ints(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
{
	TArray<int32> Out;
	const TArray<TSharedPtr<FJsonValue>>* A;
	if (O.IsValid() && O->TryGetArrayField(K, A)) for (const auto& V : *A) Out.Add((int32)V->AsNumber());
	return Out;
}
static TArray<float> Floats(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
{
	TArray<float> Out;
	const TArray<TSharedPtr<FJsonValue>>* A;
	if (O.IsValid() && O->TryGetArrayField(K, A)) for (const auto& V : *A) Out.Add((float)V->AsNumber());
	return Out;
}

// ------------------------------------------------------------------ power anims
float FCoHPowerAnim::HitDelay(float DistanceCm) const
{
	float T = FramesBeforeHit / 30.f;
	if (bDelayedHit) T += DistanceCm / FeetToCm / FMath::Max(1.f, ProjectileSpeed > 0.f ? ProjectileSpeed : 60.f);
	return T;
}

static FCoHPowerAnim ReadPowerAnim(const TSharedPtr<FJsonObject>& O)
{
	FCoHPowerAnim A;
	A.FramesBeforeHit = O->HasField(TEXT("FramesBeforeHit")) ? (int32)N(O, TEXT("FramesBeforeHit")) : 15;
	A.AttackFrames = (int32)N(O, TEXT("AttackFrames"));
	A.bDelayedHit = N(O, TEXT("DelayedHit")) > 0;
	// powers_load.c power_FixupForBinFX: a delayed hit with no speed flies at 60 ft/s
	A.ProjectileSpeed = (float)N(O, TEXT("ProjectileSpeed"), A.bDelayedHit ? 60.0 : 0.0);
	for (const auto& KV : O->Values)
		if (FString(KV.Key).EndsWith(TEXT("FX")) && KV.Value->Type == EJson::String) A.FX.Add(FString(KV.Key), KV.Value->AsString().ToLower().Replace(TEXT("\\"), TEXT("/")));
	const TSharedPtr<FJsonObject>* Moves;
	if (O->TryGetObjectField(TEXT("moves"), Moves))
		for (const auto& Body : (*Moves)->Values)
		{
			auto& ByBits = A.Moves.Add(FString(Body.Key));
			const TSharedPtr<FJsonObject> BO = Body.Value->AsObject();
			if (!BO.IsValid()) continue;
			for (const auto& Bits : BO->Values)
			{
				const TSharedPtr<FJsonObject> MO = Bits.Value->AsObject();
				const TArray<TSharedPtr<FJsonValue>>* Segs;
				if (!MO.IsValid() || !MO->TryGetArrayField(TEXT("segments"), Segs)) continue;
				auto& List = ByBits.Add(FString(Bits.Key));
				for (const auto& SV : *Segs)
				{
					const auto& E = SV->AsArray();
					if (E.Num() < 4) continue;
					List.Add(MakeTuple(E[0]->AsString(), E[1]->AsString(), (int32)E[2]->AsNumber(), (int32)E[3]->AsNumber()));
				}
			}
		}
	return A;
}

void UCoHGameRules::LoadPowerAnims(const FString& File, TMap<FName, FCoHPowerAnim>& Into)
{
	TSharedPtr<FJsonValue> Root;
	if (!ReadJson(File, Root) || !Root->AsObject().IsValid()) return;
	for (const auto& KV : Root->AsObject()->Values)
		if (const TSharedPtr<FJsonObject> O = KV.Value->AsObject()) Into.Add(FName(*KV.Key), ReadPowerAnim(O));
}

const FCoHPowerAnim* UCoHGameRules::PowerAnim(FName Power) const { return PowerAnims.Find(Power); }

const FCoHPowerAnim* UCoHGameRules::VillainPowerAnim(const FString& Villain, FName Power) const
{
	if (const FCoHKitVillain* V = Villains.Find(Villain))
		for (const FCoHKitPower& P : V->Powers) if (P.Power == Power) return &P.Anim;
	return nullptr;
}

void UCoHGameRules::IndexClips(const FString& Root) const
{
	if (ClipIndex.Contains(Root)) return;
	TMap<FString, FSoftObjectPath>& Idx = ClipIndex.Add(Root);
	IAssetRegistry& AR = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry").Get();
	TArray<FAssetData> Found;
	AR.GetAssetsByPath(FName(*Root), Found, true);
	for (const FAssetData& D : Found)
	{
		if (!D.IsInstanceOf(UAnimSequenceBase::StaticClass())) continue;
		Idx.Add(D.AssetName.ToString().ToLower(), D.GetSoftObjectPath());
	}
}

UAnimSequenceBase* UCoHGameRules::ClipIn(const FString& Folder, const FString& Name) const
{
	IndexClips(Folder);
	const TMap<FString, FSoftObjectPath>& Idx = ClipIndex[Folder];
	const FString Key = Name.ToLower();
	const FSoftObjectPath* P = Idx.Find(Key);
	if (!P)
	{
		// Interchange may prefix the clip with the file or mesh name
		for (const auto& KV : Idx) if (KV.Key.EndsWith(Key) && (KV.Key.Len() == Key.Len() || KV.Key[KV.Key.Len() - Key.Len() - 1] == TEXT('_'))) { P = &KV.Value; break; }
	}
	return P ? Cast<UAnimSequenceBase>(P->TryLoad()) : nullptr;
}

UAnimSequenceBase* UCoHGameRules::PlayerClip(const FString& Body, const FString& Anim) const
{
	// male/energy_rapid -> male__energy_rapid, in the body's own library
	return ClipIn(PlayerAnimRoot / Body, Anim.Replace(TEXT("/"), TEXT("__")));
}

bool UCoHGameRules::Segments(const FCoHPowerAnim& A, const FString& Body, const FString& Bits, TArray<FCoHAnimSegment>& Out) const
{
	Out.Reset();
	const auto* ByBits = A.Moves.Find(Body);
	if (!ByBits) return false;
	const auto* List = ByBits->Find(Bits);
	if (!List) return false;
	for (const auto& E : *List)
	{
		FCoHAnimSegment Seg;
		Seg.Move = FName(*E.Get<0>());
		Seg.Clip = PlayerClip(Body, E.Get<1>());
		if (!Seg.Clip) { UE_LOG(LogTemp, Warning, TEXT("CoH anim: no clip %s for %s (the pose stays as it is)"), *E.Get<1>(), *Body); continue; }
		// frames at 30 fps; 0 = the end of the track. The game clamps a move
		// that starts past the end, so a start past the end holds the last frame.
		const float Len = Seg.Clip->GetPlayLength();
		Seg.Start = FMath::Clamp((E.Get<2>()) / 30.f, 0.f, FMath::Max(0.f, Len - 1.f / 30.f));
		Seg.End = E.Get<3>() > 0 ? FMath::Min(E.Get<3>() / 30.f, Len) : Len;
		if (Seg.End <= Seg.Start) Seg.End = FMath::Min(Seg.Start + 1.f / 30.f, Len);
		Out.Add(Seg);
	}
	return Out.Num() > 0;
}

bool UCoHGameRules::MoveSegments(const FString& Model, const TArray<FString>& Moves, TArray<FCoHAnimSegment>& Out) const
{
	Out.Reset();
	for (const FString& M : Moves)
	{
		FCoHAnimSegment Seg;
		Seg.Move = FName(*M);
		Seg.Clip = ClipIn(EnemyRoot / Model, M);
		if (!Seg.Clip) continue;
		Seg.Start = 0.f; Seg.End = Seg.Clip->GetPlayLength();
		Out.Add(Seg);
	}
	return Out.Num() > 0;
}

bool UCoHGameRules::VillainSegments(const FCoHKitVillain& V, const FString& Model, const FCoHPowerAnim& A, const FString& Bits, TArray<FCoHAnimSegment>& Out) const
{
	Out.Reset();
	const auto* ByBits = A.Moves.Find(V.SeqType.IsEmpty() ? TEXT("villain") : V.SeqType);
	const auto* List = ByBits ? ByBits->Find(Bits) : nullptr;
	if (!List) return false;
	TArray<FString> Moves;
	for (const auto& E : *List) Moves.Add(E.Get<0>());
	return MoveSegments(Model, Moves, Out);
}

USkeletalMesh* UCoHGameRules::PresetMesh(const FString& Preset, FString& OutBody) const
{
	IAssetRegistry& AR = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry").Get();
	static const TCHAR* Bodies[] = { TEXT("male"), TEXT("fem"), TEXT("huge") };
	for (const TCHAR* Body : Bodies)
	{
		TArray<FAssetData> Found;
		AR.GetAssetsByPath(FName(*(PresetRoot / Body / Preset)), Found, true);
		for (const FAssetData& D : Found)
			if (D.IsInstanceOf(USkeletalMesh::StaticClass()))
			{
				OutBody = Body;
				return Cast<USkeletalMesh>(D.GetAsset());
			}
	}
	return nullptr;
}

// ------------------------------------------------------------------ init
void UCoHGameRules::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	const double T0 = FPlatformTime::Seconds();
	FString Rules;
	GConfig->GetString(TEXT("/Script/COHREBORN.CoHPowerDatabase"), TEXT("RulesDir"), Rules, GGameIni);
	if (Rules.IsEmpty()) Rules = FPaths::ProjectContentDir() / TEXT("CoH/Data/Rules");
	const FString Out = FPaths::GetPath(Rules);         // <out>/rules -> <out>
	if (HeroRulesDir.IsEmpty()) HeroRulesDir = Rules;
	if (PowerAnimsFile.IsEmpty()) PowerAnimsFile = Out / TEXT("powers/power_anims.json");
	if (EnemyDir.IsEmpty()) EnemyDir = Out / TEXT("enemies");
	if (HeroesDir.IsEmpty()) HeroesDir = Out / TEXT("heroes");
	LoadPowerAnims(PowerAnimsFile, PowerAnims);
	LoadHeroRules(HeroRulesDir / TEXT("hero_rules.json"));
	LoadRewards(HeroRulesDir / TEXT("rewards.json"));
	LoadEnemies(EnemyDir);
	UE_LOG(LogTemp, Log, TEXT("CoH game rules: %d power anims, %d archetypes, %d sets, XP table %d, %d reward ranks, %d kit villains, %d encounters (%.1f s)"),
		PowerAnims.Num(), Classes.Num(), Sets.Num(), XPForLevel.Num(), Tables.Num(), Villains.Num(), Encounters.Num(), FPlatformTime::Seconds() - T0);
}

UCoHGameRules* UCoHGameRules::Get(const UObject* WorldContext)
{
	const UWorld* W = WorldContext ? WorldContext->GetWorld() : nullptr;
	return W && W->GetGameInstance() ? W->GetGameInstance()->GetSubsystem<UCoHGameRules>() : nullptr;
}

// ------------------------------------------------------------------ hero build
void UCoHGameRules::LoadHeroRules(const FString& File)
{
	TSharedPtr<FJsonValue> Root;
	if (!ReadJson(File, Root)) return;
	const TSharedPtr<FJsonObject> O = Root->AsObject();
	Origins = L(O, TEXT("origins"));
	PoolSets = L(O, TEXT("pool_sets"));
	EpicSets = L(O, TEXT("epic_sets"));
	XPForLevel = Ints(O, TEXT("xp_for_level"));
	const TSharedPtr<FJsonObject>* Sched;
	if (O->TryGetObjectField(TEXT("schedule"), Sched))
	{
		SchedPicks = Ints(*Sched, TEXT("power_picks"));
		SchedPools = Ints(*Sched, TEXT("new_pool_set"));
		SchedEpics = Ints(*Sched, TEXT("new_epic_set"));
	}
	for (const auto& CV : O->GetArrayField(TEXT("archetypes")))
	{
		const auto C = CV->AsObject();
		FCoHRuleClass RC;
		RC.Class = S(C, TEXT("class")); RC.Side = S(C, TEXT("side")); RC.bEpic = B(C, TEXT("epic"));
		RC.Origins = L(C, TEXT("origins")); RC.Primary = L(C, TEXT("primary")); RC.Secondary = L(C, TEXT("secondary"));
		Classes.Add(MoveTemp(RC));
	}
	const TSharedPtr<FJsonObject>* SetsO;
	if (O->TryGetObjectField(TEXT("sets"), SetsO))
		for (const auto& KV : (*SetsO)->Values)
		{
			const auto SO = KV.Value->AsObject();
			FCoHRuleSet RS;
			RS.Id = KV.Key;
			RS.SetRequires = L(SO, TEXT("set_requires"));
			RS.SpecializeRequires = L(SO, TEXT("specialize_requires"));
			for (const auto& PV : SO->GetArrayField(TEXT("powers")))
			{
				const auto PO = PV->AsObject();
				FCoHRulePower RP;
				RP.Power = FName(*S(PO, TEXT("power")));
				RP.Level = (int32)N(PO, TEXT("level"), 1);
				RP.Requires = L(PO, TEXT("requires"));
				RP.bAuto = B(PO, TEXT("auto")); RP.bFree = B(PO, TEXT("free")); RP.bPromo = B(PO, TEXT("promo"));
				RS.Powers.Add(MoveTemp(RP));
			}
			SetCI.Add(RS.Id.ToLower(), RS.Id);
			Sets.Add(RS.Id, MoveTemp(RS));
		}
	for (const auto& KV : Sets)
		for (const FCoHRulePower& P : KV.Value.Powers)
		{
			PowerCI.Add(P.Power.ToString().ToLower(), P.Power);
			PowerRule.Add(P.Power.ToString().ToLower(), &P);
		}
}

const FCoHRuleSet* UCoHGameRules::Set(const FString& Id) const
{
	if (const FString* Real = SetCI.Find(Id.ToLower())) return Sets.Find(*Real);
	return nullptr;
}

const FCoHRuleClass* UCoHGameRules::RuleClass(const FString& Class) const
{
	for (const FCoHRuleClass& C : Classes)
		if (C.Class.Equals(Class, ESearchCase::IgnoreCase) || C.Class.Equals(TEXT("Class_") + Class, ESearchCase::IgnoreCase)) return &C;
	return nullptr;
}

static FString SetOf(const FString& Power)
{
	int32 Dot;
	return Power.FindLastChar(TEXT('.'), Dot) ? Power.Left(Dot) : Power;
}

int32 UCoHGameRules::PicksAllowed(int32 Level) const { int32 N0 = 0; for (int32 X : SchedPicks) N0 += X <= Level; return N0; }
int32 UCoHGameRules::PickLevel(int32 Index) const { return SchedPicks.IsValidIndex(Index) ? SchedPicks[Index] : 99; }
static int32 CountAtOrBelow(const TArray<int32>& Sched, int32 Level) { int32 N0 = 0; for (int32 X : Sched) N0 += X <= Level; return N0; }

bool UCoHGameRules::Requires(const TArray<FString>& Expr, const FCoHHeroRecord& Hero, const TSet<FString>& Owned) const
{
	// a postfix BuyRequires expression (coh_build.Rules.requires)
	if (Expr.Num() == 0) return true;
	struct FV { bool bStr = false; FString Str; double Num = 0; bool Truth() const { return bStr ? !Str.IsEmpty() : Num != 0; } };
	TArray<FV> St;
	auto Pop = [&]() { return St.Num() ? St.Pop() : FV(); };
	auto PushB = [&](bool b) { FV V; V.Num = b ? 1 : 0; St.Add(V); };
	const int32 Lvl0 = Hero.Level - 1;
	for (const FString& T : Expr)
	{
		const FString Lt = T.ToLower();
		if (Lt == TEXT("&&") || Lt == TEXT("||"))
		{
			const FV Bv = Pop(), Av = Pop();
			PushB(Lt == TEXT("&&") ? Av.Truth() && Bv.Truth() : Av.Truth() || Bv.Truth());
		}
		else if (Lt == TEXT("!")) PushB(!Pop().Truth());
		else if (Lt == TEXT("==") || Lt == TEXT(">") || Lt == TEXT(">=") || Lt == TEXT("<") || Lt == TEXT("<=") || Lt == TEXT("!="))
		{
			const FV Bv = Pop(), Av = Pop();
			int32 Cmp;
			if (Av.bStr || Bv.bStr)
			{
				const FString As = Av.bStr ? Av.Str.ToLower() : FString::SanitizeFloat(Av.Num);
				const FString Bs = Bv.bStr ? Bv.Str.ToLower() : FString::SanitizeFloat(Bv.Num);
				Cmp = As.Compare(Bs);
			}
			else Cmp = Av.Num < Bv.Num ? -1 : (Av.Num > Bv.Num ? 1 : 0);
			bool R = false;
			if (Lt == TEXT("==")) R = Cmp == 0; else if (Lt == TEXT("!=")) R = Cmp != 0;
			else if (Lt == TEXT(">")) R = Cmp > 0; else if (Lt == TEXT(">=")) R = Cmp >= 0;
			else if (Lt == TEXT("<")) R = Cmp < 0; else R = Cmp <= 0;
			PushB(R);
		}
		else if (Lt == TEXT("$archetype")) { FV V; V.bStr = true; V.Str = Hero.Class; St.Add(V); }
		else if (Lt.StartsWith(TEXT("@"))) { FV V; V.bStr = true; V.Str = T.Mid(1); St.Add(V); }
		else if (Lt == TEXT("char>"))
		{
			const FV A = Pop();
			FV V; V.Num = (A.bStr ? A.Str : FString()).Equals(TEXT("level"), ESearchCase::IgnoreCase) ? Lvl0 : 0; St.Add(V);
		}
		else if (Lt == TEXT("auth>") || Lt == TEXT("productowned?") || Lt == TEXT("tokenowned?") || Lt == TEXT("owned?"))
		{
			Pop(); PushB(false);     // store / promotion / veteran tokens: not part of the levelled game
		}
		else if (Lt == TEXT("isvip?") || Lt == TEXT("isaccountinventoryloaded?")) PushB(true);
		else if (Lt.EndsWith(TEXT("?"))) PushB(false);
		else if (T.Contains(TEXT(".")) && !T.IsNumeric()) PushB(Owned.Contains(Lt));
		else if (T.IsNumeric()) { FV V; V.Num = FCString::Atod(*T); St.Add(V); }
		else { FV V; V.bStr = true; V.Str = T; St.Add(V); }
	}
	return St.Num() ? St.Last().Truth() : true;
}

TArray<FString> UCoHGameRules::HeroSets(const FCoHHeroRecord& Hero) const
{
	TArray<FString> Out = { Hero.Primary, Hero.Secondary };
	for (const FCoHHeroPick& P : Hero.Picks) Out.AddUnique(SetOf(P.Power.ToString()));
	return Out;
}

TArray<FName> UCoHGameRules::AutoPowers(const FCoHHeroRecord& Hero) const
{
	TSet<FString> Picked;
	for (const FCoHHeroPick& P : Hero.Picks) Picked.Add(P.Power.ToString().ToLower());
	TArray<FString> SetIds = { TEXT("Inherent.Inherent"), TEXT("Inherent.Fitness") };
	SetIds.Append(HeroSets(Hero));
	TArray<FName> Out;
	for (const FString& Id : SetIds)
	{
		const FCoHRuleSet* RS = Set(Id);
		if (!RS) continue;
		const bool bInherent = Id.StartsWith(TEXT("Inherent."), ESearchCase::IgnoreCase);
		for (const FCoHRulePower& P : RS->Powers)
		{
			if (P.bPromo || P.Level > Hero.Level) continue;
			if (!(bInherent || P.bAuto)) continue;
			if (Requires(P.Requires, Hero, Picked)) Out.AddUnique(P.Power);
		}
	}
	return Out;
}

TSet<FString> UCoHGameRules::Owned(const FCoHHeroRecord& Hero) const
{
	TSet<FString> O;
	for (const FCoHHeroPick& P : Hero.Picks) O.Add(P.Power.ToString().ToLower());
	for (const FName& P : AutoPowers(Hero)) O.Add(P.ToString().ToLower());
	return O;
}

FString UCoHGameRules::Kind(const FCoHHeroRecord& Hero, const FString& SetId) const
{
	if (SetId.Equals(Hero.Primary, ESearchCase::IgnoreCase)) return TEXT("primary");
	if (SetId.Equals(Hero.Secondary, ESearchCase::IgnoreCase)) return TEXT("secondary");
	for (const FString& P : PoolSets) if (P.Equals(SetId, ESearchCase::IgnoreCase)) return TEXT("pool");
	for (const FString& E : EpicSets) if (E.Equals(SetId, ESearchCase::IgnoreCase)) return TEXT("epic");
	return FString();
}

FString UCoHGameRules::CanPick(const FCoHHeroRecord& Hero, FName PowerIn, int32 AtLevel, int32 NumPrior) const
{
	const FName* Real = PowerCI.Find(PowerIn.ToString().ToLower());
	if (!Real) return TEXT("unknown power");
	const FString Power = Real->ToString();
	const FString SetId = SetOf(Power);
	const FCoHRuleSet* RS = Set(SetId);
	if (!RS) return TEXT("unknown set");
	const FCoHRulePower* Rule = PowerRule.FindRef(Power.ToLower());
	if (Rule && Rule->bPromo) return TEXT("promotional power");
	FCoHHeroRecord H = Hero;
	H.Level = AtLevel;
	H.Picks.SetNum(FMath::Min(NumPrior, Hero.Picks.Num()));
	const FString K = Kind(H, RS->Id);
	if (K.IsEmpty()) return FString::Printf(TEXT("%s is not a %s set"), *RS->Id, *Hero.Class);
	if (!Rule || Rule->Level > AtLevel) return FString::Printf(TEXT("available at level %d"), Rule ? Rule->Level : 1);
	const TSet<FString> Own = Owned(H);
	if (Own.Contains(Power.ToLower())) return TEXT("already owned");
	if (AtLevel == 1)
	{
		// creation: one level 1 primary power and the level 1 secondary power
		if (K != TEXT("primary") && K != TEXT("secondary")) return TEXT("level 1 takes one primary and one secondary power");
		for (const FCoHHeroPick& P : H.Picks) if (Kind(H, SetOf(P.Power.ToString())) == K) return TEXT("level 1 takes one primary and one secondary power");
	}
	const TArray<FString> HS = HeroSets(H);
	const bool bNewSet = !HS.ContainsByPredicate([&](const FString& X) { return X.Equals(RS->Id, ESearchCase::IgnoreCase); });
	if (K == TEXT("pool") && bNewSet)
	{
		int32 Have = 0; for (const FString& X : HS) Have += Kind(H, X) == TEXT("pool");
		if (Have >= CountAtOrBelow(SchedPools, AtLevel))
			return Have >= SchedPools.Num() ? FString::Printf(TEXT("already has the most pool sets (%d)"), Have)
				: FString::Printf(TEXT("no new pool set until level %d"), SchedPools[Have]);
	}
	if (K == TEXT("epic") && bNewSet)
	{
		int32 Have = 0; for (const FString& X : HS) Have += Kind(H, X) == TEXT("epic");
		if (Have >= CountAtOrBelow(SchedEpics, AtLevel)) return FString::Printf(TEXT("epic sets open at level %d"), SchedEpics.Num() ? SchedEpics[0] : 35);
	}
	if (RS->SetRequires.Num() && !Requires(RS->SetRequires, H, Own)) return RS->Id + TEXT(" SetBuyRequires not met");
	if (RS->SpecializeRequires.Num() && !Requires(RS->SpecializeRequires, H, Own)) return RS->Id + TEXT(" SpecializeRequires not met");
	if (!Requires(Rule->Requires, H, Own)) return TEXT("requirements not met (") + FString::Join(Rule->Requires, TEXT(" ")) + TEXT(")");
	return FString();
}

TArray<FName> UCoHGameRules::Options(const FCoHHeroRecord& Hero) const
{
	TArray<FName> Out;
	const int32 N0 = Hero.Picks.Num();
	if (N0 >= PicksAllowed(Hero.Level)) return Out;
	const int32 At = FMath::Max(PickLevel(N0), 1);
	TArray<FString> Cands = { Hero.Primary, Hero.Secondary };
	Cands.Append(PoolSets); Cands.Append(EpicSets);
	for (const FString& Id : Cands)
		if (const FCoHRuleSet* RS = Set(Id))
			for (const FCoHRulePower& P : RS->Powers)
				if (CanPick(Hero, P.Power, At, N0).IsEmpty()) Out.AddUnique(P.Power);
	return Out;
}

FCoHHeroRecord UCoHGameRules::NewHero(const FString& ClassIn, const FString& Primary, const FString& Secondary, const FString& First, const FString& Name, const FString& Preset) const
{
	FCoHHeroRecord H;
	const FCoHRuleClass* C = RuleClass(ClassIn);
	if (!C) return H;
	H.Class = C->Class; H.Name = Name.IsEmpty() ? TEXT("New Hero") : Name;
	H.Origin = C->Origins.Num() ? C->Origins[0] : FString();
	H.Preset = Preset;
	auto Resolve = [](const TArray<FString>& Names, const FString& Want)
	{
		for (const FString& S0 : Names) if (S0.Equals(Want, ESearchCase::IgnoreCase) || S0.EndsWith(TEXT(".") + Want, ESearchCase::IgnoreCase)) return S0;
		return Names.Num() ? Names[0] : FString();
	};
	H.Primary = Resolve(C->Primary, Primary);
	H.Secondary = Resolve(C->Secondary, Secondary);
	auto FirstOf = [&](const FString& Id, const FString& Want) -> FName
	{
		const FCoHRuleSet* RS = Set(Id);
		if (!RS) return NAME_None;
		FName Any;
		for (const FCoHRulePower& P : RS->Powers)
			if (P.Level == 1)
			{
				if (Any.IsNone()) Any = P.Power;
				if (!Want.IsEmpty() && P.Power.ToString().EndsWith(TEXT(".") + Want, ESearchCase::IgnoreCase)) return P.Power;
			}
		return Any;
	};
	H.Picks.Add({ 1, FirstOf(H.Primary, First) });
	H.Picks.Add({ 1, FirstOf(H.Secondary, FString()) });
	return H;
}

bool UCoHGameRules::LoadHero(const FString& File, FCoHHeroRecord& H) const
{
	TSharedPtr<FJsonValue> Root;
	const FString Path = FPaths::IsRelative(File) ? HeroesDir / File : File;
	if (!ReadJson(Path, Root) || !Root->AsObject().IsValid()) return false;
	const auto O = Root->AsObject();
	H = FCoHHeroRecord();
	H.Name = S(O, TEXT("name")); H.Class = S(O, TEXT("class")); H.Origin = S(O, TEXT("origin"));
	H.Level = FMath::Clamp((int32)N(O, TEXT("level"), 1), 1, MaxLevel);
	H.XP = (int32)N(O, TEXT("xp")); H.Debt = (int32)N(O, TEXT("debt")); H.Influence = (int32)N(O, TEXT("influence"));
	H.Primary = S(O, TEXT("primary")); H.Secondary = S(O, TEXT("secondary"));
	const TSharedPtr<FJsonObject>* Model;
	if (O->TryGetObjectField(TEXT("model"), Model)) H.Preset = S(*Model, TEXT("preset"));
	const TArray<TSharedPtr<FJsonValue>>* Picks;
	if (O->TryGetArrayField(TEXT("picks"), Picks))
		for (const auto& PV : *Picks) { const auto PO = PV->AsObject(); H.Picks.Add({ (int32)N(PO, TEXT("level"), 1), FName(*S(PO, TEXT("power"))) }); }
	for (const FString& I : L(O, TEXT("inspirations"))) H.Inspirations.Add(FName(*I));
	return true;
}

bool UCoHGameRules::SaveHero(const FString& File, const FCoHHeroRecord& H) const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	O->SetNumberField(TEXT("format"), 2);
	O->SetStringField(TEXT("name"), H.Name); O->SetStringField(TEXT("class"), H.Class); O->SetStringField(TEXT("origin"), H.Origin);
	O->SetNumberField(TEXT("level"), H.Level); O->SetNumberField(TEXT("xp"), H.XP);
	O->SetNumberField(TEXT("debt"), H.Debt); O->SetNumberField(TEXT("influence"), H.Influence);
	TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
	if (!H.Preset.IsEmpty()) M->SetStringField(TEXT("preset"), H.Preset);
	O->SetObjectField(TEXT("model"), M);
	O->SetStringField(TEXT("primary"), H.Primary); O->SetStringField(TEXT("secondary"), H.Secondary);
	TArray<TSharedPtr<FJsonValue>> Picks, Auto, Insp, SetsArr;
	TMap<FString, TArray<TSharedPtr<FJsonValue>>> BySet;
	TArray<FString> Order;
	for (const FCoHHeroPick& P : H.Picks)
	{
		TSharedRef<FJsonObject> PO = MakeShared<FJsonObject>();
		PO->SetNumberField(TEXT("level"), P.Level); PO->SetStringField(TEXT("power"), P.Power.ToString());
		Picks.Add(MakeShared<FJsonValueObject>(PO));
	}
	const TArray<FName> AutoP = AutoPowers(H);
	auto AddBySet = [&](const FName& P) { const FString Sid = SetOf(P.ToString()); if (!BySet.Contains(Sid)) Order.Add(Sid); BySet.FindOrAdd(Sid).Add(MakeShared<FJsonValueString>(P.ToString())); };
	for (const FName& P : AutoP) { Auto.Add(MakeShared<FJsonValueString>(P.ToString())); AddBySet(P); }
	for (const FCoHHeroPick& P : H.Picks) AddBySet(P.Power);
	for (const FString& Sid : Order)
	{
		TSharedRef<FJsonObject> SO = MakeShared<FJsonObject>();
		SO->SetStringField(TEXT("set"), Sid); SO->SetArrayField(TEXT("powers"), BySet[Sid]);
		SetsArr.Add(MakeShared<FJsonValueObject>(SO));
	}
	for (const FName& I : H.Inspirations) Insp.Add(MakeShared<FJsonValueString>(I.ToString()));
	O->SetArrayField(TEXT("picks"), Picks);
	O->SetArrayField(TEXT("auto_powers"), Auto);
	O->SetArrayField(TEXT("sets"), SetsArr);
	O->SetArrayField(TEXT("inspirations"), Insp);
	if (H.Picks.Num() < SchedPicks.Num()) O->SetNumberField(TEXT("next_pick_level"), PickLevel(H.Picks.Num()));
	FString Text;
	const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Text);
	FJsonSerializer::Serialize(O, W);
	const FString Path = FPaths::IsRelative(File) ? HeroesDir / File : File;
	return FFileHelper::SaveStringToFile(Text, *Path);
}

// ------------------------------------------------------------------ rewards
void UCoHGameRules::LoadRewards(const FString& File)
{
	TSharedPtr<FJsonValue> Root;
	if (!ReadJson(File, Root)) return;
	const auto O = Root->AsObject();
	XPForLevel = Ints(O, TEXT("xp_for_level"));
	DefeatPenalty = Ints(O, TEXT("defeat_penalty"));
	BonusAbove = Floats(O, TEXT("level_bonus_above"));
	BonusBelow = Floats(O, TEXT("level_bonus_below"));
	const TSharedPtr<FJsonObject>* Sub;
	if (O->TryGetObjectField(TEXT("team_bonus"), Sub)) for (const auto& KV : (*Sub)->Values) TeamBonus.Add(FCString::Atoi(*KV.Key), KV.Value->AsNumber());
	if (O->TryGetObjectField(TEXT("con_adjust"), Sub)) for (const auto& KV : (*Sub)->Values) ConAdjust.Add(FString(KV.Key), (int32)KV.Value->AsNumber());
	if (O->TryGetObjectField(TEXT("constants"), Sub))
	{
		XPCapLevels = (int32)N(*Sub, TEXT("xp_cap_levels"), 4); NoItemsAbove = (int32)N(*Sub, TEXT("no_items_levels_above"), 3);
		KillCreditFeet = N(*Sub, TEXT("kill_credit_ft"), 200); NoDamageRewardFeet = N(*Sub, TEXT("no_damage_reward_ft"), 300);
		DebtCapPenalties = (int32)N(*Sub, TEXT("debt_cap_penalties"), 5);
	}
	for (const auto& TV : O->GetArrayField(TEXT("inspiration_tray")))
	{
		const auto T = TV->AsObject();
		const int32 Lv = (int32)N(T, TEXT("level"));
		InspCols.SetNum(FMath::Max(InspCols.Num(), Lv)); InspRows.SetNum(FMath::Max(InspRows.Num(), Lv));
		InspCols[Lv - 1] = (int32)N(T, TEXT("columns")); InspRows[Lv - 1] = (int32)N(T, TEXT("rows"));
	}
	if (O->TryGetObjectField(TEXT("tables"), Sub))
		for (const auto& Rank : (*Sub)->Values)
		{
			auto& Rows = Tables.Add(FString(Rank.Key));
			for (const auto& Row : Rank.Value->AsObject()->Values)
			{
				auto& List = Rows.Add(FCString::Atoi(*Row.Key));
				for (const auto& SV : Row.Value->AsArray())
				{
					const auto SO = SV->AsObject();
					FCoHRewardSet RS;
					RS.Chance = N(SO, TEXT("chance")); RS.bAlways = B(SO, TEXT("always"));
					RS.XP = (int32)N(SO, TEXT("experience")); RS.Influence = (int32)N(SO, TEXT("influence"));
					RS.Groups = L(SO, TEXT("villain_groups")); RS.bDefaultGroup = B(SO, TEXT("default_group"));
					const TArray<TSharedPtr<FJsonValue>>* Drops;
					if (SO->TryGetArrayField(TEXT("drops"), Drops))
						for (const auto& DV : *Drops) { const auto DO = DV->AsObject(); RS.Drops.Add({ (int32)N(DO, TEXT("weight"), 100), L(DO, TEXT("itemsets")) }); }
					List.Add(MoveTemp(RS));
				}
			}
		}
	if (O->TryGetObjectField(TEXT("itemsets"), Sub))
		for (const auto& KV : (*Sub)->Values)
		{
			auto& Items = ItemSets.Add(FString(KV.Key));
			for (const auto& IV : KV.Value->AsArray())
			{
				const auto IO = IV->AsObject();
				Items.Add({ (int32)N(IO, TEXT("weight"), 1), S(IO, TEXT("kind")) + TEXT(":") + S(IO, TEXT("item")) });
			}
		}
}

TArray<FCoHRewardSet> UCoHGameRules::SetsFor(const FString& Rank, int32 Level0, const FString& Group) const
{
	TArray<FCoHRewardSet> Out;
	const auto* Rows = Tables.Find(Rank);
	if (!Rows || Rows->Num() == 0) return Out;
	int32 MaxRow = 1; for (const auto& KV : *Rows) MaxRow = FMath::Max(MaxRow, KV.Key);
	const TArray<FCoHRewardSet>* Row = Rows->Find(FMath::Clamp(Level0 + 1, 1, MaxRow));
	if (!Row) return Out;
	TSet<FString> Listed;
	for (const FCoHRewardSet& R : *Row) for (const FString& G : R.Groups) Listed.Add(G);
	for (const FCoHRewardSet& R : *Row)
	{
		if (R.Groups.Num()) { if (!R.Groups.Contains(Group)) continue; }
		else if (R.bDefaultGroup && Listed.Contains(Group)) continue;
		Out.Add(R);
	}
	return Out;
}

TPair<int32, int32> UCoHGameRules::TableXP(const FString& Rank, int32 Level0, const FString& Group) const
{
	int32 XP = 0, Inf = 0;
	for (const FCoHRewardSet& R : SetsFor(Rank, Level0, Group)) if (R.bAlways) { XP += R.XP; Inf += R.Influence; }
	return { XP, Inf };
}

float UCoHGameRules::LevelBonus(int32 Hero0, int32 Villain0) const
{
	const int32 D = Hero0 - Villain0;
	const TArray<float>& T = D >= 0 ? BonusAbove : BonusBelow;
	return T.Num() ? T[FMath::Min(FMath::Abs(D), T.Num() - 1)] : 1.f;
}

int32 UCoHGameRules::XPLevel(int32 XP) const
{
	int32 Lvl = 1;
	while (Lvl < MaxLevel && XPForLevel.IsValidIndex(Lvl) && XP >= XPForLevel[Lvl]) ++Lvl;
	return Lvl;
}

TPair<float, float> UCoHGameRules::Cap(const FString& Rank, int32 Exp0, const FString& Group) const
{
	const int32 E = FMath::Min(Exp0 + 1, MaxLevel - 1);
	const float AvgMax = (XPForLevel.IsValidIndex(E) ? (XPForLevel[E] - XPForLevel[E - 1]) / 2 : 1e9);
	const TPair<int32, int32> T = TableXP(Rank, E + XPCapLevels, Group);
	const float Mb = LevelBonus(0, XPCapLevels);
	float CXP = T.Key * Mb, CInf = T.Value * Mb;
	if (CXP > AvgMax) { CInf *= AvgMax / CXP; CXP = AvgMax; }
	return { CXP, CInf };
}

TArray<FCoHAward> UCoHGameRules::Defeat(const FString& Rank, int32 Villain0, const TArray<int32>& Members, float TeamShare, const FString& Group) const
{
	TArray<FCoHAward> Out;
	const int32 Num = Members.Num();
	if (Num == 0) return Out;
	const TPair<int32, int32> Base = TableXP(Rank, Villain0, Group);
	const float* TB = TeamBonus.Find(Num);
	for (const int32 Lvl0 : Members)
	{
		const float K = TeamShare * (TB ? *TB : 1.f) * (1.f / Num) * LevelBonus(Lvl0, Villain0);
		const int32 XP = FMath::CeilToInt(Base.Key * K), Inf = FMath::CeilToInt(Base.Value * K);
		const TPair<float, float> C = Cap(Rank, Lvl0, Group);
		const int32* Con = ConAdjust.Find(Rank);
		FCoHAward A;
		A.XP = (int32)FMath::Min((float)XP, C.Key);
		A.Influence = (int32)FMath::Min((float)Inf, C.Value);
		A.bItems = Lvl0 < Villain0 + (Con ? *Con : 0) + NoItemsAbove;
		Out.Add(A);
	}
	return Out;
}

void UCoHGameRules::GiveXP(FCoHHeroRecord& H, int32 Amount) const
{
	if (H.Level >= MaxLevel)
	{
		const int32 Paid = FMath::Min(H.Debt, Amount);
		H.Debt -= Paid;
		H.Influence += Amount - Paid;
		return;
	}
	if (H.Debt > 0)
	{
		int32 Worked = Amount - Amount / 2;
		int32 Got = Amount / 2;
		if (Worked > H.Debt) { Got += Worked - H.Debt; Worked = H.Debt; }
		H.Debt -= Worked;
		Amount = Got;
	}
	H.XP = FMath::Min(H.XP + Amount, XPForLevel.IsValidIndex(MaxLevel - 1) ? XPForLevel[MaxLevel - 1] : MAX_int32);
}

int32 UCoHGameRules::Defeated(FCoHHeroRecord& H, bool bInMission) const
{
	if (DefeatPenalty.Num() == 0) return 0;
	const int32 E0 = XPLevel(H.XP) - 1;
	const int32 Pen = DefeatPenalty[FMath::Min(E0, DefeatPenalty.Num() - 1)];
	const int32 Add = (int32)(Pen * (bInMission ? 0.5f : 1.f));
	const int32 Before = H.Debt;
	H.Debt = FMath::Min(H.Debt + Add, Pen * DebtCapPenalties);
	return H.Debt - Before;
}

FIntPoint UCoHGameRules::InspirationTray(int32 Level) const
{
	const int32 I = FMath::Clamp(Level, 1, InspCols.Num()) - 1;
	return InspCols.IsValidIndex(I) ? FIntPoint(InspCols[I], InspRows[I]) : FIntPoint(3, 1);
}

FName UCoHGameRules::RollDrop(const FString& Rank, int32 Villain0, const FString& Group) const
{
	// the chance sets of the row; the first inspiration item set that rolls wins
	for (const FCoHRewardSet& R : SetsFor(Rank, Villain0, Group))
	{
		if (R.bAlways || R.Drops.Num() == 0) continue;
		if (FMath::FRand() * 100.f >= R.Chance) continue;
		for (const auto& D : R.Drops)
			for (FString Name : D.Value)
			{
				const auto* Items = ItemSets.Find(Name);
				int32 Dot;
				if (!Items && Name.FindChar(TEXT('.'), Dot)) Items = ItemSets.Find(Name.Mid(Dot + 1));   // PL.InspirationsSmall
				if (!Items || Items->Num() == 0) continue;
				int32 Total = 0; for (const auto& I : *Items) Total += I.Key;
				int32 Roll = FMath::RandRange(0, FMath::Max(0, Total - 1));
				for (const auto& I : *Items)
				{
					if ((Roll -= I.Key) >= 0) continue;
					// only inspirations for now: salvage and enhancements come later
					if (I.Value.StartsWith(TEXT("Power:Inspirations."))) return FName(*I.Value.Mid(6));
					break;
				}
			}
	}
	return NAME_None;
}

// ------------------------------------------------------------------ enemies
TArray<FString> FCoHEncounter::Groups() const
{
	TArray<FString> G;
	for (const FCoHEncounterActor& A : Actors) if (!A.Group.IsEmpty()) G.AddUnique(A.Group);
	return G;
}

const TArray<FString>* FCoHKitVillain::IdleMoves(const FString& Behavior) const
{
	const TArray<FString>* Lists = BehaviorLists.Find(Behavior);
	if (!Lists) Lists = BehaviorLists.Find(TEXT("<<") + Behavior + TEXT(">>"));
	if (!Lists || Lists->Num() == 0) return nullptr;
	const TArray<FString>* M = AnimLists.Find((*Lists)[0]);
	return M && M->Num() ? M : nullptr;
}

void UCoHGameRules::LoadEnemies(const FString& Dir)
{
	TSharedPtr<FJsonValue> Root;
	if (ReadJson(Dir / TEXT("kit.json"), Root) && Root->AsObject().IsValid())
		for (const auto& KV : Root->AsObject()->Values)
		{
			const auto O = KV.Value->AsObject();
			if (!O.IsValid()) continue;
			FCoHKitVillain V;
			V.Name = KV.Key;
			V.Group = S(O, TEXT("group")); V.Rank = S(O, TEXT("rank")); V.Class = S(O, TEXT("class"));
			V.AIConfig = S(O, TEXT("ai_config")); V.SeqType = S(O, TEXT("sequencer_type"));
			if (!S(O, TEXT("ally")).IsEmpty()) V.Ally = S(O, TEXT("ally"));
			V.Costumes = L(O, TEXT("costumes"));
			for (const FString& M : L(O, TEXT("models"))) V.Models.Add(FPaths::GetBaseFilename(M));
			const TSharedPtr<FJsonObject>* Pw;
			if (O->TryGetObjectField(TEXT("powers"), Pw))
				for (const auto& P : (*Pw)->Values)
				{
					const TSharedPtr<FJsonObject> PO = P.Value->AsObject();
					if (!PO.IsValid()) continue;
					// a villain's moves are on its own sequencer type: moves.<bits>.segments
					const TSharedPtr<FJsonObject> Copy = MakeShared<FJsonObject>(*PO);
					const TSharedPtr<FJsonObject>* Moves;
					if (PO->TryGetObjectField(TEXT("moves"), Moves))
					{
						TSharedPtr<FJsonObject> Wrapped = MakeShared<FJsonObject>();
						Wrapped->SetObjectField(V.SeqType.IsEmpty() ? TEXT("villain") : V.SeqType, *Moves);
						Copy->SetObjectField(TEXT("moves"), Wrapped);
					}
					V.Powers.Add({ FName(*P.Key), ReadPowerAnim(Copy) });
				}
			const TSharedPtr<FJsonObject>* Lists;
			if (O->TryGetObjectField(TEXT("anim_lists"), Lists))
				for (const auto& AL : (*Lists)->Values)
				{
					TArray<FString> Moves;
					const TArray<TSharedPtr<FJsonValue>>* Segs;
					if (const auto ALO = AL.Value->AsObject())
						if (ALO->TryGetArrayField(TEXT("segments"), Segs))
							for (const auto& SV : *Segs) if (SV->AsArray().Num()) Moves.Add(SV->AsArray()[0]->AsString());
					V.AnimLists.Add(FString(AL.Key), Moves);
				}
			if (O->TryGetObjectField(TEXT("behavior_lists"), Lists))
				for (const auto& BL : (*Lists)->Values) V.BehaviorLists.Add(FString(BL.Key), Tokens(BL.Value));
			Villains.Add(V.Name, MoveTemp(V));
		}
	if (ReadJson(Dir / TEXT("encounters.json"), Root) && Root->AsObject().IsValid())
	{
		const TSharedPtr<FJsonObject>* EncO;
		if (Root->AsObject()->TryGetObjectField(TEXT("encounters"), EncO))
			for (const auto& KV : (*EncO)->Values)
			{
				const auto E = KV.Value->AsObject();
				if (!E.IsValid()) continue;
				FCoHEncounter Enc;
				Enc.Name = KV.Key; Enc.Kind = S(E, TEXT("kind"));
				Enc.MinLevel = (int32)N(E, TEXT("min_level"), 1); Enc.MaxLevel = (int32)N(E, TEXT("max_level"), Enc.MinLevel);
				Enc.MinTeam = (int32)N(E, TEXT("min_team"), 1); Enc.MaxTeam = (int32)N(E, TEXT("max_team"), 8);
				Enc.Respawn = N(E, TEXT("respawn"), 300);
				int32 Spots = 0;
				const TSharedPtr<FJsonObject>* SpotsO;
				if (E->TryGetObjectField(TEXT("spots"), SpotsO)) for (const auto& Sp : (*SpotsO)->Values) Spots += (int32)Sp.Value->AsNumber();
				Enc.Spots = FMath::Max(1, Spots);
				const TArray<TSharedPtr<FJsonValue>>* Actors;
				if (E->TryGetArrayField(TEXT("actors"), Actors))
					for (const auto& AV : *Actors)
					{
						const auto A = AV->AsObject();
						if (!A.IsValid() || S(A, TEXT("type")) != TEXT("villain")) continue;     // npcs (citizens) come later
						FCoHEncounterActor Act;
						Act.Group = S(A, TEXT("group")); Act.Rank = S(A, TEXT("rank")); Act.Villain = S(A, TEXT("villain"));
						Act.Count = FMath::Max(1, (int32)N(A, TEXT("number"), 1));
						if (A->HasField(TEXT("exact_heroes"))) Act.MinHeroes = Act.MaxHeroes = (int32)N(A, TEXT("exact_heroes"), 1);
						else { Act.MinHeroes = (int32)N(A, TEXT("min_heroes"), 1); Act.MaxHeroes = (int32)N(A, TEXT("max_heroes"), 8); }
						Act.AIInactive = S(A, TEXT("ai_inactive")); Act.AIActive = S(A, TEXT("ai_alerted"));
						const TSharedPtr<FJsonObject>* Rolls;
						if (A->TryGetObjectField(TEXT("rolls"), Rolls))
							for (const auto& R : (*Rolls)->Values) Act.Rolls.Add(FCString::Atoi(*R.Key), Tokens(R.Value));
						Enc.Actors.Add(MoveTemp(Act));
					}
				if (Enc.Actors.Num()) Encounters.Add(MoveTemp(Enc));
			}
	}
}

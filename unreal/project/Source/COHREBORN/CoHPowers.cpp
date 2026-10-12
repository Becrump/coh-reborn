#include "CoHPowers.h"
#include "CoHCombat.h"
#include "CoHHeroCharacter.h"
#include "CoHLifeManager.h"
#include "CoHPowerFX.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/GameInstance.h"
#include "Engine/Texture2D.h"
#include "ImageUtils.h"
#include "Animation/AnimSequence.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Volume.h"
#include "GameFramework/Character.h"
#include "GameFramework/Controller.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Net/UnrealNetwork.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "TimerManager.h"

static constexpr float FeetToCm = 30.48f;
FCoHCombatText UCoHPowerComponent::OnCombatText;

// ------------------------------------------------------------------ data
static FString JStr(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
{
	const TSharedPtr<FJsonValue> V = O->TryGetField(K);
	if (!V.IsValid()) return FString();
	if (V->Type == EJson::Array) { const auto& A = V->AsArray(); return A.Num() ? A[0]->AsString() : FString(); }
	if (V->Type == EJson::Number) return FString::SanitizeFloat(V->AsNumber());
	return V->Type == EJson::String ? V->AsString() : FString();
}
static float JNum(const TSharedPtr<FJsonObject>& O, const TCHAR* K, float Default = 0.f)
{
	const TSharedPtr<FJsonValue> V = O->TryGetField(K);
	if (!V.IsValid()) return Default;
	if (V->Type == EJson::Number) return V->AsNumber();
	if (V->Type == EJson::String) return FCString::Atof(*V->AsString());
	if (V->Type == EJson::Array && V->AsArray().Num()) return V->AsArray()[0]->AsNumber();
	return Default;
}
static TArray<FString> JList(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
{
	TArray<FString> Out;
	const TSharedPtr<FJsonValue> V = O->TryGetField(K);
	if (!V.IsValid()) return Out;
	if (V->Type == EJson::Array) for (const auto& E : V->AsArray()) Out.Add(E->AsString());
	else if (V->Type == EJson::String) Out.Add(V->AsString());
	return Out;
}
static bool LoadJson(const FString& Dir, const FString& File, TSharedPtr<FJsonValue>& Out)
{
	FString Text;
	const FString Path = Dir / File;
	if (!FFileHelper::LoadFileToString(Text, *Path))
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH rules: missing %s"), *Path);
		return false;
	}
	return FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Out) && Out.IsValid();
}

static FString Pretty(const FString& Internal)
{
	FString S = Internal.Replace(TEXT("_"), TEXT(" "));
	S.TrimStartAndEndInline();
	return S;
}

static FCoHClassDef ReadClass(const FString& Name, const TSharedPtr<FJsonObject>& O)
{
	FCoHClassDef C;
	C.Name = Name;
	C.Display = Pretty(Name.StartsWith(TEXT("Class_")) ? Name.Mid(6) : Name);
	const TSharedPtr<FJsonObject>* Sub;
	if (O->TryGetObjectField(TEXT("fields"), Sub))
	{
		C.Primary = JStr(*Sub, TEXT("PrimaryCategory"));
		C.Secondary = JStr(*Sub, TEXT("SecondaryCategory"));
	}
	if (O->TryGetObjectField(TEXT("base"), Sub))
		for (const auto& KV : (*Sub)->Values) if (KV.Value->Type == EJson::Number) C.Base.Add(FString(KV.Key).ToLower(), KV.Value->AsNumber());
	if (O->TryGetObjectField(TEXT("max"), Sub))
	{
		const TArray<TSharedPtr<FJsonValue>>* A;
		if ((*Sub)->TryGetArrayField(TEXT("HitPoints"), A)) for (const auto& V : *A) C.HitPoints.Add(V->AsNumber());
		if ((*Sub)->TryGetArrayField(TEXT("Endurance"), A)) for (const auto& V : *A) C.Endurance.Add(V->AsNumber());
	}
	if (O->TryGetObjectField(TEXT("tables"), Sub))
		for (const auto& KV : (*Sub)->Values)
		{
			TArray<float>& T = C.Tables.Add(FString(KV.Key).ToLower());
			for (const auto& V : KV.Value->AsArray()) T.Add(V->AsNumber());
		}
	return C;
}

float FCoHClassDef::TableValue(const FString& Table, int32 Level) const
{
	const TArray<float>* T = Tables.Find(Table.ToLower());
	if (!T || T->Num() == 0) return 0.f;
	return (*T)[FMath::Clamp(Level - 1, 0, T->Num() - 1)];
}

bool FCoHPowerDef::IsMelee() const
{
	for (const FString& A : AttackTypes) if (A.Contains(TEXT("Melee"))) return true;
	return Range > 0.f && Range <= 10.f;
}

static FCoHPowerDef ReadPower(const FString& Id, const TSharedPtr<FJsonObject>& O)
{
	FCoHPowerDef P;
	P.Id = FName(*Id);
	TArray<FString> Parts;
	Id.ParseIntoArray(Parts, TEXT("."));
	P.Category = Parts.Num() > 0 ? Parts[0] : FString();
	P.SetId = Parts.Num() > 1 ? Parts[0] + TEXT(".") + Parts[1] : FString();
	P.Display = Pretty(JStr(O, TEXT("Name")));
	P.Icon = JStr(O, TEXT("IconName")); P.Type = JStr(O, TEXT("Type")); P.Area = JStr(O, TEXT("EffectArea"));
	P.Target = JStr(O, TEXT("Target")); P.Affects = FString::Join(JList(O, TEXT("EntsAffected")), TEXT(" "));
	P.AttackTypes = JList(O, TEXT("AttackTypes"));
	P.AIGroups = JList(O, TEXT("AIGroups"));
	P.Accuracy = JNum(O, TEXT("Accuracy"), 1); P.Range = JNum(O, TEXT("Range")); P.Radius = JNum(O, TEXT("Radius"));
	P.Arc = JNum(O, TEXT("Arc")); P.EndCost = JNum(O, TEXT("EnduranceCost")); P.Activate = JNum(O, TEXT("TimeToActivate"), 1);
	P.Recharge = JNum(O, TEXT("RechargeTime"), 1); P.Period = JNum(O, TEXT("ActivatePeriod")); P.MaxTargets = (int32)JNum(O, TEXT("MaxTargetsHit"));
	const TArray<TSharedPtr<FJsonValue>>* Mods;
	if (O->TryGetArrayField(TEXT("mods"), Mods))
		for (const auto& MV : *Mods)
		{
			const auto M = MV->AsObject();
			FCoHMod D;
			D.Attrib = JStr(M, TEXT("Attrib")); D.Aspect = JStr(M, TEXT("Aspect")); D.Table = JStr(M, TEXT("Table"));
			D.Target = JStr(M, TEXT("Target")); D.bDuration = JStr(M, TEXT("Type")) == TEXT("kDuration");
			D.Scale = JNum(M, TEXT("Scale")); D.Magnitude = JNum(M, TEXT("Magnitude"), 1); D.Duration = JNum(M, TEXT("Duration"));
			D.Delay = JNum(M, TEXT("Delay")); D.Period = JNum(M, TEXT("Period")); D.Chance = JNum(M, TEXT("Chance"), 1);
			const FString Req = FString::Join(JList(M, TEXT("Requires")), TEXT(" ")).ToLower();
			if (Req.IsEmpty()) D.Requires = 0;
			else if (Req == TEXT("enttype target> critter eq")) D.Requires = 1;
			else if (Req == TEXT("enttype target> player eq")) D.Requires = 2;
			else D.Requires = -1;
			P.Mods.Add(MoveTemp(D));
		}
	return P;
}

void UCoHPowerDatabase::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	const double T0 = FPlatformTime::Seconds();
	const FString Dir = RulesDir.IsEmpty() ? FPaths::ProjectContentDir() / TEXT("CoH/Data/Rules") : RulesDir;
	TSharedPtr<FJsonValue> Root;
	if (LoadJson(Dir, TEXT("classes.json"), Root))
		for (const auto& KV : Root->AsObject()->Values)
		{
			FCoHClassDef C = ReadClass(FString(KV.Key), KV.Value->AsObject());
			// player archetypes; everything else (minion, lieutenant, boss...) is a critter class
			static const TCHAR* ATs[] = { TEXT("Blaster"), TEXT("Controller"), TEXT("Defender"), TEXT("Scrapper"), TEXT("Tanker"),
				TEXT("Peacebringer"), TEXT("Warshade"), TEXT("Brute"), TEXT("Corruptor"), TEXT("Dominator"), TEXT("Mastermind"),
				TEXT("Stalker"), TEXT("Arachnos_Soldier"), TEXT("Arachnos_Widow") };
			bool bAT = false;
			for (const TCHAR* A : ATs) bAT |= C.Name.Equals(FString(TEXT("Class_")) + A, ESearchCase::IgnoreCase);
			(bAT ? Archetypes : Critters).Add(MoveTemp(C));
		}
	if (LoadJson(Dir, TEXT("combat_mods.json"), Root) && Root->AsArray().Num())
	{
		// the first entry is the small-team row (1-3 players)
		const auto E = Root->AsArray()[0]->AsObject();
		const TSharedPtr<FJsonObject>* Side;
		if (E->TryGetObjectField(TEXT("HigherLevel"), Side)) for (const auto& V : (*Side)->GetArrayField(TEXT("ToHit"))) ToHitHigher.Add(V->AsNumber());
		if (E->TryGetObjectField(TEXT("LowerLevel"), Side)) for (const auto& V : (*Side)->GetArrayField(TEXT("ToHit"))) ToHitLower.Add(V->AsNumber());
	}
	if (LoadJson(Dir, TEXT("powersets.json"), Root))
		for (const auto& KV : Root->AsObject()->Values)
		{
			const auto O = KV.Value->AsObject();
			FCoHPowerSetDef S;
			S.Id = FString(KV.Key);
			S.Category = S.Id.Left(S.Id.Find(TEXT(".")));
			S.Display = Pretty(JStr(O, TEXT("Name")));
			S.Icon = JStr(O, TEXT("IconName"));
			for (const auto& E : O->GetArrayField(TEXT("powers")))
			{
				const auto EO = E->AsObject();
				S.Powers.Add({ FName(*JStr(EO, TEXT("power"))), (int32)JNum(EO, TEXT("available"), 0) + 1 });
			}
			PowerSets.Add(MoveTemp(S));
		}
	if (LoadJson(Dir, TEXT("powers.json"), Root))
		for (const auto& KV : Root->AsObject()->Values)
		{
			FCoHPowerDef P = ReadPower(FString(KV.Key), KV.Value->AsObject());
			Powers.Add(P.Id, MoveTemp(P));
		}
	if (LoadJson(Dir, TEXT("villains.json"), Root))
		for (const auto& KV : Root->AsObject()->Values)
		{
			const auto O = KV.Value->AsObject();
			FCoHVillainDef V;
			V.Name = FString(KV.Key);
			V.Class = JStr(O, TEXT("Class")); V.Rank = JStr(O, TEXT("Rank")); V.Group = JStr(O, TEXT("VillainGroup"));
			V.AIConfig = JStr(O, TEXT("AIConfig"));
			const TArray<TSharedPtr<FJsonValue>>* List;
			if (O->TryGetArrayField(TEXT("powers"), List))
				for (const auto& PV : *List)
				{
					const auto& A = PV->AsArray();
					if (A.Num() < 3) continue;
					const FString Set = A[0]->AsString() + TEXT(".") + A[1]->AsString();
					const FString One = A[2]->AsString();
					if (One != TEXT("*")) { V.Powers.Add(FName(*(Set + TEXT(".") + One))); continue; }
					// "*": every power of the set
					for (const FCoHPowerSetDef& S : PowerSets)
						if (S.Id.Equals(Set, ESearchCase::IgnoreCase)) for (const auto& E : S.Powers) V.Powers.Add(E.Key);
				}
			const TSharedPtr<FJsonObject>* Levels;
			if (O->TryGetObjectField(TEXT("levels"), Levels))
				for (const auto& L : (*Levels)->Values)
				{
					const auto LO = L.Value->AsObject();
					if (LO.IsValid()) V.Costumes.Add(FCString::Atoi(*FString(L.Key)), JList(LO, TEXT("Costumes")));
				}
			Villains.Add(V.Name, MoveTemp(V));
		}
	if (LoadJson(Dir, TEXT("ai_configs.json"), Root))
		for (const auto& KV : Root->AsObject()->Values)
		{
			TSharedPtr<FJsonObject> O = KV.Value->AsObject();
			const TSharedPtr<FJsonObject>* Inner;
			if (O->TryGetObjectField(TEXT("values"), Inner)) O = *Inner;    // tools/ai/coh_ai.py shape
			FCoHAIConfig A;
			auto Num = [&](const TCHAR* K, float D) { return JNum(O, K, D); };
			A.bPreferMelee = Num(TEXT("Misc.PreferMelee"), 0) > 0;
			A.bPreferRanged = Num(TEXT("Misc.PreferRanged"), 0) > 0;
			A.bDoNotMove = Num(TEXT("Misc.DoNotMove"), 0) > 0;
			A.bIgnoreFriendsAttacked = Num(TEXT("Misc.IgnoreFriendsAttacked"), 0) > 0;
			A.MeleeScale = Num(TEXT("Misc.PreferMeleeScale"), 1); A.RangedScale = Num(TEXT("Misc.PreferRangedScale"), 1);
			A.ShoutChance = Num(TEXT("Misc.ShoutChance"), 50); A.ShoutRadius = Num(TEXT("Misc.ShoutRadius"), 30);
			A.FOVDegrees = Num(TEXT("Misc.FOVDegrees"), 240); A.Standoff = Num(TEXT("Misc.StandoffDistance"), 10);
			A.GriefHPRatio = Num(TEXT("Misc.GriefHPRatio"), 0.7f); A.GriefTimeBegin = Num(TEXT("Misc.GriefTimeBegin"), 10);
			A.GriefTimeEnd = Num(TEXT("Misc.GriefTimeEnd"), 30); A.Fear = Num(TEXT("Feeling.Base.Fear"), 0.2f);
			A.Brain = JStr(O, TEXT("Brain.Name"));
			A.ProtectSpawnRadius = Num(TEXT("Misc.ProtectSpawnRadius"), 100);
			A.ProtectSpawnOutsideRadius = Num(TEXT("Misc.ProtectSpawnOutsideRadius"), 20);
			A.ProtectSpawnTime = Num(TEXT("Misc.ProtectSpawnTime"), 30);
			A.EventMemoryDuration = Num(TEXT("Misc.EventMemoryDuration"), 20);
			AIConfigs.Add(FString(KV.Key), A);
		}
	if (LoadJson(Dir, TEXT("behavior_aliases.json"), Root))
		for (const auto& KV : Root->AsObject()->Values)
		{
			// e.g. Loiter: DoNothing(AnimList(Observer),Timer(Rand(10,20))),WanderAround(Radius(40),AnimList(M_Sneak),Timer(Rand(2,5)))
			const FString R = JStr(KV.Value->AsObject(), TEXT("recipe"));
			const int32 Stand = R.Find(TEXT("DoNothing(")), Walk = R.Find(TEXT("WanderAround("));
			if (Walk == INDEX_NONE) continue;
			auto Rand = [&](int32 From, float& Lo, float& Hi)
			{
				const int32 T = R.Find(TEXT("Timer(Rand("), ESearchCase::IgnoreCase, ESearchDir::FromStart, From);
				if (T == INDEX_NONE) return;
				TArray<FString> P; R.Mid(T + 11, 16).ParseIntoArray(P, TEXT(","));
				if (P.Num() >= 2) { Lo = FCString::Atof(*P[0]); Hi = FCString::Atof(*P[1]); }
			};
			FCoHIdleRecipe I;
			if (Stand != INDEX_NONE && Stand < Walk)
			{
				Rand(Stand, I.StandMin, I.StandMax);
				const int32 A = R.Find(TEXT("AnimList("), ESearchCase::IgnoreCase, ESearchDir::FromStart, Stand);
				if (A != INDEX_NONE && A < Walk) I.StandAnim = R.Mid(A + 9, R.Find(TEXT(")"), ESearchCase::IgnoreCase, ESearchDir::FromStart, A) - A - 9);
			}
			else { I.StandMin = I.StandMax = 0.f; }
			const int32 Rad = R.Find(TEXT("Radius("), ESearchCase::IgnoreCase, ESearchDir::FromStart, Walk);
			if (Rad != INDEX_NONE) I.Radius = FCString::Atof(*R.Mid(Rad + 7, 6));
			Rand(Walk, I.WalkMin, I.WalkMax);
			IdleRecipes.Add(FString(KV.Key), I);
		}
	if (LoadJson(Dir, TEXT("hero_all_sets.json"), Root))
		for (const auto& SV : Root->AsObject()->GetArrayField(TEXT("sets")))
		{
			const auto O = SV->AsObject();
			FCoHHeroSet H;
			H.Id = JStr(O, TEXT("set"));
			H.Category = H.Id.Left(H.Id.Find(TEXT(".")));
			H.Name = Pretty(H.Id.Mid(H.Id.Find(TEXT(".")) + 1));
			H.Element = JStr(O, TEXT("element"));
			for (const FString& P : JList(O, TEXT("powers"))) H.Powers.Add(FName(*P));
			HeroSets.Add(MoveTemp(H));
		}
	UE_LOG(LogTemp, Log, TEXT("CoH rules from %s: %d archetypes, %d critter classes, %d sets, %d powers, %d villains, %d test-hero sets, to-hit by level %d/%d (%.1f s)"),
		*Dir, Archetypes.Num(), Critters.Num(), PowerSets.Num(), Powers.Num(), Villains.Num(), HeroSets.Num(), ToHitHigher.Num(), ToHitLower.Num(),
		FPlatformTime::Seconds() - T0);
}

const TArray<FString>* FCoHVillainDef::CostumesAt(int32 Level) const
{
	const TArray<FString>* Best = nullptr; int32 BestD = MAX_int32;
	for (const auto& KV : Costumes)
		if (KV.Value.Num() && FMath::Abs(KV.Key - Level) < BestD) { BestD = FMath::Abs(KV.Key - Level); Best = &KV.Value; }
	return Best;
}

const FCoHAIConfig& UCoHPowerDatabase::AIConfig(const FString& Name) const
{
	static const FCoHAIConfig Default;
	const FCoHAIConfig* A = AIConfigs.Find(Name);
	if (!A) A = AIConfigs.Find(TEXT("Default"));
	return A ? *A : Default;
}

const FCoHIdleRecipe& UCoHPowerDatabase::IdleRecipe(const FString& Name) const
{
	static const FCoHIdleRecipe Default;
	const FCoHIdleRecipe* I = IdleRecipes.Find(Name);
	return I ? *I : Default;
}

float UCoHPowerDatabase::LevelToHit(int32 AttackerLevel, int32 TargetLevel) const
{
	const int32 D = TargetLevel - AttackerLevel;
	const TArray<float>& T = D >= 0 ? ToHitHigher : ToHitLower;
	if (T.Num() == 0) return 1.f;
	return T[FMath::Clamp(FMath::Abs(D), 0, T.Num() - 1)];
}

UCoHPowerDatabase* UCoHPowerDatabase::Get(const UObject* WorldContext)
{
	const UWorld* W = WorldContext ? WorldContext->GetWorld() : nullptr;
	return W && W->GetGameInstance() ? W->GetGameInstance()->GetSubsystem<UCoHPowerDatabase>() : nullptr;
}

const FCoHClassDef* UCoHPowerDatabase::FindClass(const FString& Name) const
{
	for (const FCoHClassDef& C : Archetypes) if (C.Name.Equals(Name, ESearchCase::IgnoreCase)) return &C;
	for (const FCoHClassDef& C : Critters) if (C.Name.Equals(Name, ESearchCase::IgnoreCase)) return &C;
	return nullptr;
}

const FCoHClassDef* UCoHPowerDatabase::ClassForCategory(const FString& Category) const
{
	for (const FCoHClassDef& C : Archetypes)
		if (C.Primary.Equals(Category, ESearchCase::IgnoreCase) || C.Secondary.Equals(Category, ESearchCase::IgnoreCase)) return &C;
	return nullptr;
}

UTexture2D* UCoHPowerDatabase::Icon(const FString& IconName)
{
	if (IconName.IsEmpty()) return nullptr;
	const FString Key = FPaths::GetBaseFilename(IconName).ToLower();
	if (const TObjectPtr<UTexture2D>* C = IconCache.Find(Key)) return C->Get();
	// the original 32 px icons are read straight from their PNG files
	UTexture2D* T = FImageUtils::ImportFileAsTexture2D(FPaths::ProjectContentDir() / TEXT("CoH/Data/Icons") / (Key + TEXT(".cohicon")));
	if (T) { T->Filter = TF_Bilinear; T->LODGroup = TEXTUREGROUP_UI; }
	IconCache.Add(Key, T);
	return T;
}

// ------------------------------------------------------------------ component
UCoHPowerComponent::UCoHPowerComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickInterval = 0.125f;     // the game's stat tick
	SetIsReplicatedByDefault(true);
}

void UCoHPowerComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(UCoHPowerComponent, ClassName);
	DOREPLIFETIME(UCoHPowerComponent, Level);
	DOREPLIFETIME(UCoHPowerComponent, DisplayName);
	DOREPLIFETIME(UCoHPowerComponent, Health);
	DOREPLIFETIME(UCoHPowerComponent, MaxHealth);
	DOREPLIFETIME(UCoHPowerComponent, Endurance);
	DOREPLIFETIME(UCoHPowerComponent, MaxEndurance);
	DOREPLIFETIME_CONDITION(UCoHPowerComponent, Tray, COND_OwnerOnly);
	DOREPLIFETIME_CONDITION(UCoHPowerComponent, Recharges, COND_OwnerOnly);
	DOREPLIFETIME(UCoHPowerComponent, ActiveToggles);
}

FSoftObjectPath UCoHPowerComponent::FindClip(const FString& NameOrPath)
{
	if (NameOrPath.IsEmpty()) return FSoftObjectPath();
	if (NameOrPath.StartsWith(TEXT("/"))) return FSoftObjectPath(NameOrPath.Contains(TEXT(".")) ? NameOrPath : NameOrPath + TEXT(".") + FPaths::GetBaseFilename(NameOrPath));
	IAssetRegistry& AR = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry").Get();
	TArray<FAssetData> Found;
	AR.GetAssetsByClass(UAnimSequence::StaticClass()->GetClassPathName(), Found, true);
	for (const FAssetData& A : Found) if (A.AssetName.ToString().Equals(NameOrPath, ESearchCase::IgnoreCase)) return A.GetSoftObjectPath();
	return FSoftObjectPath();
}

bool UCoHPowerComponent::SetPowerAnimation(FName Power, const FString& ClipNameOrPath)
{
	FCoHPowerStyle& S = Styles.FindOrAdd(Power);
	S.Clip = FindClip(ClipNameOrPath);
	return ClipNameOrPath.IsEmpty() || S.Clip.IsValid();
}

void UCoHPowerComponent::SetPowerEmitter(FName Power, ECoHEmitter Emitter)
{
	Styles.FindOrAdd(Power).Emitter = Emitter;
}

float UCoHPowerComponent::BaseAttrib(const TCHAR* Name, float Default) const
{
	const FCoHClassDef* C = Class();
	const float* V = C ? C->Base.Find(FString(Name).ToLower()) : nullptr;
	return V ? *V : Default;
}
float UCoHPowerComponent::RegenPerSecond() const
{
	return MaxHealth * BaseAttrib(TEXT("Regeneration"), 0.25f) * FMath::Max(0.f, 1.f + BuffSum(TEXT("kRegeneration"), TEXT("kCur"))) / 60.f;
}
float UCoHPowerComponent::RecoveryPerSecond() const
{
	return MaxEndurance * BaseAttrib(TEXT("Recovery"), 1.f) * FMath::Max(0.f, 1.f + BuffSum(TEXT("kRecovery"), TEXT("kCur"))) / 60.f;
}
void UCoHPowerComponent::SetClassAndLevel(const FString& InClass, int32 InLevel)
{
	ClassName = InClass;
	Level = FMath::Clamp(InLevel, 1, 50);
	InitStats();
}

UCoHPowerComponent* UCoHPowerComponent::Of(const AActor* A)
{
	return A ? A->FindComponentByClass<UCoHPowerComponent>() : nullptr;
}

const FCoHClassDef* UCoHPowerComponent::Class() const
{
	const UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
	return DB ? DB->FindClass(ClassName) : nullptr;
}

void UCoHPowerComponent::BeginPlay()
{
	Super::BeginPlay();
	if (Tray.Num() < 10) Tray.SetNum(10);
	InitStats();
}

void UCoHPowerComponent::InitStats()
{
	if (GetOwnerRole() != ROLE_Authority) return;
	if (const FCoHClassDef* C = Class())
	{
		if (C->HitPoints.Num()) MaxHealth = C->HitPoints[FMath::Clamp(Level - 1, 0, C->HitPoints.Num() - 1)];
		MaxEndurance = C->Endurance.Num() ? C->Endurance[FMath::Clamp(Level - 1, 0, C->Endurance.Num() - 1)] : 100.f;
		if (DisplayName.IsEmpty()) DisplayName = C->Display;
	}
	Reset();
}

void UCoHPowerComponent::Reset()
{
	Health = MaxHealth;
	Endurance = MaxEndurance;
	Buffs.Reset();
	MezUntil = 0;
	ActiveToggles.Reset();
}

float UCoHPowerComponent::BuffSum(const FString& Attrib, const FString& Aspect) const
{
	float S = 0;
	for (const FCoHBuff& B : Buffs) if (B.Aspect == Aspect && B.Attrib.Equals(Attrib, ESearchCase::IgnoreCase)) S += B.Value;
	return S;
}

static const TCHAR* DamageAttrib(ECoHDamage T)
{
	static const TCHAR* Names[] = { TEXT("kSmashing"), TEXT("kLethal"), TEXT("kFire"), TEXT("kCold"), TEXT("kEnergy"), TEXT("kNegative_Energy"), TEXT("kPsionic"), TEXT("kToxic") };
	return Names[FMath::Clamp((int32)T, 0, 7)];
}
static bool ParseDamage(const FString& Attrib, ECoHDamage& Out)
{
	for (int32 i = 0; i < (int32)ECoHDamage::Count; ++i)
		if (Attrib.Equals(DamageAttrib((ECoHDamage)i), ESearchCase::IgnoreCase)) { Out = (ECoHDamage)i; return true; }
	return false;
}

float UCoHPowerComponent::Resistance(ECoHDamage Type) const
{
	return FMath::Clamp(BuffSum(DamageAttrib(Type), TEXT("kRes")), -1.f, 0.9f);
}

float UCoHPowerComponent::Defense(bool bMelee) const
{
	return BuffSum(TEXT("kDefense"), TEXT("kCur")) + BuffSum(bMelee ? TEXT("kMelee_Attack") : TEXT("kRanged_Attack"), TEXT("kCur"));
}

bool UCoHPowerComponent::IsMezzed() const
{
	const UWorld* W = GetWorld();
	return W && W->GetTimeSeconds() < MezUntil;
}

FString UCoHPowerComponent::MezName() const { return IsMezzed() ? Mez : FString(); }

FLinearColor UCoHPowerComponent::DamageColour(ECoHDamage Type)
{
	switch (Type)
	{
	case ECoHDamage::Fire: return FLinearColor(1.f, 0.35f, 0.05f);
	case ECoHDamage::Cold: return FLinearColor(0.45f, 0.8f, 1.f);
	case ECoHDamage::Energy: return FLinearColor(0.35f, 0.55f, 1.f);
	case ECoHDamage::NegativeEnergy: return FLinearColor(0.55f, 0.15f, 0.8f);
	case ECoHDamage::Psionic: return FLinearColor(0.95f, 0.35f, 0.9f);
	case ECoHDamage::Toxic: return FLinearColor(0.4f, 0.95f, 0.2f);
	case ECoHDamage::Lethal: return FLinearColor(0.85f, 0.85f, 0.85f);
	default: return FLinearColor(1.f, 0.85f, 0.4f);
	}
}

FLinearColor UCoHPowerComponent::ConColour(int32 MyLevel, int32 TheirLevel)
{
	const int32 D = TheirLevel - MyLevel;
	if (D <= -4) return FLinearColor(0.5f, 0.5f, 0.5f);      // grey
	if (D <= -2) return FLinearColor(0.2f, 0.8f, 0.2f);      // green
	if (D == -1) return FLinearColor(0.3f, 0.5f, 1.f);       // blue
	if (D == 0) return FLinearColor::White;
	if (D == 1) return FLinearColor(1.f, 0.9f, 0.1f);        // yellow
	if (D == 2) return FLinearColor(1.f, 0.55f, 0.1f);       // orange
	if (D <= 4) return FLinearColor(1.f, 0.15f, 0.1f);       // red
	return FLinearColor(0.6f, 0.1f, 0.9f);                   // purple
}

float UCoHPowerComponent::RechargeLeft(FName Power) const
{
	const UWorld* W = GetWorld();
	for (const FCoHRecharge& R : Recharges) if (R.Power == Power) return FMath::Max(0.f, R.ReadyAt - (W ? (float)W->GetTimeSeconds() : 0.f));
	return 0.f;
}

float UCoHPowerComponent::RechargeTotal(FName Power) const
{
	const UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
	const FCoHPowerDef* P = DB ? DB->FindPower(Power) : nullptr;
	return P ? P->Recharge + P->Activate : 1.f;
}

void UCoHPowerComponent::SetTray(int32 Slot, FName Power)
{
	if (Tray.Num() < 10) Tray.SetNum(10);
	if (Tray.IsValidIndex(Slot)) Tray[Slot] = Power;
	if (GetOwnerRole() != ROLE_Authority) ServerSetTray(Slot, Power);
}
void UCoHPowerComponent::ServerSetTray_Implementation(int32 Slot, FName Power)
{
	if (Tray.Num() < 10) Tray.SetNum(10);
	if (Tray.IsValidIndex(Slot)) Tray[Slot] = Power;
}

void UCoHPowerComponent::ActivateSlot(int32 Slot)
{
	if (Tray.IsValidIndex(Slot) && !Tray[Slot].IsNone()) ActivatePower(Tray[Slot]);
}

void UCoHPowerComponent::ActivatePower(FName Power)
{
	AActor* T = Target.Get();
	FVector Loc = T ? T->GetActorLocation() : GetOwner()->GetActorLocation() + GetOwner()->GetActorForwardVector() * 1500.f;
	ServerActivate(Power, T, Loc);
}

static float Now0(const UWorld* W) { return W ? W->GetTimeSeconds() : 0.f; }

static AActor* NearestFoe(const UCoHPowerComponent* Me, float MaxRange, bool bInFront)
{
	const AActor* Owner = Me->GetOwner();
	AActor* Best = nullptr; float BestD = MaxRange * MaxRange;
	for (TActorIterator<ACharacter> It(Me->GetWorld()); It; ++It)
	{
		const UCoHPowerComponent* C = UCoHPowerComponent::Of(*It);
		if (!C || C == Me || C->IsDefeated() || C->bPlayerSide == Me->bPlayerSide) continue;
		const FVector To = It->GetActorLocation() - Owner->GetActorLocation();
		if (bInFront && FVector::DotProduct(To.GetSafeNormal2D(), Owner->GetActorForwardVector()) < 0.2f) continue;
		const float D = To.SizeSquared();
		if (D < BestD) { BestD = D; Best = *It; }
	}
	return Best;
}

void UCoHPowerComponent::ServerActivate_Implementation(FName Power, AActor* TargetActor, FVector_NetQuantize Location)
{
	UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
	const FCoHPowerDef* P = DB ? DB->FindPower(Power) : nullptr;
	UWorld* W = GetWorld();
	UE_LOG(LogTemp, Log, TEXT("CoH activate %s by %s (target %s): %s"), *Power.ToString(), *GetNameSafe(GetOwner()), *GetNameSafe(TargetActor),
		!P ? TEXT("unknown power") : IsDefeated() ? TEXT("defeated") : Now0(W) < BusyUntil ? TEXT("busy") : RechargeLeft(Power) > 0.f ? TEXT("recharging") : TEXT("ok"));
	if (!P || !W || IsDefeated()) return;
	const float Now = W->GetTimeSeconds();
	// toggles switch off at once, even while held
	if (P->Type == TEXT("kToggle") && ActiveToggles.Contains(Power))
	{
		ActiveToggles.Remove(Power);
		Buffs.RemoveAll([&](const FCoHBuff& B) { return B.Source == Power; });
		return;
	}
	if (IsMezzed()) { MulticastText(TEXT("Can't act: ") + Mez, FLinearColor(1, 0.4f, 0.4f)); return; }
	if (Now < BusyUntil || RechargeLeft(Power) > 0.f) return;
	if (Endurance < P->EndCost) { MulticastText(TEXT("Not enough endurance"), FLinearColor(0.4f, 0.6f, 1)); return; }

	AActor* Owner = GetOwner();
	const bool bNeedsFoe = P->Target == TEXT("kFoe");
	const float Reach = P->Range * FeetToCm + 120.f;
	if (bNeedsFoe)
	{
		const UCoHPowerComponent* TC = Of(TargetActor);
		if (!TC || TC->IsDefeated() || !IsFoe(TC)) TargetActor = NearestFoe(this, FMath::Max(Reach, 600.f), true);
		if (!TargetActor) { MulticastText(TEXT("No target"), FLinearColor(1, 1, 1)); return; }
		if (FVector::Dist(Owner->GetActorLocation(), TargetActor->GetActorLocation()) > Reach)
		{ MulticastText(TEXT("Out of range"), FLinearColor(1, 1, 1)); return; }
		// only buildings and terrain block line of sight, not other people
		// (volumes such as the PCG generators are invisible: skip them)
		TArray<FHitResult> Blocks;
		FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHPowerLOS), false, Owner);
		Q.AddIgnoredActor(TargetActor);
		W->LineTraceMultiByObjectType(Blocks, Owner->GetActorLocation() + FVector(0, 0, 60), TargetActor->GetActorLocation() + FVector(0, 0, 40),
			FCollisionObjectQueryParams(ECC_WorldStatic), Q);
		for (const FHitResult& Block : Blocks)
		{
			if (!Block.bBlockingHit || Cast<AVolume>(Block.GetActor())) continue;
			UE_LOG(LogTemp, Log, TEXT("CoH line of sight blocked by %s"), *GetNameSafe(Block.GetActor()));
			MulticastText(TEXT("Target not in view"), FLinearColor(1, 1, 1)); return;
		}
		Location = TargetActor->GetActorLocation();
	}
	else if (P->Target == TEXT("kFriend"))
	{
		const UCoHPowerComponent* TC = Of(TargetActor);
		if (!TC || IsFoe(TC)) TargetActor = Owner;   // friendly power with no friend targeted: self
		Location = TargetActor->GetActorLocation();
	}
	else if (P->Target == TEXT("kCaster")) { TargetActor = Owner; Location = Owner->GetActorLocation(); }

	Endurance -= P->Type == TEXT("kToggle") ? 0.f : P->EndCost;
	FCoHRecharge* R = Recharges.FindByPredicate([&](const FCoHRecharge& X) { return X.Power == Power; });
	if (!R) { R = &Recharges.AddDefaulted_GetRef(); R->Power = Power; }
	R->ReadyAt = Now + P->Activate + P->Recharge;
	BusyUntil = Now + P->Activate;

	if (TargetActor && TargetActor != Owner)
	{
		FVector To = TargetActor->GetActorLocation() - Owner->GetActorLocation(); To.Z = 0;
		if (!To.IsNearlyZero()) Owner->SetActorRotation(To.Rotation());
	}
	if (P->Type == TEXT("kToggle"))
	{
		ActiveToggles.AddUnique(Power);
		NextToggleTick = 0;       // apply on the next tick
	}
	MulticastPlay(Power, TargetActor, Location, 0);
	if (P->Type == TEXT("kToggle") || P->Type == TEXT("kAuto")) return;
	// effects land at the release point of the animation (about half way)
	const float ReleaseAt = FMath::Max(0.15f, P->Activate * (P->IsMelee() ? 0.45f : 0.55f));
	FTimerHandle H;
	W->GetTimerManager().SetTimer(H, FTimerDelegate::CreateUObject(this, &UCoHPowerComponent::Release, Power, TWeakObjectPtr<AActor>(TargetActor), FVector(Location)), ReleaseAt, false);
	// a fight breaks out: civilians nearby run, traffic stops
	ACoHLifeManager::ReportDanger(Owner, Owner->GetActorLocation(), 1500.f, 4.f);
}

void UCoHPowerComponent::Release(FName Power, TWeakObjectPtr<AActor> TargetActor, FVector Location)
{
	UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
	const FCoHPowerDef* P = DB ? DB->FindPower(Power) : nullptr;
	if (!P || IsDefeated()) return;
	Execute(*P, TargetActor.Get(), Location);
}

TArray<UCoHPowerComponent*> UCoHPowerComponent::Gather(const FCoHPowerDef& P, AActor* TargetActor, FVector Center) const
{
	TArray<UCoHPowerComponent*> Out;
	AActor* Owner = GetOwner();
	const bool bFoes = P.Affects.Contains(TEXT("kFoe")) || P.Target == TEXT("kFoe");
	const bool bFriends = P.Affects.Contains(TEXT("kFriend")) || P.Affects.Contains(TEXT("kTeammate"));
	const bool bSelf = P.Affects.Contains(TEXT("kCaster")) || P.Target == TEXT("kCaster");
	auto Wants = [&](UCoHPowerComponent* C)
	{
		if (!C || C->IsDefeated()) return false;
		if (C == this) return bSelf || (bFriends && P.Area != TEXT("kCharacter"));
		return IsFoe(C) ? bFoes : bFriends;
	};
	if (P.Area == TEXT("kCharacter"))
	{
		UCoHPowerComponent* C = Of(P.Target == TEXT("kCaster") ? Owner : TargetActor);
		if (Wants(C)) Out.Add(C);
		return Out;
	}
	const bool bCone = P.Area == TEXT("kCone");
	const float Radius = (bCone ? P.Range : P.Radius) * FeetToCm + 50.f;
	if (!bCone && P.Range <= 0.f && P.Target != TEXT("kLocation")) Center = Owner->GetActorLocation();   // point-blank
	if (bCone) Center = Owner->GetActorLocation();
	struct FHit { UCoHPowerComponent* C; float D; };
	TArray<FHit> Hits;
	for (TActorIterator<ACharacter> It(GetWorld()); It; ++It)
	{
		UCoHPowerComponent* C = Of(*It);
		if (!Wants(C)) continue;
		const FVector To = It->GetActorLocation() - Center;
		const float D = To.Size();
		if (D > Radius) continue;
		if (bCone && D > 1.f)
		{
			const float Ang = FMath::RadiansToDegrees(FMath::Acos(FVector::DotProduct(To.GetSafeNormal2D(), Owner->GetActorForwardVector())));
			if (Ang > FMath::Max(P.Arc, 20.f) * 0.5f) continue;
		}
		Hits.Add({ C, D });
	}
	Hits.Sort([](const FHit& A, const FHit& B) { return A.D < B.D; });
	const int32 Max = P.MaxTargets > 0 ? P.MaxTargets : 16;
	for (int32 i = 0; i < Hits.Num() && i < Max; ++i) Out.Add(Hits[i].C);
	return Out;
}

void UCoHPowerComponent::Execute(const FCoHPowerDef& P, AActor* TargetActor, FVector Location)
{
	const FCoHClassDef* C = Class();
	const float BaseToHit = C && C->Base.Contains(TEXT("tohit")) ? C->Base[TEXT("tohit")] : 0.75f;
	for (UCoHPowerComponent* V : Gather(P, TargetActor, Location))
	{
		const bool bSelf = V == this;
		if (IsFoe(V))
		{
			// to-hit: base + buffs - defence, scaled by the level difference
			// (combat_mods.def), kept within 5-95%, then times accuracy
			const UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
			const float LevelMod = DB ? DB->LevelToHit(Level, V->Level) : 1.f;
			const float ToHit = FMath::Clamp((BaseToHit + BuffSum(TEXT("kToHit"), TEXT("kCur")) - V->Defense(P.IsMelee())) * LevelMod, 0.05f, 0.95f);
			const float Chance = FMath::Clamp(ToHit * P.Accuracy, 0.05f, 0.95f);
			LastHitChance = Chance;
			if (FMath::FRand() > Chance) { V->MulticastText(TEXT("MISS"), FLinearColor(0.8f, 0.8f, 0.8f)); continue; }
		}
		ApplyMods(P, V, bSelf, -1.f);
	}
	// mods that always target the caster (self buffs on attacks)
	for (const FCoHMod& M : P.Mods)
		if (M.Target == TEXT("kSelf") && M.Aspect != TEXT("kStr") && P.Target != TEXT("kCaster")) ApplyMod(P, M, this, -1.f);
}

void UCoHPowerComponent::ApplyMods(const FCoHPowerDef& P, UCoHPowerComponent* Victim, bool bSelf, float DurationOverride)
{
	for (const FCoHMod& M : P.Mods)
	{
		if (M.Target == TEXT("kSelf") && !bSelf) continue;       // handled once in Execute
		ApplyMod(P, M, Victim, DurationOverride);
	}
}

void UCoHPowerComponent::ApplyMod(const FCoHPowerDef& P, const FCoHMod& M, UCoHPowerComponent* Victim, float DurationOverride)
{
	if (!Victim || M.Requires < 0) return;
	if (M.Requires == 1 && Victim->bPlayerSide) return;
	if (M.Requires == 2 && !Victim->bPlayerSide) return;
	if (M.Aspect == TEXT("kStr")) return;                       // enhancement-style strength mods: later
	if (M.Chance < 1.f && FMath::FRand() > M.Chance) return;
	UWorld* W = GetWorld();
	if (M.Delay > 0.f && DurationOverride < 0.f)
	{
		FCoHMod Now = M; Now.Delay = 0;
		TWeakObjectPtr<UCoHPowerComponent> Self(this), V(Victim);
		const FCoHPowerDef Copy = P;
		FTimerHandle H;
		W->GetTimerManager().SetTimer(H, FTimerDelegate::CreateLambda([Self, V, Copy, Now]()
		{
			if (Self.IsValid() && V.IsValid() && !V->IsDefeated()) Self->ApplyMod(Copy, Now, V.Get(), -1.f);
		}), M.Delay, false);
		return;
	}
	const FCoHClassDef* Table = nullptr;
	if (const UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this))
	{
		Table = bPlayerSide ? DB->ClassForCategory(P.Category) : nullptr;
		if (!Table) Table = DB->FindClass(ClassName);
	}
	const float T = Table ? Table->TableValue(M.Table, Level) : 0.f;
	float Amount = M.bDuration ? M.Magnitude : M.Scale * T * M.Magnitude;
	float Duration = M.bDuration ? M.Scale * T : M.Duration;
	if (DurationOverride >= 0.f) Duration = DurationOverride;
	const float Now = W->GetTimeSeconds();
	AActor* Causer = GetOwner();

	ECoHDamage Dmg;
	if (M.Aspect == TEXT("kAbs") && ParseDamage(M.Attrib, Dmg))
	{
		const float Hit = -Amount;
		if (Hit <= 0.f) return;
		if (M.Period > 0.f && Duration > 0.f)
		{
			// damage over time: a tick every Period
			const int32 Ticks = FMath::Max(1, FMath::FloorToInt(Duration / M.Period));
			TWeakObjectPtr<UCoHPowerComponent> V(Victim); TWeakObjectPtr<AActor> Who(Causer);
			for (int32 i = 1; i <= Ticks; ++i)
			{
				FTimerHandle H;
				W->GetTimerManager().SetTimer(H, FTimerDelegate::CreateLambda([V, Who, Hit, Dmg]()
				{ if (V.IsValid() && !V->IsDefeated()) V->ApplyDamage(Hit, Dmg, Who.Get()); }), M.Period * i, false);
			}
			return;
		}
		Victim->ApplyDamage(Hit, Dmg, Causer);
		return;
	}
	if (M.Attrib == TEXT("kHitPoints") && M.Aspect == TEXT("kAbs")) { if (Amount > 0) Victim->Heal(Amount); else Victim->ApplyDamage(-Amount, ECoHDamage::Smashing, Causer); return; }
	if (M.Attrib == TEXT("kEndurance") && M.Aspect == TEXT("kAbs")) { Victim->Endurance = FMath::Clamp(Victim->Endurance + Amount, 0.f, Victim->MaxEndurance); return; }
	if (M.Attrib == TEXT("kHeld") || M.Attrib == TEXT("kStun") || M.Attrib == TEXT("kSleep") || M.Attrib == TEXT("kImmobilized") || M.Attrib == TEXT("kImmobilize"))
	{
		if (Amount <= 0.f || Duration <= 0.f || !IsFoe(Victim)) return;
		Victim->MezUntil = FMath::Max(Victim->MezUntil, Now + Duration);
		Victim->Mez = M.Attrib.Mid(1);
		Victim->MulticastText(Victim->Mez.ToUpper(), FLinearColor(0.6f, 0.8f, 1.f));
		if (ACoHCombatEnemy* E = Cast<ACoHCombatEnemy>(Victim->GetOwner())) E->OnMezzed(Duration);
		return;
	}
	if (M.Attrib == TEXT("kKnockback") || M.Attrib == TEXT("kKnockup"))
	{
		if (Amount < 0.75f || !IsFoe(Victim)) return;
		FVector Away = Victim->GetOwner()->GetActorLocation() - Causer->GetActorLocation(); Away.Z = 0;
		const FVector Launch = M.Attrib == TEXT("kKnockup") ? FVector(0, 0, 500 + Amount * 120)
			: Away.GetSafeNormal() * (250.f + Amount * 160.f) + FVector(0, 0, 220);
		if (ACoHCombatEnemy* E = Cast<ACoHCombatEnemy>(Victim->GetOwner())) E->LaunchRagdoll(Launch);
		else if (ACharacter* Ch = Cast<ACharacter>(Victim->GetOwner())) Ch->LaunchCharacter(Launch, true, true);
		return;
	}
	if (M.Attrib == TEXT("kTaunt"))
	{
		if (ACoHCombatEnemy* E = Cast<ACoHCombatEnemy>(Victim->GetOwner())) E->Taunt(Cast<APawn>(Causer), FMath::Max(Duration, 4.f));
		return;
	}
	// buffs and debuffs that last a while: resistance, defence, to-hit,
	// regeneration, recovery
	if (M.Aspect == TEXT("kRes") || M.Aspect == TEXT("kCur"))
	{
		if (Duration <= 0.f || FMath::IsNearlyZero(Amount)) return;
		FCoHBuff B;
		B.Attrib = M.Attrib; B.Aspect = M.Aspect; B.Value = Amount; B.Until = Now + Duration; B.Source = P.Id;
		// refreshing the same buff from the same power replaces it
		const int32 Existing = Victim->Buffs.IndexOfByPredicate([&](const FCoHBuff& X) { return X.Source == B.Source && X.Attrib == B.Attrib && X.Aspect == B.Aspect; });
		if (Existing != INDEX_NONE) Victim->Buffs[Existing] = B; else Victim->Buffs.Add(B);
	}
}

void UCoHPowerComponent::ToggleTick(const FCoHPowerDef& P)
{
	const float Period = P.Period > 0.f ? P.Period : 0.5f;
	if (P.Type == TEXT("kToggle"))
	{
		if (Endurance < P.EndCost) { ActiveToggles.Remove(P.Id); MulticastText(P.Display + TEXT(" off: no endurance"), FLinearColor(0.4f, 0.6f, 1)); return; }
		Endurance -= P.EndCost;
	}
	const AActor* Owner = GetOwner();
	for (UCoHPowerComponent* V : Gather(P, const_cast<AActor*>(Owner), Owner->GetActorLocation()))
	{
		if (IsFoe(V))
		{
			const UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
			const float Chance = FMath::Clamp(FMath::Clamp((BaseAttrib(TEXT("ToHit"), 0.75f) - V->Defense(P.IsMelee())) * (DB ? DB->LevelToHit(Level, V->Level) : 1.f), 0.05f, 0.95f) * P.Accuracy, 0.05f, 0.95f);
			if (FMath::FRand() > Chance) continue;
		}
		ApplyMods(P, V, V == this, Period + 0.6f);
	}
}

float UCoHPowerComponent::ApplyDamage(float Amount, ECoHDamage Type, AActor* Causer)
{
	if (IsDefeated() || Amount <= 0.f || GetOwnerRole() != ROLE_Authority) return 0.f;
	const float Final = Amount * (1.f - Resistance(Type));
	Health = FMath::Max(0.f, Health - Final);
	LastHurt = GetWorld()->GetTimeSeconds();
	MulticastText(Final < 1.f ? FString::Printf(TEXT("%.1f"), Final) : FString::Printf(TEXT("%.0f"), Final), DamageColour(Type));
	if (ACoHCombatEnemy* E = Cast<ACoHCombatEnemy>(GetOwner()))
	{
		if (IsDefeated()) E->OnDefeated(Causer); else E->OnHurt(Causer, Final);
	}
	else if (ACoHHeroCharacter* H = Cast<ACoHHeroCharacter>(GetOwner()))
	{
		if (IsDefeated()) { ++Defeats; H->OnDefeated(); }
	}
	return Final;
}

void UCoHPowerComponent::Heal(float Amount)
{
	if (IsDefeated() || Amount <= 0.f) return;
	const float Before = Health;
	Health = FMath::Min(MaxHealth, Health + Amount);
	if (Health > Before + 0.5f) MulticastText(FString::Printf(TEXT("+%.0f"), Health - Before), FLinearColor(0.3f, 1.f, 0.4f));
}

void UCoHPowerComponent::TickComponent(float Dt, ELevelTick TickType, FActorComponentTickFunction* Fn)
{
	Super::TickComponent(Dt, TickType, Fn);
	if (GetOwnerRole() != ROLE_Authority || IsDefeated()) return;
	const float Now = GetWorld()->GetTimeSeconds();
	Buffs.RemoveAll([&](const FCoHBuff& B) { return B.Until < Now; });
	// regeneration and recovery from the class's base attributes: the game
	// restores Max * attribute / 60 per second (a Blaster's 0.25 regeneration
	// = 5% of max HP every 12 s; recovery 1.0 = 1.67 endurance per second)
	Health = FMath::Min(MaxHealth, Health + RegenPerSecond() * Dt);
	Endurance = FMath::Min(MaxEndurance, Endurance + RecoveryPerSecond() * Dt);
	if (Now >= NextToggleTick)
	{
		NextToggleTick = Now + 0.5f;
		const UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
		if (!DB) return;
		for (const FName& Id : TArray<FName>(ActiveToggles))
			if (const FCoHPowerDef* P = DB->FindPower(Id)) ToggleTick(*P);
		// auto powers in the tray are always on
		for (const FName& Id : Tray)
			if (const FCoHPowerDef* P = DB->FindPower(Id)) if (P->Type == TEXT("kAuto")) ToggleTick(*P);
	}
}

// ------------------------------------------------------------------ presentation
void UCoHPowerComponent::MulticastText_Implementation(const FString& Text, FLinearColor Colour)
{
	UE_LOG(LogTemp, Log, TEXT("CoH %s: %s"), *GetNameSafe(GetOwner()), *Text);
	OnCombatText.Broadcast(GetOwner(), Text, Colour);
}

void UCoHPowerComponent::MulticastPlay_Implementation(FName Power, AActor* TargetActor, FVector_NetQuantize Location, uint8 Hits)
{
	UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
	if (const FCoHPowerDef* P = DB ? DB->FindPower(Power) : nullptr) PlayLocal(*P, TargetActor, Location, Hits);
}

void UCoHPowerComponent::PlayLocal(const FCoHPowerDef& P, AActor* TargetActor, FVector Location, uint8)
{
	AActor* Owner = GetOwner();
	const FCoHPowerStyle* Style = Styles.Find(P.Id);
	const FCoHPowerStyle Def;
	const FCoHPowerStyle& S = Style ? *Style : Def;
	// element colour from the first damage mod, else a support gold / buff blue
	FLinearColor Colour(1.f, 0.85f, 0.3f);
	for (const FCoHMod& M : P.Mods) { ECoHDamage D; if (M.Aspect == TEXT("kAbs") && ParseDamage(M.Attrib, D)) { Colour = DamageColour(D); break; } }
	if (P.Type == TEXT("kToggle") || P.Type == TEXT("kAuto")) Colour = FLinearColor(0.4f, 0.7f, 1.f);
	if (S.Tint.A > 0.f) Colour = S.Tint;
	const bool bMelee = P.IsMelee();
	const bool bArea = P.Area == TEXT("kSphere") || P.Area == TEXT("kLocation") || P.Area == TEXT("kCone");
	float Release = FMath::Max(0.15f, P.Activate * (bMelee ? 0.45f : 0.55f));
	if (ACoHHeroCharacter* H = Cast<ACoHHeroCharacter>(Owner)) H->PlayPowerAnimation(bMelee ? 0 : (bArea ? 2 : 1), P.Activate, S.Animation, S.Clip);
	else if (ACoHCombatEnemy* E = Cast<ACoHCombatEnemy>(Owner)) E->PlayAttackAnimation();
	if (P.Type == TEXT("kToggle") || P.Type == TEXT("kAuto"))
	{
		ACoHPowerFX::Burst(Owner, Owner->GetActorLocation(), 150.f, Colour, 0.6f, 0.f);
		return;
	}
	const FVector From = ACoHPowerFX::EmitterLocation(Owner, S.Emitter);
	if (P.Area == TEXT("kCone"))
		ACoHPowerFX::Cone(Owner, From, Owner->GetActorForwardVector(), P.Range * FeetToCm, FMath::Max(P.Arc, 20.f), Colour, Release);
	else if (bArea && (P.Range <= 0.f && P.Target != TEXT("kLocation")))
		ACoHPowerFX::Burst(Owner, Owner->GetActorLocation(), P.Radius * FeetToCm, Colour, 0.5f, Release);
	else if (!bMelee && TargetActor != Owner)
	{
		const FVector To = TargetActor ? TargetActor->GetActorLocation() : Location;
		ACoHPowerFX::Bolt(Owner, From, To, Colour, Release, bArea ? P.Radius * FeetToCm : 0.f);
	}
	else if (bMelee && TargetActor)
		ACoHPowerFX::Burst(Owner, TargetActor->GetActorLocation(), 60.f, Colour, 0.25f, Release);
}

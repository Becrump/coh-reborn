// The game-systems rules from the original data, loaded once per game
// instance (all derived from the game files, kept outside git):
//
//   power_anims.json   (coh2unreal.powanim)  power -> moves per body, hit timing, effects
//   hero_rules.json    (tools/rules/coh_build.py)   archetypes, power picks, pools, epics, inherents
//   rewards.json       (tools/rules/coh_rewards.py) XP, influence, debt, inspiration drops
//   kit.json, encounters.json (coh2unreal.enemies, tools/ai/coh_encounters.py)
//
// The hero build rules (requires, can_pick, options, auto_powers) and the
// reward rules (defeat, give_xp, defeated) are ports of those Python tools,
// line for line, so the server builds and levels a hero exactly as the
// selftests check.
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "CoHBodyAnim.h"
#include "CoHGameRules.generated.h"

class UAnimSequenceBase;
class FJsonObject;
class FJsonValue;

/** A power's presentation from power_anims.json: timing, effects and moves. */
struct FCoHPowerAnim
{
	int32 FramesBeforeHit = 15;
	int32 AttackFrames = 0;
	bool bDelayedHit = false;
	float ProjectileSpeed = 0.f;      // ft/s
	TMap<FString, FString> FX;        // ActivationFX, AttackFX, HitFX, ContinuingFX, WindUpFX, InitialAttackFX ...
	/** body (male, fem, huge or a villain's seq type) -> bit field -> [move, anim, first, last] */
	TMap<FString, TMap<FString, TArray<TTuple<FString, FString, int32, int32>>>> Moves;
	/** Seconds from the start of the attack to the hit (projectiles: plus travel). */
	float HitDelay(float DistanceCm) const;
};

/** One bought power: the level it was taken at. */
USTRUCT(BlueprintType)
struct FCoHHeroPick
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 Level = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName Power;
};

/** A hero file, format 2 (docs/hero-build.md), plus the leveling fields. */
USTRUCT(BlueprintType)
struct FCoHHeroRecord
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FString Name = TEXT("New Hero");
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FString Class = TEXT("Class_Blaster");
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FString Origin;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 Level = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 XP = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 Debt = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 Influence = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FString Preset;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FString Primary;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FString Secondary;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) TArray<FCoHHeroPick> Picks;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) TArray<FName> Inspirations;
};

struct FCoHRulePower
{
	FName Power;
	int32 Level = 1;
	TArray<FString> Requires;         // postfix tokens (empty: none)
	bool bAuto = false, bFree = false, bPromo = false;
};

struct FCoHRuleSet
{
	FString Id;
	TArray<FString> SetRequires, SpecializeRequires;
	TArray<FCoHRulePower> Powers;
};

struct FCoHRuleClass
{
	FString Class, Side;
	bool bEpic = false;
	TArray<FString> Origins, Primary, Secondary;
};

/** rewards.json: one reward set of a rank's table row. */
struct FCoHRewardSet
{
	float Chance = 0; bool bAlways = false;
	int32 XP = 0, Influence = 0;
	TArray<FString> Groups; bool bDefaultGroup = false;
	TArray<TPair<int32, TArray<FString>>> Drops;   // weight, item sets
};

struct FCoHAward { int32 XP = 0, Influence = 0; bool bItems = false; };

/** kit.json: a villain's presentation and moves. */
struct FCoHKitPower
{
	FName Power;
	FCoHPowerAnim Anim;
};
struct FCoHKitVillain
{
	FString Name, Group, Rank, Class, AIConfig, SeqType;
	TArray<FString> Costumes;
	TArray<FString> Models;                       // costumes with an exported model
	TArray<FCoHKitPower> Powers;
	TMap<FString, TArray<FString>> AnimLists;     // anim list -> its move chain (clip names)
	TMap<FString, TArray<FString>> BehaviorLists; // idle behavior (<<PL_SprayPaint>>) -> anim lists
	/** Moves of an idle behavior (the first anim list it plays), or empty. */
	const TArray<FString>* IdleMoves(const FString& Behavior) const;
};

/** encounters.json: one actor slot of a spawn definition. */
struct FCoHEncounterActor
{
	FString Group, Rank, Villain;     // Villain set: a named villain
	int32 Count = 1, MinHeroes = 1, MaxHeroes = 8;
	FString AIInactive, AIActive;
	TMap<int32, TArray<FString>> Rolls;   // level -> villains that slot can roll
};
struct FCoHEncounter
{
	FString Name, Kind;
	int32 MinLevel = 1, MaxLevel = 1, MinTeam = 1, MaxTeam = 8, Spots = 1;
	float Respawn = 300;
	TArray<FCoHEncounterActor> Actors;
	TArray<FString> Groups() const;
};

UCLASS(Config = Game)
class COHREBORN_API UCoHGameRules : public UGameInstanceSubsystem
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	static UCoHGameRules* Get(const UObject* WorldContext);

	/** power_anims.json (player powers). Default: <RulesDir>/../powers. */
	UPROPERTY(Config) FString PowerAnimsFile;
	/** hero_rules.json and rewards.json. Default: the powers RulesDir. */
	UPROPERTY(Config) FString HeroRulesDir;
	/** kit.json, encounters.json, enemy_power_anims.json. */
	UPROPERTY(Config) FString EnemyDir;
	/** Hero files (format 2). */
	UPROPERTY(Config) FString HeroesDir;
	/** Imported clips: <AnimRoot>/<body>/<clip>. */
	UPROPERTY(Config) FString PlayerAnimRoot = TEXT("/Game/CoH/Player/Anims");
	/** Imported player-body presets: <PresetRoot>/<body>/<preset>/... */
	UPROPERTY(Config) FString PresetRoot = TEXT("/Game/CoH/Player/Presets");
	/** Imported villain models: <EnemyRoot>/<costume>/... */
	UPROPERTY(Config) FString EnemyRoot = TEXT("/Game/CoH/Enemies");

	// --- power animations ---------------------------------------------------
	const FCoHPowerAnim* PowerAnim(FName Power) const;
	/** The move chain of a power for a body: AttackBits, or ActivationBits for
	 *  toggles and self powers, or HitBits for the victim. */
	bool Segments(const FCoHPowerAnim& A, const FString& Body, const FString& Bits, TArray<FCoHAnimSegment>& Out) const;
	/** A villain's move chain: each move is its own clip on the villain's model
	 *  (<EnemyRoot>/<model>/<move>). Bits: AttackBits, HitBits ... */
	bool VillainSegments(const FCoHKitVillain& V, const FString& Model, const FCoHPowerAnim& A, const FString& Bits, TArray<FCoHAnimSegment>& Out) const;
	/** Clips for a list of move names on a villain model. */
	bool MoveSegments(const FString& Model, const TArray<FString>& Moves, TArray<FCoHAnimSegment>& Out) const;
	/** A clip of the player library: "male/energy_rapid" on body "fem". */
	UAnimSequenceBase* PlayerClip(const FString& Body, const FString& Anim) const;
	/** Any clip under a folder by (case-insensitive) asset name. */
	UAnimSequenceBase* ClipIn(const FString& Folder, const FString& Name) const;
	/** The skeletal mesh of an imported preset (Model_Positron), and its body. */
	class USkeletalMesh* PresetMesh(const FString& Preset, FString& OutBody) const;

	// --- hero build ---------------------------------------------------------
	bool HasHeroRules() const { return Classes.Num() > 0; }
	const FCoHRuleClass* RuleClass(const FString& Class) const;
	bool Requires(const TArray<FString>& Expr, const FCoHHeroRecord& Hero, const TSet<FString>& Owned) const;
	TArray<FName> AutoPowers(const FCoHHeroRecord& Hero) const;
	TSet<FString> Owned(const FCoHHeroRecord& Hero) const;
	TArray<FString> HeroSets(const FCoHHeroRecord& Hero) const;
	/** Why the hero cannot take Power as a pick made at AtLevel after the
	 *  first NumPrior picks; empty when it can. */
	FString CanPick(const FCoHHeroRecord& Hero, FName Power, int32 AtLevel, int32 NumPrior) const;
	/** What the next pick may take (empty: no pick open). */
	TArray<FName> Options(const FCoHHeroRecord& Hero) const;
	int32 PicksAllowed(int32 Level) const;
	int32 PickLevel(int32 Index) const;
	FCoHHeroRecord NewHero(const FString& Class, const FString& Primary, const FString& Secondary, const FString& First, const FString& Name, const FString& Preset) const;
	bool LoadHero(const FString& File, FCoHHeroRecord& Out) const;
	bool SaveHero(const FString& File, const FCoHHeroRecord& Hero) const;

	// --- leveling -----------------------------------------------------------
	bool HasRewards() const { return XPForLevel.Num() > 0; }
	int32 XPLevel(int32 XP) const;
	int32 XPFor(int32 Level) const { return XPForLevel.IsValidIndex(Level - 1) ? XPForLevel[Level - 1] : 0; }
	/** XP and influence for each member of one team (0-based combat levels). */
	TArray<FCoHAward> Defeat(const FString& Rank, int32 Villain0, const TArray<int32>& Members, float TeamShare, const FString& Group) const;
	/** Applies an award: half pays debt while in debt; at 50 it becomes influence. */
	void GiveXP(FCoHHeroRecord& Hero, int32 Amount) const;
	/** Debt for a defeat by villains; returns the debt added. */
	int32 Defeated(FCoHHeroRecord& Hero, bool bInMission = false) const;
	FIntPoint InspirationTray(int32 Level) const;
	/** Rolls the drop of a defeated villain: an inspiration power or None. */
	FName RollDrop(const FString& Rank, int32 Villain0, const FString& Group) const;
	float KillCreditFeet = 200.f, NoDamageRewardFeet = 300.f;

	// --- enemies ------------------------------------------------------------
	const FCoHKitVillain* Kit(const FString& Villain) const { return Villains.Find(Villain); }
	const FCoHPowerAnim* VillainPowerAnim(const FString& Villain, FName Power) const;
	TArray<FCoHEncounter> Encounters;
	TMap<FString, FCoHKitVillain> Villains;

private:
	void LoadPowerAnims(const FString& File, TMap<FName, FCoHPowerAnim>& Into);
	void LoadHeroRules(const FString& File);
	void LoadRewards(const FString& File);
	void LoadEnemies(const FString& Dir);
	void IndexClips(const FString& Root) const;
	const FCoHRuleSet* Set(const FString& Id) const;
	FString Kind(const FCoHHeroRecord& Hero, const FString& SetId) const;
	TArray<FCoHRewardSet> SetsFor(const FString& Rank, int32 Level0, const FString& Group) const;
	TPair<int32, int32> TableXP(const FString& Rank, int32 Level0, const FString& Group) const;
	TPair<float, float> Cap(const FString& Rank, int32 Exp0, const FString& Group) const;
	float LevelBonus(int32 Hero0, int32 Villain0) const;

	TMap<FName, FCoHPowerAnim> PowerAnims;
	mutable TMap<FString, TMap<FString, FSoftObjectPath>> ClipIndex;   // folder -> lower name -> clip
	TArray<FCoHRuleClass> Classes;
	TMap<FString, FCoHRuleSet> Sets;
	TMap<FString, FString> SetCI;      // lower id -> id
	TMap<FString, FName> PowerCI;      // lower id -> power
	TMap<FString, const FCoHRulePower*> PowerRule;
	TArray<FString> PoolSets, EpicSets, Origins;
	TArray<int32> SchedPicks, SchedPools, SchedEpics, XPForLevel, DefeatPenalty, InspCols, InspRows;
	TArray<float> BonusAbove, BonusBelow;
	TMap<int32, float> TeamBonus;
	TMap<FString, int32> ConAdjust;
	TMap<FString, TMap<int32, TArray<FCoHRewardSet>>> Tables;
	TMap<FString, TArray<TPair<int32, FString>>> ItemSets;   // weighted items (kind.item)
	int32 XPCapLevels = 4, NoItemsAbove = 3, DebtCapPenalties = 5;
};

// City of Heroes power system, driven by the original Issue 24 data.
//
// tools/powers/export_powers.py turns the game's defs into JSON
// (Content/CoH/Data/Powers): archetypes with their per-level tables, power
// sets and 2,600+ powers with their attrib mods. UCoHPowerDatabase loads it
// once; UCoHPowerComponent gives any character (hero or enemy) health,
// endurance, defence, resistance, a power tray and recharge timers, and
// runs a power: endurance, to-hit roll, damage / heals / buffs / holds /
// knockback from the mods, area (single, sphere, cone, location), toggles
// and auto powers. The server decides every outcome; clients get the
// animation and effects through a multicast.
//
// Presentation is separate from the numbers so heroes can restyle powers:
// an FCoHPowerStyle (animation, emitter point, colour) picks how a power
// looks without changing what it does.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "CoHPowers.generated.h"

class UAnimSequenceBase;
class UTexture2D;

/** Travel powers every hero has (the tray's inherent powers). Climb is ours: the original game had none. */
namespace CoHTravel
{
	const FName Sprint(TEXT("Inherent.Inherent.Sprint"));
	const FName Climb(TEXT("Inherent.Inherent.Climb"));
}

UENUM(BlueprintType)
enum class ECoHDamage : uint8 { Smashing, Lethal, Fire, Cold, Energy, NegativeEnergy, Psionic, Toxic, Count };

UENUM(BlueprintType)
enum class ECoHEmitter : uint8 { RightHand, LeftHand, BothHands, Eyes, Chest, Mouth, Feet, Back, Overhead };

struct FCoHMod
{
	FString Attrib;         // kFire, kHeld, kRes...
	FString Aspect;         // kAbs, kCur, kRes, kStr
	FString Table;
	FString Target;         // kTarget / kSelf
	bool bDuration = false; // Type kDuration: duration from the table, magnitude fixed
	float Scale = 0, Magnitude = 1, Duration = 0, Delay = 0, Period = 0, Chance = 1;
	int32 Requires = 0;     // 0 any, 1 only critters, 2 only players, -1 never (other conditions)
};

struct FCoHPowerDef
{
	FName Id;
	FString Display, Short, Help, Icon, SetId, Category;
	FString Type;           // kClick, kToggle, kAuto
	FString Area;           // kCharacter, kSphere, kCone, kLocation
	FString Target;         // kFoe, kCaster, kFriend, kLocation
	FString Affects;        // kFoe, kFriend, kCaster
	TArray<FString> AttackTypes;
	float Accuracy = 1, Range = 0, Radius = 0, Arc = 0, EndCost = 0, Activate = 1, Recharge = 1, Period = 0;
	int32 MaxTargets = 0;
	TArray<FCoHMod> Mods;
	TArray<FString> AIGroups;   // how villain AI uses it: kBuff, kHealSelf, kHealAlly, kDebuff...
	bool IsMelee() const;
	bool IsHostile() const { return Target == TEXT("kFoe") || Affects == TEXT("kFoe"); }
};

struct FCoHPowerSetDef
{
	FString Id, Category, Display, Icon;
	TArray<TPair<FName, int32>> Powers;   // power id, level available
};

/** A villain from defs/villains: rank class and its powers. */
struct FCoHVillainDef
{
	FString Name, Class, Rank, Group, AIConfig;
	TArray<FName> Powers;     // expanded power ids (auto powers included)
	TMap<int32, TArray<FString>> Costumes;   // by level: the original costume (mesh) names
	/** Costumes for a level (the nearest level listed). */
	const TArray<FString>* CostumesAt(int32 Level) const;
};

/** A villain AI config from aiscript/config (inheritance resolved). Distances in feet. */
struct FCoHAIConfig
{
	bool bPreferMelee = false, bPreferRanged = false, bDoNotMove = false, bIgnoreFriendsAttacked = false;
	float MeleeScale = 1, RangedScale = 1;
	float ShoutChance = 50, ShoutRadius = 30;
	float FOVDegrees = 240, Standoff = 10;
	float GriefHPRatio = 0.7f, GriefTimeBegin = 10, GriefTimeEnd = 30, Fear = 0.2f;
	float ProtectSpawnRadius = 100, ProtectSpawnOutsideRadius = 20, ProtectSpawnTime = 30, EventMemoryDuration = 20;
	FString Brain;
};

/** Idle routine from behavior_aliases (Loiter, Wander...): stand for a
 *  while, then walk to a random spot near home for a while, repeating. */
struct FCoHIdleRecipe
{
	float StandMin = 10, StandMax = 20;   // seconds
	float Radius = 40;                    // feet around home
	float WalkMin = 2, WalkMax = 5;       // seconds
	FString StandAnim;                    // original anim list name (Observer, Lookout...)
};

/** A set the test hero owns (hero_all_sets.json). */
struct FCoHHeroSet
{
	FString Id, Category, Name, Element;
	TArray<FName> Powers;
};

struct FCoHClassDef
{
	FString Name, Display, Primary, Secondary;
	TMap<FString, float> Base;
	TArray<float> HitPoints, Endurance;
	TMap<FString, TArray<float>> Tables;  // lower-case name
	float TableValue(const FString& Table, int32 Level) const;
};

/** The rules: loads the JSON written by tools/rules/coh_rules.py (export,
 *  catalog, testhero) from RulesDir once per game instance: class tables,
 *  combat mods, powers, power sets, villains and the test hero's sets. The
 *  data is derived from the game files and stays outside git. */
UCLASS(Config = Game)
class COHREBORN_API UCoHPowerDatabase : public UGameInstanceSubsystem
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	static UCoHPowerDatabase* Get(const UObject* WorldContext);

	const FCoHPowerDef* FindPower(FName Id) const { return Powers.Find(Id); }
	const FCoHClassDef* FindClass(const FString& Name) const;
	/** Archetype whose primary or secondary is this category (for tables). */
	const FCoHClassDef* ClassForCategory(const FString& Category) const;
	UTexture2D* Icon(const FString& IconName);

	TArray<FCoHClassDef> Archetypes;
	TArray<FCoHPowerSetDef> PowerSets;
	TMap<FName, FCoHPowerDef> Powers;
	TArray<FCoHClassDef> Critters;
	TMap<FString, FCoHVillainDef> Villains;
	TMap<FString, FCoHAIConfig> AIConfigs;
	const FCoHAIConfig& AIConfig(const FString& Name) const;
	TMap<FString, FCoHIdleRecipe> IdleRecipes;
	const FCoHIdleRecipe& IdleRecipe(const FString& Name) const;
	TArray<FCoHHeroSet> HeroSets;
	/** combat_mods.def: to-hit multipliers by level difference (index =
	 *  levels apart) when the target is higher / lower than the attacker. */
	TArray<float> ToHitHigher, ToHitLower;
	float LevelToHit(int32 AttackerLevel, int32 TargetLevel) const;

	/** Folder with classes.json, powers.json, powersets.json, villains.json,
	 *  combat_mods.json and hero_all_sets.json. */
	UPROPERTY(Config) FString RulesDir;
private:
	/** Icons load from the original PNGs (Content/CoH/Data/Icons/*.cohicon). */
	UPROPERTY() TMap<FString, TObjectPtr<UTexture2D>> IconCache;
};

/** How a power looks: chosen per hero, never changes the numbers. */
USTRUCT(BlueprintType)
struct FCoHPowerStyle
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite) ECoHEmitter Emitter = ECoHEmitter::RightHand;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 Animation = -1;   // -1: default for the power type
	/** A specific clip (any animation on the hero's skeleton); overrides Animation. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FSoftObjectPath Clip;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FLinearColor Tint = FLinearColor(0, 0, 0, 0); // alpha 0: element colour / the effects' own colours
	/** The second power colour (alpha 0: the effects' own). Tint is the first. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FLinearColor Tint2 = FLinearColor(0, 0, 0, 0);
	/** True once the hero picked Emitter: the original cast point is replaced. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bCustomEmitter = false;
	/** Entry of the power's customizable themes (Bright Fire ...), -1 the default effects. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 Theme = -1;
	/** A point the hero clicked on the body: the nearest bone and the offset from it in cm
	 *  (actor axes: x forward, y right, z up). Replaces the Emitter preset for the effects;
	 *  Emitter then only picks the pose. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bCustomPoint = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName PointBone;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FVector PointOffset = FVector::ZeroVector;
};

USTRUCT()
struct FCoHRecharge
{
	GENERATED_BODY()
	UPROPERTY() FName Power;
	UPROPERTY() float ReadyAt = 0;      // server world time
};

USTRUCT()
struct FCoHBuff
{
	GENERATED_BODY()
	FString Attrib, Aspect;
	float Value = 0, Until = 0;
	FName Source;
};

DECLARE_MULTICAST_DELEGATE_ThreeParams(FCoHCombatText, AActor* /*Who*/, const FString& /*Text*/, FLinearColor /*Colour*/);

UCLASS(ClassGroup = CoH, meta = (BlueprintSpawnableComponent))
class COHREBORN_API UCoHPowerComponent : public UActorComponent
{
	GENERATED_BODY()
public:
	UCoHPowerComponent();

	/** Archetype or critter class name (Class_Blaster, Class_Minion_Grunt...). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "CoH|Powers") FString ClassName = TEXT("Class_Blaster");
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "CoH|Powers") int32 Level = 10;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CoH|Powers") bool bPlayerSide = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "CoH|Powers") FString DisplayName;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Replicated, Category = "CoH|Powers") float Health = 100;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Replicated, Category = "CoH|Powers") float MaxHealth = 100;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Replicated, Category = "CoH|Powers") float Endurance = 100;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Replicated, Category = "CoH|Powers") float MaxEndurance = 100;

	/** Tray slots (power ids; None = empty). Owner only. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "CoH|Powers") TArray<FName> Tray;
	UPROPERTY(Replicated) TArray<FCoHRecharge> Recharges;
	/** Powers the character owns (a built hero: picks and auto powers). Auto
	 *  powers here run all the time, on the tray or not. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "CoH|Powers") TArray<FName> Owned;
	/** Body for the original moves: male, fem, huge, or a villain's sequencer type. Empty: no original moves. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "CoH|Powers") FString Body;
	/** Damage taken from each attacker, for the defeat rewards (server). */
	TMap<TWeakObjectPtr<AActor>, float> DamageBy;
	/** Server: a power used outside the tray and its timers (inspirations). */
	void UseFreePower(FName Power);
	/** Seconds from the start of a power to its hit on a target this far away
	 *  (the original FramesBeforeHit, plus the projectile's flight). */
	float HitDelay(FName Power, float DistanceCm) const;
	UPROPERTY(Replicated) TArray<FName> ActiveToggles;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CoH|Powers") TMap<FName, FCoHPowerStyle> Styles;

	/** Owner: current target (sent with each activation). */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "CoH|Powers") TWeakObjectPtr<AActor> Target;

	// --- use ---------------------------------------------------------------
	/** Local: activate the power in this tray slot. */
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void ActivateSlot(int32 Slot);
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void ActivatePower(FName Power);
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void SetTargetActor(AActor* NewTarget) { Target = NewTarget; }
	UFUNCTION(BlueprintPure, Category = "CoH|Powers") AActor* GetTargetActor() const { return Target.Get(); }
	/** Auto-attack lock (Ctrl + number, as in the original game): the locked
	 *  power fires whenever it is ready and the target is valid and in range.
	 *  One lock at a time; locking another power moves it; the same slot again
	 *  turns it off. It ends when the target is defeated or leaves range. */
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void ToggleAutoSlot(int32 Slot);
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void StopAuto(const FString& Why);
	UPROPERTY(Transient, BlueprintReadOnly, Category = "CoH|Powers") FName AutoPower;
	/** Presentation: play this clip for the power (asset path, or just the
	 *  clip name, e.g. "MM_Attack_02"); empty = the default for its type. */
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") bool SetPowerAnimation(FName Power, const FString& ClipNameOrPath);
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void SetPowerEmitter(FName Power, ECoHEmitter Emitter);
	/** The two power colours (alpha < 1 on Primary: back to the effects' own colours). */
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void SetPowerColors(FName Power, FLinearColor Primary, FLinearColor Secondary);
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void SetPowerTheme(FName Power, int32 Theme);
	/** Casts from a clicked point of the body: Bone plus Offset (cm, actor axes); Pose is the ECoHEmitter whose move fits the region. */
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void SetPowerPoint(FName Power, FName Bone, FVector Offset, ECoHEmitter Pose);
	/** Back to the power's original look (emitter, colours, theme; the clip stays). */
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void ResetPowerLook(FName Power);
	/** Plays the power here, locally, against a dummy 30 ft ahead, with the hero's style: the
	 *  customize preview. No numbers run (no damage, endurance or recharge). */
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void PreviewPower(FName Power);
	/** Finds an animation asset by name (any folder) or path. */
	static FSoftObjectPath FindClip(const FString& NameOrPath);
	UFUNCTION(Server, Reliable) void ServerActivate(FName Power, AActor* TargetActor, FVector_NetQuantize Location);
	UFUNCTION(Server, Reliable) void ServerSetTray(int32 Slot, FName Power);
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void SetTray(int32 Slot, FName Power);

	// --- state -------------------------------------------------------------
	UFUNCTION(BlueprintPure, Category = "CoH|Powers") float RechargeLeft(FName Power) const;
	float RechargeTotal(FName Power) const;
	bool IsToggleOn(FName Power) const { return ActiveToggles.Contains(Power); }
	UFUNCTION(BlueprintPure, Category = "CoH|Powers") bool IsDefeated() const { return Health <= 0.f; }
	/** Reputation (vigilante) / notoriety (hero), 0..1: makes villains break sooner. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "CoH|Powers") float Reputation = 0.f;
	/** Times this character has been defeated (villains forget a hero who went down). */
	int32 Defeats = 0;
	bool IsMezzed() const;
	float Resistance(ECoHDamage Type) const;
	float Defense(bool bMelee) const;
	FString MezName() const;

	/** Damage from outside the power system (brawl, enemy swings). */
	float ApplyDamage(float Amount, ECoHDamage Type, AActor* Causer);
	void Heal(float Amount);
	void Reset();
	/** Server: max HP / endurance from the class tables at Level, then full. */
	void InitStats();
	/** Server: switch class / level (the creator, tests). */
	UFUNCTION(BlueprintCallable, Category = "CoH|Powers") void SetClassAndLevel(const FString& InClass, int32 InLevel);
	/** HP and endurance restored per second (class base x buffs). */
	UFUNCTION(BlueprintPure, Category = "CoH|Powers") float RegenPerSecond() const;
	UFUNCTION(BlueprintPure, Category = "CoH|Powers") float RecoveryPerSecond() const;
	/** Chance to hit of the last roll this character made (for tests and the combat log). */
	UPROPERTY(BlueprintReadOnly, Category = "CoH|Powers") float LastHitChance = 0.f;
	float BaseAttrib(const TCHAR* Name, float Default) const;
	static UCoHPowerComponent* Of(const AActor* A);
	static FLinearColor DamageColour(ECoHDamage Type);
	/** Con colour of Other's level as seen from this level. */
	static FLinearColor ConColour(int32 MyLevel, int32 TheirLevel);

	static FCoHCombatText OnCombatText;

	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const override;

	UFUNCTION(NetMulticast, Unreliable) void MulticastPlay(FName Power, AActor* TargetActor, FVector_NetQuantize Location, uint8 Hits);
	UFUNCTION(NetMulticast, Unreliable) void MulticastText(const FString& Text, FLinearColor Colour);
	/** Everyone: play a hit reaction on this character. */
	UFUNCTION(NetMulticast, Unreliable) void MulticastHurt(float Amount);

private:
	void Execute(const FCoHPowerDef& P, AActor* TargetActor, FVector Location);
	void Release(FName Power, TWeakObjectPtr<AActor> TargetActor, FVector Location);
	void ApplyMods(const FCoHPowerDef& P, UCoHPowerComponent* Victim, bool bSelf, float DurationOverride);
	void ApplyMod(const FCoHPowerDef& P, const FCoHMod& M, UCoHPowerComponent* Victim, float DurationOverride);
	TArray<UCoHPowerComponent*> Gather(const FCoHPowerDef& P, AActor* TargetActor, FVector Center) const;
	bool IsFoe(const UCoHPowerComponent* Other) const { return Other && Other->bPlayerSide != bPlayerSide; }
	float BuffSum(const FString& Attrib, const FString& Aspect) const;
	void ToggleTick(const FCoHPowerDef& P);
	void PlayLocal(const FCoHPowerDef& P, AActor* TargetActor, FVector Location, uint8 Hits);
	const FCoHClassDef* Class() const;

	TArray<FCoHBuff> Buffs;
	float MezUntil = 0;
	FString Mez;
	float NextToggleTick = 0;
	float BusyUntil = 0;
	float LastHurt = -100;
	// auto-attack lock (owning client)
	void TickAutoAttack();
	void LocalText(const FString& Text) const;
	TWeakObjectPtr<AActor> AutoTarget;
	float NextAutoTry = 0;
};

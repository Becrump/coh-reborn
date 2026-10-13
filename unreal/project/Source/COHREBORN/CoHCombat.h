#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/Actor.h"
#include "CoHCombat.generated.h"
class UAnimSequence;
class USkeletalMesh;
class AAIController;
class UCoHPowerComponent;
UENUM(BlueprintType)
enum class ECoHEnemyState : uint8 { Idle, Chase, Attack, Hit, ReturnHome, Dead };
/** Runtime combat pawn. Original encounter actors remain editable layout previews. */
UCLASS()
class COHREBORN_API ACoHCombatEnemy : public ACharacter
{
 GENERATED_BODY()
 friend class ACoHEnemySpawner;
public:
 ACoHCombatEnemy();
 void InitializeFromPreview(AActor* Preview, const TMap<FString,FString>& Clips);
 virtual void BeginPlay() override;
 virtual void Tick(float DeltaSeconds) override;
 virtual float TakeDamage(float Damage, const FDamageEvent& Event, AController* EventInstigator, AActor* Causer) override;
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Combat") ECoHEnemyState State = ECoHEnemyState::Idle;
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Combat") float Health = 100.f;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") float AggroRange = 1500.f;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") float LeashRange = 2400.f;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") float AttackRange = 160.f;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") float AttackDamage = 8.f;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") float AttackCooldown = 1.6f;
 UFUNCTION(BlueprintCallable, Category="CoH|Combat")
 void LaunchRagdoll(FVector LaunchVelocity);
 UFUNCTION(BlueprintCallable, Category="CoH|Combat")
 static bool EnsureRagdollPhysics(USkeletalMesh* BodyMesh);
 bool IsDead() const { return State == ECoHEnemyState::Dead; }
 FVector Home;
 /** Health, defence and powers come from the original critter class tables. */
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Combat") TObjectPtr<UCoHPowerComponent> Powers;
 /** Set up from the enemy catalog (mesh + idle/run/attack/hit/death clips). */
 void InitializeFromCatalog(const TMap<FString,FString>& Entry, const FString& Faction, const FString& RankClass, int32 InLevel);
 /** Use a villain definition from the rules (class, rank, powers). Auto
  *  powers (inherent resistances...) run all the time; click powers are its attacks. */
 void ApplyVillain(const FString& VillainName, int32 InLevel);
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Combat") FString Villain;
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Combat") TArray<FName> Attacks;
 // power system hooks (server)
 void OnHurt(AActor* Causer, float Damage = 0.f);
 /** Taunt: attack this pawn for Seconds whatever else is going on. */
 void Taunt(APawn* Who, float Seconds);
 /** A group mate or someone nearby called for help against Who. */
 void Alert(APawn* Who);
 /** Spawn group (members share aggro when one is attacked). */
 int32 GroupId = INDEX_NONE;
 /** AI config name from the villain definition (aiscript/config). */
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Combat") FString AIConfigName;
 /** Idle routine from behavior_aliases: Loiter (stand 10-20 s, stroll
  *  within 40 ft for 2-5 s) or Wander (same timings, lookout stance). */
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") FString IdleBehavior = TEXT("Loiter");
 /** Rank from the villain definition (Minion, Lieutenant, Boss...). */
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Combat") FString Rank;
 /** Villain group (Hellions, Skulls...): only the same group answers a call for help. */
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Combat") FString Faction;
 /** What the brain is doing, for tests and debugging. */
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Combat") FString Thought;
 void OnDefeated(AActor* Causer);
 void OnMezzed(float Seconds);
 void Aggro(APawn* Who);
 void PlayAttackAnimation();
 /** Wander: the group moves its home around now and then. */
 void SetHome(const FVector& NewHome) { Home = NewHome; }
 /** Morale (for later): would this villain break and scatter against Hero?
  *  Chance from the level gap (5% per level above the villain's +2,
  *  bosses steadier) plus the hero's reputation / notoriety (0..1). Rolls
  *  a random number; the server setting bMorale can turn it off. */
 UFUNCTION(BlueprintCallable, Category="CoH|Combat") bool ShouldScatter(APawn* Hero) const;
 void FinishReaction();
 UFUNCTION(BlueprintPure, Category="CoH|Combat") float ScatterChance(APawn* Hero) const;
 /** Harassment role while the gang holds a civilian: 1 grabs, 2 threatens. */
 int32 HarassRole = 0;
 /** Mesh turn relative to the capsule (preview-placed enemies: 180, rules villains: 90). */
 float MeshYaw = 180.f;
 bool bHarassPosed = false;
 FVector HarassSpot = FVector::ZeroVector;
 /** Fighting, helping or walking home: the spawner leaves it alone. */
 bool IsBusy() const { return Target != nullptr || bReturning; }
 /** Walk somewhere; with no nav mesh on the way (it is only built near
  *  players and groups) head straight there until it can path again. */
 void GoTo(const FVector& Where, float Acceptance);
 void GoToActor(AActor* Who, float Acceptance);
private:
 void SetState(ECoHEnemyState Next);
 void BindPowers();
 FName PickAttack(float Distance, float& OutReach) const;
 bool Think(float Delta, class AAIController* AI);
 APawn* ChooseTarget();
 void Shout(APawn* Who);
 bool UseSupportPower(const TCHAR* Group);
 TMap<TWeakObjectPtr<APawn>, float> Threat;
 TMap<TWeakObjectPtr<APawn>, double> LastEvent;     // event memory: last seen / hurt by
 TMap<TWeakObjectPtr<APawn>, int32> DefeatsSeen;    // a hero who went down since is forgotten
 void Idle(class AAIController* AI, double Now);
 bool Harass(class AAIController* AI, double Now);
 void CallForHelp(APawn* Who, float RadiusFeet);
 double IdleUntil = 0, ProtectUntil = 0;
 bool bIdleWalking = false, bCalledHelp = false, bReturning = false, bHelping = false;
 FName LastAttack;
 TWeakObjectPtr<APawn> TauntedBy;
 double TauntUntil = 0, FleeUntil = 0, NextSupportTime = 0;
 bool bFled = false, bBuffed = false;
 bool CanSee(APawn* Pawn) const;
 void LandAttack();
 UPROPERTY(Transient) TObjectPtr<APawn> Target;
public:
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") TObjectPtr<UAnimSequence> IdleClip;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") TObjectPtr<UAnimSequence> RunClip;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") TObjectPtr<UAnimSequence> AttackClip;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") TObjectPtr<UAnimSequence> HitClip;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat") TObjectPtr<UAnimSequence> DeathClip;
private:
 void RecoverRagdoll();
 bool bRagdoll = false;
 double RagdollStarted = 0;
 FTimerHandle RagdollTimer;
 FTimerHandle AttackTimer, ReactionTimer;
 double NextAttackTime = 0;
 double NextPathTime = 0;
};
/** Activates a bounded number of nearby candidates; never runs thousands of combat pawns. */
UCLASS()
class COHREBORN_API ACoHCombatDirector : public AActor
{
 GENERATED_BODY()
public:
 ACoHCombatDirector();
 virtual void BeginPlay() override;
 virtual void Tick(float DeltaSeconds) override;
 virtual void EndPlay(const EEndPlayReason::Type Reason) override;
 UPROPERTY(EditAnywhere, Category="CoH|Combat") float ActivationRadius = 2400.f;
 UPROPERTY(EditAnywhere, Category="CoH|Combat") int32 MaxActiveEnemies = 16;
 UPROPERTY(EditAnywhere, Category="CoH|Combat") FString CatalogRelativePath = TEXT("CoH/Data/enemy_combat.json");
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Combat") int32 ActiveCount = 0;
private:
 TMap<FString,TMap<FString,FString>> Catalog;
 TMap<TWeakObjectPtr<AActor>,TWeakObjectPtr<ACoHCombatEnemy>> Active;
 TSet<TWeakObjectPtr<AActor>> Defeated;
};

/** Keeps wandering groups of original-faction villains around the players:
 *  picks reachable spots on the nav mesh in a ring around a player, spawns
 *  3-5 of one faction there (minions, a lieutenant, sometimes a boss) at
 *  levels near the player's, lets the group drift around, and removes
 *  groups that are defeated or left far behind. */
UCLASS(Config = Game)
class COHREBORN_API ACoHEnemySpawner : public AActor
{
 GENERATED_BODY()
public:
 ACoHEnemySpawner();
 virtual void BeginPlay() override;
 virtual void Tick(float DeltaSeconds) override;
 virtual void EndPlay(const EEndPlayReason::Type Reason) override;
 UPROPERTY(EditAnywhere, Config, Category="CoH|Spawning") int32 MaxGroups = 16;
 /** Server setting: wandering villain gangs on or off (DefaultGame.ini). */
 UPROPERTY(EditAnywhere, Config, Category="CoH|Spawning") bool bWanderingGangs = true;
 /** Server setting: idle gangs grab and threaten a passing civilian. */
 UPROPERTY(EditAnywhere, Config, Category="CoH|Spawning") bool bCivilianHarassment = true;
 /** Server setting: villains may break and scatter (ShouldScatter). */
 UPROPERTY(EditAnywhere, Config, Category="CoH|Spawning") bool bMorale = true;
 static bool bMoraleOn;
 /** Groups kept alive per player online (capped by MaxGroups: 16 is enough for about 7 players). */
 UPROPERTY(EditAnywhere, Config, Category="CoH|Spawning") int32 GroupsPerPlayer = 3;
 /** No spawning or wandering destinations inside these circles: X, Y and radius (Z), cm. Default: City Hall plaza. */
 UPROPERTY(EditAnywhere, Config, Category="CoH|Spawning") TArray<FVector> NoSpawnZones = { FVector(3900.f, 20100.f, 7500.f) };
 static TArray<FVector> NoSpawn;
 UPROPERTY(EditAnywhere, Category="CoH|Spawning") float MinDistance = 3500.f;
 UPROPERTY(EditAnywhere, Category="CoH|Spawning") float MaxDistance = 11000.f;
 UPROPERTY(EditAnywhere, Category="CoH|Spawning") float DespawnDistance = 22000.f;
 /** Factions to use (folders of the catalog) and their weights. */
 UPROPERTY(EditAnywhere, Category="CoH|Spawning") TMap<FString,float> Factions;
 /** Levels relative to the nearest player's. */
 UPROPERTY(EditAnywhere, Category="CoH|Spawning") int32 LevelBelow = 2;
 UPROPERTY(EditAnywhere, Category="CoH|Spawning") int32 LevelAbove = 1;
 UPROPERTY(EditAnywhere, Category="CoH|Spawning") FString CatalogRelativePath = TEXT("CoH/Data/enemies.cohdata");
 UPROPERTY(VisibleAnywhere, Category="CoH|Spawning") int32 AliveGroups = 0;
 /** Tests: spawn one named villain (e.g. Hellions_Brawl_Thug) at a level, Distance cm in front of Near. */
 UFUNCTION(BlueprintCallable, Category="CoH|Spawning") ACoHCombatEnemy* SpawnVillainNear(const FString& VillainName, int32 Level, APawn* Near, float Distance = 1200.f);
 /** Tests: stop spawning groups (and clear the ones alive). */
 UFUNCTION(BlueprintCallable, Category="CoH|Spawning") void SetSpawning(bool bOn);
 /** Tests: spawn one group of a faction at a level, Distance cm from Near. */
 UFUNCTION(BlueprintCallable, Category="CoH|Spawning") bool SpawnTestGroup(APawn* Near, const FString& Faction, int32 Level, float Distance = 2000.f) { return SpawnGroup(Near, Faction, Level, Distance); }
 UPROPERTY(EditAnywhere, Category="CoH|Spawning") bool bSpawning = true;
private:
 struct FGroup
 {
  FString Faction; FVector Center; TArray<TWeakObjectPtr<ACoHCombatEnemy>> Members; double NextWander = 0;
  int32 Id = 0;
  int32 Victim = INDEX_NONE;    // civilian held (life manager index)
  double HarassUntil = 0, NextHarass = 0;
  bool bHolding = false;
 };
 TArray<FGroup> Groups;
 TMap<FString,TArray<TMap<FString,FString>>> Catalog;
 double NextSpawn = 0;
 int32 NextGroupId = 1;
 bool SpawnGroup(APawn* Near, const FString& ForceFaction = FString(), int32 ForceLevel = 0, float ForceDistance = 0.f);
 void TickHarassment(double Now);
 const TMap<FString,FString>& BodyFor(const struct FCoHVillainDef* V,int32 Level,const TArray<TMap<FString,FString>>& Members) const;
};

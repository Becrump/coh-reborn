#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "CoHHeroCharacter.generated.h"

class UCameraComponent;
class USpringArmComponent;
class UInputAction;
class UInputMappingContext;
class UCoHPowerComponent;
class UCoHHudWidget;
struct FInputActionValue;

/**
 * Playable hero for testing the zone: third-person camera, run, sprint and
 * jump. Input is built in code (Enhanced Input objects created at startup),
 * so it needs no input assets. Mesh and animation blueprint come from
 * DefaultGame.ini ([/Script/COHREBORN.CoHHeroCharacter]) or the details
 * panel, e.g. the retargeted Iron Vanguard and ABP_Unarmed.
 */
UCLASS(Config = Game)
class COHREBORN_API ACoHHeroCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	ACoHHeroCharacter();

	UPROPERTY(Config, EditAnywhere, Category = "CoH|Hero")
	FSoftObjectPath HeroMesh;

	UPROPERTY(Config, EditAnywhere, Category = "CoH|Hero")
	FSoftClassPath HeroAnimClass;

	/** Turn of the mesh so it faces the capsule's forward (+X): -90 for the
	 *  UE mannequin, 90 for Meshy exports. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Hero")
	float MeshYaw = -90.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Hero")
	float RunSpeed = 600.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Hero")
	float SprintSpeed = 1100.f;

	/** Super Jump (F toggles): jump launch speed, run speed, air control. */
	UPROPERTY(EditAnywhere, Category = "CoH|Travel")
	float SuperJumpVelocity = 2400.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Travel")
	float SuperJumpRunSpeed = 900.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Travel")
	float ClimbSpeed = 350.f;
	/** Climb on: the wall climb is this much faster. */
	UPROPERTY(EditAnywhere, Category = "Climb") float ClimbPowerSpeedScale = 1.4f;
	/** Endurance per second a wall climb costs without the Climb power on (Sprint costs about 0.3). */
	UPROPERTY(EditAnywhere, Category = "Climb") float ClimbFastDrain = 4.f;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Travel")
 float SuperSpeedRunSpeed = 2400.f;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Travel")
 float FlightSpeed = 1200.f;
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Travel")
 bool bFlight = false;
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CoH|Travel")
 bool bSuperSpeed = false;
 UFUNCTION(BlueprintCallable, Category="CoH|Travel")
 void SetFlightEnabled(bool bEnabled);
 UFUNCTION(BlueprintCallable, Category="CoH|Travel")
 void SetSuperSpeedEnabled(bool bEnabled);

	/** Melee power animations (and the scripted brawl combo), in turn. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Brawl")
	TArray<FSoftObjectPath> PunchAnims;

	/** Climbing clips (up, down, left, right), played while on a wall. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Travel")
	TArray<FSoftObjectPath> ClimbAnims;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CoH|Combat")
 float MaxHealth = 100.f;
 UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CoH|Combat")
 float Health = 100.f;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CoH|Combat")
 float BrawlDamage = 25.f;
 virtual float TakeDamage(float Damage, const FDamageEvent& Event, AController* EventInstigator, AActor* Causer) override;
 UFUNCTION(BlueprintCallable, Category="CoH|Brawl")
 void PerformBrawl();
 UFUNCTION(BlueprintCallable, Category="CoH|Combat")
 void PerformUppercut();
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat")
 float UppercutDamage=35.f;
 UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Combat")
 float UppercutLaunchSpeed=1100.f;
 virtual void Tick(float DeltaSeconds) override;
	virtual void Jump() override;
	UFUNCTION(BlueprintCallable, Category="CoH|Settings")
	void ToggleGraphicsMenu();
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	UPROPERTY(Transient)
	TObjectPtr<class UCoHGraphicsMenu> GraphicsMenu;

	/** The hero built by the original rules: archetype, picks, XP, debt. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CoH|Hero")
	TObjectPtr<class UCoHHeroProgress> Progress;

	/** Play as an original player body (a preset from the hero file) with
	 *  the original power moves; false: the mesh above and its anim blueprint. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Hero")
	bool bCoHBody = true;
	/** Hero file (format 2) in the rules' HeroesDir, e.g. Class_Blaster.json. Empty: the test hero. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Hero")
	FString HeroFile;
	/** Continue from <hero>_save.json when it exists. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Hero")
	bool bResumeSave = true;
	/** Mesh turn for the CoH bodies. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Hero")
	float CoHMeshYaw = -90.f;
	/** Body of the preset in use: male, fem, huge (empty: not a CoH body). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CoH|Hero")
	FString CoHBodyType;
	/** Plays a power's original moves (AttackBits, or ActivationBits for
	 *  toggles and self powers) on a CoH body. False: no moves for it. */
	bool PlayPowerMoves(FName Power, bool bActivation);
	/** The generic pose for a cast point (ECoHEmitter value): right / left arm out, both arms out,
	 *  eyes, chest, mouth, feet, back, overhead; the original moves on the hero's body type.
	 *  False: the body has none of its clips. */
	bool PlayEmitterPose(uint8 Emitter, float Duration);
	/** Plays a list of moves (victim hit reactions...). */
	bool PlayMoves(const TArray<struct FCoHAnimSegment>& Segments, float Lock);
	class UCoHBodyAnim* BodyAnim() const;

	/** Powers: health, endurance, tray and the original power data. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CoH|Powers")
	TObjectPtr<UCoHPowerComponent> Powers;

	/** Test hero: archetype tables, level and the powers on the tray at start
	 *  (any power can be added from the Power Browser, P). */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Powers")
	FString TestArchetype = TEXT("Class_Blaster");
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Powers")
	int32 TestLevel = 10;
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Powers")
	TArray<FName> StartTray;
	/** Power animations: ranged (thrust), area (charged slam). */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Powers")
	TArray<FSoftObjectPath> RangedAnims;
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Powers")
	TArray<FSoftObjectPath> AreaAnims;
	/** Targeted area powers (Fire Ball, Rain of Fire): a throw. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Powers")
	TArray<FSoftObjectPath> ThrowAnims;
	/** Self and ally powers (buffs, heals, toggles); empty = no body animation. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Powers")
	TArray<FSoftObjectPath> SelfAnims;
	/** Flinch when hurt: the first clip is the heavy one (a big hit). */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Combat")
	TArray<FSoftObjectPath> HitReactAnims;
	/** Everyone: flinch (skipped while a power animation, climb or flight runs). */
	void PlayHitReaction(float Amount);

	/** Plays the animation for a power: Kind 0 melee, 1 ranged, 2 area
	 *  around the hero, 3 thrown area, 4 self or ally. */
	void PlayPowerAnimation(int32 Kind, float Duration, int32 AnimIndex, const FSoftObjectPath& Clip = FSoftObjectPath());
	/** Animation test bench: play any clip on the hero now. */
	UFUNCTION(BlueprintCallable, Category = "CoH|Animation") bool PreviewAnimation(const FString& ClipNameOrPath);
	/** Where the effect should leave a clip: a notify named CoHRelease (or
	 *  Release / Fire / Hit), else 45% of the clip. Seconds from the start. */
	static float ReleaseTime(const class UAnimSequenceBase* Clip, bool* bFromNotify = nullptr);
	void ToggleAnimBench();
	/** Editor tool: add (or move) a socket on a skeleton. Bone-space offset. */
	/** Normal play input, as in the original game: the mouse cursor shows,
	 *  left click selects, hold the right button to turn the camera. */
	static void RestoreGameInput(APlayerController* PC);
	UFUNCTION(BlueprintCallable, Category = "CoH|Animation") static bool AddSkeletonSocket(class USkeleton* Skeleton, FName Socket, FName Bone, FVector Location);
	/** Health reached zero: back to the start point, healed. */
	void OnDefeated();
	/** Tab: the nearest foe in view first, then the next nearest. */
	void CycleTarget();
	/** Left mouse: target whoever is under the cursor / crosshair. */
	void SelectTarget(const FInputActionValue& Value);

	/** Monorail: a rider picked a destination in the train's menu. */
	UFUNCTION(Server, Reliable)
	void ServerChooseMonorailDestination(class ARebornMonorail* Train, int32 Destination);

protected:
	virtual void BeginPlay() override;
	virtual void SetupPlayerInputComponent(UInputComponent* Input) override;

private:
	void Move(const FInputActionValue& Value);
	void Look(const FInputActionValue& Value);
	void CameraDragOn(const FInputActionValue& Value);
	void CameraDragOff(const FInputActionValue& Value);
	bool bCameraDrag = false;
	void SprintOn(const FInputActionValue& Value);
	void ToggleClimbPower();
	bool ClimbPowerOn() const;
	bool SprintPowerOn() const;
	bool bSprintPowerSeen = false, bClimbPowerSeen = false;
	void SprintOff(const FInputActionValue& Value);
	void ToggleSuperJump(const FInputActionValue& Value);
 void ToggleFlight(const FInputActionValue& Value);
 void ToggleSuperSpeed(const FInputActionValue& Value);
 void FlyUp(const FInputActionValue& Value);
 void FlyDown(const FInputActionValue& Value);
	void LetGo(const FInputActionValue& Value);
	void Punch(const FInputActionValue& Value);
	void Zoom(const FInputActionValue& Value);
	void UpdateCamera(float DeltaSeconds);
	void EndPunch();
 void LandPunch();
 void UppercutInput(const FInputActionValue& Value);
 bool bUppercutPunch=false;
 double NextUppercutTime=0;
 FVector RespawnLocation;
 float PunchHitTimeLeft = 0.f;
 bool bPunchLanded = false;
	void RestoreLocomotion();
	void ApplyCoHBody();
	void SetupBodyAnim();
	bool bBodyApplied = false;
	FString BodyPreset;
	void UpdateClimbAnim();
	/** A climb clip of the hero's CoH body (<body>__<name>, tools/anim/climb_clips_unreal.py), or null. */
	class UAnimSequenceBase* BodyClip(const FString& Name) const;
	/** Plays one climb move once (mounting the wall, stepping off); the climb loop resumes after it. */
	void PlayClimbMove(const FString& Name);
	void ApplyMovementMode();
	bool TraceWall(FHitResult& Hit, float Height, float Reach) const;
	void StartClimb(const FVector& Normal);
	void StopClimb();

	bool bSuperJump = false;
	bool bSprint = false;
	bool bClimbing = false;
	FVector WallNormal = FVector::ZeroVector;
	FVector2D MoveInput = FVector2D::ZeroVector;
	float ClimbCooldown = 0.f;
	int32 ComboStep = 0;
	float PunchTimeLeft = 0.f;      // > 0 while a punch plays
	float ComboWindow = 0.f;        // time left to chain the next punch
	bool bQueuedPunch = false;
	int32 ClimbClip = -1;
	float ZoomTarget = 450.f;       // camera distance; 0 = first person
	bool bFirstPerson = false;
	UPROPERTY(Transient)
	TObjectPtr<UClass> LocomotionAnimClass;
	UPROPERTY(Transient) TObjectPtr<UCoHHudWidget> Hud;
	void TogglePowerBrowser();

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<USpringArmComponent> Boom;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(Transient)
	TObjectPtr<UInputMappingContext> Mapping;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> MoveAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LookAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> JumpAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SprintAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SuperJumpAction;
 UPROPERTY(Transient)
 TObjectPtr<UInputAction> FlightAction;
 UPROPERTY(Transient)
 TObjectPtr<UInputAction> SuperSpeedAction;
 UPROPERTY(Transient)
 TObjectPtr<UInputAction> FlyDownAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LetGoAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SelectAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> CameraDragAction;
	double LastTabTime = -100.0;
	double NextHitReact = 0.0;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ZoomAction;
};

/** Game mode that plays as the CoH hero. */
UCLASS()
class COHREBORN_API ACoHGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ACoHGameMode();

	/** Players arriving by monorail (URL option Arrive=Monorail) start at
	 *  the PlayerStarts tagged MonorailArrival, inside the waiting train. */
	virtual AActor* ChoosePlayerStart_Implementation(AController* Player) override;
	/** Maps with no enemy spawner placed (or not in the loaded cells) get one,
	 *  so the original encounters and wandering gangs run everywhere. */
	virtual void StartPlay() override;
};

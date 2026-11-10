// Active ragdoll: rigid bodies with "muscles" (docs/ragdoll.md).
//
// The body is the physics asset's rigid bodies and joints. Unreal's physical
// animation drives act as muscles that pull every joint toward the pose the
// animation is playing, with a tension that changes over time:
//   - Flinch : a hit jolts the upper body from the hit's direction; strong
//              muscles bring it back within half a second (legs stay planted).
//   - Ragdoll: knockback / knockdown. The body braces in the knock pose, the
//              muscles relax as it tumbles, and some tension stays while it lies.
//   - Limp   : defeat. Tension fades to nothing over about a second.
//   - Tumble : heroes (the capsule keeps moving the player): the limbs and
//              spine flail around the hips while airborne, and settle on landing.
// The joints are tuned in code (swing and twist limits, masses, damping) by
// the original CoH bone names, so every imported model gets the same body
// without editing physics assets. The gameplay (who is knocked how far) stays
// with the power rules; this only changes how a body moves.
//
// Multiplayer: the host decides (hits, knocks, get-ups) and calls the
// multicasts; each PC runs the physics locally. Nothing here changes game state.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "CoHActiveRagdoll.generated.h"

class USkeletalMeshComponent;
class UPhysicalAnimationComponent;

UENUM(BlueprintType)
enum class ECoHBodyMode : uint8 { Animated, Flinch, Tumble, Ragdoll, Limp };

UCLASS(ClassGroup = CoH, meta = (BlueprintSpawnableComponent), Config = Game)
class COHREBORN_API UCoHActiveRagdoll : public UActorComponent
{
	GENERATED_BODY()
public:
	UCoHActiveRagdoll();
	static UCoHActiveRagdoll* Of(const AActor* Actor);

	// --- tuning (DefaultGame.ini, [/Script/COHREBORN.CoHActiveRagdoll]) ------
	/** Off: the old limp ragdoll and no flinches. */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") bool bEnabled = true;
	/** Muscle stiffness at tension 1 (physical animation orientation strength). */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float MuscleStrength = 1000.f;
	/** Muscle damping at tension 1 (angular velocity strength). */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float MuscleDamping = 80.f;
	/** Knocked: tension while bracing, how long, then down to the tumble tension. */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float BraceTension = 0.8f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float BraceSeconds = 0.25f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float RelaxSeconds = 0.8f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float TumbleTension = 0.3f;
	/** Defeated: tension at the blow, fading to limp over DefeatRelaxSeconds. */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float DefeatTension = 0.5f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float DefeatRelaxSeconds = 1.2f;
	/** Flinch: the upper body's speed (cm/s) from a hit worth a full health bar
	 *  (smaller hits scale down to FlinchMin of it), how far physics takes over, and for how long. */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float FlinchSpeed = 320.f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float FlinchMin = 0.3f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float FlinchWeight = 0.8f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float FlinchSeconds = 0.5f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float FlinchTension = 1.5f;
	/** Hero tumble: how much the limbs follow physics in the air. */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float TumbleWeight = 0.75f;
	/** Seconds the get-up crossfades from where the body lies into the GetUp move. */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") float GetUpBlendSeconds = 0.4f;
	/** Joint limits, masses and damping by CoH bone name (off: the physics asset as it is). */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Ragdoll") bool bTuneJoints = true;

	// --- host -> every PC ------------------------------------------------------
	/** Host: a hit for Fraction of max health from Causer; jolts the body on every PC. */
	void HitReact(const AActor* Causer, float Fraction);
	UFUNCTION(NetMulticast, Unreliable) void MulticastFlinch(FVector_NetQuantizeNormal Dir, float Strength);
	/** Host: a hero was knocked (the capsule is launched); the limbs flail on every PC. */
	UFUNCTION(NetMulticast, Reliable) void MulticastTumble(FVector_NetQuantize10 Launch);

	// --- local (the owner calls these on every PC) -----------------------------
	void Flinch(const FVector& Dir, float Strength);
	/** Whole body to physics with muscles; false: no physics bodies (nothing done). */
	bool StartRagdoll(const FVector& LaunchVelocity, bool bDefeated);
	void Tumble(const FVector& Launch);
	/** Back to animation: physics off, collision as before. */
	void StopPhysics();
	/** Bodies have come to rest. */
	bool IsSettled(float MaxSpeed = 60.f) const;
	FVector PelvisLocation() const;
	/** Yaw for the capsule to get up from where the body lies (the GetUp move
	 *  starts on the back, sitting up toward the feet). */
	float GetUpYaw(bool& bOutFaceUp) const;
	/** The body's pose as bone-local transforms for a mesh placed at
	 *  NewComponent (what the get-up crossfades from). */
	bool CaptureLocalPose(const FTransform& NewComponent, TArray<FTransform>& OutLocal) const;
	ECoHBodyMode GetMode() const { return Mode; }
	bool IsPhysical() const { return Mode == ECoHBodyMode::Ragdoll || Mode == ECoHBodyMode::Limp; }

	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
	USkeletalMeshComponent* Body() const;
	bool HasBodies() const;
	/** Bone names on this mesh (CoH first, UE mannequin as a fallback). */
	void ResolveBones();
	/** Joint limits, masses, damping and the muscle drives; again whenever the
	 *  physics state may have been rebuilt (a new mesh). */
	void PrepareBodies();
	void SetTension(float Tension);
	void BeginPhysicsCollision();
	void EndPhysicsCollision();
	void EndFlinch();

	UPROPERTY(Transient) TObjectPtr<UPhysicalAnimationComponent> Muscles;
	ECoHBodyMode Mode = ECoHBodyMode::Animated;
	float ModeTime = 0.f, FlinchPeak = 0.f, LandedAt = -1.f;
	double LastFlinch = 0.0;
	FName Pelvis, Spine, Chest, Head;
	/** The mesh's forward in component space (taken while it is still upright). */
	FVector ForwardLocal = FVector(0, 1, 0);
	bool bSavedCollision = false;
	FName SavedProfile;
	TEnumAsByte<ECollisionEnabled::Type> SavedEnabled = ECollisionEnabled::NoCollision;
};

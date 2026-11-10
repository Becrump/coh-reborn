// Animation for the original player and villain bodies (male, fem, huge and
// the monster skeletons), played the way the game's sequencer plays them: a
// power runs a chain of moves (docs/powers-and-player-models.md), each move
// one stretch of an .anim track ([anim, firstFrame, lastFrame] at 30 fps),
// then goes back to a cycling ready. No animation blueprint is needed: this
// native anim instance samples the clips itself and crossfades between them.
//
// Two ways to drive it:
//   - locomotion (heroes): idle / combat idle / run / jump / fall / fly are
//     picked from the owner's movement every frame;
//   - base clip (villains): the owner sets the looping clip (SetBase), as the
//     enemy state machine already does with PlayAnimation.
// Either way PlaySegments plays a move chain over the top, then returns.
#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "CoHBodyAnim.generated.h"

class UAnimSequenceBase;

/** One move: a stretch of a clip, in seconds (End <= Start: to the clip's end). */
USTRUCT(BlueprintType)
struct FCoHAnimSegment
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite) TObjectPtr<UAnimSequenceBase> Clip;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float Start = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float End = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName Move;
	float Length() const;
};

/** What the proxy samples: up to two clips and the blend between them. */
struct FCoHBodyPose
{
	UAnimSequenceBase* A = nullptr; float TimeA = 0.f;
	UAnimSequenceBase* B = nullptr; float TimeB = 0.f;
	float Alpha = 1.f;          // weight of A
	float Lean = 0.f;           // degrees the neck and head tilt forward on top of the pose
};

struct FCoHBodyAnimProxy : public FAnimInstanceProxy
{
	FCoHBodyAnimProxy() = default;
	FCoHBodyAnimProxy(UAnimInstance* In) : FAnimInstanceProxy(In) {}
	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	virtual bool Evaluate(FPoseContext& Output) override;
	FCoHBodyPose Pose;
};

UCLASS(Transient, NotBlueprintable)
class COHREBORN_API UCoHBodyAnim : public UAnimInstance
{
	GENERATED_BODY()
public:
	// --- locomotion clips (heroes) -------------------------------------------
	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> Idle;
	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> CombatIdle;
	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> Run;
	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> JumpUp;
	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> Fall;
	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> Land;
	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> Fly;
	/** Pick the looping clip from the owner's movement (false: SetBase drives it). */
	bool bAutoLocomotion = true;
	/** Crossfade between clips and moves, seconds (the game blended a few frames). */
	float BlendTime = 0.12f;
	/** Run clip speed (cm/s) that plays at rate 1; faster movement plays it faster. */
	float RunCycleSpeed = 600.f;

	/** The looping (or held) base clip when not in auto locomotion. */
	void SetBase(UAnimSequenceBase* Clip, bool bLoop, float Rate = 1.f);
	/** Plays a move chain, then goes back to the base / locomotion. Rate
	 *  scales every move (1 = the game's 30 fps). */
	void PlaySegments(const TArray<FCoHAnimSegment>& Segments, float Rate = 1.f);
	void StopSegments();
	bool IsPlayingSegments() const { return Seg != INDEX_NONE; }
	/** Seconds the chain still runs. */
	float SegmentsLeft() const;
	/** In combat for a while after a power: idle uses the combat ready. */
	void MarkCombat(float Seconds = 8.f);
	/** Tilts the neck and head forward by Degrees for Seconds (an eye beam, a breath), eased in and out. */
	void LeanHead(float Degrees, float Seconds) { LeanTarget = Degrees; LeanHold = Seconds; }
	/** Holds the current pose (death); cleared by SetBase or PlaySegments. */
	void Freeze(bool bOn) { bFrozen = bOn; }

	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override { return new FCoHBodyAnimProxy(this); }
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override { delete InProxy; }

	FCoHBodyPose Current() const;

private:
	void Switch(UAnimSequenceBase* Clip, float StartTime);
	UAnimSequenceBase* PickLocomotion(float& OutRate) const;

	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> Playing;
	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> Previous;
	float Time = 0.f, PrevTime = 0.f, Blend = 1.f, Rate = 1.f;
	bool bLoop = true, bFrozen = false;
	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> Base;
	bool bBaseLoop = true; float BaseRate = 1.f;
	UPROPERTY(Transient) TArray<FCoHAnimSegment> Segments;
	int32 Seg = INDEX_NONE;
	float SegRate = 1.f;
	double CombatUntil = 0.0;
	float LeanTarget = 0.f, LeanHold = 0.f, LeanNow = 0.f;
	bool bWasFalling = false;
	float LandLeft = 0.f;
};

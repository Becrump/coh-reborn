// Anim instance with no Anim Blueprint: plays one AnimSequence at a time and
// crossfades from the previous one, the way the CoH sequencer interpolated
// between moves. UCoHIdleComponent drives it through an idle graph.
#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "CoHIdleAnimInstance.generated.h"

class UAnimSequence;

/** One clip being sampled: which sequence, and where in it (seconds). */
struct FCoHClipSample
{
	// kept alive by UCoHIdleComponent::Clips
	UAnimSequence* Seq = nullptr;
	float Time = 0.f;
};

USTRUCT()
struct FCoHIdleAnimProxy : public FAnimInstanceProxy
{
	GENERATED_BODY()

	FCoHIdleAnimProxy() {}
	FCoHIdleAnimProxy(UAnimInstance* InAnimInstance) : FAnimInstanceProxy(InAnimInstance) {}

	virtual void PreEvaluateAnimation(UAnimInstance* InAnimInstance) override;
	virtual bool Evaluate(FPoseContext& Output) override;

private:
	FCoHClipSample Cur;
	FCoHClipSample Prev;
	/** Weight of Cur; Prev fades out as this goes 0 -> 1. */
	float Alpha = 1.f;
};

UCLASS(Transient, NotBlueprintable)
class COHREBORN_API UCoHIdleAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	/** Start Seq at StartTime, blending from whatever is playing over BlendTime seconds. */
	void PlayClip(UAnimSequence* Seq, float StartTime, float PlayRate, float BlendTime);

	/** True once the current clip has reached its last frame (it then holds). */
	bool IsClipFinished() const;

	UAnimSequence* GetCurrentClip() const { return Cur.Seq; }

protected:
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;

private:
	friend struct FCoHIdleAnimProxy;

	FCoHClipSample Cur;
	FCoHClipSample Prev;
	float Rate = 1.f;
	float PrevRate = 1.f;
	float Alpha = 1.f;
	float BlendTime = 0.f;
};

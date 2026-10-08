#include "CoHIdleAnimInstance.h"

#include "Animation/AnimNodeBase.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimationPoseData.h"
#include "AnimationRuntime.h"

void UCoHIdleAnimInstance::PlayClip(UAnimSequence* Seq, float StartTime, float PlayRate, float InBlendTime)
{
	if (InBlendTime > 0.f && Cur.Seq)
	{
		Prev = Cur;
		PrevRate = 0.f;     // the old move freezes on the frame it ended on, as in CoH
		Alpha = 0.f;
	}
	else
	{
		Prev = FCoHClipSample();
		Alpha = 1.f;
	}
	Cur.Seq = Seq;
	Cur.Time = StartTime;
	Rate = PlayRate;
	BlendTime = InBlendTime;
}

bool UCoHIdleAnimInstance::IsClipFinished() const
{
	return !Cur.Seq || Cur.Time >= Cur.Seq->GetPlayLength();
}

void UCoHIdleAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);
	if (Cur.Seq)
	{
		Cur.Time = FMath::Min(Cur.Time + DeltaSeconds * Rate, Cur.Seq->GetPlayLength());
	}
	if (Prev.Seq)
	{
		Prev.Time = FMath::Min(Prev.Time + DeltaSeconds * PrevRate, Prev.Seq->GetPlayLength());
	}
	if (Alpha < 1.f)
	{
		Alpha = BlendTime > 0.f ? FMath::Min(1.f, Alpha + DeltaSeconds / BlendTime) : 1.f;
		if (Alpha >= 1.f)
		{
			Prev = FCoHClipSample();
		}
	}
}

FAnimInstanceProxy* UCoHIdleAnimInstance::CreateAnimInstanceProxy()
{
	return new FCoHIdleAnimProxy(this);
}

void FCoHIdleAnimProxy::PreEvaluateAnimation(UAnimInstance* InAnimInstance)
{
	FAnimInstanceProxy::PreEvaluateAnimation(InAnimInstance);
	// game thread, after NativeUpdateAnimation: copy the clip state for the
	// worker-thread Evaluate
	const UCoHIdleAnimInstance* Inst = CastChecked<UCoHIdleAnimInstance>(InAnimInstance);
	Cur = Inst->Cur;
	Prev = Inst->Prev;
	Alpha = Inst->Alpha;
}

static void SampleClip(const FCoHClipSample& Clip, FPoseContext& Pose)
{
	FAnimationPoseData Data(Pose);
	Clip.Seq->GetAnimationPose(Data, FAnimExtractContext(double(Clip.Time)));
}

bool FCoHIdleAnimProxy::Evaluate(FPoseContext& Output)
{
	if (!Cur.Seq)
	{
		Output.ResetToRefPose();
		return true;
	}
	if (!Prev.Seq || Alpha >= 1.f)
	{
		SampleClip(Cur, Output);
		return true;
	}
	FPoseContext PrevPose(Output);
	FPoseContext CurPose(Output);
	SampleClip(Prev, PrevPose);
	SampleClip(Cur, CurPose);
	FAnimationPoseData Blended(Output);
	FAnimationRuntime::BlendTwoPosesTogether(
		FAnimationPoseData(PrevPose), FAnimationPoseData(CurPose), 1.f - Alpha, Blended);
	return true;
}

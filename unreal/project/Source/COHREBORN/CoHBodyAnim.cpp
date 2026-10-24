#include "CoHBodyAnim.h"
#include "Animation/AnimSequenceBase.h"
#include "Animation/AnimationPoseData.h"
#include "AnimationRuntime.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"

float FCoHAnimSegment::Length() const
{
	if (!Clip) return 0.f;
	const float L = Clip->GetPlayLength();
	const float S = FMath::Clamp(Start, 0.f, L);
	const float E = End > Start ? FMath::Min(End, L) : L;
	return FMath::Max(0.f, E - S);
}

// ------------------------------------------------------------------ proxy
void FCoHBodyAnimProxy::PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds)
{
	FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);
	if (const UCoHBodyAnim* B = Cast<UCoHBodyAnim>(InAnimInstance)) Pose = B->Current();
}

static void Sample(const UAnimSequenceBase* Clip, float Time, FAnimationPoseData& Out)
{
	const float L = Clip->GetPlayLength();
	Clip->GetAnimationPose(Out, FAnimExtractContext((double)FMath::Clamp(Time, 0.f, L), false));
}

bool FCoHBodyAnimProxy::Evaluate(FPoseContext& Output)
{
	if (!Pose.A)
	{
		Output.ResetToRefPose();
		return true;
	}
	FAnimationPoseData Out(Output);
	if (!Pose.B || Pose.Alpha >= 0.999f)
	{
		Sample(Pose.A, Pose.TimeA, Out);
		return true;
	}
	FPoseContext PA(Output), PB(Output);
	FAnimationPoseData DA(PA), DB(PB);
	Sample(Pose.A, Pose.TimeA, DA);
	Sample(Pose.B, Pose.TimeB, DB);
	FAnimationRuntime::BlendTwoPosesTogether(DA, DB, Pose.Alpha, Out);
	return true;
}

// ------------------------------------------------------------------ instance
FCoHBodyPose UCoHBodyAnim::Current() const
{
	FCoHBodyPose P;
	P.A = Playing; P.TimeA = Time;
	P.B = Blend < 1.f ? Previous.Get() : nullptr; P.TimeB = PrevTime;
	P.Alpha = FMath::Clamp(Blend, 0.f, 1.f);
	if (!P.A && P.B) { P.A = P.B; P.TimeA = P.TimeB; P.B = nullptr; P.Alpha = 1.f; }
	return P;
}

void UCoHBodyAnim::Switch(UAnimSequenceBase* Clip, float StartTime)
{
	if (Clip == Playing && FMath::Abs(StartTime - Time) < 0.05f) return;    // a chain that runs on
	Previous = Playing; PrevTime = Time;
	Playing = Clip; Time = StartTime;
	Blend = Previous && BlendTime > 0.f ? 0.f : 1.f;
}

void UCoHBodyAnim::SetBase(UAnimSequenceBase* Clip, bool bInLoop, float InRate)
{
	bFrozen = false;
	if (Clip == Base && bInLoop == bBaseLoop && Seg == INDEX_NONE && Playing == Clip) { BaseRate = InRate; return; }
	Base = Clip; bBaseLoop = bInLoop; BaseRate = InRate;
	if (Seg == INDEX_NONE && !bAutoLocomotion)
	{
		Switch(Clip, 0.f);
		bLoop = bInLoop; Rate = InRate;
	}
}

void UCoHBodyAnim::PlaySegments(const TArray<FCoHAnimSegment>& In, float InRate)
{
	bFrozen = false;
	Segments.Reset();
	for (const FCoHAnimSegment& S : In) if (S.Clip && S.Length() > 0.f) Segments.Add(S);
	if (Segments.Num() == 0) { Seg = INDEX_NONE; return; }
	Seg = 0;
	SegRate = FMath::Max(0.05f, InRate);
	Switch(Segments[0].Clip, Segments[0].Start);
	bLoop = false; Rate = SegRate;
}

void UCoHBodyAnim::StopSegments()
{
	if (Seg == INDEX_NONE) return;
	Seg = INDEX_NONE;
	Segments.Reset();
	float R = 1.f;
	UAnimSequenceBase* Next = bAutoLocomotion ? PickLocomotion(R) : Base.Get();
	Switch(Next, 0.f);
	bLoop = bAutoLocomotion || bBaseLoop; Rate = bAutoLocomotion ? R : BaseRate;
}

float UCoHBodyAnim::SegmentsLeft() const
{
	if (Seg == INDEX_NONE || !Segments.IsValidIndex(Seg)) return 0.f;
	const FCoHAnimSegment& S = Segments[Seg];
	const float End = S.Start + S.Length();
	float Left = FMath::Max(0.f, End - Time);
	for (int32 i = Seg + 1; i < Segments.Num(); ++i) Left += Segments[i].Length();
	return Left / SegRate;
}

void UCoHBodyAnim::MarkCombat(float Seconds)
{
	if (const UWorld* W = GetWorld()) CombatUntil = FMath::Max(CombatUntil, W->GetTimeSeconds() + Seconds);
}

UAnimSequenceBase* UCoHBodyAnim::PickLocomotion(float& OutRate) const
{
	OutRate = 1.f;
	const ACharacter* C = Cast<ACharacter>(TryGetPawnOwner());
	const UCharacterMovementComponent* M = C ? C->GetCharacterMovement() : nullptr;
	const UWorld* W = GetWorld();
	const bool bCombat = W && W->GetTimeSeconds() < CombatUntil;
	UAnimSequenceBase* Ready = bCombat && CombatIdle ? CombatIdle.Get() : Idle.Get();
	if (!M) return Ready;
	const float Speed = M->Velocity.Size2D();
	if (M->IsFlying()) return Fly ? Fly.Get() : (Speed > 50.f && Run ? Run.Get() : Ready);
	if (M->IsFalling())
	{
		if (M->Velocity.Z > 100.f && JumpUp) return JumpUp;
		return Fall ? Fall.Get() : (JumpUp ? JumpUp.Get() : Ready);
	}
	if (LandLeft > 0.f && Land && Speed < 50.f) return Land;
	if (Speed > 30.f && Run)
	{
		OutRate = FMath::Clamp(Speed / FMath::Max(100.f, RunCycleSpeed), 0.5f, 2.f);
		return Run;
	}
	return Ready;
}

void UCoHBodyAnim::NativeUpdateAnimation(float Dt)
{
	Super::NativeUpdateAnimation(Dt);
	if (bFrozen) return;
	if (Blend < 1.f) { Blend = FMath::Min(1.f, Blend + Dt / FMath::Max(0.01f, BlendTime)); PrevTime += Dt; }
	// landing: a short land move when touching down from a fall
	if (const ACharacter* C = Cast<ACharacter>(TryGetPawnOwner()))
		if (const UCharacterMovementComponent* M = C->GetCharacterMovement())
		{
			const bool bFalling = M->IsFalling();
			if (bWasFalling && !bFalling && Land) LandLeft = FMath::Min(Land->GetPlayLength(), 0.35f);
			bWasFalling = bFalling;
		}
	LandLeft = FMath::Max(0.f, LandLeft - Dt);

	if (Seg != INDEX_NONE)
	{
		Time += Dt * SegRate;
		while (Seg != INDEX_NONE)
		{
			const FCoHAnimSegment& S = Segments[Seg];
			const float End = S.Start + S.Length();
			if (Time < End) break;
			const float Over = Time - End;
			if (++Seg >= Segments.Num()) { StopSegments(); return; }
			const FCoHAnimSegment& N = Segments[Seg];
			// the next move of the chain: same clip running on, or a new one
			if (N.Clip == Playing && FMath::Abs(N.Start - End) < 0.05f) Time = N.Start + Over;
			else { Switch(N.Clip, N.Start + Over); }
		}
		return;
	}
	if (bAutoLocomotion)
	{
		float R = 1.f;
		UAnimSequenceBase* Want = PickLocomotion(R);
		if (Want != Playing) Switch(Want, 0.f);
		bLoop = Want != Land && Want != JumpUp;
		Rate = R;
	}
	if (!Playing) return;
	Time += Dt * Rate;
	const float L = Playing->GetPlayLength();
	if (L <= 0.f) { Time = 0.f; return; }
	if (bLoop) Time = FMath::Fmod(Time, L);
	else Time = FMath::Min(Time, L);
}

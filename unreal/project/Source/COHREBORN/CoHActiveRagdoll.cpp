#include "CoHActiveRagdoll.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "PhysicsEngine/BodyInstance.h"
#include "PhysicsEngine/ConstraintInstance.h"
#include "PhysicsEngine/PhysicalAnimationComponent.h"
#include "PhysicsEngine/PhysicsAsset.h"

namespace
{
	/** A joint by its child bone (CoH names; L/R share a row): swing and twist limits in degrees, mass in kg. */
	struct FCoHJoint { const TCHAR* Bone; float Swing; float Twist; float Mass; };
	// limits a little inside a human's range so poses never fold through
	// themselves; knees and elbows barely twist. Masses for an ~80 kg body.
	const FCoHJoint GJoints[] = {
		{ TEXT("HIPS"),  0.f,  0.f, 12.f },
		{ TEXT("WAIST"), 25.f, 15.f, 8.f },
		{ TEXT("CHEST"), 20.f, 15.f, 14.f },
		{ TEXT("NECK"),  35.f, 30.f, 2.f },
		{ TEXT("HEAD"),  30.f, 25.f, 5.f },
		{ TEXT("COL_R"), 10.f, 5.f, 1.f },   { TEXT("COL_L"), 10.f, 5.f, 1.f },
		{ TEXT("UARMR"), 85.f, 50.f, 2.5f }, { TEXT("UARML"), 85.f, 50.f, 2.5f },
		{ TEXT("LARMR"), 75.f, 8.f, 1.5f },  { TEXT("LARML"), 75.f, 8.f, 1.5f },
		{ TEXT("HANDR"), 35.f, 20.f, .5f },  { TEXT("HANDL"), 35.f, 20.f, .5f },
		{ TEXT("ULEGR"), 60.f, 20.f, 9.f },  { TEXT("ULEGL"), 60.f, 20.f, 9.f },
		{ TEXT("LLEGR"), 70.f, 5.f, 4.f },   { TEXT("LLEGL"), 70.f, 5.f, 4.f },
		{ TEXT("FOOTR"), 30.f, 10.f, 1.2f }, { TEXT("FOOTL"), 30.f, 10.f, 1.2f },
	};
	const FCoHJoint* JointFor(FName Bone)
	{
		for (const FCoHJoint& J : GJoints) if (Bone == FName(J.Bone)) return &J;
		return nullptr;
	}
	FName FirstBone(const USkeletalMeshComponent* M, std::initializer_list<const TCHAR*> Names)
	{
		for (const TCHAR* N : Names) if (M->GetBodyInstance(FName(N))) return FName(N);
		return NAME_None;
	}
	/** Reference pose of a bone in component space. */
	FTransform RefComponentSpace(const FReferenceSkeleton& Ref, int32 Bone)
	{
		FTransform T = FTransform::Identity;
		for (int32 B = Bone; B != INDEX_NONE; B = Ref.GetParentIndex(B)) T = T * Ref.GetRefBonePose()[B];
		return T;
	}
}

UCoHActiveRagdoll::UCoHActiveRagdoll()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = false;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;
	SetIsReplicatedByDefault(true);
}

UCoHActiveRagdoll* UCoHActiveRagdoll::Of(const AActor* Actor)
{
	return Actor ? Actor->FindComponentByClass<UCoHActiveRagdoll>() : nullptr;
}

void UCoHActiveRagdoll::BeginPlay()
{
	Super::BeginPlay();
	Muscles = NewObject<UPhysicalAnimationComponent>(GetOwner(), TEXT("CoHMuscles"));
	Muscles->RegisterComponent();
}

USkeletalMeshComponent* UCoHActiveRagdoll::Body() const
{
	const ACharacter* C = Cast<ACharacter>(GetOwner());
	return C ? C->GetMesh() : (GetOwner() ? GetOwner()->FindComponentByClass<USkeletalMeshComponent>() : nullptr);
}

bool UCoHActiveRagdoll::HasBodies() const
{
	const USkeletalMeshComponent* M = Body();
	const UPhysicsAsset* P = M ? M->GetPhysicsAsset() : nullptr;
	return P && P->SkeletalBodySetups.Num() > 0 && M->Bodies.Num() > 0;
}

void UCoHActiveRagdoll::ResolveBones()
{
	const USkeletalMeshComponent* M = Body();
	Pelvis = FirstBone(M, { TEXT("HIPS"), TEXT("pelvis"), TEXT("Pelvis") });
	if (Pelvis.IsNone() && M->Bodies.Num() > 0 && M->Bodies[0]) Pelvis = M->GetBoneName(M->Bodies[0]->InstanceBoneIndex);
	Spine = FirstBone(M, { TEXT("WAIST"), TEXT("spine_01"), TEXT("spine_02") });
	Chest = FirstBone(M, { TEXT("CHEST"), TEXT("spine_03"), TEXT("spine_04"), TEXT("spine_02") });
	Head = FirstBone(M, { TEXT("HEAD"), TEXT("head") });
	if (Chest.IsNone()) Chest = Spine.IsNone() ? Pelvis : Spine;
}

void UCoHActiveRagdoll::PrepareBodies()
{
	USkeletalMeshComponent* M = Body();
	if (!M) return;
	ResolveBones();
	if (bTuneJoints)
	{
		for (FConstraintInstance* CI : M->Constraints)
		{
			const FCoHJoint* J = CI ? JointFor(CI->GetChildBoneName()) : nullptr;
			if (!J || J->Swing <= 0.f) continue;
			CI->SetAngularSwing1Limit(ACM_Limited, J->Swing);
			CI->SetAngularSwing2Limit(ACM_Limited, J->Swing);
			CI->SetAngularTwistLimit(ACM_Limited, J->Twist);
		}
		for (FBodyInstance* BI : M->Bodies)
		{
			if (!BI) continue;
			const FCoHJoint* J = JointFor(M->GetBoneName(BI->InstanceBoneIndex));
			// costume bones (capes, belts, fingers) are light so they never swing the body
			BI->SetMassOverride(J ? J->Mass : 0.3f, true);
			BI->UpdateMassProperties();
			BI->LinearDamping = 0.05f;
			BI->AngularDamping = 1.f;
			BI->UpdateDampingProperties();
		}
	}
	if (Muscles && !Pelvis.IsNone())
	{
		Muscles->SetSkeletalMeshComponent(M);
		FPhysicalAnimationData D;
		D.bIsLocalSimulation = true;             // joint-relative: muscles, not puppet strings
		D.OrientationStrength = MuscleStrength;
		D.AngularVelocityStrength = MuscleDamping;
		D.PositionStrength = 0.f;
		D.VelocityStrength = 0.f;
		D.MaxLinearForce = 0.f;                  // 0: no cap
		D.MaxAngularForce = 0.f;
		Muscles->ApplyPhysicalAnimationSettingsBelow(Pelvis, D, true);
	}
}

void UCoHActiveRagdoll::SetTension(float Tension)
{
	if (Muscles) Muscles->SetStrengthMultiplyer(FMath::Max(0.f, Tension));
}

void UCoHActiveRagdoll::BeginPhysicsCollision()
{
	USkeletalMeshComponent* M = Body();
	if (!M) return;
	if (!bSavedCollision)
	{
		SavedProfile = M->GetCollisionProfileName();
		SavedEnabled = M->GetCollisionEnabled();
		bSavedCollision = true;
	}
	M->SetCollisionProfileName(TEXT("Ragdoll"));
	M->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	// bodies pass through characters (no shoving players) and never push the camera
	M->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	M->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
}

void UCoHActiveRagdoll::EndPhysicsCollision()
{
	USkeletalMeshComponent* M = Body();
	if (!M || !bSavedCollision) return;
	M->SetCollisionProfileName(SavedProfile);
	M->SetCollisionEnabled(SavedEnabled);
	bSavedCollision = false;
}

// ------------------------------------------------------------------ hits
void UCoHActiveRagdoll::HitReact(const AActor* Causer, float Fraction)
{
	const AActor* Me = GetOwner();
	if (!bEnabled || !Me || !Me->HasAuthority()) return;
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - LastFlinch < 0.12) return;                 // a burst of ticks is one jolt
	LastFlinch = Now;
	FVector Dir = Causer ? Me->GetActorLocation() - Causer->GetActorLocation() : -Me->GetActorForwardVector();
	Dir.Z = 0.f;
	Dir = Dir.GetSafeNormal();
	if (Dir.IsNearlyZero()) Dir = -Me->GetActorForwardVector();
	const float Strength = FMath::Lerp(FlinchMin, 1.f, FMath::Clamp(Fraction * 3.f, 0.f, 1.f));
	MulticastFlinch(Dir, Strength);
}

void UCoHActiveRagdoll::MulticastFlinch_Implementation(FVector_NetQuantizeNormal Dir, float Strength)
{
	Flinch(Dir, Strength);
}

void UCoHActiveRagdoll::Flinch(const FVector& Dir, float Strength)
{
	USkeletalMeshComponent* M = Body();
	if (!bEnabled || !M || !HasBodies()) return;
	const FVector Kick = Dir.GetSafeNormal() * FlinchSpeed * Strength;
	if (Mode == ECoHBodyMode::Ragdoll || Mode == ECoHBodyMode::Limp || Mode == ECoHBodyMode::Tumble)
	{
		// already physical: a hit on a falling or downed body jolts it
		if (FBodyInstance* BI = M->GetBodyInstance(Chest)) BI->AddImpulse(Kick * 0.6f, true);
		return;
	}
	if (Mode == ECoHBodyMode::Animated)
	{
		PrepareBodies();
		if (Spine.IsNone()) return;
		BeginPhysicsCollision();
		M->SetAllBodiesBelowSimulatePhysics(Spine, true, true);
	}
	M->SetAllBodiesBelowPhysicsBlendWeight(Spine, 0.f, false, true);
	SetTension(FlinchTension);
	Mode = ECoHBodyMode::Flinch;
	ModeTime = 0.f;
	FlinchPeak = FMath::Clamp(FlinchWeight * (0.6f + 0.4f * Strength), 0.f, 1.f);
	if (FBodyInstance* BI = M->GetBodyInstance(Chest)) BI->AddImpulse(Kick, true);
	if (FBodyInstance* BI = M->GetBodyInstance(Head)) BI->AddImpulse(Kick * 0.7f, true);
	SetComponentTickEnabled(true);
}

void UCoHActiveRagdoll::EndFlinch()
{
	USkeletalMeshComponent* M = Body();
	if (M && !Spine.IsNone())
	{
		M->SetAllBodiesBelowPhysicsBlendWeight(Spine, 0.f, false, true);
		M->SetAllBodiesBelowSimulatePhysics(Spine, false, true);
	}
	EndPhysicsCollision();
	Mode = ECoHBodyMode::Animated;
	SetComponentTickEnabled(false);
}

// ------------------------------------------------------------------ knocks and defeat
bool UCoHActiveRagdoll::StartRagdoll(const FVector& LaunchVelocity, bool bDefeated)
{
	USkeletalMeshComponent* M = Body();
	if (!M || !HasBodies()) return false;
	const bool bWasPhysical = IsPhysical();
	if (!bWasPhysical && GetOwner())
		ForwardLocal = M->GetComponentTransform().InverseTransformVectorNoScale(GetOwner()->GetActorForwardVector());
	if (Mode == ECoHBodyMode::Flinch) EndFlinch();
	if (!bWasPhysical) PrepareBodies();
	BeginPhysicsCollision();
	M->SetEnableGravity(true);
	M->SetAllBodiesSimulatePhysics(true);
	M->SetAllBodiesPhysicsBlendWeight(1.f);
	M->WakeAllRigidBodies();
	if (!bEnabled) SetTension(0.f);
	else SetTension(bDefeated ? DefeatTension : BraceTension);
	// the whole body takes the launch, the top a little more than the feet, so
	// it tips over the legs (knocked off its feet) instead of sliding as a block
	const float FeetZ = M->Bodies.Num() > 0 ? M->Bounds.Origin.Z - M->Bounds.BoxExtent.Z : M->GetComponentLocation().Z;
	const float Height = FMath::Max(50.f, M->Bounds.BoxExtent.Z * 2.f);
	const bool bFast = LaunchVelocity.Size() > 700.f;
	for (FBodyInstance* BI : M->Bodies)
	{
		if (!BI) continue;
		const float H = FMath::Clamp((BI->GetUnrealWorldTransform().GetLocation().Z - FeetZ) / Height, 0.f, 1.f);
		BI->AddImpulse(LaunchVelocity * (0.75f + 0.5f * H), true);
		const FName Bone = M->GetBoneName(BI->InstanceBoneIndex);
		if (Bone == Pelvis || Bone == Chest) BI->SetUseCCD(bFast);   // big knockbacks don't pass through walls
	}
	Mode = bDefeated ? ECoHBodyMode::Limp : ECoHBodyMode::Ragdoll;
	ModeTime = 0.f;
	SetComponentTickEnabled(true);
	return true;
}

void UCoHActiveRagdoll::MulticastTumble_Implementation(FVector_NetQuantize10 Launch)
{
	Tumble(Launch);
}

void UCoHActiveRagdoll::Tumble(const FVector& Launch)
{
	USkeletalMeshComponent* M = Body();
	if (!bEnabled || !M || !HasBodies() || IsPhysical()) return;
	if (Mode == ECoHBodyMode::Flinch) EndFlinch();
	PrepareBodies();
	if (Pelvis.IsNone()) return;
	BeginPhysicsCollision();
	// the hips stay on the (launched) capsule; everything hanging off them flails
	M->SetAllBodiesBelowSimulatePhysics(Pelvis, true, false);
	M->SetAllBodiesBelowPhysicsBlendWeight(Pelvis, TumbleWeight, false, false);
	SetTension(BraceTension);
	// limbs lag the launch a little: the whiplash
	for (FBodyInstance* BI : M->Bodies)
		if (BI && BI->IsInstanceSimulatingPhysics()) BI->AddImpulse(-Launch * 0.15f, true);
	Mode = ECoHBodyMode::Tumble;
	ModeTime = 0.f;
	LandedAt = -1.f;
	SetComponentTickEnabled(true);
}

void UCoHActiveRagdoll::StopPhysics()
{
	USkeletalMeshComponent* M = Body();
	if (M)
	{
		M->SetAllBodiesSimulatePhysics(false);
		M->SetAllBodiesPhysicsBlendWeight(0.f);
		for (FBodyInstance* BI : M->Bodies) if (BI) BI->SetUseCCD(false);
	}
	SetTension(0.f);
	EndPhysicsCollision();
	Mode = ECoHBodyMode::Animated;
	SetComponentTickEnabled(false);
}

// ------------------------------------------------------------------ resting body
bool UCoHActiveRagdoll::IsSettled(float MaxSpeed) const
{
	const USkeletalMeshComponent* M = Body();
	if (!M) return true;
	for (const FName B : { Pelvis, Chest })
		if (const FBodyInstance* BI = B.IsNone() ? nullptr : M->GetBodyInstance(B))
			if (BI->GetUnrealWorldVelocity().Size() > MaxSpeed) return false;
	return true;
}

FVector UCoHActiveRagdoll::PelvisLocation() const
{
	const USkeletalMeshComponent* M = Body();
	if (!M) return GetOwner() ? GetOwner()->GetActorLocation() : FVector::ZeroVector;
	return Pelvis.IsNone() ? M->GetBoneLocation(M->GetBoneName(0)) : M->GetBoneLocation(Pelvis);
}

float UCoHActiveRagdoll::GetUpYaw(bool& bOutFaceUp) const
{
	bOutFaceUp = true;
	const USkeletalMeshComponent* M = Body();
	const USkeletalMesh* Mesh = M ? M->GetSkeletalMeshAsset() : nullptr;
	const float Fallback = GetOwner() ? GetOwner()->GetActorRotation().Yaw : 0.f;
	if (!Mesh || Pelvis.IsNone()) return Fallback;
	const int32 PelvisIndex = M->GetBoneIndex(Pelvis);
	if (PelvisIndex == INDEX_NONE) return Fallback;
	// the body's rotation from the hips: how far they turned from the reference pose
	const FQuat World = M->GetBoneQuaternion(Pelvis, EBoneSpaces::WorldSpace);
	const FQuat Ref = RefComponentSpace(Mesh->GetRefSkeleton(), PelvisIndex).GetRotation();
	const FQuat BodyRot = World * Ref.Inverse();
	const FVector Front = BodyRot.RotateVector(ForwardLocal);
	bOutFaceUp = Front.Z >= 0.f;
	// head direction along the ground
	FVector HeadWay = M->GetBoneLocation(Head.IsNone() ? Chest : Head) - M->GetBoneLocation(Pelvis);
	HeadWay.Z = 0.f;
	FVector Facing = HeadWay.SizeSquared() > 25.f ? HeadWay.GetSafeNormal() * (bOutFaceUp ? -1.f : 1.f) : FVector(Front.X, Front.Y, 0.f).GetSafeNormal();
	return Facing.IsNearlyZero() ? Fallback : Facing.Rotation().Yaw;
}

bool UCoHActiveRagdoll::CaptureLocalPose(const FTransform& NewComponent, TArray<FTransform>& OutLocal) const
{
	const USkeletalMeshComponent* M = Body();
	const USkeletalMesh* Mesh = M ? M->GetSkeletalMeshAsset() : nullptr;
	if (!Mesh) return false;
	const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
	const int32 Num = FMath::Min(M->GetNumBones(), Ref.GetNum());
	TArray<FTransform> CS;
	CS.SetNum(Num);
	OutLocal.SetNum(Num);
	for (int32 i = 0; i < Num; ++i)
	{
		CS[i] = M->GetBoneTransform(i).GetRelativeTransform(NewComponent);
		CS[i].SetScale3D(FVector::OneVector);
		const int32 Parent = Ref.GetParentIndex(i);
		FTransform L = Parent == INDEX_NONE ? CS[i] : CS[i].GetRelativeTransform(CS[Parent]);
		L.SetScale3D(Ref.GetRefBonePose()[i].GetScale3D());
		L.NormalizeRotation();
		OutLocal[i] = L;
	}
	return true;
}

// ------------------------------------------------------------------ tension over time
void UCoHActiveRagdoll::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	USkeletalMeshComponent* M = Body();
	if (!M) return;
	ModeTime += DeltaTime;
	switch (Mode)
	{
	case ECoHBodyMode::Flinch:
	{
		// up in 60 ms, hold, then hand back to the animation
		const float T = ModeTime;
		const float W = T < 0.06f ? FlinchPeak * T / 0.06f
			: T < 0.15f ? FlinchPeak
			: FlinchPeak * (1.f - (T - 0.15f) / FMath::Max(0.05f, FlinchSeconds - 0.15f));
		if (T >= FlinchSeconds || W <= 0.f) { EndFlinch(); return; }
		M->SetAllBodiesBelowPhysicsBlendWeight(Spine, W, false, true);
		break;
	}
	case ECoHBodyMode::Tumble:
	{
		const ACharacter* C = Cast<ACharacter>(GetOwner());
		const bool bGround = !C || C->GetCharacterMovement()->IsMovingOnGround();
		if (LandedAt < 0.f && ModeTime > 0.2f && bGround) LandedAt = ModeTime;
		SetTension(FMath::Lerp(BraceTension, 1.f, FMath::Clamp(ModeTime / 0.6f, 0.f, 1.f)));
		float W = TumbleWeight;
		if (LandedAt >= 0.f) W *= 1.f - (ModeTime - LandedAt) / 0.35f;
		if (W <= 0.f || ModeTime > 6.f)
		{
			M->SetAllBodiesBelowPhysicsBlendWeight(Pelvis, 0.f, false, false);
			M->SetAllBodiesBelowSimulatePhysics(Pelvis, false, false);
			SetTension(0.f);
			EndPhysicsCollision();
			Mode = ECoHBodyMode::Animated;
			SetComponentTickEnabled(false);
			return;
		}
		M->SetAllBodiesBelowPhysicsBlendWeight(Pelvis, W, false, false);
		break;
	}
	case ECoHBodyMode::Ragdoll:
	{
		// brace, then relax into the tumble; some tone stays while it lies there
		const float T = ModeTime;
		const float Tension = T < BraceSeconds ? BraceTension
			: FMath::Lerp(BraceTension, TumbleTension, FMath::Clamp((T - BraceSeconds) / FMath::Max(0.05f, RelaxSeconds), 0.f, 1.f));
		if (bEnabled) SetTension(Tension);
		break;
	}
	case ECoHBodyMode::Limp:
	{
		const float A = FMath::Clamp(ModeTime / FMath::Max(0.05f, DefeatRelaxSeconds), 0.f, 1.f);
		if (bEnabled) SetTension(DefeatTension * (1.f - A));
		if (A >= 1.f) SetComponentTickEnabled(false);   // fully limp: nothing left to do
		break;
	}
	default:
		SetComponentTickEnabled(false);
		break;
	}
}

#include "CoHPowerFX.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Math/RotationMatrix.h"

static const TCHAR* FXMaterial = TEXT("/Game/CoH/FX/M_CoH_PowerFX.M_CoH_PowerFX");

ACoHPowerFX::ACoHPowerFX()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = false;
	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Mesh->SetCastShadow(false);
	Mesh->SetVisibility(false);
	RootComponent = Mesh;
}

ACoHPowerFX* ACoHPowerFX::Make(AActor* Owner, FVector Where, FLinearColor InColour, bool bSphere)
{
	UWorld* W = Owner ? Owner->GetWorld() : nullptr;
	if (!W || W->GetNetMode() == NM_DedicatedServer) return nullptr;
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ACoHPowerFX* FX = W->SpawnActor<ACoHPowerFX>(Where, FRotator::ZeroRotator, P);
	if (!FX) return nullptr;
	UStaticMesh* Shape = LoadObject<UStaticMesh>(nullptr, bSphere ? TEXT("/Engine/BasicShapes/Sphere.Sphere") : TEXT("/Engine/BasicShapes/Cone.Cone"));
	FX->Mesh->SetStaticMesh(Shape);
	if (UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, FXMaterial, nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		FX->Mat = UMaterialInstanceDynamic::Create(Base, FX);
		FX->Mat->SetVectorParameterValue(TEXT("Colour"), InColour);
		FX->Mat->SetScalarParameterValue(TEXT("Opacity"), 1.f);
		FX->Mesh->SetMaterial(0, FX->Mat);
	}
	FX->Colour = InColour;
	return FX;
}

void ACoHPowerFX::Bolt(AActor* Owner, FVector From, FVector To, FLinearColor Colour, float Delay, float Radius)
{
	ACoHPowerFX* FX = Make(Owner, From, Colour, true);
	if (!FX) return;
	FX->From = From; FX->To = To; FX->bMoving = true; FX->Delay = Delay;
	FX->Travel = FMath::Clamp(FVector::Dist(From, To) / 4000.f, 0.08f, 0.5f);
	FX->StartScale = FX->EndScale = FVector(0.25f);
	FX->Life = FX->Travel;
	FX->BurstRadius = Radius;
}

void ACoHPowerFX::Burst(AActor* Owner, FVector Where, float Radius, FLinearColor Colour, float Life, float Delay)
{
	ACoHPowerFX* FX = Make(Owner, Where, Colour, true);
	if (!FX) return;
	FX->Delay = Delay; FX->Life = Life;
	FX->StartScale = FVector(0.1f);
	FX->EndScale = FVector(FMath::Max(Radius, 40.f) / 50.f);   // the engine sphere is 100 cm across
}

void ACoHPowerFX::Cone(AActor* Owner, FVector From, FVector Dir, float Range, float Arc, FLinearColor Colour, float Delay)
{
	ACoHPowerFX* FX = Make(Owner, From, Colour, false);
	if (!FX) return;
	// the engine cone points up (+Z) with its base at -50: lay it along Dir,
	// tip at the caster
	FX->SetActorRotation(FRotationMatrix::MakeFromZ(-Dir).Rotator());
	const float Width = 2.f * Range * FMath::Tan(FMath::DegreesToRadians(FMath::Min(Arc, 170.f) * 0.5f)) / 100.f;
	FX->SetActorLocation(From + Dir * Range * 0.5f);
	FX->Delay = Delay; FX->Life = 0.45f;
	FX->StartScale = FVector(Width * 0.2f, Width * 0.2f, Range / 100.f * 0.3f);
	FX->EndScale = FVector(Width, Width * 0.35f, Range / 100.f);
}

FName ACoHPowerFX::SocketFor(ECoHEmitter Emitter)
{
	switch (Emitter)
	{
	case ECoHEmitter::LeftHand: return TEXT("emit_hand_l");
	case ECoHEmitter::BothHands: return TEXT("emit_palms");
	case ECoHEmitter::Eyes: return TEXT("emit_eyes");
	case ECoHEmitter::Chest: return TEXT("emit_chest");
	case ECoHEmitter::Mouth: return TEXT("emit_mouth");
	case ECoHEmitter::Feet: return TEXT("emit_feet");
	case ECoHEmitter::Back: return TEXT("emit_back");
	case ECoHEmitter::Overhead: return TEXT("emit_overhead");
	default: return TEXT("emit_hand_r");
	}
}

FVector ACoHPowerFX::EmitterLocation(const AActor* Owner, ECoHEmitter Emitter)
{
	const ACharacter* C = Cast<ACharacter>(Owner);
	const USkeletalMeshComponent* M = C ? C->GetMesh() : nullptr;
	auto Bone = [&](const TCHAR* Name, FVector Fallback)
	{
		return M && M->DoesSocketExist(Name) ? M->GetSocketLocation(Name) : Fallback;
	};
	const FVector Base = Owner->GetActorLocation();
	const FVector Fwd = Owner->GetActorForwardVector();
	// the hero skeleton carries an emit_* socket for each emitter point
	if (M)
	{
		if (Emitter == ECoHEmitter::BothHands && M->DoesSocketExist(TEXT("emit_palm_l")) && M->DoesSocketExist(TEXT("emit_palm_r")))
			return (M->GetSocketLocation(TEXT("emit_palm_l")) + M->GetSocketLocation(TEXT("emit_palm_r"))) * 0.5f;
		const FName Socket = SocketFor(Emitter);
		if (M->DoesSocketExist(Socket)) return M->GetSocketLocation(Socket);
	}
	switch (Emitter)
	{
	case ECoHEmitter::LeftHand: return Bone(TEXT("hand_l"), Base + FVector(0, 0, 40) + Fwd * 40);
	case ECoHEmitter::BothHands: return (Bone(TEXT("hand_l"), Base) + Bone(TEXT("hand_r"), Base)) * 0.5f;
	case ECoHEmitter::Eyes: return Bone(TEXT("head"), Base + FVector(0, 0, 70)) + Fwd * 12 + FVector(0, 0, 6);
	case ECoHEmitter::Chest: return Bone(TEXT("spine_04"), Bone(TEXT("spine_03"), Base + FVector(0, 0, 40))) + Fwd * 15;
	case ECoHEmitter::Mouth: return Bone(TEXT("head"), Base + FVector(0, 0, 65)) + Fwd * 12 - FVector(0, 0, 4);
	case ECoHEmitter::Feet: return Base - FVector(0, 0, 80) + Fwd * 30;
	default: return Bone(TEXT("hand_r"), Base + FVector(0, 0, 40) + Fwd * 40);
	}
}

void ACoHPowerFX::Tick(float Dt)
{
	Super::Tick(Dt);
	if (Delay > 0.f)
	{
		Delay -= Dt;
		if (Delay > 0.f) return;
		// launch from wherever the hand is now
		if (bMoving) SetActorLocation(From);
	}
	Mesh->SetVisibility(true);
	Age += Dt;
	const float A = FMath::Clamp(Age / FMath::Max(Life, 0.01f), 0.f, 1.f);
	if (bMoving)
	{
		SetActorLocation(FMath::Lerp(From, To, A));
		SetActorScale3D(StartScale);
		if (A >= 1.f)
		{
			if (BurstRadius > 0.f) Burst(this, To, BurstRadius, Colour, 0.45f, 0.f);
			else Burst(this, To, 45.f, Colour, 0.2f, 0.f);
			Destroy();
		}
		return;
	}
	SetActorScale3D(FMath::Lerp(StartScale, EndScale, FMath::Sqrt(A)));
	if (Mat) Mat->SetScalarParameterValue(TEXT("Opacity"), 1.f - A);
	if (A >= 1.f) Destroy();
}

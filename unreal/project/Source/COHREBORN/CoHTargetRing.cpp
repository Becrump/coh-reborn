#include "CoHTargetRing.h"
#include "CoHPowers.h"
#include "ProceduralMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "GameFramework/Character.h"
#include "Components/CapsuleComponent.h"

// the placeholder power effects' unlit additive glow (Colour, Opacity)
static const TCHAR* RingMaterial = TEXT("/Game/CoH/FX/M_CoH_PowerFX.M_CoH_PowerFX");

static const FLinearColor FoeColour(1.f, 0.10f, 0.06f);
static const FLinearColor FriendColour(0.15f, 1.f, 0.30f);
static const FLinearColor ContactColour(0.25f, 0.55f, 1.f);

ACoHTargetRing::ACoHTargetRing()
{
	PrimaryActorTick.bCanEverTick = true;
	// after everyone has moved and animated, so the ring never trails its target
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
	SetReplicates(false);
	Ring = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Ring"));
	Ring->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Ring->SetCastShadow(false);
	Ring->bUseAsyncCooking = true;
	Ring->SetVisibility(false);
	RootComponent = Ring;
}

void ACoHTargetRing::BuildMesh()
{
	// a flat band of radius 1 (scaled to the target), a thin bright rim outside
	// a softer inner band, like the original's selection circle
	TArray<FVector> V; TArray<int32> T; TArray<FVector> N; TArray<FVector2D> UV; TArray<FLinearColor> C; TArray<FProcMeshTangent> Tg;
	const int32 Seg = 64;
	auto Band = [&](float In, float Out)
	{
		const int32 Base = V.Num();
		for (int32 i = 0; i <= Seg; ++i)
		{
			const float A = 2.f * PI * i / Seg;
			const FVector D(FMath::Cos(A), FMath::Sin(A), 0.f);
			V.Add(D * In); V.Add(D * Out);
			N.Add(FVector::UpVector); N.Add(FVector::UpVector);
			UV.Add(FVector2D(float(i) / Seg, 0.f)); UV.Add(FVector2D(float(i) / Seg, 1.f));
		}
		for (int32 i = 0; i < Seg; ++i)
		{
			const int32 a = Base + i * 2, b = a + 1, c = a + 2, d = a + 3;
			T.Append({ a, c, b, b, c, d });
		}
	};
	Band(0.86f, 1.f);       // rim
	Band(0.70f, 0.80f);     // inner band
	Ring->CreateMeshSection_LinearColor(0, V, T, N, UV, C, Tg, false);
	if (UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, RingMaterial, nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		Mat = UMaterialInstanceDynamic::Create(Base, this);
		Ring->SetMaterial(0, Mat);
	}
	else UE_LOG(LogTemp, Warning, TEXT("CoH target ring: %s missing, ring drawn without its glow"), RingMaterial);
}

void ACoHTargetRing::Follow(AActor* InTarget, const AActor* InViewer)
{
	Viewer = InViewer;
	if (InTarget != Target.Get()) { Target = InTarget; Age = 0.f; }
}

void ACoHTargetRing::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!Viewer.IsValid()) { Destroy(); return; }     // its hero has left
	AActor* T = Target.Get();
	if (!T || T->IsHidden())
	{
		Ring->SetVisibility(false);
		return;
	}
	if (Ring->GetNumSections() == 0) BuildMesh();
	Age += DeltaSeconds;

	// at the feet: the bottom of a character's capsule, else the actor's origin
	FVector Feet = T->GetActorLocation();
	float Radius = 60.f;
	if (const ACharacter* Ch = Cast<ACharacter>(T))
		if (const UCapsuleComponent* Cap = Ch->GetCapsuleComponent())
		{
			Feet.Z -= Cap->GetScaledCapsuleHalfHeight();
			Radius = FMath::Clamp(Cap->GetScaledCapsuleRadius() * 1.6f, 55.f, 450.f);
		}
	Feet.Z += 3.f;     // just above the floor, so it never sinks into it

	// foe or friend from the viewer's side; anyone without powers (contacts,
	// story people) is someone to talk to
	const UCoHPowerComponent* TC = UCoHPowerComponent::Of(T);
	const UCoHPowerComponent* Me = UCoHPowerComponent::Of(Viewer.Get());
	const FLinearColor Col = !TC ? ContactColour : (Me ? Me->IsFoe(TC) : !TC->bPlayerSide) ? FoeColour : FriendColour;
	const bool bDown = TC && TC->IsDefeated();

	// a pop when first selected, then a slow breathe
	const float Pop = 1.f + 0.35f * FMath::Exp(-Age * 10.f);
	const float Breathe = 0.5f + 0.5f * FMath::Sin(Age * 3.5f);
	SetActorLocation(Feet);
	SetActorScale3D(FVector(Radius * Pop * (1.f + 0.03f * Breathe), Radius * Pop * (1.f + 0.03f * Breathe), 1.f));
	if (Mat)
	{
		Mat->SetVectorParameterValue(TEXT("Colour"), Col);
		Mat->SetScalarParameterValue(TEXT("Opacity"), (bDown ? 0.35f : 1.f) * (0.75f + 0.25f * Breathe));
	}
	Ring->SetVisibility(true);
}

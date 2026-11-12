#include "CoHHeroStage.h"

#include "Camera/CameraComponent.h"
#include "CoHHeroCharacter.h"
#include "CoHPowers.h"
#include "Components/CapsuleComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	const FVector HeroLook(0.f, 0.f, 100.f);   // the camera aims at the hero's chest
	constexpr int32 NumSearchlights = 2;

	template <class T>
	T* Movable(T* C)
	{
		C->SetMobility(EComponentMobility::Movable);
		return C;
	}

	void Tint(UStaticMeshComponent* Mesh, const FLinearColor& Col)
	{
		// /Engine/BasicShapes/BasicShapeMaterial has a "Color" parameter
		if (UMaterialInstanceDynamic* M = Mesh->CreateDynamicMaterialInstance(0)) M->SetVectorParameterValue(TEXT("Color"), Col);
	}
}

ACoHHeroStage::ACoHHeroStage()
{
	PrimaryActorTick.bCanEverTick = true;
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderMesh(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> PlaneMesh(TEXT("/Engine/BasicShapes/Plane.Plane"));

	Root = Movable(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	SetRootComponent(Root);

	// dark polished floor, the pedestal (top at the actor's origin) and a holo ring around it
	Floor = Movable(CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Floor")));
	Floor->SetupAttachment(Root);
	Floor->SetStaticMesh(PlaneMesh.Object);
	Floor->SetRelativeLocation(FVector(0.f, 0.f, -30.f));
	Floor->SetRelativeScale3D(FVector(80.f, 80.f, 1.f));

	Pedestal = Movable(CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Pedestal")));
	Pedestal->SetupAttachment(Root);
	Pedestal->SetStaticMesh(CylinderMesh.Object);
	Pedestal->SetRelativeLocation(FVector(0.f, 0.f, -15.f));
	Pedestal->SetRelativeScale3D(FVector(2.4f, 2.4f, .3f));

	Ring = Movable(CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Ring")));
	Ring->SetupAttachment(Root);
	Ring->SetStaticMesh(CylinderMesh.Object);
	Ring->SetRelativeLocation(FVector(0.f, 0.f, -28.f));
	Ring->SetRelativeScale3D(FVector(2.8f, 2.8f, .04f));
	Ring->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	Camera = Movable(CreateDefaultSubobject<UCameraComponent>(TEXT("Camera")));
	Camera->SetupAttachment(Root);

	// key: warm, high and to the camera's left; rim: CoH blue from behind; fill: soft blue
	Key = Movable(CreateDefaultSubobject<USpotLightComponent>(TEXT("Key")));
	Key->SetupAttachment(Root);
	Key->SetRelativeLocation(FVector(320.f, 260.f, 380.f));
	Key->SetLightColor(FLinearColor(1.f, .9f, .78f));
	Key->SetOuterConeAngle(28.f);
	Key->SetInnerConeAngle(16.f);

	Rim = Movable(CreateDefaultSubobject<USpotLightComponent>(TEXT("Rim")));
	Rim->SetupAttachment(Root);
	Rim->SetRelativeLocation(FVector(-300.f, -170.f, 320.f));
	Rim->SetLightColor(FLinearColor(.2f, .6f, 1.f));
	Rim->SetOuterConeAngle(30.f);
	Rim->SetInnerConeAngle(18.f);

	Fill = Movable(CreateDefaultSubobject<UPointLightComponent>(TEXT("Fill")));
	Fill->SetupAttachment(Root);
	Fill->SetRelativeLocation(FVector(260.f, -260.f, 120.f));
	Fill->SetLightColor(FLinearColor(.45f, .6f, 1.f));
	Fill->SetAttenuationRadius(900.f);

	// the holo ring's glow on the hero's feet
	Under = Movable(CreateDefaultSubobject<UPointLightComponent>(TEXT("Under")));
	Under->SetupAttachment(Root);
	Under->SetRelativeLocation(FVector(110.f, 0.f, 8.f));
	Under->SetLightColor(FLinearColor(.25f, .7f, 1.f));
	Under->SetAttenuationRadius(260.f);
	Under->SetCastShadows(false);

	// two searchlights far behind, sweeping the haze like the HQ's
	for (int32 i = 0; i < NumSearchlights; ++i)
	{
		USpotLightComponent* S = Movable(CreateDefaultSubobject<USpotLightComponent>(*FString::Printf(TEXT("Searchlight%d"), i)));
		S->SetupAttachment(Root);
		S->SetRelativeLocation(FVector(-1100.f, i == 0 ? 520.f : -640.f, -20.f));
		S->SetLightColor(i == 0 ? FLinearColor(1.f, .85f, .5f) : FLinearColor(.5f, .75f, 1.f));
		S->SetOuterConeAngle(3.5f);
		S->SetInnerConeAngle(1.5f);
		S->SetAttenuationRadius(6000.f);
		S->SetVolumetricScatteringIntensity(6.f);
		S->SetCastShadows(false);
		Searchlights.Add(S);
	}

	Fog = Movable(CreateDefaultSubobject<UExponentialHeightFogComponent>(TEXT("Haze")));
	Fog->SetupAttachment(Root);
	Fog->SetRelativeLocation(FVector(0.f, 0.f, -30.f));
	Fog->SetFogDensity(.02f);
	Fog->SetFogInscatteringColor(FLinearColor(.01f, .02f, .05f));
	Fog->SetVolumetricFog(true);
	Fog->SetVolumetricFogScatteringDistribution(.6f);
}

void ACoHHeroStage::Build()
{
	Tint(Floor, FLinearColor(.012f, .018f, .03f));
	Tint(Pedestal, FLinearColor(.05f, .07f, .1f));
	Tint(Ring, FLinearColor(.2f, .65f, 1.f));

	Key->SetIntensityUnits(ELightUnits::Candelas);   Key->SetIntensity(KeyCandela);
	Rim->SetIntensityUnits(ELightUnits::Candelas);   Rim->SetIntensity(RimCandela);
	Fill->SetIntensityUnits(ELightUnits::Candelas);  Fill->SetIntensity(FillCandela);
	Under->SetIntensityUnits(ELightUnits::Candelas); Under->SetIntensity(FillCandela * .6f);
	for (USpotLightComponent* S : Searchlights) { S->SetIntensityUnits(ELightUnits::Candelas); S->SetIntensity(SearchlightCandela); }

	// point the stage lights at the hero
	const FVector Chest = HeroLook;
	Key->SetRelativeRotation((Chest - Key->GetRelativeLocation()).Rotation());
	Rim->SetRelativeRotation((Chest - Rim->GetRelativeLocation()).Rotation());

	// camera in front (+X), looking back at the hero
	const FVector CamAt(CameraDistance, 0.f, 120.f);
	Camera->SetRelativeLocation(CamAt);
	Camera->SetRelativeRotation((HeroLook - CamAt).Rotation());
	Camera->SetFieldOfView(CameraFOV);
	FPostProcessSettings& PP = Camera->PostProcessSettings;
	// one fixed exposure: auto exposure would pump in a room this dark
	PP.bOverride_AutoExposureMinBrightness = PP.bOverride_AutoExposureMaxBrightness = true;
	PP.AutoExposureMinBrightness = PP.AutoExposureMaxBrightness = ExposureEV;
	PP.bOverride_VignetteIntensity = true;  PP.VignetteIntensity = .55f;
	PP.bOverride_BloomIntensity = true;     PP.BloomIntensity = 1.2f;
	Camera->PostProcessBlendWeight = 1.f;
}

void ACoHHeroStage::BeginPlay()
{
	Super::BeginPlay();
	Build();
}

void ACoHHeroStage::ShowHero(const FString& HeroFile)
{
	if (bShownOnce && Shown == HeroFile && StageHero) return;
	bShownOnce = true;
	Shown = HeroFile;
	if (StageHero) { StageHero->Destroy(); StageHero = nullptr; }
	UWorld* World = GetWorld();
	if (!World) return;

	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	const float Half = GetDefault<ACoHHeroCharacter>()->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const FTransform At(FRotator(0.f, RestYaw + Yaw, 0.f), GetActorLocation() + FVector(0.f, 0.f, Half + 1.f));
	StageHero = World->SpawnActor<ACoHHeroCharacter>(ACoHHeroCharacter::StaticClass(), At, SP);
	if (!StageHero) return;
	StageHero->ShowcaseHero(HeroFile);
	PowerFaceTime = 0.f;
}

void ACoHHeroStage::Turn(float Degrees)
{
	Yaw = FRotator::NormalizeAxis(Yaw + Degrees);
	PowerFaceTime = 0.f;
}

void ACoHHeroStage::ResetTurn()
{
	Yaw = 0.f;
	PowerFaceTime = 0.f;
}

void ACoHHeroStage::PlayPower(FName Power)
{
	if (!StageHero || !StageHero->Powers) return;
	// side-on, facing screen right, so the effect crosses the view instead of the camera
	PowerFaceTime = 5.f;
	StageHero->SetActorRotation(FRotator(0.f, -90.f, 0.f));
	StageHero->Powers->PreviewPower(Power);
}

void ACoHHeroStage::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Time += DeltaSeconds;

	// searchlights: slow crossing sweeps
	for (int32 i = 0; i < Searchlights.Num(); ++i)
	{
		const float Period = i == 0 ? 11.f : 14.f;
		const float Swing = FMath::Sin((Time + i * 3.f) * TWO_PI / Period);
		Searchlights[i]->SetRelativeRotation(FRotator(62.f + 8.f * FMath::Cos(Time * .3f + i), (i == 0 ? -20.f : 20.f) + Swing * 26.f, 0.f));
	}

	// the hero eases back to the camera after a power, else follows the drag
	if (StageHero)
	{
		if (PowerFaceTime > 0.f) { PowerFaceTime -= DeltaSeconds; return; }
		const FRotator Want(0.f, RestYaw + Yaw, 0.f);
		StageHero->SetActorRotation(FMath::RInterpTo(StageHero->GetActorRotation(), Want, DeltaSeconds, 8.f));
	}
}

void ACoHHeroStage::EndPlay(const EEndPlayReason::Type Reason)
{
	if (StageHero) { StageHero->Destroy(); StageHero = nullptr; }
	Super::EndPlay(Reason);
}

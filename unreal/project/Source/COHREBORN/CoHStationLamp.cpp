#include "CoHStationLamp.h"

#include "Components/SceneComponent.h"
#include "Components/SpotLightComponent.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialParameterCollection.h"

ACoHStationLamp::ACoHStationLamp()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;   // only needed for the night switch

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);

	Light = CreateDefaultSubobject<USpotLightComponent>(TEXT("Light"));
	Light->SetupAttachment(Root);
	Light->SetRelativeRotation(FRotator(-90.f, 0.f, 0.f));   // a spot points along X: straight down
	Light->SetMobility(EComponentMobility::Movable);
	Light->SetIntensityUnits(ELightUnits::Candelas);
}

void ACoHStationLamp::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	Apply(1.f);
}

void ACoHStationLamp::BeginPlay()
{
	Super::BeginPlay();
	const bool bNight = bOnlyAtNight && NightCollection;
	SetActorTickEnabled(bNight);
	Apply(bNight ? 0.f : 1.f);
}

void ACoHStationLamp::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bOnlyAtNight && NightCollection)
	{
		Apply(FMath::Clamp(UKismetMaterialLibrary::GetScalarParameterValue(this, NightCollection, TEXT("Night")), 0.f, 1.f));
	}
}

void ACoHStationLamp::Apply(float NightFactor)
{
	if (!Light)
	{
		return;
	}
	Light->SetLightColor(Color);
	Light->SetIntensity(Intensity * NightFactor);
	Light->SetInnerConeAngle(FMath::Min(InnerCone, OuterCone - 1.f));
	Light->SetOuterConeAngle(OuterCone);
	Light->SetAttenuationRadius(Radius);
	Light->SetSourceRadius(SourceRadius);
	Light->SetCastShadows(bCastShadows);
	Light->SetVolumetricScatteringIntensity(ShaftStrength);
	Light->SetVisibility(NightFactor > 0.01f);
}

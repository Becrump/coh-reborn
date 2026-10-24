#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CoHStationLamp.generated.h"

class USceneComponent;
class USpotLightComponent;
class UMaterialParameterCollection;

/**
 * The light of a hanging lamp: a soft cone straight down. Place the actor just
 * under the shade (its origin is the lamp). Always on, or only at night.
 * Every setting updates live in the editor viewport.
 */
UCLASS()
class COHREBORN_API ACoHStationLamp : public AActor
{
	GENERATED_BODY()

public:
	ACoHStationLamp();

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY(VisibleAnywhere, Category = "Lamp")
	TObjectPtr<USceneComponent> Root;

	UPROPERTY(VisibleAnywhere, Category = "Lamp")
	TObjectPtr<USpotLightComponent> Light;

	/** Warm white by default. */
	UPROPERTY(EditAnywhere, Category = "Lamp")
	FLinearColor Color = FLinearColor(1.f, 0.88f, 0.70f);

	/** Candelas. Raise it if the cone reads weak under the night look. */
	UPROPERTY(EditAnywhere, Category = "Lamp", meta = (ClampMin = "0"))
	float Intensity = 5000.f;

	/** Full brightness inside this angle (degrees from straight down). */
	UPROPERTY(EditAnywhere, Category = "Lamp", meta = (ClampMin = "1", ClampMax = "80"))
	float InnerCone = 30.f;

	/** Falls to nothing at this angle. */
	UPROPERTY(EditAnywhere, Category = "Lamp", meta = (ClampMin = "2", ClampMax = "88"))
	float OuterCone = 65.f;

	/** How far the light reaches (cm): about the height of the ceiling above the floor, plus a little. */
	UPROPERTY(EditAnywhere, Category = "Lamp", meta = (ClampMin = "50"))
	float Radius = 700.f;

	/** Size of the bulb (cm); larger gives softer edges. */
	UPROPERTY(EditAnywhere, Category = "Lamp", meta = (ClampMin = "0"))
	float SourceRadius = 12.f;

	/** Off by default: many lamps with shadows are costly. */
	UPROPERTY(EditAnywhere, Category = "Lamp")
	bool bCastShadows = false;

	/** The visible shaft of light in fog. Needs Volumetric Fog on the fog actor; 0 turns it off. */
	UPROPERTY(EditAnywhere, Category = "Lamp", meta = (ClampMin = "0"))
	float ShaftStrength = 1.f;

	/** On only when MPC Night says it is night (set the collection below). Off: always lit. */
	UPROPERTY(EditAnywhere, Category = "Lamp|Night")
	bool bOnlyAtNight = false;

	/** The collection with a scalar "Night" (0 day, 1 night), for example MPC_CoH. */
	UPROPERTY(EditAnywhere, Category = "Lamp|Night")
	TObjectPtr<UMaterialParameterCollection> NightCollection;

private:
	void Apply(float NightFactor);
};

// Runs the monorail ride level (L_MonorailRide): the riders stand in a train
// car while tunnel sections and lights stream past the windows, and the
// server then travels everyone on to the destination zone (the Dest= URL
// option set by ARebornMonorail). The ride level is also the seamless-travel
// transition map, so the zone loads while the ride keeps playing.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RebornRideDirector.generated.h"

class UStaticMesh;
class UMaterialInterface;
class UStaticMeshComponent;

UCLASS()
class COHREBORN_API ARebornRideDirector : public AActor
{
	GENERATED_BODY()

public:
	ARebornRideDirector();

	/** Seconds of riding before the server moves on to the destination. */
	UPROPERTY(EditAnywhere, Category = "Ride")
	float RideSeconds = 18.f;

	/** Apparent train speed (cm/s) of the scrolling tunnel. */
	UPROPERTY(EditAnywhere, Category = "Ride")
	float Speed = 2400.f;

	UPROPERTY(EditAnywhere, Category = "Ride")
	TObjectPtr<UStaticMesh> WallMesh;

	UPROPERTY(EditAnywhere, Category = "Ride")
	TObjectPtr<UMaterialInterface> WallMaterial;

	UPROPERTY(EditAnywhere, Category = "Ride")
	TObjectPtr<UMaterialInterface> LightMaterial;

	/** Tunnel section length (cm) and how many sections loop past. */
	UPROPERTY(EditAnywhere, Category = "Ride")
	float SectionLength = 2500.f;

	UPROPERTY(EditAnywhere, Category = "Ride")
	int32 Sections = 14;

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	UPROPERTY()
	TArray<TObjectPtr<USceneComponent>> Rings;

	float Elapsed = 0.f;
	bool bLeft = false;
	FString Destination;
};

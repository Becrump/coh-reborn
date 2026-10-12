// A rideable monorail train that runs a timetable along a track spline.
//
// The train's place on the line is a pure function of the server clock
// (AGameStateBase::GetServerWorldTimeSeconds), so every client shows the
// same train in the same place without streaming positions: the actor only
// replicates its existence. The cars are movable static meshes with walkable
// floors, so players who step inside ride along (character "based"
// movement). At each stop the train eases in, opens its doors, waits and
// leaves; at the ends of the line it reverses.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RebornMonorail.generated.h"

class USplineComponent;
class UStaticMesh;
class UStaticMeshComponent;

USTRUCT(BlueprintType)
struct FRebornMonorailStop
{
	GENERATED_BODY()

	/** Shown to riders ("Atlas Park", "Steel Canyon"...). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Monorail")
	FText Name;

	/** Where the middle of the train stops (world space; snapped to the track). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Monorail")
	FVector Location = FVector::ZeroVector;

	/** Distance along the track, filled in at BeginPlay. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Monorail")
	float Distance = 0.f;
};

UCLASS()
class COHREBORN_API ARebornMonorail : public AActor
{
	GENERATED_BODY()

public:
	ARebornMonorail();

	/** Actor whose spline is the track (beam top = spline). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Monorail")
	TObjectPtr<AActor> Track;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Monorail")
	TArray<FRebornMonorailStop> Stops;

	UPROPERTY(EditAnywhere, Category = "Monorail|Look")
	TObjectPtr<UStaticMesh> CarMesh;

	/** End cars (nose forward on the leading end). */
	UPROPERTY(EditAnywhere, Category = "Monorail|Look")
	TObjectPtr<UStaticMesh> NoseMesh;

	UPROPERTY(EditAnywhere, Category = "Monorail|Look")
	TObjectPtr<UStaticMesh> DoorMesh;

	UPROPERTY(EditAnywhere, Category = "Monorail")
	int32 NumCars = 3;

	/** Car length plus gap (cm). */
	UPROPERTY(EditAnywhere, Category = "Monorail")
	float CarPitch = 1550.f;

	UPROPERTY(EditAnywhere, Category = "Monorail")
	float CruiseSpeed = 2200.f;

	UPROPERTY(EditAnywhere, Category = "Monorail")
	float Acceleration = 120.f;

	/** Seconds at each stop with the doors open. */
	UPROPERTY(EditAnywhere, Category = "Monorail")
	float DwellSeconds = 25.f;

	/** Seconds the train waits at each end of the line before reversing. */
	UPROPERTY(EditAnywhere, Category = "Monorail")
	float TurnaroundSeconds = 30.f;

	/** Door x positions on a car (cm from the car centre) and how far a leaf slides. */
	UPROPERTY(EditAnywhere, Category = "Monorail")
	TArray<float> DoorX = { -350.f, 350.f };

	UPROPERTY(EditAnywhere, Category = "Monorail")
	float DoorSlide = 85.f;

	/** Name of the stop the train is at (empty while moving). */
	UFUNCTION(BlueprintPure, Category = "Monorail")
	FText CurrentStopName() const;

	/** Name of the next stop. */
	UFUNCTION(BlueprintPure, Category = "Monorail")
	FText NextStopName() const;

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void OnConstruction(const FTransform& Transform) override;

private:
	struct FLeg
	{
		float From, To;      // distances along the track
		float Start;         // timetable time the leg starts (s)
		float Move;          // seconds moving
		float Wait;          // seconds waiting at To
		int32 StopTo;        // stop index at To, or INDEX_NONE (line end)
	};

	USplineComponent* TrackSpline() const;
	void BuildCars();
	void BuildTimetable();
	/** Distance along the track and door opening (0..1) at timetable time T. */
	void Evaluate(double T, float& OutDist, float& OutDoors, int32& OutStop, int32& OutNext) const;
	float MoveTime(float Length) const;
	float TravelDistance(float Elapsed, float Length) const;
	void PlaceCars(float Dist, float Doors, float Direction);

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Cars;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Doors;

	TArray<FLeg> Legs;
	float Cycle = 0.f;
	int32 AtStop = INDEX_NONE;
	int32 NextStop = INDEX_NONE;
};

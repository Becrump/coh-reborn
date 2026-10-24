// Brings a converted City of Heroes zone to life: civilians walking CoH's
// NPC nodes, traffic driving CoH's lane arrows, the monorail, the blimp and
// police drones. Reads <zone>_life.json written by coh2unreal.life.
//
// Everything here is cosmetic and runs on each client around its camera
// (no replication): gameplay NPCs such as encounter victims belong to the
// server-side encounter system instead.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CoHLifeManager.generated.h"

class USkeletalMeshComponent;
class UStaticMeshComponent;
class UInstancedStaticMeshComponent;
class USkeletalMesh;
class UStaticMesh;
class UAnimSequence;
class UMaterialParameterCollection;

/** A directed graph of points with a travel direction (lanes, routes). */
struct FCoHGraph
{
	TArray<FVector> P;          // position (cm)
	TArray<FVector> D;          // unit direction of travel (XY, Z = 0)
	TArray<TArray<int32>> Next; // nodes reachable from each node

	int32 Num() const { return P.Num(); }
	void Build(float Radius, float MaxLateral, float MaxRise, int32 MaxNext);
	/** Position and heading along the curve From->To at T (0..1). */
	void Eval(int32 From, int32 To, float T, FVector& OutPos, FRotator& OutRot) const;
	float SegLength(int32 From, int32 To) const { return FVector::Dist(P[From], P[To]); }
};

/** Something moving along a graph. */
struct FCoHMover
{
	int32 From = INDEX_NONE;
	int32 To = INDEX_NONE;
	int32 Prev = INDEX_NONE;
	float T = 0.f;
	float Speed = 0.f;
	float Pause = 0.f;
	int32 Kind = 0;             // mesh variant
	int32 Instance = INDEX_NONE; // ISM instance index (cars)
	float Fear = 0.f;            // seconds left fleeing
	FVector Danger = FVector::ZeroVector;
	FVector Velocity = FVector::ZeroVector;
	float BlockedSeconds = 0.f;
	USceneComponent* Comp = nullptr;
	int32 Route = INDEX_NONE;    // walking circuit being followed (civilians)
	int32 RouteStep = 0;         // index of From in that circuit
	float HeldUntil = 0.f;       // held by villains until this clock time (renewed while held)
	int32 HeldBy = 0;            // gang id holding them (0 = free)
};

/** A walk link that crosses a road at a signalled junction. */
struct FCoHCrossing
{
	TArray<int32> Signals;   // indices into the signal list that stop the crossed traffic
	float TIn = 0.f;         // link parameter (lower node -> higher node) at the first lane line
	float TOut = 0.f;        // ... and at the last one
};

UCLASS()
class COHREBORN_API ACoHLifeManager : public AActor
{
	GENERATED_BODY()

public:
	ACoHLifeManager();

	/** <zone>_life.json from coh2unreal (absolute path). */
	UPROPERTY(EditAnywhere, Category = "CoH|Data")
	FFilePath LifeJson;

	/** Simulate only within this distance of the camera (cm). */
	UPROPERTY(EditAnywhere, Category = "CoH|Data")
	float ActiveRadius = 12000.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Crowds")
	float CrowdDensity = 1.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CoH|Traffic")
	float TrafficDensity = 1.f;

	// --- civilians ---
	UPROPERTY(EditAnywhere, Category = "CoH|Civilians")
	TArray<TObjectPtr<USkeletalMesh>> CivilianMeshes;

	UPROPERTY(EditAnywhere, Category = "CoH|Civilians")
	TObjectPtr<UAnimSequence> WalkAnim;

	UPROPERTY(EditAnywhere, Category = "CoH|Civilians")
	TObjectPtr<UAnimSequence> IdleAnim;

	/** Played while fleeing; speed RunAnimSpeed. */
	UPROPERTY(EditAnywhere, Category = "CoH|Civilians")
	TObjectPtr<UAnimSequence> RunAnim;

	UPROPERTY(EditAnywhere, Category = "CoH|Civilians")
	float RunSpeed = 480.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Civilians")
	float RunAnimSpeed = 500.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Civilians")
	int32 MaxCivilians = 120;

	UPROPERTY(EditAnywhere, Category = "CoH|Civilians")
	float WalkSpeed = 140.f;

	/** Speed the walk animation was authored at (cm/s), for play rate. */
	UPROPERTY(EditAnywhere, Category = "CoH|Civilians")
	float WalkAnimSpeed = 150.f;

	// --- traffic ---
	UPROPERTY(EditAnywhere, Category = "CoH|Traffic")
	TArray<TObjectPtr<UStaticMesh>> CarMeshes;

	UPROPERTY(EditAnywhere, Category = "CoH|Traffic")
	int32 MaxCars = 30;

	UPROPERTY(EditAnywhere, Category = "CoH|Traffic")
	float CarSpeed = 1100.f;

	/** Cars keep at least this much road ahead clear (cm). */
	UPROPERTY(EditAnywhere, Category = "CoH|Traffic")
	float CarGap = 900.f;

	// --- monorail, blimp, drones ---
	UPROPERTY(EditAnywhere, Category = "CoH|Ambient")
	TObjectPtr<UStaticMesh> MonorailMesh;

	UPROPERTY(EditAnywhere, Category = "CoH|Ambient")
	float MonorailSpeed = 2200.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Ambient")
	TObjectPtr<UStaticMesh> BlimpMesh;

	UPROPERTY(EditAnywhere, Category = "CoH|Ambient")
	float BlimpSpeed = 700.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Ambient")
	TObjectPtr<UStaticMesh> DroneMesh;

	UPROPERTY(EditAnywhere, Category = "CoH|Ambient")
	int32 MaxDrones = 24;

	/** Something dangerous happened (a fight, an explosion): civilians
	 *  within Radius run away from it and cars nearby stop. Call from any
	 *  gameplay code on each client; cheap. */
	UFUNCTION(BlueprintCallable, Category = "CoH", meta = (WorldContext = "WorldContextObject"))
	static void ReportDanger(UObject* WorldContextObject, FVector Location, float Radius = 2500.f, float Seconds = 8.f);

	// --- villains harassing civilians (server) ---
	/** A free, visible civilian within Radius of At, or INDEX_NONE. */
	int32 FindCivilianNear(const FVector& At, float Radius) const;
	FVector CivilianLocation(int32 Index) const;
	/** Stop the civilian, face Toward and cower. A hold lasts HoldSeconds and
	 *  must be renewed, so a civilian is never left trapped if the gang vanishes. */
	bool HoldCivilian(int32 Index, int32 Gang, const FVector& Toward, float HoldSeconds = 3.f);
	/** Let them go: they run from From; with Hero set they first turn and thank the hero. */
	void ReleaseCivilian(int32 Index, int32 Gang, const FVector& From, AActor* Hero = nullptr);
	/** Pose for a held civilian (a flinch held on one frame). */
	UPROPERTY(EditAnywhere, Category = "CoH|Civilians")
	TObjectPtr<UAnimSequence> CowerAnim;
	static ACoHLifeManager* Get(const UObject* WorldContext);

	/** Console/testing: danger at the camera's look point. */
	UFUNCTION(Exec)
	void CoHPanic();

	// --- day/night ---
	/** MPC_CoH: its Night value (0 day .. 1 night) scales the city. */
	UPROPERTY(EditAnywhere, Category = "CoH|Night")
	TObjectPtr<UMaterialParameterCollection> NightCollection;

	/** Share of civilians / moving cars still out at full night. */
	UPROPERTY(EditAnywhere, Category = "CoH|Night")
	float NightCivilianScale = 0.3f;

	UPROPERTY(EditAnywhere, Category = "CoH|Night")
	float NightCarScale = 0.35f;

	/** Cars parked along the curbs near the camera, by day and at night. */
	UPROPERTY(EditAnywhere, Category = "CoH|Night")
	int32 ParkedCarsDay = 12;

	UPROPERTY(EditAnywhere, Category = "CoH|Night")
	int32 ParkedCarsNight = 30;

	/** Counts after loading, for checking in the editor. */
	UPROPERTY(VisibleAnywhere, Category = "CoH|Data")
	FString Status;

protected:
	virtual void BeginPlay() override;

public:
	virtual void Tick(float DeltaSeconds) override;

private:
	bool LoadLife();
	void BuildWalkGraph();
	FVector CameraLocation() const;
	int32 RandomNodeNear(const FCoHGraph& G, const FVector& Center, float MinDist, float MaxDist) const;
	void PickNext(const FCoHGraph& G, FCoHMover& M) const;
	float GroundZ(const FVector& P) const;

	void TickWalkers(float Dt, const FVector& Cam);
	void TickCars(float Dt, const FVector& Cam);
	void TickRoute(FCoHGraph& G, FCoHMover& M, float Dt);
	void TickDrones(float Dt, const FVector& Cam);

	FCoHGraph Lanes;     // road traffic
	FCoHGraph Monorail;
	FCoHGraph BlimpRoute;
	FCoHGraph Walk;      // civilians: undirected links in Next
	TArray<FVector> DronePosts;

	TArray<FCoHMover> Walkers;
	TArray<FCoHMover> Cars;
	TArray<FCoHMover> Drones;
	FCoHMover Train;
	FCoHMover Blimp;

	UPROPERTY()
	TArray<TObjectPtr<UInstancedStaticMeshComponent>> CarISMs;

	float Clock = 0.f;
	float Night = 0.f;

	/** Curb spots beside the outermost lanes (position, facing). */
	TArray<FTransform> ParkingSpots;
	TArray<FCoHMover> Parked;   // From = spot index, Kind/Instance = ISM
	float ParkedRefresh = 0.f;
	void FindParkingSpots();
	void TickParked(float Dt, const FVector& Cam);

	/** Real headlights (two spotlights each) for the cars nearest the
	 *  camera at night; the rest only show their glowing lamp textures. */
	UPROPERTY(EditAnywhere, Category = "CoH|Traffic")
	int32 HeadlightCars = 10;

	UPROPERTY()
	TArray<TObjectPtr<class USpotLightComponent>> Headlights;
	void UpdateHeadlights(const TArray<FVector>& Positions, const TArray<FVector>& Headings, int32 ActiveCars, const FVector& Cam);

	/** Share of civilians that walk long circuits instead of wandering. */
	UPROPERTY(EditAnywhere, Category = "CoH|Crowds")
	float CircuitShare = 0.75f;

	UPROPERTY(EditAnywhere, Category = "CoH|Crowds")
	int32 NumCircuits = 16;

	/** Long walking loops through the city (walk node indices, closed). */
	TArray<TArray<int32>> Circuits;
	void BuildCircuits();
	bool WalkPath(int32 From, int32 To, TArray<int32>& Out) const;
	bool RouteSpotNear(const FVector& Center, float MinDist, float MaxDist, int32& OutRoute, int32& OutStep) const;

	// --- crowd spread and road crossings ---
	/** Walk links that cross a road are kept only at signalled junctions, and civilians
	 *  wait at the kerb for a red light. Off: the old free crossing everywhere. */
	UPROPERTY(EditAnywhere, Category = "CoH|Crowds")
	bool bSignalCrossings = true;

	/** A signal controls a crossing if its stop line is this far ahead of it (cm) ... */
	UPROPERTY(EditAnywhere, Category = "CoH|Crowds")
	float CrossingSignalRange = 3000.f;

	/** ... and no further than this to the side of the lane (cm). */
	UPROPERTY(EditAnywhere, Category = "CoH|Crowds")
	float CrossingSignalLateral = 900.f;

	/** Walk nodes are thinned where they bunch: density is counted within this radius (cm). */
	UPROPERTY(EditAnywhere, Category = "CoH|Crowds")
	float DensityRadius = 3000.f;

	/** Draw crossings (green: safe now, red: wait) and log the busiest 100 m cells. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CoH|Crowds")
	bool bDebugCrowds = false;

	TMap<uint64, FCoHCrossing> Crossings;
	TArray<float> WalkWeight;            // per walk node: chance to accept it as a spot, evens out density
	float DebugClock = 0.f;
	static uint64 LinkKey(int32 A, int32 B) { return (uint64(FMath::Min(A, B)) << 32) | uint32(FMath::Max(A, B)); }
	void BuildCrossings();
	void BuildWalkWeights();
	bool WalkAccept(int32 Node) const;
	const FCoHCrossing* FindCrossing(int32 A, int32 B, float& OutTIn, float& OutTOut) const;
	bool CrossingIsSafe(const FCoHCrossing& C, float SpanSeconds) const;
	void DebugCrowds(float Dt);

	// --- traffic signals ---
	/** Writes SignalClock (server seconds) here each frame; the signal-head
	 *  material reads it, so lamps and stopping cars share one timing. */
	UPROPERTY(EditAnywhere, Category = "CoH|Traffic")
	TObjectPtr<UMaterialParameterCollection> SignalCollection;

	/** Seconds for a full signal cycle (each direction: green, amber, red). */
	UPROPERTY(EditAnywhere, Category = "CoH|Traffic")
	float SignalCycle = 40.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Traffic")
	float SignalAmber = 3.f;

public:
	/** 0 green, 1 amber, 2 red for a signal group at junction phase Offset. */
	UFUNCTION(BlueprintPure, Category = "CoH|Traffic")
	int32 SignalState(float Offset, int32 Group) const;

private:
	/** Stop lines from the life file: where a lane meets a signalled junction. */
	struct FCoHSignal { FVector P; FVector D; float Offset; int32 Group; };
	TArray<FCoHSignal> Signals;
	double SignalTime = 0.0;

	struct FDanger { FVector P; float Radius; float Until; };
	TArray<FDanger> Dangers;
	void StartFleeing(FCoHMover& M, const FVector& From, float Seconds);
};

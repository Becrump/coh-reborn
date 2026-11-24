// The original game's civilians and traffic (server/spawnarea rules,
// generator beacons, the BasicBeacon walking wire and the TrafficBeacon
// lanes), read from <out>/civilians/<zone>.json (tools/zones/civilians.py).
// Each zone keeps the original population (every generator up to its
// MaxActiveEntities, MaxNPCCount for the zone, about one spawn try per
// generator a second) while someone is in or near it; only the nearest are
// drawn, out to the original fade distances (270 ft people, 950 ft cars).
//
// Cosmetic and client side like the life manager: every PC runs its own,
// nothing replicates. See docs/civilians.md.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Async/Future.h"
#include "CoHCivilians.generated.h"

class USkeletalMesh;
class USkeletalMeshComponent;
class UAnimSequenceBase;

struct FCoHCivType
{
	FString Name;
	bool bCar = false;
	TArray<FString> Costumes;
	int32 Max = 600, Scared = 0, TypeNum = 0, Alive = 0;
	float Run = 0.7f, RunVar = 0.f;     // feet per server tick (30 a second)
};

struct FCoHCivGen
{
	int32 Max = 1, SpawnMax = -1;
	TArray<int32> Types;
};

struct FCoHCivSpawn
{
	int32 Gen = 0;
	FVector P = FVector::ZeroVector;
	float Yaw = 0.f;
	int32 Alive = 0, Spawned = 0;
};

struct FCoHCivZone
{
	FString Id, Name;
	int32 MaxNpc = 600, Npcs = 0;
	TArray<FCoHCivType> Types;
	TArray<FCoHCivGen> Gens;
	TArray<FCoHCivSpawn> Spawns;
	TArray<FVector> WireP;
	TArray<TArray<int32>> WireNext;
	TArray<FVector> LaneP;
	TArray<FVector> LaneDir;
	TArray<TArray<int32>> LaneNext;
	TArray<int32> LaneTypeNum;
	TSet<int32> LaneKill;
	TMap<FIntPoint, TArray<int32>> WireGrid, LaneGrid;
	FBox2D Bounds = FBox2D(ForceInit);
	TSet<uint64> Blocked;              // wire links found blocked (the original needed a clear line)
	bool bActive = false;
	double QuietSince = 0.0;

	int32 Nearest(const TArray<FVector>& P, const TMap<FIntPoint, TArray<int32>>& Grid, const FVector& At, float MaxDist, TFunctionRef<bool(int32)> Ok) const;
};

struct FCoHCivAgent
{
	int32 Zone = 0, Type = 0, Spawn = 0, Look = 0;
	bool bCar = false, bDead = false;
	FVector Pos = FVector::ZeroVector, Goal = FVector::ZeroVector;
	float Yaw = 0.f, Speed = 0.f;      // Speed: the type's run speed, cm/s
	int32 Prev = INDEX_NONE, At = INDEX_NONE, To = INDEX_NONE;
	// cars: a curve from P0 to P1 (directions D0, D1), T along it
	FVector P0, P1, D0, D1;
	float T = 0.f, SegLen = 1.f;
	double ScaredUntil = 0.0, FaceUntil = 0.0;
	FVector Danger = FVector::ZeroVector;
	int32 Vis = INDEX_NONE;
	float GroundZ = 0.f, NextGround = 0.f;
	bool bGround = false;
};

UCLASS(Config = Game)
class COHREBORN_API ACoHCivilians : public AActor
{
	GENERATED_BODY()
public:
	ACoHCivilians();
	static ACoHCivilians* Get(const UWorld* World);
	/** Something frightening at Location (fights, powers): the original's afraid state. */
	static void ReportDanger(const UObject* WorldContext, const FVector& Location, float Radius);

	virtual void BeginPlay() override;
	virtual void Tick(float Dt) override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	/** "/civilians": on, off, or a status line. */
	FString Command(const FString& Arg);

	UPROPERTY(EditAnywhere, Config, Category = "CoH|Civilians") bool bEnabled = true;
	/** Zones left to the upgraded city life (the rebuilt Atlas Park has its own streets). */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Civilians") TArray<FString> ModernZones = {TEXT("city_01_01")};
	/** Generated types left out (the monorail runs as its own train). */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Civilians") TArray<FString> SkipTypes = {TEXT("Monorail")};
	/** A zone comes alive while the camera is this close to it (cm). */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Civilians") float WakeDistance = 30000.f;
	/** The original fade distances: people 270 ft, cars 950 ft. */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Civilians") float PeopleDrawDistance = 8230.f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Civilians") float CarDrawDistance = 28960.f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Civilians") int32 MaxDrawnPeople = 150;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Civilians") int32 MaxDrawnCars = 60;
	/** Rotation that turns an imported model to face +X. */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Civilians") float MeshYaw = -90.f;

private:
	struct FLook
	{
		FString Name;
		USkeletalMesh* Mesh = nullptr;      // held by Keep
		UAnimSequenceBase* Idle = nullptr, *Walk = nullptr, *Run = nullptr, *Fear = nullptr, *FearRun = nullptr;
		bool bTried = false;
	};
	struct FVis
	{
		USkeletalMeshComponent* Comp = nullptr;   // held by Comps
		int32 Agent = INDEX_NONE;
		int32 Look = INDEX_NONE;
		UAnimSequenceBase* Playing = nullptr;
	};

	FString Folder;
	bool bOneWorld = false;
	TMap<FString, FVector2D> Offsets;
	TArray<FCoHCivZone> Zones;
	TMap<FString, int32> ZoneIndex;
	TMap<int32, TFuture<TSharedPtr<FCoHCivZone>>> Loading;
	TArray<FCoHCivAgent> Agents;
	TArray<FLook> Looks;
	TMap<FString, int32> LookIndex;
	TArray<FVis> Pool;
	UPROPERTY() TArray<TObjectPtr<USkeletalMeshComponent>> Comps;
	UPROPERTY() TArray<TObjectPtr<UObject>> Keep;
	double NextSpawn = 0.0, NextStatus = 0.0;
	int32 LoadsThisTick = 0;

	FVector CameraLocation() const;
	void WakeZones(const FVector& Cam);
	static TSharedPtr<FCoHCivZone> LoadZone(const FString& File, const FString& Id, FVector2D Offset);
	void Populate(int32 ZoneIdx);
	bool SpawnOne(int32 ZoneIdx, int32 SpawnIdx);
	void Remove(FCoHCivAgent& A);
	void StepPerson(FCoHCivAgent& A, float Dt, double Now);
	void StepCar(FCoHCivAgent& A, float Dt);
	bool NextWire(FCoHCivAgent& A, bool bNear);
	bool NextLane(FCoHCivAgent& A);
	void Draw(const FVector& Cam, float Dt, double Now);
	int32 LookFor(const FString& Costume);
	FLook* Resolve(int32 Look);
	void Scare(const FVector& Location, float Radius);
};

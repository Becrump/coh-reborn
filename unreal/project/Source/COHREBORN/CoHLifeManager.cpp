#include "CoHLifeManager.h"

#include "Animation/AnimSequence.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialParameterCollection.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	// traffic tuning kept here (not UPROPERTYs) so Live Coding can apply it
	constexpr float CarScale = 1.05f;        // pack cars read a touch small next to CoH buildings
	constexpr float CarBodyRadius = 260.f;   // half a car length: closer centres overlap
	constexpr float CrossLook = 1.4f;        // x CarGap: how far ahead to watch crossing traffic
	constexpr float CrowdRadius = 300.f;     // civilians closer than this count as a crowd
	constexpr int32 MinWalkArea = 8;         // walk-graph islands smaller than this are skipped
}

DEFINE_LOG_CATEGORY_STATIC(LogCoHLife, Log, All);

// ------------------------------------------------------------------ graph

void FCoHGraph::Build(float Radius, float MaxLateral, float MaxRise, int32 MaxNext)
{
	// Link each node to the nearest nodes ahead of it in its direction of
	// travel (lane arrows), allowing gentle turns at junctions.
	const float Cell = Radius;
	TMap<FIntPoint, TArray<int32>> Grid;
	for (int32 i = 0; i < P.Num(); ++i)
	{
		Grid.FindOrAdd(FIntPoint(FMath::FloorToInt(P[i].X / Cell), FMath::FloorToInt(P[i].Y / Cell))).Add(i);
	}
	Next.SetNum(P.Num());
	for (int32 i = 0; i < P.Num(); ++i)
	{
		const FIntPoint C(FMath::FloorToInt(P[i].X / Cell), FMath::FloorToInt(P[i].Y / Cell));
		TArray<TPair<float, int32>> Cands;
		for (int32 dx = -1; dx <= 1; ++dx)
		{
			for (int32 dy = -1; dy <= 1; ++dy)
			{
				const TArray<int32>* Bucket = Grid.Find(FIntPoint(C.X + dx, C.Y + dy));
				if (!Bucket)
				{
					continue;
				}
				for (int32 j : *Bucket)
				{
					if (j == i || FMath::Abs(P[j].Z - P[i].Z) > MaxRise)
					{
						continue;
					}
					const FVector Delta = P[j] - P[i];
					const FVector2D Flat(Delta.X, Delta.Y);
					const float Dist = Flat.Size();
					if (Dist < 50.f || Dist > Radius)
					{
						continue;
					}
					const FVector2D Dir(D[i].X, D[i].Y);
					const float Ahead = FVector2D::DotProduct(Dir, Flat);
					if (Ahead < 0.5f * Dist)
					{
						continue;   // not in front
					}
					const float Lateral = FMath::Abs(FVector2D::CrossProduct(Dir, Flat));
					if (Lateral > FMath::Max(MaxLateral, Dist * 0.6f))
					{
						continue;
					}
					if (FVector2D::DotProduct(Dir, FVector2D(D[j].X, D[j].Y)) < -0.2f)
					{
						continue;   // oncoming lane
					}
					Cands.Add({Dist + Lateral * 3.f, j});
				}
			}
		}
		Cands.Sort([](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key < B.Key; });
		for (int32 k = 0; k < Cands.Num() && k < MaxNext; ++k)
		{
			Next[i].Add(Cands[k].Value);
		}
	}
}

void FCoHGraph::Eval(int32 From, int32 To, float T, FVector& OutPos, FRotator& OutRot) const
{
	const FVector A = P[From], B = P[To];
	const float Len = FVector::Dist2D(A, B);
	if (D[From].IsNearlyZero() || D[To].IsNearlyZero())
	{
		OutPos = FMath::Lerp(A, B, T);
		OutRot = (B - A).GetSafeNormal2D().Rotation();
		return;
	}
	// cubic Hermite through both arrows, tangents along their directions
	const FVector Ta = D[From] * Len, Tb = D[To] * Len;
	const float t2 = T * T, t3 = t2 * T;
	OutPos = (2 * t3 - 3 * t2 + 1) * A + (t3 - 2 * t2 + T) * Ta + (-2 * t3 + 3 * t2) * B + (t3 - t2) * Tb;
	OutPos.Z = FMath::Lerp(A.Z, B.Z, T);
	FVector Vel = (6 * t2 - 6 * T) * A + (3 * t2 - 4 * T + 1) * Ta + (-6 * t2 + 6 * T) * B + (3 * t2 - 2 * T) * Tb;
	Vel.Z = 0.f;
	OutRot = Vel.IsNearlyZero() ? D[From].Rotation() : Vel.Rotation();
}

// ----------------------------------------------------------------- loading

ACoHLifeManager::ACoHLifeManager()
{
	PrimaryActorTick.bCanEverTick = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

static void ReadGraph(const TSharedPtr<FJsonObject>& Root, const TCHAR* Key, FCoHGraph& G)
{
	const TArray<TSharedPtr<FJsonValue>>* Arr;
	if (!Root->TryGetArrayField(Key, Arr))
	{
		return;
	}
	for (const TSharedPtr<FJsonValue>& V : *Arr)
	{
		const TSharedPtr<FJsonObject> O = V->AsObject();
		const TArray<TSharedPtr<FJsonValue>>& Pv = O->GetArrayField(TEXT("p"));
		const TArray<TSharedPtr<FJsonValue>>& Dv = O->GetArrayField(TEXT("d"));
		G.P.Add(FVector(Pv[0]->AsNumber(), Pv[1]->AsNumber(), Pv[2]->AsNumber()));
		G.D.Add(FVector(Dv[0]->AsNumber(), Dv[1]->AsNumber(), 0.f).GetSafeNormal());
	}
}

static FVector ReadPoint(const TSharedPtr<FJsonValue>& V)
{
	const TArray<TSharedPtr<FJsonValue>>& Pv = V->AsArray();
	return FVector(Pv[0]->AsNumber(), Pv[1]->AsNumber(), Pv[2]->AsNumber());
}

bool ACoHLifeManager::LoadLife()
{
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *LifeJson.FilePath))
	{
		Status = FString::Printf(TEXT("could not read %s"), *LifeJson.FilePath);
		UE_LOG(LogCoHLife, Warning, TEXT("%s"), *Status);
		return false;
	}
	TSharedPtr<FJsonObject> Root;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		Status = TEXT("bad life json");
		return false;
	}
	ReadGraph(Root, TEXT("traffic"), Lanes);
	ReadGraph(Root, TEXT("monorail"), Monorail);
	ReadGraph(Root, TEXT("blimp"), BlimpRoute);
	const TArray<TSharedPtr<FJsonValue>>* Arr;
	if (Root->TryGetArrayField(TEXT("npc"), Arr))
	{
		for (const TSharedPtr<FJsonValue>& V : *Arr)
		{
			Walk.P.Add(ReadPoint(V));
			Walk.D.Add(FVector::ZeroVector);
		}
	}
	if (Root->TryGetArrayField(TEXT("drones"), Arr))
	{
		for (const TSharedPtr<FJsonValue>& V : *Arr)
		{
			DronePosts.Add(ReadPoint(V));
		}
	}
	Lanes.Build(4500.f, 250.f, 300.f, 3);
	Monorail.Build(8000.f, 300.f, 600.f, 2);
	BlimpRoute.Build(30000.f, 3000.f, 5000.f, 2);
	BuildWalkGraph();
	BuildCircuits();
	FindParkingSpots();
	return true;
}

void ACoHLifeManager::BuildWalkGraph()
{
	// Civilians may walk between nodes within 25 m that can see each other
	// (traces only block once the level has collision).
	const float Radius = 4000.f;     // CoH walk nodes are often 25-40 m apart
	UWorld* World = GetWorld();
	FCollisionQueryParams Params(SCENE_QUERY_STAT(CoHWalkLink), false, this);
	TMap<FIntPoint, TArray<int32>> Grid;
	for (int32 i = 0; i < Walk.Num(); ++i)
	{
		Grid.FindOrAdd(FIntPoint(FMath::FloorToInt(Walk.P[i].X / Radius), FMath::FloorToInt(Walk.P[i].Y / Radius))).Add(i);
	}
	Walk.Next.SetNum(Walk.Num());
	for (int32 i = 0; i < Walk.Num(); ++i)
	{
		const FIntPoint C(FMath::FloorToInt(Walk.P[i].X / Radius), FMath::FloorToInt(Walk.P[i].Y / Radius));
		TArray<TPair<float, int32>> Near;
		for (int32 dx = -1; dx <= 1; ++dx)
		{
			for (int32 dy = -1; dy <= 1; ++dy)
			{
				if (const TArray<int32>* B = Grid.Find(FIntPoint(C.X + dx, C.Y + dy)))
				{
					for (int32 j : *B)
					{
						const float Dist = FVector::Dist(Walk.P[i], Walk.P[j]);
						if (j != i && Dist > 150.f && Dist < Radius && FMath::Abs(Walk.P[i].Z - Walk.P[j].Z) < 250.f)
						{
							Near.Add({Dist, j});
						}
					}
				}
			}
		}
		Near.Sort([](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key < B.Key; });
		for (int32 k = 0; k < Near.Num() && Walk.Next[i].Num() < 6; ++k)
		{
			const int32 j = Near[k].Value;
			FHitResult Hit;
			// chest height: benches, planters and low walls don't cut a path
			const FVector Up(0, 0, 140.f);
			if (World && World->LineTraceSingleByChannel(Hit, Walk.P[i] + Up, Walk.P[j] + Up, ECC_Visibility, Params))
			{
				continue;
			}
			Walk.Next[i].AddUnique(j);
		}
	}
	// two-way paths
	for (int32 i = 0; i < Walk.Num(); ++i)
	{
		for (int32 j : TArray<int32>(Walk.Next[i]))
		{
			Walk.Next[j].AddUnique(i);
		}
	}
	// walkable areas: drop small islands (door spawn knots, rooftops) so
	// nobody spawns where they can only shuffle on the spot
	TArray<int32> Comp;
	Comp.Init(INDEX_NONE, Walk.Num());
	TArray<int32> Size;
	for (int32 s = 0; s < Walk.Num(); ++s)
	{
		if (Comp[s] != INDEX_NONE)
		{
			continue;
		}
		const int32 Id = Size.Add(0);
		TArray<int32> Stack = {s};
		Comp[s] = Id;
		while (Stack.Num())
		{
			const int32 c = Stack.Pop(EAllowShrinking::No);
			++Size[Id];
			for (int32 n : Walk.Next[c])
			{
				if (Comp[n] == INDEX_NONE)
				{
					Comp[n] = Id;
					Stack.Add(n);
				}
			}
		}
	}
	int32 Dropped = 0;
	for (int32 i = 0; i < Walk.Num(); ++i)
	{
		if (Size[Comp[i]] < MinWalkArea)
		{
			Walk.Next[i].Reset();
			++Dropped;
		}
	}
	UE_LOG(LogTemp, Log, TEXT("CoHLife walk graph: %d nodes, %d areas, %d nodes on small islands dropped"),
		Walk.Num(), Size.Num(), Dropped);
}

void ACoHLifeManager::BeginPlay()
{
	Super::BeginPlay();
	if (!LoadLife())
	{
		return;
	}
	for (UStaticMesh* Mesh : CarMeshes)
	{
		UInstancedStaticMeshComponent* Ism = NewObject<UInstancedStaticMeshComponent>(this);
		Ism->SetStaticMesh(Mesh);
		Ism->SetMobility(EComponentMobility::Movable);
		Ism->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Ism->SetupAttachment(RootComponent);
		Ism->RegisterComponent();
		CarISMs.Add(Ism);
	}
	auto MakeMesh = [this](UStaticMesh* Mesh) -> UStaticMeshComponent*
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetStaticMesh(Mesh);
		C->SetMobility(EComponentMobility::Movable);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetupAttachment(RootComponent);
		C->RegisterComponent();
		return C;
	};
	if (MonorailMesh && Monorail.Num() > 1)
	{
		Train.From = 0;
		PickNext(Monorail, Train);
		Train.Speed = MonorailSpeed;
		Train.Comp = MakeMesh(MonorailMesh);
	}
	if (BlimpMesh && BlimpRoute.Num() > 1)
	{
		Blimp.From = FMath::RandRange(0, BlimpRoute.Num() - 1);
		PickNext(BlimpRoute, Blimp);
		Blimp.Speed = BlimpSpeed;
		Blimp.Comp = MakeMesh(BlimpMesh);
	}
	if (DroneMesh)
	{
		for (int32 i = 0; i < FMath::Min(MaxDrones, DronePosts.Num()); ++i)
		{
			FCoHMover M;
			M.From = FMath::RandRange(0, DronePosts.Num() - 1);
			M.T = FMath::FRand() * 100.f;
			M.Comp = MakeMesh(DroneMesh);
			Drones.Add(M);
		}
	}
	int32 Links = 0;
	for (const TArray<int32>& N : Walk.Next)
	{
		Links += N.Num();
	}
	Status = FString::Printf(TEXT("lanes %d, walk nodes %d (%d links), monorail %d, blimp %d, drones %d"),
		Lanes.Num(), Walk.Num(), Links, Monorail.Num(), BlimpRoute.Num(), DronePosts.Num());
	UE_LOG(LogCoHLife, Log, TEXT("CoH life: %s"), *Status);
}

void ACoHLifeManager::FindParkingSpots()
{
	// A lane with no same-direction lane just to its right is the curb lane
	// (traffic keeps right); park 3.3 m to its right, facing with traffic.
	TMap<FIntPoint, TArray<int32>> Grid;
	const float Cell = 1000.f;
	for (int32 i = 0; i < Lanes.Num(); ++i)
	{
		Grid.FindOrAdd(FIntPoint(FMath::FloorToInt(Lanes.P[i].X / Cell), FMath::FloorToInt(Lanes.P[i].Y / Cell))).Add(i);
	}
	for (int32 i = 0; i < Lanes.Num(); ++i)
	{
		const FVector D = Lanes.D[i];
		const FVector Right(-D.Y, D.X, 0.f);
		bool bOuter = true;
		const FIntPoint C(FMath::FloorToInt(Lanes.P[i].X / Cell), FMath::FloorToInt(Lanes.P[i].Y / Cell));
		for (int32 dx = -1; dx <= 1 && bOuter; ++dx)
		{
			for (int32 dy = -1; dy <= 1 && bOuter; ++dy)
			{
				if (const TArray<int32>* B = Grid.Find(FIntPoint(C.X + dx, C.Y + dy)))
				{
					for (int32 j : *B)
					{
						const FVector Delta = Lanes.P[j] - Lanes.P[i];
						const float Side = FVector::DotProduct(Delta, Right);
						if (j != i && Side > 150.f && Side < 600.f && FMath::Abs(FVector::DotProduct(Delta, D)) < 800.f
							&& FVector::DotProduct(Lanes.D[j], D) > 0.5f)
						{
							bOuter = false;
							break;
						}
					}
				}
			}
		}
		if (bOuter && Lanes.Next[i].Num() == 1)   // straight road, not a junction
		{
			ParkingSpots.Add(FTransform(D.Rotation(), Lanes.P[i] + Right * 330.f));
		}
	}
}

void ACoHLifeManager::TickParked(float Dt, const FVector& Cam)
{
	if (CarISMs.Num() == 0 || ParkingSpots.Num() == 0)
	{
		return;
	}
	const int32 Want = FMath::RoundToInt(FMath::Lerp(float(ParkedCarsDay), float(ParkedCarsNight), Night));
	while (Parked.Num() < ParkedCarsNight)
	{
		FCoHMover M;
		M.From = INDEX_NONE;
		M.Kind = FMath::RandRange(0, CarISMs.Num() - 1);
		M.Instance = CarISMs[M.Kind]->AddInstance(FTransform(FQuat::Identity, FVector::ZeroVector, FVector::ZeroVector), true);
		Parked.Add(M);
	}
	ParkedRefresh -= Dt;
	const bool bRefresh = ParkedRefresh <= 0.f;
	if (bRefresh)
	{
		ParkedRefresh = 3.f;
	}
	for (int32 k = 0; k < Parked.Num(); ++k)
	{
		FCoHMover& M = Parked[k];
		const bool bActive = k < Want;
		const bool bFar = M.From != INDEX_NONE
			&& FVector::Dist2D(ParkingSpots[M.From].GetLocation(), Cam) > ActiveRadius * 1.1f;
		if (bActive && (M.From == INDEX_NONE || (bFar && bRefresh)))
		{
			for (int32 Try = 0; Try < 30; ++Try)
			{
				const int32 S = FMath::RandRange(0, ParkingSpots.Num() - 1);
				if (FVector::Dist2D(ParkingSpots[S].GetLocation(), Cam) < ActiveRadius)
				{
					M.From = S;
					break;
				}
			}
		}
		FTransform T = (bActive && M.From != INDEX_NONE) ? ParkingSpots[M.From]
			: FTransform(FQuat::Identity, FVector::ZeroVector, FVector::ZeroVector);
		if (bActive && M.From != INDEX_NONE)
		{
			T.SetScale3D(FVector(CarScale));
		}
		CarISMs[M.Kind]->UpdateInstanceTransform(M.Instance, T, true, false, true);
	}
}

// ------------------------------------------------------------------ helpers

FVector ACoHLifeManager::CameraLocation() const
{
	if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		return Cam->GetCameraLocation();
	}
	return GetActorLocation();
}

int32 ACoHLifeManager::RandomNodeNear(const FCoHGraph& G, const FVector& Center, float MinDist, float MaxDist) const
{
	for (int32 Try = 0; Try < 40; ++Try)
	{
		const int32 i = FMath::RandRange(0, G.Num() - 1);
		const float Dist = FVector::Dist2D(G.P[i], Center);
		if (Dist >= MinDist && Dist <= MaxDist && G.Next[i].Num() > 0)
		{
			return i;
		}
	}
	return INDEX_NONE;
}

void ACoHLifeManager::PickNext(const FCoHGraph& G, FCoHMover& M) const
{
	const TArray<int32>& Options = G.Next[M.From];
	if (Options.Num() == 0)
	{
		M.To = INDEX_NONE;
		return;
	}
	TArray<int32> Choice;
	for (int32 n : Options)
	{
		if (n != M.Prev)
		{
			Choice.Add(n);
		}
	}
	M.To = Choice.Num() ? Choice[FMath::RandRange(0, Choice.Num() - 1)] : Options[0];
	M.T = 0.f;
}

float ACoHLifeManager::GroundZ(const FVector& P) const
{
	FHitResult Hit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(CoHGround), false, this);
	if (GetWorld()->LineTraceSingleByChannel(Hit, P + FVector(0, 0, 150), P - FVector(0, 0, 400), ECC_Visibility, Params))
	{
		return Hit.ImpactPoint.Z;
	}
	return P.Z;
}

// ------------------------------------------------------------------ danger

void ACoHLifeManager::ReportDanger(UObject* WorldContextObject, FVector Location, float Radius, float Seconds)
{
	UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	if (!World)
	{
		return;
	}
	for (TActorIterator<ACoHLifeManager> It(World); It; ++It)
	{
		ACoHLifeManager* Mgr = *It;
		Mgr->Dangers.Add({Location, Radius, Mgr->Clock + Seconds});
		for (FCoHMover& M : Mgr->Walkers)
		{
			if (M.Comp && FVector::Dist2D(M.Comp->GetComponentLocation(), Location) < Radius)
			{
				Mgr->StartFleeing(M, Location, Seconds * FMath::FRandRange(0.8f, 1.3f));
			}
		}
	}
}

void ACoHLifeManager::CoHPanic()
{
	FVector Loc = CameraLocation();
	if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		FHitResult Hit;
		const FVector End = Loc + Cam->GetCameraRotation().Vector() * 20000.f;
		if (GetWorld()->LineTraceSingleByChannel(Hit, Loc, End, ECC_Visibility))
		{
			Loc = Hit.ImpactPoint;
		}
	}
	ReportDanger(this, Loc, 3000.f, 8.f);
}

bool ACoHLifeManager::WalkPath(int32 From, int32 To, TArray<int32>& Out) const
{
	// Dijkstra over the walk graph (edge cost = distance)
	const int32 N = Walk.Num();
	TArray<float> Dist;
	Dist.Init(FLT_MAX, N);
	TArray<int32> Prev;
	Prev.Init(INDEX_NONE, N);
	TArray<TPair<float, int32>> Heap;
	auto Less = [](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key < B.Key; };
	Dist[From] = 0.f;
	Heap.HeapPush({0.f, From}, Less);
	while (Heap.Num())
	{
		TPair<float, int32> Top;
		Heap.HeapPop(Top, Less, EAllowShrinking::No);
		const int32 U = Top.Value;
		if (Top.Key > Dist[U])
		{
			continue;
		}
		if (U == To)
		{
			break;
		}
		for (int32 V : Walk.Next[U])
		{
			const float D = Dist[U] + FVector::Dist(Walk.P[U], Walk.P[V]);
			if (D < Dist[V])
			{
				Dist[V] = D;
				Prev[V] = U;
				Heap.HeapPush({D, V}, Less);
			}
		}
	}
	if (Prev[To] == INDEX_NONE)
	{
		return false;
	}
	TArray<int32> Rev;
	for (int32 X = To; X != INDEX_NONE && X != From; X = Prev[X])
	{
		Rev.Add(X);
	}
	for (int32 k = Rev.Num() - 1; k >= 0; --k)
	{
		Out.Add(Rev[k]);
	}
	return true;
}

void ACoHLifeManager::BuildCircuits()
{
	// nodes that are part of the walkable network
	TArray<int32> Live;
	for (int32 i = 0; i < Walk.Num(); ++i)
	{
		if (Walk.Next[i].Num() > 0)
		{
			Live.Add(i);
		}
	}
	Circuits.Reset();
	if (Live.Num() < 20)
	{
		return;
	}
	for (int32 c = 0; c < NumCircuits * 3 && Circuits.Num() < NumCircuits; ++c)
	{
		// 4-6 waypoints far apart, joined by shortest paths, closed into a loop
		TArray<int32> Way = {Live[FMath::RandRange(0, Live.Num() - 1)]};
		const int32 Want = FMath::RandRange(4, 6);
		for (int32 w = 1; w < Want; ++w)
		{
			int32 Best = INDEX_NONE;
			float BestScore = -1.f;
			for (int32 Try = 0; Try < 25; ++Try)
			{
				const int32 Cand = Live[FMath::RandRange(0, Live.Num() - 1)];
				const float FromLast = FVector::Dist2D(Walk.P[Cand], Walk.P[Way.Last()]);
				if (FromLast < 8000.f || FromLast > 30000.f)
				{
					continue;     // 80-300 m legs
				}
				float Spread = FLT_MAX;
				for (int32 P : Way)
				{
					Spread = FMath::Min(Spread, FVector::Dist2D(Walk.P[Cand], Walk.P[P]));
				}
				if (Spread > BestScore)
				{
					BestScore = Spread;
					Best = Cand;
				}
			}
			if (Best != INDEX_NONE)
			{
				Way.Add(Best);
			}
		}
		if (Way.Num() < 3)
		{
			continue;
		}
		TArray<int32> Loop = {Way[0]};
		bool bOk = true;
		for (int32 w = 0; w < Way.Num() && bOk; ++w)
		{
			bOk = WalkPath(Loop.Last(), Way[(w + 1) % Way.Num()], Loop);
		}
		if (bOk && Loop.Num() > 30)
		{
			Loop.Pop();           // last node repeats the first
			Circuits.Add(MoveTemp(Loop));
		}
	}
	int32 Total = 0;
	for (const TArray<int32>& L : Circuits)
	{
		Total += L.Num();
	}
	UE_LOG(LogTemp, Log, TEXT("CoHLife circuits: %d loops, %d steps on average"),
		Circuits.Num(), Circuits.Num() ? Total / Circuits.Num() : 0);
}

bool ACoHLifeManager::RouteSpotNear(const FVector& Center, float MinDist, float MaxDist, int32& OutRoute, int32& OutStep) const
{
	for (int32 Try = 0; Try < 30 && Circuits.Num(); ++Try)
	{
		const int32 R = FMath::RandRange(0, Circuits.Num() - 1);
		const int32 S = FMath::RandRange(0, Circuits[R].Num() - 1);
		const float D = FVector::Dist2D(Walk.P[Circuits[R][S]], Center);
		if (D >= MinDist && D <= MaxDist)
		{
			OutRoute = R;
			OutStep = S;
			return true;
		}
	}
	return false;
}

void ACoHLifeManager::StartFleeing(FCoHMover& M, const FVector& From, float Seconds)
{
	M.Route = INDEX_NONE;      // panic overrides the walk
	M.Fear = Seconds;
	M.Danger = From;
	M.Pause = 0.f;
	if (USkeletalMeshComponent* S = Cast<USkeletalMeshComponent>(M.Comp))
	{
		if (RunAnim)
		{
			S->PlayAnimation(RunAnim, true);
			S->SetPlayRate(RunSpeed / RunAnimSpeed);
		}
		M.Instance = 2;   // running
	}
	// turn round if currently walking towards the danger
	if (M.To != INDEX_NONE && FVector::Dist2D(Walk.P[M.To], From) < FVector::Dist2D(Walk.P[M.From], From))
	{
		Swap(M.From, M.To);
		M.T = 1.f - M.T;
		M.Prev = INDEX_NONE;
	}
}

// -------------------------------------------------------------------- tick

void ACoHLifeManager::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Clock += DeltaSeconds;
	Dangers.RemoveAll([this](const FDanger& D) { return Clock > D.Until; });
	if (NightCollection)
	{
		Night = FMath::Clamp(UKismetMaterialLibrary::GetScalarParameterValue(this, NightCollection, TEXT("Night")), 0.f, 1.f);
	}
	const FVector Cam = CameraLocation();
	TickWalkers(DeltaSeconds, Cam);
	TickCars(DeltaSeconds, Cam);
	TickParked(DeltaSeconds, Cam);
	if (Train.Comp)
	{
		TickRoute(Monorail, Train, DeltaSeconds);
	}
	if (Blimp.Comp)
	{
		TickRoute(BlimpRoute, Blimp, DeltaSeconds);
	}
	TickDrones(DeltaSeconds, Cam);
}

void ACoHLifeManager::TickWalkers(float Dt, const FVector& Cam)
{
	if (Walk.Num() == 0 || CivilianMeshes.Num() == 0 || !WalkAnim)
	{
		return;
	}
	// spread people out: of several random walk nodes, take the one furthest
	// from everyone already out (CoH packs its nodes into plazas and doors)
	auto SpreadNode = [this](float MinDist, float MaxDist, const FVector& Center) -> int32
	{
		int32 Best = INDEX_NONE;
		float BestGap = -1.f;
		for (int32 Try = 0; Try < 10; ++Try)
		{
			const int32 N = RandomNodeNear(Walk, Center, MinDist, MaxDist);
			if (N == INDEX_NONE)
			{
				continue;
			}
			float Gap = FLT_MAX;
			for (const FCoHMover& W : Walkers)
			{
				if (W.Comp)
				{
					Gap = FMath::Min(Gap, FVector::DistSquared2D(W.Comp->GetComponentLocation(), Walk.P[N]));
				}
			}
			if (Gap > BestGap)
			{
				BestGap = Gap;
				Best = N;
			}
		}
		return Best;
	};
	while (Walkers.Num() < MaxCivilians)
	{
		FCoHMover M;
		int32 R, Step;
		if (FMath::FRand() < CircuitShare && RouteSpotNear(Cam, 0.f, ActiveRadius * 0.8f, R, Step))
		{
			M.Route = R;
			M.RouteStep = Step;
			M.From = Circuits[R][Step];
			M.To = Circuits[R][(Step + 1) % Circuits[R].Num()];
		}
		else
		{
			M.From = SpreadNode(0.f, ActiveRadius * 0.8f, Cam);
			if (M.From == INDEX_NONE)
			{
				break;
			}
			PickNext(Walk, M);
		}
		M.T = FMath::FRand();
		M.Speed = WalkSpeed * FMath::FRandRange(0.8f, 1.2f);
		M.Kind = FMath::RandRange(0, CivilianMeshes.Num() - 1);
		USkeletalMeshComponent* S = NewObject<USkeletalMeshComponent>(this);
		S->SetSkeletalMeshAsset(CivilianMeshes[M.Kind]);
		S->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		S->SetupAttachment(RootComponent);
		// cheap crowds: no ray tracing (skips per-frame skin-cache work) and
		// no animation while off screen
		S->bVisibleInRayTracing = false;
		S->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
		S->RegisterComponent();
		S->SetAnimationMode(EAnimationMode::AnimationSingleNode);
		S->PlayAnimation(WalkAnim, true);
		S->SetPlayRate(M.Speed / WalkAnimSpeed);
		M.Instance = 1;   // 1 = walking, 0 = idle
		M.Comp = S;
		Walkers.Add(M);
	}
	const int32 ActiveWalkers = FMath::RoundToInt(MaxCivilians * FMath::Lerp(1.f, NightCivilianScale, Night));
	// where everyone is now, to spot crowds: walk graphs have tight knots
	// (door spawn points) that random walkers drift into and rarely leave
	TArray<FVector> WalkerPos;
	for (const FCoHMover& W : Walkers)
	{
		WalkerPos.Add(W.Comp ? W.Comp->GetComponentLocation() : FVector::ZeroVector);
	}
	for (int32 w = 0; w < Walkers.Num(); ++w)
	{
		FCoHMover& M = Walkers[w];
		USkeletalMeshComponent* S = Cast<USkeletalMeshComponent>(M.Comp);
		if (M.Fear <= 0.f && w < ActiveWalkers)
		{
			int32 Close = 0;
			for (int32 o = 0; o < Walkers.Num(); ++o)
			{
				if (o != w && o < ActiveWalkers && FVector::DistSquared2D(WalkerPos[o], WalkerPos[w]) < FMath::Square(CrowdRadius))
				{
					++Close;
				}
			}
			if (Close >= 2 && FMath::FRand() < Dt * 0.5f)
			{
				M.To = INDEX_NONE;   // the "stuck" branch below moves them elsewhere
			}
		}
		const bool bOut = w < ActiveWalkers || M.Fear > 0.f;
		if (S->IsVisible() != bOut)
		{
			S->SetVisibility(bOut);   // gone home for the night / back out
		}
		if (!bOut)
		{
			continue;
		}
		if (M.To == INDEX_NONE || FVector::Dist2D(Walk.P[M.From], Cam) > ActiveRadius)
		{
			// out of range or stuck: reappear somewhere near the camera
			int32 R, Step;
			if (FMath::FRand() < CircuitShare && RouteSpotNear(Cam, ActiveRadius * 0.4f, ActiveRadius * 0.8f, R, Step))
			{
				M.Route = R;
				M.RouteStep = Step;
				M.From = Circuits[R][Step];
				M.To = Circuits[R][(Step + 1) % Circuits[R].Num()];
				M.Prev = INDEX_NONE;
				M.T = 0.f;
			}
			else
			{
				const int32 N = SpreadNode(ActiveRadius * 0.4f, ActiveRadius * 0.8f, Cam);
				if (N != INDEX_NONE)
				{
					M.Route = INDEX_NONE;
					M.From = N;
					M.Prev = INDEX_NONE;
					PickNext(Walk, M);
				}
			}
			continue;
		}
		if (M.Pause > 0.f)
		{
			M.Pause -= Dt;
			if (M.Pause <= 0.f && M.Instance == 0)
			{
				S->PlayAnimation(WalkAnim, true);
				S->SetPlayRate(M.Speed / WalkAnimSpeed);
				M.Instance = 1;
			}
			continue;
		}
		const bool bFleeing = M.Fear > 0.f;
		if (bFleeing)
		{
			M.Fear -= Dt;
			if (M.Fear <= 0.f)
			{
				S->PlayAnimation(WalkAnim, true);   // calmed down
				S->SetPlayRate(M.Speed / WalkAnimSpeed);
				M.Instance = 1;
			}
		}
		const float Speed = bFleeing ? RunSpeed : M.Speed;
		M.T += Speed * Dt / FMath::Max(Walk.SegLength(M.From, M.To), 1.f);
		if (M.T >= 1.f)
		{
			M.Prev = M.From;
			M.From = M.To;
			if (M.Route != INDEX_NONE && Circuits.IsValidIndex(M.Route))
			{
				const TArray<int32>& L = Circuits[M.Route];
				M.RouteStep = (M.RouteStep + 1) % L.Num();
				M.To = L[(M.RouteStep + 1) % L.Num()];
				M.T = 0.f;
			}
			else
			{
				PickNext(Walk, M);
			}
			if (bFleeing)
			{
				// run on to whichever neighbour is furthest from the danger
				float Best = -1.f;
				for (int32 n : Walk.Next[M.From])
				{
					const float Dist = FVector::Dist2D(Walk.P[n], M.Danger);
					if (Dist > Best)
					{
						Best = Dist;
						M.To = n;
					}
				}
			}
			else if (FMath::FRand() < (M.Route != INDEX_NONE ? 0.03f : 0.15f))   // commuters rarely stop
			{
				M.Pause = FMath::FRandRange(2.f, 6.f);
				if (IdleAnim)
				{
					S->PlayAnimation(IdleAnim, true);
					S->SetPlayRate(1.f);
					M.Instance = 0;
				}
			}
			if (M.To == INDEX_NONE)
			{
				continue;
			}
		}
		FVector Pos;
		FRotator Rot;
		Walk.Eval(M.From, M.To, M.T, Pos, Rot);
		Pos.Z = GroundZ(Pos);
		// UE mannequins face +Y, so turn them a quarter to face travel
		S->SetWorldLocationAndRotation(Pos, FRotator(0.f, Rot.Yaw - 90.f, 0.f));
	}
}

void ACoHLifeManager::TickCars(float Dt, const FVector& Cam)
{
	if (Lanes.Num() == 0 || CarISMs.Num() == 0)
	{
		return;
	}
	// is a lane node already occupied by a car (spawn / respawn check)
	auto IsLaneNodeTaken = [this](int32 Node)
	{
		for (const FCoHMover& C : Cars)
		{
			FVector P;
			FRotator R;
			if (C.To != INDEX_NONE)
			{
				Lanes.Eval(C.From, C.To, C.T, P, R);
			}
			else
			{
				P = Lanes.P[C.From];
			}
			if (FVector::Dist2D(P, Lanes.P[Node]) < CarGap && FMath::Abs(P.Z - Lanes.P[Node].Z) < 200.f)
			{
				return true;
			}
		}
		return false;
	};
	while (Cars.Num() < MaxCars)
	{
		FCoHMover M;
		M.From = RandomNodeNear(Lanes, Cam, 0.f, ActiveRadius);
		if (M.From == INDEX_NONE)
		{
			break;
		}
		if (IsLaneNodeTaken(M.From))
		{
			break;      // try again next frame rather than spawn inside a car
		}
		PickNext(Lanes, M);
		M.T = FMath::FRand();
		M.Speed = CarSpeed;
		M.Kind = FMath::RandRange(0, CarISMs.Num() - 1);
		M.Instance = CarISMs[M.Kind]->AddInstance(FTransform(Lanes.P[M.From]), true);
		Cars.Add(M);
	}
	TArray<FVector> Positions;
	TArray<FVector> Headings;
	for (const FCoHMover& M : Cars)
	{
		FVector P;
		FRotator R;
		if (M.To != INDEX_NONE)
		{
			Lanes.Eval(M.From, M.To, M.T, P, R);
		}
		else
		{
			P = Lanes.P[M.From];
			R = Lanes.D[M.From].Rotation();
		}
		Positions.Add(P);
		Headings.Add(R.Vector());
	}
	const int32 ActiveCars = FMath::RoundToInt(MaxCars * FMath::Lerp(1.f, NightCarScale, Night));
	for (int32 i = 0; i < Cars.Num(); ++i)
	{
		FCoHMover& M = Cars[i];
		if (i >= ActiveCars)
		{
			// off the road for the night: hide (scale 0) without reordering
			CarISMs[M.Kind]->UpdateInstanceTransform(M.Instance,
				FTransform(FQuat::Identity, FVector::ZeroVector, FVector::ZeroVector), true, false, true);
			continue;
		}
		const bool bFar = FVector::Dist2D(Positions[i], Cam) > ActiveRadius * 1.1f;
		if (M.To == INDEX_NONE || bFar)
		{
			const int32 N = RandomNodeNear(Lanes, Cam, ActiveRadius * 0.5f, ActiveRadius);
			if (N != INDEX_NONE && !IsLaneNodeTaken(N))
			{
				M.From = N;
				M.Prev = INDEX_NONE;
				PickNext(Lanes, M);
			}
			continue;
		}
		// slow down behind the car ahead; stop near trouble
		float Target = CarSpeed;
		for (const FDanger& Dg : Dangers)
		{
			if (Clock < Dg.Until && FVector::Dist2D(Positions[i], Dg.P) < Dg.Radius * 1.5f)
			{
				Target = 0.f;
			}
		}
		for (int32 j = 0; j < Cars.Num(); ++j)
		{
			if (j == i)
			{
				continue;
			}
			const FVector Delta = Positions[j] - Positions[i];
			if (FMath::Abs(Delta.Z) > 200.f)
			{
				continue;   // other level (overpass)
			}
			const float Ahead = FVector::DotProduct(Delta, Headings[i]);
			const float Side = FMath::Abs(FVector::CrossProduct(Headings[i], Delta).Z);
			if (Ahead > 0.f && Ahead < CarGap * 2.f && Side < 250.f)
			{
				// same lane: follow at a gap
				Target = FMath::Min(Target, CarSpeed * FMath::Clamp((Ahead - CarGap) / CarGap, 0.f, 1.f));
			}
			else if (Ahead > 0.f && Ahead < CarGap * CrossLook && Side < 600.f)
			{
				// crossing or merging traffic just ahead: give way. When two
				// cars would wait for each other, the lower index goes first.
				const float Cos = FVector::DotProduct(Headings[i], Headings[j]);
				const float TheirAhead = FVector::DotProduct(-Delta, Headings[j]);
				const bool bTheyWaitForMe = TheirAhead > 0.f && TheirAhead < CarGap * CrossLook;
				if (Cos < 0.7f && (!bTheyWaitForMe || j < i))
				{
					Target = 0.f;
				}
			}
		}
		M.Speed = FMath::FInterpTo(M.Speed, Target, Dt, Target < M.Speed ? 6.f : 1.5f);
		const float PrevT = M.T;
		M.T += M.Speed * Dt / FMath::Max(Lanes.SegLength(M.From, M.To), 1.f);
		if (M.T < 1.f)
		{
			// never drive into another car's body: undo the step if it would
			FVector NewP;
			FRotator NewR;
			Lanes.Eval(M.From, M.To, M.T, NewP, NewR);
			for (int32 j = 0; j < Cars.Num(); ++j)
			{
				if (j != i && j < ActiveCars
					&& FVector::Dist2D(NewP, Positions[j]) < 2.f * CarBodyRadius
					&& FVector::Dist2D(NewP, Positions[j]) < FVector::Dist2D(Positions[i], Positions[j])
					&& FMath::Abs(NewP.Z - Positions[j].Z) < 200.f)
				{
					M.T = PrevT;
					M.Speed = 0.f;
					break;
				}
			}
		}
		if (M.T >= 1.f)
		{
			M.Prev = M.From;
			M.From = M.To;
			PickNext(Lanes, M);
			if (M.To == INDEX_NONE)
			{
				continue;
			}
		}
		FVector P;
		FRotator R;
		Lanes.Eval(M.From, M.To, M.T, P, R);
		Positions[i] = P;
		CarISMs[M.Kind]->UpdateInstanceTransform(M.Instance, FTransform(R, P, FVector(CarScale)), true, false, true);
	}
	for (UInstancedStaticMeshComponent* Ism : CarISMs)
	{
		Ism->MarkRenderStateDirty();
	}
	UpdateHeadlights(Positions, Headings, ActiveCars, Cam);
}

void ACoHLifeManager::UpdateHeadlights(const TArray<FVector>& Positions, const TArray<FVector>& Headings,
	int32 ActiveCars, const FVector& Cam)
{
	if (Headlights.Num() == 0)
	{
		for (int32 k = 0; k < HeadlightCars * 2; ++k)
		{
			USpotLightComponent* L = NewObject<USpotLightComponent>(this);
			L->SetMobility(EComponentMobility::Movable);
			L->SetIntensityUnits(ELightUnits::Candelas);
			L->SetIntensity(4000.f);
			L->SetLightColor(FLinearColor(1.f, 0.93f, 0.82f));
			L->SetAttenuationRadius(2500.f);
			L->SetInnerConeAngle(14.f);
			L->SetOuterConeAngle(30.f);
			L->SetCastShadows(false);
			L->SetVisibility(false);
			L->SetupAttachment(RootComponent);
			L->RegisterComponent();
			Headlights.Add(L);
		}
	}
	// nearest moving cars to the camera, at night only
	TArray<TPair<float, int32>> Near;
	if (Night > 0.3f)
	{
		for (int32 i = 0; i < FMath::Min(ActiveCars, Positions.Num()); ++i)
		{
			Near.Add({FVector::DistSquared(Positions[i], Cam), i});
		}
		Near.Sort([](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key < B.Key; });
	}
	for (int32 k = 0; k < Headlights.Num(); ++k)
	{
		const int32 Car = k / 2;
		USpotLightComponent* L = Headlights[k];
		if (Car >= Near.Num())
		{
			L->SetVisibility(false);
			continue;
		}
		const int32 i = Near[Car].Value;
		const FVector F = Headings[i].GetSafeNormal2D();
		const FVector R(-F.Y, F.X, 0.f);
		const float Side = (k % 2 == 0) ? -70.f : 70.f;
		const FVector P = Positions[i] + F * 215.f + R * Side + FVector(0.f, 0.f, 70.f);
		L->SetWorldLocationAndRotation(P, (F + FVector(0.f, 0.f, -0.12f)).Rotation());
		L->SetVisibility(true);
	}
}

void ACoHLifeManager::TickRoute(FCoHGraph& G, FCoHMover& M, float Dt)
{
	if (M.To == INDEX_NONE)
	{
		M.From = FMath::RandRange(0, G.Num() - 1);
		M.Prev = INDEX_NONE;
		PickNext(G, M);
		return;
	}
	M.T += M.Speed * Dt / FMath::Max(G.SegLength(M.From, M.To), 1.f);
	if (M.T >= 1.f)
	{
		M.Prev = M.From;
		M.From = M.To;
		PickNext(G, M);
		if (M.To == INDEX_NONE)
		{
			return;
		}
	}
	FVector P;
	FRotator R;
	G.Eval(M.From, M.To, M.T, P, R);
	M.Comp->SetWorldLocationAndRotation(P, R);
}

void ACoHLifeManager::TickDrones(float Dt, const FVector& Cam)
{
	for (FCoHMover& M : Drones)
	{
		M.T += Dt;
		const FVector Post = DronePosts[M.From];
		// slow orbit around the post with a gentle bob
		const float A = M.T * 0.35f;
		const FVector P = Post + FVector(FMath::Cos(A) * 600.f, FMath::Sin(A) * 600.f, 900.f + FMath::Sin(M.T * 1.7f) * 60.f);
		M.Comp->SetWorldLocationAndRotation(P, FRotator(0.f, FMath::RadiansToDegrees(A) + 90.f, 0.f));
	}
}

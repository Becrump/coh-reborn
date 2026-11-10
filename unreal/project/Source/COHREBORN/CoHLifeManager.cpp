#include "CoHLifeManager.h"

#include "Animation/AnimSequence.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "DrawDebugHelpers.h"
#include "Dom/JsonObject.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/Pawn.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "Misc/ConfigCacheIni.h"
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
	if (Root->TryGetArrayField(TEXT("signals"), Arr))
	{
		for (const TSharedPtr<FJsonValue>& V : *Arr)
		{
			const TSharedPtr<FJsonObject>* O;
			if (V->TryGetObject(O))
			{
				FCoHSignal S;
				S.P = ReadPoint((*O)->TryGetField(TEXT("p")));
				const TArray<TSharedPtr<FJsonValue>>& Dir = (*O)->GetArrayField(TEXT("d"));
				S.D = FVector(Dir[0]->AsNumber(), Dir[1]->AsNumber(), 0.f).GetSafeNormal();
				S.Offset = (*O)->GetNumberField(TEXT("offset"));
				S.Group = (*O)->GetIntegerField(TEXT("group"));
				Signals.Add(S);
			}
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
	int32 LinksTested = 0, LinksRejected = 0;
	TMap<FString, int32> Blockers;
	TArray<FString> BlockerSamples;
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
			const FVector Up(0, 0, 85.f);
			++LinksTested;
			if (World && World->SweepSingleByChannel(Hit, Walk.P[i] + Up, Walk.P[j] + Up, FQuat::Identity, ECC_Visibility, FCollisionShape::MakeCapsule(35.f, 75.f), Params))
			{
				++LinksRejected;
				const UPrimitiveComponent* BC = Hit.GetComponent();
				const FString Key = BC ? FString::Printf(TEXT("%s | %s | %s"), *BC->GetClass()->GetName(),
					*BC->GetName().Left(24), BC->IsA<UStaticMeshComponent>() && Cast<UStaticMeshComponent>(BC)->GetStaticMesh() ? *Cast<UStaticMeshComponent>(BC)->GetStaticMesh()->GetName().Left(32) : TEXT("-")) : FString(TEXT("none"));
				++Blockers.FindOrAdd(Key);
				if (LinksRejected % 60 == 1 && BlockerSamples.Num() < 200)
				{
					const FBoxSphereBounds BB = BC ? BC->Bounds : FBoxSphereBounds();
					BlockerSamples.Add(FString::Printf(TEXT("link %d-%d len %.0f at (%.0f,%.0f,%.0f) hit %s owner %s ext (%.0f,%.0f,%.0f) startPenetrating %d"),
						i, j, FVector::Dist(Walk.P[i], Walk.P[j]), Hit.ImpactPoint.X, Hit.ImpactPoint.Y, Hit.ImpactPoint.Z, *Key,
						BC && BC->GetOwner() ? *BC->GetOwner()->GetName().Left(40) : TEXT("-"), BB.BoxExtent.X, BB.BoxExtent.Y, BB.BoxExtent.Z, Hit.bStartPenetrating ? 1 : 0));
				}
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
	BuildCrossings();
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
	{
		int32 Largest = 0, Links = 0, InSmall = 0;
		for (int32 Sz : Size) Largest = FMath::Max(Largest, Sz);
		for (int32 i = 0; i < Walk.Num(); ++i) Links += Walk.Next[i].Num();
		for (int32 Sz : Size) if (Sz < MinWalkArea) InSmall += Sz;
		UE_LOG(LogCoHLife, Log, TEXT("CoHLife walk stats: %d links (directed), largest area %d, %d nodes in areas < %d; sweep tested %d links, rejected %d"),
			Links, Largest, InSmall, MinWalkArea, LinksTested, LinksRejected);
		Blockers.ValueSort([](int32 A, int32 B) { return A > B; });
		int32 N = 0;
		for (const TPair<FString, int32>& B : Blockers)
		{
			if (N++ >= 15) break;
			UE_LOG(LogCoHLife, Log, TEXT("CoHLife blocker x%d: %s"), B.Value, *B.Key);
		}
		for (const FString& L : BlockerSamples) UE_LOG(LogCoHLife, Log, TEXT("CoHLife blocked sample: %s"), *L);
	}
	BuildWalkWeights();
}

// Walk links that cross a lane line are road crossings. A crossing is kept only when
// signal stop lines for that traffic (all one group) are near it; every other link
// across a road is cut, so nobody steps into traffic at a random spot.
void ACoHLifeManager::BuildCrossings()
{
	Crossings.Reset();
	if (!bSignalCrossings || Lanes.Num() == 0 || Signals.Num() == 0)
	{
		return;
	}
	const float Cell = 2000.f;
	auto CellOf = [Cell](const FVector& P) { return FIntPoint(FMath::FloorToInt(P.X / Cell), FMath::FloorToInt(P.Y / Cell)); };
	TMap<FIntPoint, TArray<FIntPoint>> LaneGrid;   // lane segments (from, to) near each cell
	for (int32 a = 0; a < Lanes.Num(); ++a)
	{
		for (int32 b : Lanes.Next[a])
		{
			const int32 Steps = FMath::Max(1, FMath::CeilToInt(FVector::Dist2D(Lanes.P[a], Lanes.P[b]) / (Cell * .5f)));
			for (int32 s = 0; s <= Steps; ++s)
			{
				LaneGrid.FindOrAdd(CellOf(FMath::Lerp(Lanes.P[a], Lanes.P[b], float(s) / Steps))).AddUnique(FIntPoint(a, b));
			}
		}
	}
	int32 Roads = 0;
	TArray<TPair<int32, int32>> Cut;
	for (int32 i = 0; i < Walk.Num(); ++i)
	{
		for (int32 j : Walk.Next[i])
		{
			if (j < i)
			{
				continue;
			}
			const FVector P1 = Walk.P[i], P2 = Walk.P[j];
			const FVector2D R(P2.X - P1.X, P2.Y - P1.Y);
			TSet<uint64> Seen;
			TSet<int32> Sigs;
			bool bGroup[2] = {false, false};
			float TMin = 2.f, TMax = -1.f;
			int32 Hits = 0;
			const int32 Steps = FMath::Max(1, FMath::CeilToInt(FVector::Dist2D(P1, P2) / (Cell * .5f)));
			for (int32 s = 0; s <= Steps; ++s)
			{
				const FIntPoint C0 = CellOf(FMath::Lerp(P1, P2, float(s) / Steps));
				for (int32 dx = -1; dx <= 1; ++dx)
				{
					for (int32 dy = -1; dy <= 1; ++dy)
					{
						const TArray<FIntPoint>* Segs = LaneGrid.Find(FIntPoint(C0.X + dx, C0.Y + dy));
						if (!Segs)
						{
							continue;
						}
						for (const FIntPoint& L : *Segs)
						{
							bool bAlready = false;
							Seen.Add((uint64(L.X) << 32) | uint32(L.Y), &bAlready);
							if (bAlready)
							{
								continue;
							}
							const FVector A = Lanes.P[L.X], B = Lanes.P[L.Y];
							const FVector2D Sg(B.X - A.X, B.Y - A.Y);
							const float Den = R.X * Sg.Y - R.Y * Sg.X;
							if (FMath::Abs(Den) < 1e-3f)
							{
								continue;
							}
							const FVector2D QP(A.X - P1.X, A.Y - P1.Y);
							const float T = (QP.X * Sg.Y - QP.Y * Sg.X) / Den;
							const float U = (QP.X * R.Y - QP.Y * R.X) / Den;
							if (T < 0.f || T > 1.f || U < 0.f || U > 1.f
								|| FMath::Abs(FMath::Lerp(P1.Z, P2.Z, T) - FMath::Lerp(A.Z, B.Z, U)) > 300.f)
							{
								continue;
							}
							++Hits;
							TMin = FMath::Min(TMin, T);
							TMax = FMath::Max(TMax, T);
							const FVector X = P1 + (P2 - P1) * T;
							const FVector2D Dir = Sg.GetSafeNormal();
							for (int32 k = 0; k < Signals.Num(); ++k)
							{
								const FCoHSignal& S = Signals[k];
								const FVector Delta = S.P - X;
								const float Ahead = Dir.X * Delta.X + Dir.Y * Delta.Y;
								const float Lateral = FMath::Abs(Dir.X * Delta.Y - Dir.Y * Delta.X);
								// same road: the stop line's heading is along the lane (either way round)
								if (FMath::Abs(Dir.X * S.D.X + Dir.Y * S.D.Y) > .6f && Ahead > -300.f
									&& Ahead < CrossingSignalRange && Lateral < CrossingSignalLateral)
								{
									Sigs.Add(k);
									bGroup[S.Group ? 1 : 0] = true;
								}
							}
						}
					}
				}
			}
			if (Hits == 0)
			{
				continue;
			}
			++Roads;
			if (Sigs.Num() == 0 || (bGroup[0] && bGroup[1]))
			{
				Cut.Emplace(i, j);
			}
			else
			{
				FCoHCrossing& X = Crossings.Add(LinkKey(i, j));
				X.Signals = Sigs.Array();
				X.TIn = TMin;
				X.TOut = TMax;
			}
		}
	}
	for (const TPair<int32, int32>& L : Cut)
	{
		Walk.Next[L.Key].Remove(L.Value);
		Walk.Next[L.Value].Remove(L.Key);
	}
	UE_LOG(LogCoHLife, Log, TEXT("CoHLife crossings: %d links cross a road, %d kept at signals, %d cut"),
		Roads, Crossings.Num(), Cut.Num());
}

// Nodes are not spread evenly (the plaza has far more than a side street), so picking a
// node at random packs the crowd where nodes cluster. Each node gets a chance to be
// accepted that falls with its local node count, which evens out people per area.
void ACoHLifeManager::BuildWalkWeights()
{
	WalkWeight.Init(1.f, Walk.Num());
	const float R = FMath::Max(500.f, DensityRadius);
	TMap<FIntPoint, TArray<int32>> Grid;
	for (int32 i = 0; i < Walk.Num(); ++i)
	{
		if (Walk.Next[i].Num() > 0)
		{
			Grid.FindOrAdd(FIntPoint(FMath::FloorToInt(Walk.P[i].X / R), FMath::FloorToInt(Walk.P[i].Y / R))).Add(i);
		}
	}
	TArray<int32> Count;
	Count.Init(0, Walk.Num());
	double Sum = 0;
	int32 Live = 0, Peak = 0;
	for (int32 i = 0; i < Walk.Num(); ++i)
	{
		if (Walk.Next[i].Num() == 0)
		{
			continue;
		}
		const FIntPoint C(FMath::FloorToInt(Walk.P[i].X / R), FMath::FloorToInt(Walk.P[i].Y / R));
		for (int32 dx = -1; dx <= 1; ++dx)
		{
			for (int32 dy = -1; dy <= 1; ++dy)
			{
				if (const TArray<int32>* B = Grid.Find(FIntPoint(C.X + dx, C.Y + dy)))
				{
					for (int32 j : *B)
					{
						if (FVector::Dist2D(Walk.P[i], Walk.P[j]) < R)
						{
							++Count[i];
						}
					}
				}
			}
		}
		Sum += Count[i];
		Peak = FMath::Max(Peak, Count[i]);
		++Live;
	}
	if (Live == 0)
	{
		return;
	}
	const float Mean = float(Sum / Live);
	for (int32 i = 0; i < Walk.Num(); ++i)
	{
		if (Count[i] > 0)
		{
			WalkWeight[i] = FMath::Clamp(Mean / Count[i], .08f, 1.f);
		}
	}
	UE_LOG(LogCoHLife, Log, TEXT("CoHLife walk density: %.0f nodes per %.0f m radius on average, up to %d"), Mean, R / 100.f, Peak);
}

bool ACoHLifeManager::WalkAccept(int32 Node) const
{
	return !WalkWeight.IsValidIndex(Node) || FMath::FRand() < WalkWeight[Node];
}

const FCoHCrossing* ACoHLifeManager::FindCrossing(int32 A, int32 B, float& OutTIn, float& OutTOut) const
{
	const FCoHCrossing* C = Crossings.Find(LinkKey(A, B));
	if (!C)
	{
		return nullptr;
	}
	if (A < B)
	{
		OutTIn = C->TIn;
		OutTOut = C->TOut;
	}
	else
	{
		OutTIn = 1.f - C->TOut;
		OutTOut = 1.f - C->TIn;
	}
	return C;
}

// Safe to start across: every controlling signal has been red long enough for the
// junction to clear, and stays red long enough to get over.
bool ACoHLifeManager::CrossingIsSafe(const FCoHCrossing& C, float SpanSeconds) const
{
	const float Half = SignalCycle * 0.5f;
	for (int32 K : C.Signals)
	{
		const FCoHSignal& S = Signals[K];
		float T = FMath::Fmod(float(FMath::Fmod(SignalTime, 3600.0)) + S.Offset + (S.Group ? Half : 0.f), SignalCycle);
		if (T < 0.f)
		{
			T += SignalCycle;
		}
		if (T < Half || T - Half < 1.5f || SignalCycle - T < SpanSeconds + 1.f)
		{
			return false;
		}
	}
	return true;
}

void ACoHLifeManager::DebugCrowds(float Dt)
{
	UWorld* World = GetWorld();
	const FVector Up(0, 0, 60.f);
	for (const TPair<uint64, FCoHCrossing>& It : Crossings)
	{
		const int32 A = int32(It.Key >> 32), B = int32(It.Key & 0xffffffffu);
		const bool bSafe = CrossingIsSafe(It.Value, 8.f);
		DrawDebugLine(World, Walk.P[A] + Up, Walk.P[B] + Up, bSafe ? FColor::Green : FColor::Red, false, 0.f, 0, 6.f);
	}
	DebugClock += Dt;
	if (DebugClock < 5.f)
	{
		return;
	}
	DebugClock = 0.f;
	TMap<FIntPoint, int32> Cells;
	int32 Shown = 0;
	for (const FCoHMover& M : Walkers)
	{
		if (M.Comp && M.Comp->IsVisible())
		{
			const FVector P = M.Comp->GetComponentLocation();
			++Cells.FindOrAdd(FIntPoint(FMath::FloorToInt(P.X / 10000.f), FMath::FloorToInt(P.Y / 10000.f)));
			++Shown;
		}
	}
	Cells.ValueSort([](int32 A, int32 B) { return A > B; });
	FString Busiest;
	int32 N = 0;
	for (const TPair<FIntPoint, int32>& C : Cells)
	{
		if (N++ >= 5)
		{
			break;
		}
		Busiest += FString::Printf(TEXT(" (%d,%d)=%d"), C.Key.X, C.Key.Y, C.Value);
	}
	UE_LOG(LogCoHLife, Log, TEXT("CoHLife crowd: %d shown, %d cells of 100 m used, busiest:%s"), Shown, Cells.Num(), *Busiest);
}

void ACoHLifeManager::BeginPlay()
{
	Super::BeginPlay();
	GConfig->GetFloat(TEXT("CoH.CitySettings"), TEXT("CrowdDensity"), CrowdDensity, GGameUserSettingsIni);
	GConfig->GetFloat(TEXT("CoH.CitySettings"), TEXT("TrafficDensity"), TrafficDensity, GGameUserSettingsIni);
	if (!LoadLife())
	{
		return;
	}
	for (UStaticMesh* Mesh : CarMeshes)
	{
		UInstancedStaticMeshComponent* Ism = NewObject<UInstancedStaticMeshComponent>(this);
		Ism->SetStaticMesh(Mesh);
		Ism->SetMobility(EComponentMobility::Movable);
		// Both traffic and parked cars use this pool. Keep their authored
		// convex hulls as kinematic blockers; lane simulation drives them.
		Ism->SetCollisionProfileName(TEXT("BlockAllDynamic"));
		Ism->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		Ism->SetGenerateOverlapEvents(false);
		Ism->SetCanEverAffectNavigation(false);
		Ism->SetupAttachment(RootComponent);
		Ism->RegisterComponent();
		CarISMs.Add(Ism);
		// the lamp lens material (one shared instance) gets a dynamic copy so its glow follows the night
		for (int32 Slot = 0; Slot < Ism->GetNumMaterials(); ++Slot)
		{
			if (UMaterialInterface* Mat = Ism->GetMaterial(Slot))
			{
				const FName SlotName = Mesh->GetStaticMaterials().IsValidIndex(Slot) ? Mesh->GetStaticMaterials()[Slot].MaterialSlotName : NAME_None;
				if (Mat->GetName().Contains(TEXT("MI_Veh_Light")) || SlotName == FName(TEXT("veh_light")))
				{
					HeadlightMats.Add(Ism->CreateDynamicMaterialInstance(Slot, Mat));
				}
			}
		}
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
					const FVector Spot = ParkingSpots[S].GetLocation();
					bool bOccupied = false;
					for (const FCoHMover& Other : Parked)
						if (&Other != &M && Other.From != INDEX_NONE
							&& FVector::Dist2D(ParkingSpots[Other.From].GetLocation(), Spot) < 2.f * CarBodyRadius
							&& FMath::Abs(ParkingSpots[Other.From].GetLocation().Z - Spot.Z) < 180.f) { bOccupied = true; break; }
					for (TActorIterator<APawn> It(GetWorld()); It && !bOccupied; ++It)
						if (It->IsPlayerControlled() && FVector::Dist2D(It->GetActorLocation(), Spot) < CarBodyRadius + 100.f
							&& FMath::Abs(It->GetActorLocation().Z - Spot.Z) < 180.f) bOccupied = true;
					if (bOccupied) continue;
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
	const bool bWalk = &G == &Walk;
	for (int32 Try = 0; Try < (bWalk ? 120 : 40); ++Try)
	{
		const int32 i = FMath::RandRange(0, G.Num() - 1);
		const float Dist = FVector::Dist2D(G.P[i], Center);
		if (Dist >= MinDist && Dist <= MaxDist && G.Next[i].Num() > 0 && (!bWalk || WalkAccept(i)))
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
			if (M.Comp && M.HeldBy == 0 && FVector::Dist2D(M.Comp->GetComponentLocation(), Location) < Radius)
			{
				Mgr->StartFleeing(M, Location, Seconds * FMath::FRandRange(0.8f, 1.3f));
			}
		}
	}
}

ACoHLifeManager* ACoHLifeManager::Get(const UObject* WorldContext)
{
	UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	if (!World) return nullptr;
	for (TActorIterator<ACoHLifeManager> It(World); It; ++It) return *It;
	return nullptr;
}

int32 ACoHLifeManager::FindCivilianNear(const FVector& At, float Radius) const
{
	int32 Best = INDEX_NONE; float BestD = Radius;
	for (int32 I = 0; I < Walkers.Num(); ++I)
	{
		const FCoHMover& M = Walkers[I];
		if (!M.Comp || !M.Comp->IsVisible() || M.HeldBy != 0 || M.Fear > 0.f) continue;
		const float D = FVector::Dist2D(M.Comp->GetComponentLocation(), At);
		if (D < BestD) { BestD = D; Best = I; }
	}
	return Best;
}

FVector ACoHLifeManager::CivilianLocation(int32 Index) const
{
	return Walkers.IsValidIndex(Index) && Walkers[Index].Comp ? Walkers[Index].Comp->GetComponentLocation() : FVector::ZeroVector;
}

bool ACoHLifeManager::HoldCivilian(int32 Index, int32 Gang, const FVector& Toward, float HoldSeconds)
{
	if (!Walkers.IsValidIndex(Index)) return false;
	FCoHMover& M = Walkers[Index];
	if (!M.Comp || (M.HeldBy != 0 && M.HeldBy != Gang)) return false;
	const bool bNew = M.HeldBy == 0;
	if (bNew) UE_LOG(LogTemp, Log, TEXT("CoH civilian %d held by gang %d"), Index, Gang);
	M.HeldBy = Gang;
	M.HeldUntil = Clock + HoldSeconds;
	M.Fear = 0.f; M.Velocity = FVector::ZeroVector;
	if (bNew)
	{
		const FVector P = M.Comp->GetComponentLocation();
		M.Comp->SetWorldRotation(FRotator(0, (Toward - P).Rotation().Yaw - 90.f, 0));
		if (USkeletalMeshComponent* S = Cast<USkeletalMeshComponent>(M.Comp))
		{
			UAnimSequence* Pose = CowerAnim ? CowerAnim.Get() : IdleAnim.Get();
			if (Pose)
			{
				S->PlayAnimation(Pose, false);
				S->SetPosition(Pose->GetPlayLength() * 0.35f);   // the flinch, held
				S->SetPlayRate(0.f);
			}
			M.Instance = 3;
		}
	}
	return true;
}

void ACoHLifeManager::ReleaseCivilian(int32 Index, int32 Gang, const FVector& From, AActor* Hero)
{
	if (!Walkers.IsValidIndex(Index)) return;
	FCoHMover& M = Walkers[Index];
	if (M.HeldBy != Gang) return;
	M.HeldBy = 0; M.HeldUntil = 0.f;
	UE_LOG(LogTemp, Log, TEXT("CoH civilian %d released by gang %d%s"), Index, Gang, Hero ? TEXT(", thanks the hero and runs") : TEXT(", runs"));
	if (USkeletalMeshComponent* S = Cast<USkeletalMeshComponent>(M.Comp)) S->SetPlayRate(1.f);
	M.Instance = -1;
	if (Hero && M.Comp)
	{
		// turn to the hero for a moment of thanks, then run
		const FVector P = M.Comp->GetComponentLocation();
		M.Comp->SetWorldRotation(FRotator(0, (Hero->GetActorLocation() - P).Rotation().Yaw - 90.f, 0));
		M.Pause = 1.5f;
	}
	StartFleeing(M, From, 8.f * FMath::FRandRange(0.8f, 1.3f));
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
		int32 First = Live[FMath::RandRange(0, Live.Num() - 1)];
		for (int32 Try = 0; Try < 20 && !WalkAccept(First); ++Try)
		{
			First = Live[FMath::RandRange(0, Live.Num() - 1)];
		}
		TArray<int32> Way = {First};
		const int32 Want = FMath::RandRange(4, 6);
		for (int32 w = 1; w < Want; ++w)
		{
			int32 Best = INDEX_NONE;
			float BestScore = -1.f;
			for (int32 Try = 0; Try < 25; ++Try)
			{
				const int32 Cand = Live[FMath::RandRange(0, Live.Num() - 1)];
				if (!WalkAccept(Cand))
				{
					continue;
				}
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
		if (D >= MinDist && D <= MaxDist && WalkAccept(Circuits[R][S]))
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
	{
		const AGameStateBase* GS = GetWorld()->GetGameState();
		SignalTime = GS ? GS->GetServerWorldTimeSeconds() : GetWorld()->GetTimeSeconds();
		if (SignalCollection)
		{
			UKismetMaterialLibrary::SetScalarParameterValue(this, SignalCollection, TEXT("SignalClock"),
				float(FMath::Fmod(SignalTime, 3600.0)));
		}
	}
	Dangers.RemoveAll([this](const FDanger& D) { return Clock > D.Until; });
	if (NightCollection)
	{
		Night = FMath::Clamp(UKismetMaterialLibrary::GetScalarParameterValue(this, NightCollection, TEXT("Night")), 0.f, 1.f);
	}
	const FVector Cam = CameraLocation();
	TickWalkers(DeltaSeconds, Cam);
	if (bDebugCrowds)
	{
		DebugCrowds(DeltaSeconds);
	}
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
    if (!Walk.Num() || !CivilianMeshes.Num() || !WalkAnim || Dt <= 0.f) return;
    Dt = FMath::Min(Dt, 0.1f); // no long collision jumps after a frame hitch
    FCollisionQueryParams Query(SCENE_QUERY_STAT(CoHCrowdClearance), false, this);
    const FVector BodyUp(0, 0, 85.f);
    const FCollisionShape Body = FCollisionShape::MakeCapsule(35.f, 75.f);
    auto Clear = [&](const FVector& A, const FVector& B) {
        FHitResult Hit;
        return !GetWorld()->SweepSingleByChannel(Hit, A + BodyUp, B + BodyUp,
            FQuat::Identity, ECC_Visibility, Body, Query);
    };
    // Never appear in the middle of a road crossing.
    auto InCrossing = [&](int32 A, int32 B, float T) {
        float TIn, TOut;
        return FindCrossing(A, B, TIn, TOut) && T > TIn - 0.03f && T < TOut + 0.03f;
    };
    // Sample positions along routes, rather than packing people at marker nodes.
    // Every candidate, including circuit commuters, uses the same clearance score.
    auto Place = [&](FCoHMover& M, float MinDist) {
        FCoHMover Best;
        FVector BestPos;
        FRotator BestRot;
        float BestGap = 0.f, BestScore = -FLT_MAX;
        for (int32 Try = 0; Try < 48; ++Try)
        {
            FCoHMover Candidate;
            int32 R, Step;
            if (FMath::FRand() < CircuitShare && RouteSpotNear(Cam, MinDist, ActiveRadius * .9f, R, Step))
            {
                Candidate.Route = R;
                Candidate.RouteStep = Step;
                Candidate.From = Circuits[R][Step];
                Candidate.To = Circuits[R][(Step + 1) % Circuits[R].Num()];
            }
            else
            {
                Candidate.From = RandomNodeNear(Walk, Cam, MinDist, ActiveRadius * .9f);
                if (Candidate.From == INDEX_NONE) continue;
                PickNext(Walk, Candidate);
            }
            if (Candidate.To == INDEX_NONE) continue;
            Candidate.T = FMath::FRand();
            if (InCrossing(Candidate.From, Candidate.To, Candidate.T)) continue;
            FVector P;
            FRotator Rot;
            Walk.Eval(Candidate.From, Candidate.To, Candidate.T, P, Rot);
            P.Z = GroundZ(P);
            if (FVector::Dist2D(P, Cam) > ActiveRadius || !Clear(P, P)) continue;
            float Gap = ActiveRadius;
            int32 Neighbours = 0;
            for (const FCoHMover& Other : Walkers)
            {
                if (Other.Comp && Other.Comp != M.Comp && Other.Comp->IsVisible())
                {
                    const float D = FVector::Dist2D(P, Other.Comp->GetComponentLocation());
                    Gap = FMath::Min(Gap, D);
                    if (D < DensityRadius) ++Neighbours;
                }
            }
            // Prefer empty ground: each person already within DensityRadius costs as much as 60 cm of free space.
            const float Score = FMath::Min(Gap, 600.f) - 60.f * Neighbours;
            if (Gap >= 220.f && Score > BestScore)
            {
                Best = Candidate; BestPos = P; BestRot = Rot; BestGap = Gap; BestScore = Score;
            }
        }
        if (BestGap < 220.f) return false; // postpone spawning rather than stack bodies
        M.From = Best.From; M.To = Best.To; M.T = Best.T;
        M.Route = Best.Route; M.RouteStep = Best.RouteStep;
        M.Prev = INDEX_NONE; M.Velocity = FVector::ZeroVector; M.BlockedSeconds = 0.f;
        if (M.Comp) M.Comp->SetWorldLocationAndRotation(BestPos, FRotator(0, BestRot.Yaw - 90.f, 0));
        return true;
    };
    int32 Active = FMath::RoundToInt(MaxCivilians * CrowdDensity * FMath::Lerp(1.f, NightCivilianScale, Night));
    {
        // Only as many people as the walkable network around the camera can hold (one per 9 m of
        // path), so a short stretch of pavement never turns into a single-file crowd.
        float PathLength = 0.f;
        for (int32 i = 0; i < Walk.Num(); ++i)
        {
            if (Walk.Next[i].Num() == 0 || FVector::Dist2D(Walk.P[i], Cam) > ActiveRadius) continue;
            for (int32 j : Walk.Next[i])
                if (j > i && FVector::Dist2D(Walk.P[j], Cam) <= ActiveRadius) PathLength += FVector::Dist2D(Walk.P[i], Walk.P[j]);
        }
        Active = FMath::Min(Active, FMath::Max(6, FMath::FloorToInt(PathLength / 900.f)));
    }
    // Limit initialization work per frame; all newly spawned positions are committed immediately.
    for (int32 Spawn = 0; Spawn < 4 && Walkers.Num() < MaxCivilians; ++Spawn)
    {
        FCoHMover M;
        USkeletalMeshComponent* S = NewObject<USkeletalMeshComponent>(this);
        S->SetSkeletalMeshAsset(CivilianMeshes[FMath::RandRange(0, CivilianMeshes.Num() - 1)]);
        S->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        S->SetupAttachment(RootComponent);
        S->bVisibleInRayTracing = false;
        S->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
        S->RegisterComponent();
        M.Comp = S;
        if (!Place(M, 0.f)) { S->DestroyComponent(); break; }
        M.Speed = WalkSpeed * FMath::FRandRange(.8f, 1.2f);
        S->SetAnimationMode(EAnimationMode::AnimationSingleNode);
        S->PlayAnimation(WalkAnim, true);
        M.Instance = 1;
        Walkers.Add(M);
    }
    TArray<FVector> Positions, Velocities;
    for (const FCoHMover& M : Walkers)
    {
        Positions.Add(M.Comp->GetComponentLocation()); Velocities.Add(M.Velocity);
    }
    // Random walks drift into the densest knot of the graph, so once a second the walker in the
    // most crowded spot (and out of the player's sight) is moved to empty ground instead.
    RecycleClock += Dt;
    if (RecycleClock >= 1.f && Active > 8)
    {
        RecycleClock = 0.f;
        const float Mean = Active * FMath::Square(DensityRadius / ActiveRadius);
        const int32 Cap = FMath::Max(6, FMath::CeilToInt(Mean * 3.f));
        int32 Worst = INDEX_NONE, WorstCount = Cap;
        for (int32 I = 0; I < Walkers.Num(); ++I)
        {
            const FCoHMover& M = Walkers[I];
            if (I >= Active || M.Fear > 0.f || M.HeldBy != 0 || !M.Comp->IsVisible()
                || FVector::Dist2D(Positions[I], Cam) < 3500.f) continue;
            int32 Count = 0;
            for (int32 J = 0; J < Walkers.Num(); ++J)
            {
                if (J != I && J < Active && FVector::Dist2D(Positions[I], Positions[J]) < DensityRadius) ++Count;
            }
            if (Count > WorstCount) { Worst = I; WorstCount = Count; }
        }
        if (Worst != INDEX_NONE && Place(Walkers[Worst], ActiveRadius * .4f))
        {
            Positions[Worst] = Walkers[Worst].Comp->GetComponentLocation();
            Velocities[Worst] = FVector::ZeroVector;
        }
    }
    for (int32 I = 0; I < Walkers.Num(); ++I)
    {
        FCoHMover& M = Walkers[I];
        USkeletalMeshComponent* S = Cast<USkeletalMeshComponent>(M.Comp);
        const bool Visible = I < Active || M.Fear > 0.f;
        const bool Returning = Visible && !S->IsVisible();
        S->SetVisibility(Visible);
        if (!Visible) { M.Velocity = FVector::ZeroVector; continue; }
        if (Returning || M.To == INDEX_NONE || FVector::Dist2D(Positions[I], Cam) > ActiveRadius * 1.1f)
        {
            if (Place(M, ActiveRadius * .4f)) Positions[I] = S->GetComponentLocation();
            continue;
        }
        if (M.HeldBy != 0)
        {
            if (Clock < M.HeldUntil) { M.Velocity = FVector::ZeroVector; continue; }
            // the gang stopped renewing the hold (gone, defeated): free them
            UE_LOG(LogTemp, Log, TEXT("CoH civilian %d hold expired, runs"), I);
            M.HeldBy = 0; S->SetPlayRate(1.f); M.Instance = -1;
            StartFleeing(M, Positions[I], 6.f);
        }
        if (M.Pause > 0.f)
        {
            M.Pause -= Dt; M.Velocity = FVector::ZeroVector;
            if (IdleAnim && M.Instance != 0) { S->PlayAnimation(IdleAnim, true); M.Instance = 0; }
            continue;
        }
        const bool Fleeing = M.Fear > 0.f;
        M.Fear = FMath::Max(0.f, M.Fear - Dt);
        const float Speed = Fleeing ? RunSpeed : M.Speed;
        const FVector Old = S->GetComponentLocation();
        // A short look-ahead along the corridor leaves room for local steering.
        FVector Target;
        FRotator Heading;
        Walk.Eval(M.From, M.To, FMath::Min(1.f, M.T + 120.f / FMath::Max(1.f, Walk.SegLength(M.From, M.To))), Target, Heading);
        FVector Wanted = (Target - Old).GetSafeNormal2D() * Speed;
        // Kerb: stop just before a road crossing until its signals are red long enough to get over.
        bool bWaiting = false;
        if (!Fleeing && Crossings.Num())
        {
            float TIn, TOut;
            if (const FCoHCrossing* Cross = FindCrossing(M.From, M.To, TIn, TOut))
            {
                const float Len = FMath::Max(1.f, Walk.SegLength(M.From, M.To));
                const float TWait = FMath::Max(0.f, TIn - 350.f / Len);
                if (M.T >= TWait && M.T <= TWait + 120.f / Len
                    && !CrossingIsSafe(*Cross, ((TOut - TIn) * Len + 700.f) / FMath::Max(1.f, Speed)))
                {
                    bWaiting = true;
                    Wanted = FVector::ZeroVector;
                }
            }
        }
        for (int32 J = 0; J < Walkers.Num(); ++J)
        {
            if (J == I || !Walkers[J].Comp->IsVisible() || FMath::Abs(Positions[J].Z - Old.Z) > 160.f) continue;
            const FVector Delta = Old - Positions[J];
            const FVector Predicted = Delta + (Wanted - Velocities[J]) * .6f;
            const float Distance = Delta.Size2D();
            if (Distance < 150.f || (Predicted.Size2D() < 100.f && Distance < 350.f))
            {
                FVector Away = Delta.GetSafeNormal2D();
                if (Away.IsNearlyZero()) Away = FVector(I < J ? 1.f : -1.f, 0, 0);
                Wanted += Away * Speed * FMath::Clamp((180.f - FMath::Min(Distance, Predicted.Size2D())) / 100.f, 0.f, 1.5f);
            }
        }
        Wanted = Wanted.GetClampedToMaxSize2D(Speed);
        FVector Next = Old + Wanted * Dt;
        Next.Z = GroundZ(Next);
        FHitResult Hit;
        if (GetWorld()->SweepSingleByChannel(Hit, Old + BodyUp, Next + BodyUp, FQuat::Identity, ECC_Visibility, Body, Query))
        {
            // Slide tangentially around poles/walls instead of walking through them.
            FVector Slide = FVector::VectorPlaneProject(Wanted, Hit.Normal).GetSafeNormal2D();
            if (Slide.IsNearlyZero()) Slide = FVector(-Hit.Normal.Y, Hit.Normal.X, 0);
            Next = Old + Slide * Speed * Dt;
            Next.Z = GroundZ(Next);
            if (!Clear(Old, Next)) Next = Old;
        }
        for (int32 J = 0; J < Walkers.Num(); ++J)
        {
            if (J != I && Walkers[J].Comp->IsVisible() && FMath::Abs(Positions[J].Z - Next.Z) < 160.f
                && FVector::Dist2D(Next, Positions[J]) < 75.f
                && FVector::Dist2D(Next, Positions[J]) < FVector::Dist2D(Old, Positions[J])) { Next = Old; break; }
        }
        M.Velocity = (Next - Old) / Dt;
        const float ActualSpeed = M.Velocity.Size2D();
        M.BlockedSeconds = (ActualSpeed < 5.f && !bWaiting) ? M.BlockedSeconds + Dt : 0.f;
        if (M.BlockedSeconds > 3.f)
        {
            // Reverse onto a known corridor instead of teleporting a visible person.
            Swap(M.From, M.To); M.T = 1.f - M.T; M.Route = INDEX_NONE; M.BlockedSeconds = 0.f;
        }
        const FVector Segment = Walk.P[M.To] - Walk.P[M.From];
        M.T = FMath::Clamp(FVector::DotProduct(Next - Walk.P[M.From], Segment) / FMath::Max(1.f, Segment.SizeSquared()), 0.f, 1.f);
        if (FVector::Dist2D(Next, Walk.P[M.To]) < 85.f)
        {
            M.Prev = M.From; M.From = M.To;
            if (M.Route != INDEX_NONE && Circuits.IsValidIndex(M.Route))
            {
                const auto& Loop = Circuits[M.Route];
                M.RouteStep = (M.RouteStep + 1) % Loop.Num(); M.To = Loop[(M.RouteStep + 1) % Loop.Num()]; M.T = 0.f;
            }
            else PickNext(Walk, M);
            if (Fleeing)
            {
                float Best = -1.f;
                for (int32 N : Walk.Next[M.From])
                    if (FVector::Dist2D(Walk.P[N], M.Danger) > Best) { Best = FVector::Dist2D(Walk.P[N], M.Danger); M.To = N; }
            }
        }
        const int32 Animation = ActualSpeed < 8.f ? 0 : (Fleeing && RunAnim ? 2 : 1);
        if (Animation != M.Instance)
        {
            S->PlayAnimation(Animation == 0 && IdleAnim ? IdleAnim : (Animation == 2 ? RunAnim : WalkAnim), true);
            M.Instance = Animation;
        }
        S->SetPlayRate(Animation == 0 ? (IdleAnim ? 1.f : 0.f) : ActualSpeed / (Animation == 2 ? RunAnimSpeed : WalkAnimSpeed));
        const FRotator Rot = ActualSpeed > 8.f ? FRotator(0, M.Velocity.Rotation().Yaw - 90.f, 0) : S->GetComponentRotation();
        S->SetWorldLocationAndRotation(Next, Rot);
        Positions[I] = Next;
    }
}

void ACoHLifeManager::TickCars(float Dt, const FVector& Cam)
{
	if (Lanes.Num() == 0 || CarISMs.Num() == 0)
	{
		return;
	}
	TArray<APawn*> Players;
	for (TActorIterator<APawn> It(GetWorld()); It; ++It)
		if (It->IsPlayerControlled()) Players.Add(*It);
	FVector CamForward = FVector::ForwardVector;
	if (const APlayerCameraManager* PCM = UGameplayStatics::GetPlayerCameraManager(this, 0))
		CamForward = PCM->GetCameraRotation().Vector().GetSafeNormal2D();
	// is a lane node already occupied by a car (spawn / respawn check)
	auto IsLaneNodeTaken = [this, &Players](int32 Node)
	{
		for (const APawn* Player : Players)
			if (FVector::Dist2D(Player->GetActorLocation(), Lanes.P[Node]) < CarBodyRadius + 100.f
				&& FMath::Abs(Player->GetActorLocation().Z - Lanes.P[Node].Z) < 180.f) return true;
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
		if (M.To == INDEX_NONE) break;
		FVector SpawnPosition;
		FRotator SpawnRotation;
		Lanes.Eval(M.From, M.To, M.T, SpawnPosition, SpawnRotation);
		if (Players.ContainsByPredicate([&](const APawn* Player) {
			return FVector::Dist2D(Player->GetActorLocation(), SpawnPosition) < CarBodyRadius + 100.f
				&& FMath::Abs(Player->GetActorLocation().Z - SpawnPosition.Z) < 180.f;
		})) break;
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
	const int32 ActiveCars = FMath::RoundToInt(MaxCars * TrafficDensity * FMath::Lerp(1.f, NightCarScale, Night));
	for (int32 i = 0; i < Cars.Num(); ++i)
	{
		FCoHMover& M = Cars[i];
		auto Hide = [&]()
		{
			CarISMs[M.Kind]->UpdateInstanceTransform(M.Instance,
				FTransform(FQuat::Identity, FVector::ZeroVector, FVector::ZeroVector), true, false, true);
			M.Speed = 0.f;
			M.bHidden = true;
		};
		if (i >= ActiveCars)
		{
			// off the road for the night: hide (scale 0) without reordering
			if (!M.bHidden) Hide();
			M.To = INDEX_NONE;      // comes back through the respawn below, out of sight
			continue;
		}
		// Cars exist only near a player: farther than the active radius from every player
		// (and the camera) they are hidden, and come back at a lane point nobody can see.
		float Nearest = FVector::Dist2D(Positions[i], Cam);
		for (const APawn* Pl : Players) Nearest = FMath::Min(Nearest, FVector::Dist2D(Positions[i], Pl->GetActorLocation()));
		const bool bFar = Nearest > ActiveRadius * 1.1f;
		if (M.To == INDEX_NONE || bFar || M.bHidden)
		{
			if (!M.bHidden && (bFar || M.To == INDEX_NONE) && Nearest > ActiveRadius * 1.1f) Hide();
			else if (!M.bHidden && M.To == INDEX_NONE) Hide();
			for (int32 Try = 0; Try < 12; ++Try)
			{
				const int32 N = RandomNodeNear(Lanes, Cam, ActiveRadius * 0.35f, ActiveRadius);
				if (N == INDEX_NONE) break;
				bool bSeen = false;
				const FVector NP = Lanes.P[N];
				for (const APawn* Pl : Players)
					if (FVector::Dist2D(NP, Pl->GetActorLocation()) < ActiveRadius * .75f) bSeen = true;
				if (FVector::Dist2D(NP, Cam) < ActiveRadius * .75f && FVector::DotProduct(CamForward, (NP - Cam).GetSafeNormal2D()) > -.1f) bSeen = true;
				if (bSeen || IsLaneNodeTaken(N)) continue;
				M.From = N;
				M.Prev = INDEX_NONE;
				M.bHidden = false;
				PickNext(Lanes, M);
				M.T = 0.f;
				break;
			}
			if (M.bHidden || M.To == INDEX_NONE) continue;
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
			if (j == i || j >= ActiveCars)
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
        // red (or amber) signal ahead in this lane: stop at the line
        for (const FCoHSignal& S : Signals)
        {
            const FVector Delta = S.P - Positions[i];
            if (FMath::Abs(Delta.Z) > 300.f || FVector::DotProduct(Headings[i], S.D) < 0.8f) continue;
            const float Ahead = FVector::DotProduct(Delta, Headings[i]);
            const float Side = FMath::Abs(FVector::CrossProduct(Headings[i], Delta).Z);
            if (Ahead > -50.f && Ahead < 300.f + M.Speed * 1.2f && Side < 800.f && SignalState(S.Offset, S.Group) != 0)
            {
                // already over the line when it turned amber: carry on
                if (!(Ahead < 150.f && SignalState(S.Offset, S.Group) == 1))
                {
                    Target = FMath::Min(Target, CarSpeed * FMath::Clamp((Ahead - 150.f) / 1200.f, 0.f, 1.f));
                }
            }
        }
        // Pedestrians have priority. Look ahead by braking distance and predict
        // crossing movement; parked sidewalk pedestrians do not stop road traffic.
        const float Look = CarBodyRadius + 120.f + M.Speed * .8f + M.Speed * M.Speed / 1200.f;
        auto YieldToPedestrian = [&](const FVector& Ped, const FVector& Velocity)
        {
            if (FMath::Abs(Ped.Z - Positions[i].Z) > 180.f) return;
            for (float Horizon : {0.f, .5f, 1.f})
            {
                const FVector Delta = Ped + Velocity * Horizon - Positions[i];
                const float Ahead = FVector::DotProduct(Delta, Headings[i]);
                const float Side = FMath::Abs(FVector::CrossProduct(Headings[i], Delta).Z);
                if (Ahead > -CarBodyRadius && Ahead < Look && Side < 165.f)
                    Target = FMath::Min(Target, FMath::Sqrt(1200.f * FMath::Max(0.f, Ahead - CarBodyRadius - 140.f)));
            }
        };
        for (const FCoHMover& W : Walkers)
            if (W.Comp && W.Comp->IsVisible()) YieldToPedestrian(W.Comp->GetComponentLocation(), W.Velocity);
        for (const APawn* Player : Players)
            YieldToPedestrian(Player->GetActorLocation(), Player->GetVelocity());
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
        FVector CandidatePosition;
        FRotator CandidateRotation;
        Lanes.Eval(M.From, M.To, FMath::Min(1.f, M.T), CandidatePosition, CandidateRotation);
        for (const FCoHMover& W : Walkers)
        {
            if (!W.Comp || !W.Comp->IsVisible()) continue;
            const FVector Ped = W.Comp->GetComponentLocation();
            const FVector Delta = Ped - CandidatePosition;
            if (FMath::Abs(Delta.Z) < 180.f
                && FMath::Abs(FVector::DotProduct(Delta, CandidateRotation.Vector())) < CarBodyRadius + 65.f
                && FMath::Abs(FVector::CrossProduct(CandidateRotation.Vector(), Delta).Z) < 165.f
                && FVector::DistSquared2D(Ped, CandidatePosition) < FVector::DistSquared2D(Ped, Positions[i]))
            { M.T = PrevT; M.Speed = 0.f; break; }
        }
        // Last-step guard: instance transforms do not sweep, so never
        // teleport a collidable vehicle into a player while braking.
        for (const APawn* Player : Players)
        {
            const FVector Ped = Player->GetActorLocation();
            const FVector Delta = Ped - CandidatePosition;
            if (FMath::Abs(Delta.Z) < 180.f
                && FMath::Abs(FVector::DotProduct(Delta, CandidateRotation.Vector())) < CarBodyRadius + 65.f
                && FMath::Abs(FVector::CrossProduct(CandidateRotation.Vector(), Delta).Z) < 165.f
                && FVector::DistSquared2D(Ped, CandidatePosition) < FVector::DistSquared2D(Ped, Positions[i]))
            { M.T = PrevT; M.Speed = 0.f; break; }
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
		// Lane arrows sit below kerbs and medians, so ride on the highest static surface under the
		// car (centre, nose, tail) and pitch with it instead of sinking into it.
		{
			const FVector Fwd = R.Vector();
			auto StaticTop = [&](const FVector& Q, float& OutZ)
			{
				TArray<FHitResult> Hits;
				FCollisionQueryParams Q2(SCENE_QUERY_STAT(CoHCarGround), false, this);
				GetWorld()->LineTraceMultiByChannel(Hits, Q + FVector(0, 0, 110.f), Q - FVector(0, 0, 60.f), ECC_Visibility, Q2);
				bool bFound = false;
				for (const FHitResult& H : Hits)
				{
					const UPrimitiveComponent* C = H.GetComponent();
					if (C && C->Mobility == EComponentMobility::Static && (!bFound || H.ImpactPoint.Z > OutZ))
					{
						OutZ = H.ImpactPoint.Z;
						bFound = true;
					}
				}
				return bFound;
			};
			float ZC = P.Z, ZF = P.Z, ZR = P.Z;
			const bool bC = StaticTop(P, ZC), bF = StaticTop(P + Fwd * 220.f, ZF), bR = StaticTop(P - Fwd * 220.f, ZR);
			if (bC || bF || bR)
			{
				const float Top = FMath::Max3(bC ? ZC : P.Z, bF ? ZF : P.Z, bR ? ZR : P.Z);
				P.Z = FMath::Max(P.Z, FMath::Min(Top, P.Z + 60.f));
				if (bF && bR)
				{
					R.Pitch = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan2(ZF - ZR, 440.f)), -12.f, 12.f);
				}
			}
		}
		Positions[i].Z = P.Z;
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
	const float LampGlow = FMath::Clamp((Night - 0.2f) / 0.3f, 0.f, 1.f);
	for (UMaterialInstanceDynamic* Lamp : HeadlightMats)
	{
		if (Lamp) Lamp->SetScalarParameterValue(TEXT("Headlight Amt LE"), LampGlow);
	}
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
		// lamps sit at the nose of this car's mesh (bounds are in mesh space, origin at the car's middle)
		float Nose = 215.f, Width = 70.f, Height = 70.f;
		if (Cars.IsValidIndex(i) && CarMeshes.IsValidIndex(Cars[i].Kind) && CarMeshes[Cars[i].Kind])
		{
			const FBoxSphereBounds B = CarMeshes[Cars[i].Kind]->GetBounds();
			Nose = (B.Origin.X + B.BoxExtent.X - 15.f) * CarScale;
			Width = B.BoxExtent.Y * .62f * CarScale;
			Height = (B.Origin.Z - B.BoxExtent.Z + B.BoxExtent.Z * 2.f * .38f) * CarScale;
		}
		const FVector P = Positions[i] + F * Nose + R * (Side < 0.f ? -Width : Width) + FVector(0.f, 0.f, Height);
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

int32 ACoHLifeManager::SignalState(float Offset, int32 Group) const
{
	// group 0 is green for the first half of the cycle, group 1 for the second
	const float Half = SignalCycle * 0.5f;
	float T = FMath::Fmod(float(FMath::Fmod(SignalTime, 3600.0)) + Offset + (Group ? Half : 0.f), SignalCycle);
	if (T < 0.f) T += SignalCycle;
	if (T < Half - SignalAmber) return 0;
	if (T < Half) return 1;
	return 2;
}

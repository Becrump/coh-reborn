#include "CoHCivilians.h"
#include "CoHGameRules.h"
#include "Animation/AnimSequenceBase.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Async/Async.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	constexpr float Ft = 30.48f;
	constexpr float TicksPerSecond = 30.f;      // the original server's speeds are feet per tick
	constexpr float GridCell = 3000.f;
	constexpr float NpcBeaconRadius = 3.f * Ft; // MapSpec NPCBeaconRadius default

	FIntPoint Cell(const FVector& P) { return FIntPoint(FMath::FloorToInt(P.X / GridCell), FMath::FloorToInt(P.Y / GridCell)); }

	uint64 LinkKey(int32 A, int32 B) { return A < B ? (uint64(A) << 32 | uint32(B)) : (uint64(B) << 32 | uint32(A)); }

	FVector Hermite(const FVector& P0, const FVector& P1, const FVector& M0, const FVector& M1, float T, FVector* OutTangent = nullptr)
	{
		const float T2 = T * T, T3 = T2 * T;
		if (OutTangent)
			*OutTangent = (6 * T2 - 6 * T) * P0 + (3 * T2 - 4 * T + 1) * M0 + (-6 * T2 + 6 * T) * P1 + (3 * T2 - 2 * T) * M1;
		return (2 * T3 - 3 * T2 + 1) * P0 + (T3 - 2 * T2 + T) * M0 + (-2 * T3 + 3 * T2) * P1 + (T3 - T2) * M1;
	}
}

int32 FCoHCivZone::Nearest(const TArray<FVector>& P, const TMap<FIntPoint, TArray<int32>>& Grid, const FVector& At, float MaxDist, TFunctionRef<bool(int32)> Ok) const
{
	const FIntPoint C = Cell(At);
	const int32 R = FMath::CeilToInt(MaxDist / GridCell);
	int32 Best = INDEX_NONE;
	float BestD = MaxDist * MaxDist;
	for (int32 X = C.X - R; X <= C.X + R; ++X)
		for (int32 Y = C.Y - R; Y <= C.Y + R; ++Y)
			if (const TArray<int32>* L = Grid.Find(FIntPoint(X, Y)))
				for (int32 i : *L)
				{
					const float D = FVector::DistSquared(P[i], At);
					if (D < BestD && Ok(i)) { BestD = D; Best = i; }
				}
	return Best;
}

ACoHCivilians::ACoHCivilians()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = false;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

ACoHCivilians* ACoHCivilians::Get(const UWorld* World)
{
	if (!World) return nullptr;
	for (TActorIterator<ACoHCivilians> It(const_cast<UWorld*>(World)); It; ++It) return *It;
	return nullptr;
}

void ACoHCivilians::ReportDanger(const UObject* WorldContext, const FVector& Location, float Radius)
{
	if (ACoHCivilians* C = WorldContext ? Get(WorldContext->GetWorld()) : nullptr) C->Scare(Location, Radius);
}

void ACoHCivilians::BeginPlay()
{
	Super::BeginPlay();
	if (GetNetMode() == NM_DedicatedServer) { SetActorTickEnabled(false); return; }
	// the zones sit at their one-world places only on the ParagonCity map
	bOneWorld = GetWorld()->GetMapName().Contains(TEXT("ParagonCity"));
	FString Rules;
	GConfig->GetString(TEXT("/Script/COHREBORN.CoHPowerDatabase"), TEXT("RulesDir"), Rules, GGameIni);
	if (Rules.IsEmpty()) Rules = FPaths::ProjectContentDir() / TEXT("CoH/Data/Rules");
	Folder = FPaths::GetPath(Rules) / TEXT("civilians");
	FString Text;
	TSharedPtr<FJsonObject> Root;
	if (!FFileHelper::LoadFileToString(Text, *(Folder / TEXT("civilians.json"))) ||
		!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH civilians: no %s (tools/zones/civilians.py)"), *(Folder / TEXT("civilians.json")));
		SetActorTickEnabled(false);
		return;
	}
	const TSharedPtr<FJsonObject>* ZonesObj;
	if (Root->TryGetObjectField(TEXT("zones"), ZonesObj))
		for (const auto& KV : (*ZonesObj)->Values)
		{
			const TSharedPtr<FJsonObject> Z = KV.Value->AsObject();
			const TArray<TSharedPtr<FJsonValue>>* Off;
			if (!Z.IsValid() || !Z->TryGetArrayField(TEXT("offset_cm"), Off) || Off->Num() < 2) continue;   // not in the one world
			if (ModernZones.Contains(FString(KV.Key))) continue;
			Offsets.Add(FString(KV.Key), FVector2D((*Off)[0]->AsNumber(), (*Off)[1]->AsNumber()));
		}
	UE_LOG(LogTemp, Log, TEXT("CoH civilians: %d zones with the original civilians%s"), Offsets.Num(), bOneWorld ? TEXT("") : TEXT(" (not on this map: only the ParagonCity world has them)"));
	if (!bOneWorld) SetActorTickEnabled(false);
}

void ACoHCivilians::EndPlay(const EEndPlayReason::Type Reason)
{
	for (auto& KV : Loading) KV.Value.Wait();
	Loading.Reset();
	Super::EndPlay(Reason);
}

FVector ACoHCivilians::CameraLocation() const
{
	const APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (PC && PC->PlayerCameraManager) return PC->PlayerCameraManager->GetCameraLocation();
	if (PC && PC->GetPawn()) return PC->GetPawn()->GetActorLocation();
	return FVector(FLT_MAX);
}

TSharedPtr<FCoHCivZone> ACoHCivilians::LoadZone(const FString& File, const FString& Id, FVector2D Offset)
{
	FString Text;
	TSharedPtr<FJsonObject> R;
	if (!FFileHelper::LoadFileToString(Text, *File) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), R) || !R.IsValid()) return nullptr;
	TSharedPtr<FCoHCivZone> Z = MakeShared<FCoHCivZone>();
	Z->Id = Id;
	R->TryGetStringField(TEXT("name"), Z->Name);
	const FVector Shift(Offset.X, Offset.Y, 0.f);
	auto Vec = [&](const TSharedPtr<FJsonValue>& V)
	{
		if (!V.IsValid()) return Shift;
		const TArray<TSharedPtr<FJsonValue>>& A = V->AsArray();
		return A.Num() >= 3 ? FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber()) + Shift : Shift;
	};
	auto Arr = [](const TSharedPtr<FJsonObject>& O, const TCHAR* K) -> const TArray<TSharedPtr<FJsonValue>>&
	{
		static const TArray<TSharedPtr<FJsonValue>> Empty;
		const TArray<TSharedPtr<FJsonValue>>* A;
		return O.IsValid() && O->TryGetArrayField(K, A) ? *A : Empty;
	};
	const TSharedPtr<FJsonObject>* O;
	if (R->TryGetObjectField(TEXT("area"), O)) { double M = 600; (*O)->TryGetNumberField(TEXT("max_npc"), M); Z->MaxNpc = M < 0 ? MAX_int32 : (int32)M; }
	TMap<FString, int32> TypeIdx;
	if (R->TryGetObjectField(TEXT("types"), O))
		for (const auto& KV : (*O)->Values)
		{
			const TSharedPtr<FJsonObject> T = KV.Value->AsObject();
			FCoHCivType Ty;
			Ty.Name = FString(KV.Key);
			FString Kind; T->TryGetStringField(TEXT("kind"), Kind);
			Ty.bCar = Kind == TEXT("car");
			for (const auto& C : Arr(T, TEXT("costumes"))) Ty.Costumes.Add(C->AsString());
			double N;
			if (T->TryGetNumberField(TEXT("max"), N)) Ty.Max = N < 0 ? MAX_int32 : (int32)N;
			if (T->TryGetNumberField(TEXT("run"), N)) Ty.Run = (float)N;
			if (T->TryGetNumberField(TEXT("run_var"), N)) Ty.RunVar = (float)N;
			if (T->TryGetNumberField(TEXT("scared"), N)) Ty.Scared = (int32)N;
			if (T->TryGetNumberField(TEXT("typenum"), N)) Ty.TypeNum = (int32)N;
			if (Ty.Costumes.Num()) TypeIdx.Add(Ty.Name, Z->Types.Add(MoveTemp(Ty)));
		}
	TMap<FString, int32> GenIdx;
	if (R->TryGetObjectField(TEXT("generators"), O))
		for (const auto& KV : (*O)->Values)
		{
			const TSharedPtr<FJsonObject> G = KV.Value->AsObject();
			FCoHCivGen Gen;
			double N;
			if (G->TryGetNumberField(TEXT("max"), N)) Gen.Max = (int32)N;
			if (G->TryGetNumberField(TEXT("spawn_max"), N)) Gen.SpawnMax = (int32)N;
			for (const auto& T : Arr(G, TEXT("types"))) if (const int32* I = TypeIdx.Find(T->AsString())) Gen.Types.Add(*I);
			if (Gen.Types.Num()) GenIdx.Add(FString(KV.Key), Z->Gens.Add(MoveTemp(Gen)));
		}
	for (const auto& V : Arr(R, TEXT("spawns")))
	{
		const TSharedPtr<FJsonObject> S = V->AsObject();
		FString G; S->TryGetStringField(TEXT("gen"), G);
		const int32* GI = GenIdx.Find(G);
		if (!GI) continue;
		FCoHCivSpawn Sp;
		Sp.Gen = *GI;
		Sp.P = Vec(S->Values.FindRef(TEXT("p")));
		double Y = 0; S->TryGetNumberField(TEXT("yaw"), Y); Sp.Yaw = (float)Y;
		Z->Bounds += FVector2D(Sp.P);
		Z->Spawns.Add(Sp);
	}
	const TSharedPtr<FJsonObject>* W;
	if (R->TryGetObjectField(TEXT("wire"), W))
	{
		for (const auto& V : Arr(*W, TEXT("p"))) { const FVector P = Vec(V); Z->WireGrid.FindOrAdd(Cell(P)).Add(Z->WireP.Add(P)); Z->Bounds += FVector2D(P); }
		Z->WireNext.SetNum(Z->WireP.Num());
		TSet<int32> NoAuto;
		for (const auto& V : Arr(*W, TEXT("noauto"))) NoAuto.Add((int32)V->AsNumber());
		for (const auto& V : Arr(*W, TEXT("links")))
		{
			const TArray<TSharedPtr<FJsonValue>>& L = V->AsArray();
			if (L.Num() < 2) continue;
			const int32 A = (int32)L[0]->AsNumber(), B = (int32)L[1]->AsNumber();
			if (!Z->WireP.IsValidIndex(A) || !Z->WireP.IsValidIndex(B)) continue;
			Z->WireNext[A].Add(B);
			Z->WireNext[B].Add(A);
		}
	}
	if (R->TryGetObjectField(TEXT("traffic"), W))
	{
		for (const auto& V : Arr(*W, TEXT("p"))) { const FVector P = Vec(V); Z->LaneGrid.FindOrAdd(Cell(P)).Add(Z->LaneP.Add(P)); }
		for (const auto& V : Arr(*W, TEXT("yaw"))) Z->LaneDir.Add(FRotator(0.f, (float)V->AsNumber(), 0.f).Vector());
		for (const auto& V : Arr(*W, TEXT("typenum"))) Z->LaneTypeNum.Add((int32)V->AsNumber());
		for (const auto& V : Arr(*W, TEXT("kill"))) Z->LaneKill.Add((int32)V->AsNumber());
		for (const auto& V : Arr(*W, TEXT("next")))
		{
			TArray<int32>& N = Z->LaneNext.AddDefaulted_GetRef();
			for (const auto& J : V->AsArray()) N.Add((int32)J->AsNumber());
		}
		const int32 N = Z->LaneP.Num();
		Z->LaneDir.SetNum(N); Z->LaneTypeNum.SetNum(N); Z->LaneNext.SetNum(N);
	}
	return Z;
}

void ACoHCivilians::WakeZones(const FVector& Cam)
{
	const UCoHGameRules* GR = UCoHGameRules::Get(this);
	const double Now = GetWorld()->GetTimeSeconds();
	for (const auto& KV : Offsets)
	{
		// near: by the zone's rectangle (game rules), else by its loaded beacons
		bool bNear = false;
		if (GR) for (const auto& R : GR->ZoneRects) if (R.Key == KV.Key) { bNear = R.Value.ExpandBy(WakeDistance).IsInside(FVector2D(Cam)); break; }
		int32* Idx = ZoneIndex.Find(KV.Key);
		if (Idx && Zones[*Idx].Bounds.bIsValid && !bNear) bNear = Zones[*Idx].Bounds.ExpandBy(WakeDistance).IsInside(FVector2D(Cam));
		if (!Idx)
		{
			if (!bNear) continue;
			const int32 New = Zones.AddDefaulted();
			Zones[New].Id = KV.Key;
			ZoneIndex.Add(KV.Key, New);
			const FString File = Folder / (KV.Key + TEXT(".json"));
			const FString Id = KV.Key;
			const FVector2D Off = KV.Value;
			Loading.Add(New, Async(EAsyncExecution::ThreadPool, [File, Id, Off]() { return LoadZone(File, Id, Off); }));
			continue;
		}
		FCoHCivZone& Z = Zones[*Idx];
		if (bNear) Z.QuietSince = Now;
		if (Z.bActive && !bNear && Now - Z.QuietSince > 30.0)
		{
			// everyone in the zone goes home until someone comes back
			Z.bActive = false;
			for (FCoHCivAgent& A : Agents) if (A.Zone == *Idx) Remove(A);
			UE_LOG(LogTemp, Log, TEXT("CoH civilians: %s asleep"), *Z.Name);
		}
		else if (!Z.bActive && bNear && !Loading.Contains(*Idx) && Z.Spawns.Num())
		{
			Z.bActive = true;
			Z.QuietSince = Now;
			UE_LOG(LogTemp, Log, TEXT("CoH civilians: %s awake (%d spawn points, %d walk beacons, %d lane arrows)"), *Z.Name, Z.Spawns.Num(), Z.WireP.Num(), Z.LaneP.Num());
		}
	}
	for (auto It = Loading.CreateIterator(); It; ++It)
	{
		if (!It.Value().IsReady()) continue;
		TSharedPtr<FCoHCivZone> Got = It.Value().Get();
		const FString Id = Zones[It.Key()].Id;
		if (Got.IsValid())
		{
			// keep only the types we run (the monorail has its own train)
			for (FCoHCivType& T : Got->Types)
				for (const FString& S : SkipTypes) if (T.Name.Contains(S)) { T.Costumes.Reset(); break; }
			Zones[It.Key()] = MoveTemp(*Got);
		}
		else UE_LOG(LogTemp, Warning, TEXT("CoH civilians: could not read %s"), *(Folder / (Id + TEXT(".json"))));
		Zones[It.Key()].Id = Id;
		Zones[It.Key()].QuietSince = Now;
		It.RemoveCurrent();
	}
}

void ACoHCivilians::Populate(int32 ZoneIdx)
{
	// entgenProcess: every generator, in a random order, tries once
	FCoHCivZone& Z = Zones[ZoneIdx];
	const int32 N = Z.Spawns.Num();
	if (!N) return;
	const int32 Start = FMath::RandRange(0, N - 1);
	for (int32 k = 0; k < N; ++k) SpawnOne(ZoneIdx, (Start + k * 7919) % N);
}

bool ACoHCivilians::SpawnOne(int32 ZoneIdx, int32 SpawnIdx)
{
	FCoHCivZone& Z = Zones[ZoneIdx];
	FCoHCivSpawn& S = Z.Spawns[SpawnIdx];
	const FCoHCivGen& G = Z.Gens[S.Gen];
	// entgenCheckLimiterStep1/2: the generator's own cap and count, the type's cap, the zone's NPC cap
	if (S.Alive >= G.Max || (G.SpawnMax >= 0 && S.Spawned >= G.SpawnMax) || Z.Npcs >= Z.MaxNpc) return false;
	const int32 TI = G.Types[FMath::RandRange(0, G.Types.Num() - 1)];
	FCoHCivType& T = Z.Types[TI];
	if (!T.Costumes.Num() || T.Alive >= T.Max) return false;
	FCoHCivAgent A;
	A.Zone = ZoneIdx; A.Type = TI; A.Spawn = SpawnIdx; A.bCar = T.bCar;
	A.Look = LookFor(T.Costumes[FMath::RandRange(0, T.Costumes.Num() - 1)]);
	A.Pos = S.P;
	A.Yaw = S.Yaw;
	// setSpeed: RunSpeed + RunSpeedVariation * qfrand(), feet per tick
	A.Speed = FMath::Max(0.05f, T.Run + T.RunVar * FMath::FRandRange(-1.f, 1.f)) * TicksPerSecond * Ft;
	if (A.bCar)
	{
		const FVector Fwd = FRotator(0.f, S.Yaw, 0.f).Vector();
		// aiFindRandomNearbyBeacon with beaconScoreCar: an arrow ahead, facing our way, of our type
		const int32 L = Z.Nearest(Z.LaneP, Z.LaneGrid, S.P, 100.f * Ft, [&](int32 i)
		{
			return (!T.TypeNum || Z.LaneTypeNum[i] == T.TypeNum) && (Z.LaneDir[i] | Fwd) > 0.5f;
		});
		if (L == INDEX_NONE) return false;
		A.To = L;
		A.P0 = S.P; A.P1 = Z.LaneP[L]; A.D0 = Fwd; A.D1 = Z.LaneDir[L];
		A.SegLen = FMath::Max(1.f, FVector::Dist(A.P0, A.P1));
		A.T = 0.f;
	}
	else
	{
		A.Prev = INDEX_NONE;
		A.At = Z.Nearest(Z.WireP, Z.WireGrid, S.P, 150.f * Ft, [&](int32 i) { return Z.WireNext[i].Num() > 0; });
		if (A.At == INDEX_NONE) return false;
		A.Goal = Z.WireP[A.At];
	}
	++S.Alive; ++S.Spawned; ++T.Alive; ++Z.Npcs;
	Agents.Add(A);
	return true;
}

void ACoHCivilians::Remove(FCoHCivAgent& A)
{
	if (A.bDead) return;
	A.bDead = true;
	if (Zones.IsValidIndex(A.Zone))
	{
		FCoHCivZone& Z = Zones[A.Zone];
		if (Z.Spawns.IsValidIndex(A.Spawn)) --Z.Spawns[A.Spawn].Alive;
		if (Z.Types.IsValidIndex(A.Type)) --Z.Types[A.Type].Alive;
		--Z.Npcs;
	}
	if (Pool.IsValidIndex(A.Vis)) { Pool[A.Vis].Agent = INDEX_NONE; Pool[A.Vis].Comp->SetVisibility(false); }
	A.Vis = INDEX_NONE;
}

bool ACoHCivilians::NextWire(FCoHCivAgent& A, bool bNear)
{
	// aiNPCMoveWire: a random linked beacon, not the one we came from when there is another
	FCoHCivZone& Z = Zones[A.Zone];
	const TArray<int32>& Links = Z.WireNext[A.At];
	TArray<int32, TInlineAllocator<16>> Options;
	for (int32 j : Links)
		if (j != A.Prev && !Z.Blocked.Contains(LinkKey(A.At, j))) Options.Add(j);
	if (!Options.Num() && A.Prev != INDEX_NONE && !Z.Blocked.Contains(LinkKey(A.At, A.Prev))) Options.Add(A.Prev);
	while (Options.Num())
	{
		const int32 k = FMath::RandRange(0, Options.Num() - 1);
		const int32 j = Options[k];
		if (bNear)
		{
			// the original only linked beacons with a clear way between them; the
			// world only has collision near the camera, so check there and remember
			FHitResult Hit;
			FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHCivilianWire), false, this);
			const FVector Up(0, 0, 120.f);
			if (GetWorld()->LineTraceSingleByChannel(Hit, Z.WireP[A.At] + Up, Z.WireP[j] + Up, ECC_WorldStatic, Q))
			{
				Z.Blocked.Add(LinkKey(A.At, j));
				Options.RemoveAtSwap(k);
				continue;
			}
		}
		A.Prev = A.At;
		A.At = j;
		const float Ang = FMath::FRand() * PI, Dist = FMath::FRand() * NpcBeaconRadius;
		A.Goal = Z.WireP[j] + FVector(FMath::Cos(Ang) * Dist, FMath::Sin(Ang) * Dist, 0.f);
		return true;
	}
	return false;
}

void ACoHCivilians::StepPerson(FCoHCivAgent& A, float Dt, double Now)
{
	const FCoHCivType& T = Zones[A.Zone].Types[A.Type];
	const bool bScared = Now < A.ScaredUntil;
	if (Now < A.FaceUntil)
	{
		// aiNPCPriorityDoBasicActions: face whoever scared me for a second ...
		A.Yaw = (A.Danger - A.Pos).Rotation().Yaw;
		return;
	}
	if (A.FaceUntil > 0.0)
	{
		// ... then turn round and go back the way I came
		A.FaceUntil = 0.0;
		if (A.Prev != INDEX_NONE) { Swap(A.Prev, A.At); A.Goal = Zones[A.Zone].WireP[A.At]; }
	}
	// ScaredType 1 keeps walking; the others run while scared. Walking is run speed / 4.8.
	const bool bRun = bScared && T.Scared != 1;
	float Move = (bRun ? A.Speed : A.Speed / 4.8f) * Dt;
	const bool bNear = A.Vis != INDEX_NONE;
	for (int32 Guard = 0; Move > 0.f && Guard < 4; ++Guard)
	{
		FVector To = A.Goal - A.Pos;
		To.Z = 0.f;
		const float D = To.Size();
		if (D > Move)
		{
			A.Pos += To / D * Move;
			A.Yaw = To.Rotation().Yaw;
			break;
		}
		A.Pos.X = A.Goal.X; A.Pos.Y = A.Goal.Y;
		Move -= D;
		if (!NextWire(A, bNear)) { Remove(A); return; }   // nowhere to go: kill_me_please
	}
	if (!A.bGround) A.Pos.Z = FMath::FInterpTo(A.Pos.Z, A.Goal.Z, Dt, 2.f);
}

bool ACoHCivilians::NextLane(FCoHCivAgent& A)
{
	// aiCar: on to a random next arrow of our type; a killer arrow takes the car away
	FCoHCivZone& Z = Zones[A.Zone];
	if (Z.LaneKill.Contains(A.To) || !Z.LaneNext.IsValidIndex(A.To)) return false;
	const FCoHCivType& T = Z.Types[A.Type];
	TArray<int32, TInlineAllocator<8>> Options;
	for (int32 j : Z.LaneNext[A.To]) if (Z.LaneP.IsValidIndex(j) && (!T.TypeNum || Z.LaneTypeNum[j] == T.TypeNum)) Options.Add(j);
	if (!Options.Num()) return false;
	const int32 Next = Options[FMath::RandRange(0, Options.Num() - 1)];
	A.Prev = A.To;
	A.P0 = Z.LaneP[A.To]; A.D0 = Z.LaneDir[A.To];
	A.To = Next;
	A.P1 = Z.LaneP[Next]; A.D1 = Z.LaneDir[Next];
	A.SegLen = FMath::Max(1.f, FVector::Dist(A.P0, A.P1));
	A.T = 0.f;
	return true;
}

void ACoHCivilians::StepCar(FCoHCivAgent& A, float Dt)
{
	float Move = A.Speed * Dt;
	for (int32 Guard = 0; Guard < 4; ++Guard)
	{
		const float Left = (1.f - A.T) * A.SegLen;
		if (Move < Left) { A.T += Move / A.SegLen; break; }
		Move -= Left;
		if (!NextLane(A)) { Remove(A); return; }
	}
	FVector Tangent;
	const FVector M0 = A.D0 * A.SegLen, M1 = A.D1 * A.SegLen;
	A.Pos = Hermite(A.P0, A.P1, M0, M1, A.T, &Tangent);
	if (!Tangent.IsNearlyZero()) A.Yaw = Tangent.Rotation().Yaw;
}

void ACoHCivilians::Scare(const FVector& Location, float Radius)
{
	const double Now = GetWorld()->GetTimeSeconds();
	for (FCoHCivAgent& A : Agents)
	{
		if (A.bDead || A.bCar || Now < A.ScaredUntil || FVector::DistSquared2D(A.Pos, Location) > Radius * Radius) continue;
		const int32 Type = Zones[A.Zone].Types[A.Type].Scared;
		A.ScaredUntil = Now + (Type == 1 ? 5.0 : 20.0);
		A.FaceUntil = Now + 1.0;
		A.Danger = Location;
	}
}

int32 ACoHCivilians::LookFor(const FString& Costume)
{
	if (const int32* I = LookIndex.Find(Costume)) return *I;
	const int32 I = Looks.AddDefaulted();
	Looks[I].Name = Costume;
	LookIndex.Add(Costume, I);
	return I;
}

ACoHCivilians::FLook* ACoHCivilians::Resolve(int32 Look)
{
	FLook& L = Looks[Look];
	if (L.bTried) return L.Mesh ? &L : nullptr;
	if (LoadsThisTick >= 2) return nullptr;     // spread the loads over frames
	++LoadsThisTick;
	L.bTried = true;
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!R) return nullptr;
	// a costume on a player body, else on its own rig (/Game/CoH/NPCs/<costume>)
	FString Body, Dir;
	L.Mesh = R->PresetMesh(L.Name, Body);
	if (L.Mesh) Dir = R->PresetRoot / Body / L.Name;
	else
	{
		Dir = TEXT("/Game/CoH/NPCs") / L.Name;
		IAssetRegistry& AR = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry").Get();
		TArray<FAssetData> Found;
		AR.GetAssetsByPath(FName(*Dir), Found, true);
		for (const FAssetData& D : Found) if (D.IsInstanceOf(USkeletalMesh::StaticClass())) { L.Mesh = Cast<USkeletalMesh>(D.GetAsset()); break; }
	}
	if (!L.Mesh)
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH civilians: no model %s (not imported)"), *L.Name);
		return nullptr;
	}
	L.Idle = R->ClipIn(Dir, TEXT("idle"));
	L.Walk = R->ClipIn(Dir, TEXT("walk"));
	L.Run = R->ClipIn(Dir, TEXT("run"));
	L.Fear = R->ClipIn(Dir, TEXT("fear"));
	L.FearRun = R->ClipIn(Dir, TEXT("fear_run"));
	if (!L.Walk) L.Walk = L.Run ? L.Run : L.Idle;
	if (!L.Run) L.Run = L.Walk;
	if (!L.FearRun) L.FearRun = L.Run;
	if (!L.Fear) L.Fear = L.Idle;
	for (UObject* O : {(UObject*)L.Mesh, (UObject*)L.Idle, (UObject*)L.Walk, (UObject*)L.Run, (UObject*)L.Fear, (UObject*)L.FearRun})
		if (O) Keep.AddUnique(O);
	return &L;
}

void ACoHCivilians::Draw(const FVector& Cam, float Dt, double Now)
{
	// the nearest people and cars inside the original fade distances get a model
	TArray<TPair<float, int32>> People, Cars;
	for (int32 i = 0; i < Agents.Num(); ++i)
	{
		const FCoHCivAgent& A = Agents[i];
		if (A.bDead) continue;
		const float D = FVector::DistSquared(A.Pos, Cam);
		const float Max = A.bCar ? CarDrawDistance : PeopleDrawDistance;
		if (D < Max * Max) (A.bCar ? Cars : People).Add({D, i});
	}
	People.Sort([](const auto& X, const auto& Y) { return X.Key < Y.Key; });
	Cars.Sort([](const auto& X, const auto& Y) { return X.Key < Y.Key; });
	if (People.Num() > MaxDrawnPeople) People.SetNum(MaxDrawnPeople);
	if (Cars.Num() > MaxDrawnCars) Cars.SetNum(MaxDrawnCars);
	TSet<int32> Want;
	for (const auto& P : People) Want.Add(P.Value);
	for (const auto& P : Cars) Want.Add(P.Value);
	// let go of the ones no longer wanted
	for (FVis& V : Pool)
		if (V.Agent != INDEX_NONE && (!Agents.IsValidIndex(V.Agent) || Agents[V.Agent].bDead || !Want.Contains(V.Agent)))
		{
			if (Agents.IsValidIndex(V.Agent)) Agents[V.Agent].Vis = INDEX_NONE;
			V.Agent = INDEX_NONE;
			V.Comp->SetVisibility(false);
		}
	FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHCivilianGround), false, this);
	for (int32 i : Want)
	{
		FCoHCivAgent& A = Agents[i];
		FLook* L = Resolve(A.Look);
		if (!L) continue;
		if (A.Vis == INDEX_NONE)
		{
			int32 Free = Pool.IndexOfByPredicate([](const FVis& V) { return V.Agent == INDEX_NONE; });
			if (Free == INDEX_NONE)
			{
				USkeletalMeshComponent* C = NewObject<USkeletalMeshComponent>(this);
				C->SetupAttachment(RootComponent);
				C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				C->SetGenerateOverlapEvents(false);
				C->bCastDynamicShadow = true;
				C->SetAnimationMode(EAnimationMode::AnimationSingleNode);
				C->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
				C->RegisterComponent();
				Comps.Add(C);
				FVis V; V.Comp = C;
				Free = Pool.Add(V);
			}
			FVis& V = Pool[Free];
			V.Agent = i;
			A.Vis = Free;
			if (V.Look != A.Look) { V.Comp->SetSkeletalMeshAsset(L->Mesh); V.Look = A.Look; V.Playing = nullptr; }
			V.Comp->SetVisibility(true);
			A.NextGround = 0.f;
		}
		FVis& V = Pool[A.Vis];
		// stand them on the ground (the beacons float a little), a few times a second
		A.NextGround -= Dt;
		if (A.NextGround <= 0.f)
		{
			A.NextGround = 0.25f + FMath::FRand() * 0.1f;
			FHitResult Hit;
			if (GetWorld()->LineTraceSingleByChannel(Hit, A.Pos + FVector(0, 0, 250.f), A.Pos - FVector(0, 0, 600.f), ECC_WorldStatic, Q))
			{
				A.GroundZ = Hit.ImpactPoint.Z;
				A.bGround = true;
			}
		}
		if (A.bGround) A.Pos.Z = FMath::FInterpTo(A.Pos.Z, A.GroundZ, Dt, 12.f);
		V.Comp->SetWorldLocationAndRotation(A.Pos, FRotator(0.f, A.Yaw + MeshYaw, 0.f));
		// the sequencer's moves: walking, running scared, cowering, standing
		UAnimSequenceBase* Clip;
		const bool bScared = Now < A.ScaredUntil;
		if (A.bCar) Clip = L->Walk;
		else if (Now < A.FaceUntil) Clip = Zones[A.Zone].Types[A.Type].Scared == 1 ? L->Idle : L->Fear;
		else if (bScared && Zones[A.Zone].Types[A.Type].Scared != 1) Clip = L->FearRun;
		else Clip = L->Walk;
		if (Clip && Clip != V.Playing)
		{
			V.Comp->PlayAnimation(Clip, true);
			V.Comp->SetPosition(FMath::FRand() * Clip->GetPlayLength(), false);
			V.Playing = Clip;
		}
	}
}

void ACoHCivilians::Tick(float Dt)
{
	Super::Tick(Dt);
	if (!bEnabled || !bOneWorld) return;
	Dt = FMath::Min(Dt, 0.1f);
	LoadsThisTick = 0;
	const double Now = GetWorld()->GetTimeSeconds();
	const FVector Cam = CameraLocation();
	if (Cam.X == FLT_MAX) return;
	WakeZones(Cam);
	if (Now >= NextSpawn)
	{
		NextSpawn = Now + 1.0;                  // entgenProcess runs about once a second
		for (int32 z = 0; z < Zones.Num(); ++z) if (Zones[z].bActive) Populate(z);
	}
	for (FCoHCivAgent& A : Agents)
	{
		if (A.bDead) continue;
		if (A.bCar) StepCar(A, Dt); else StepPerson(A, Dt, Now);
	}
	Draw(Cam, Dt, Now);
	// compact: drop the dead, keeping the pool's agent indices right
	if (Agents.Num() > 64 && Agents.ContainsByPredicate([](const FCoHCivAgent& A) { return A.bDead; }))
	{
		TArray<FCoHCivAgent> Alive;
		Alive.Reserve(Agents.Num());
		for (FCoHCivAgent& A : Agents)
		{
			if (A.bDead) continue;
			if (Pool.IsValidIndex(A.Vis)) Pool[A.Vis].Agent = Alive.Num();
			Alive.Add(A);
		}
		Agents = MoveTemp(Alive);
	}
}

FString ACoHCivilians::Command(const FString& Arg)
{
	if (Arg.Equals(TEXT("off"), ESearchCase::IgnoreCase))
	{
		bEnabled = false;
		for (FCoHCivAgent& A : Agents) Remove(A);
		Agents.Reset();
		for (FCoHCivZone& Z : Zones) Z.bActive = false;
		return TEXT("Original civilians off.");
	}
	if (Arg.Equals(TEXT("on"), ESearchCase::IgnoreCase)) { bEnabled = true; return TEXT("Original civilians on."); }
	int32 People = 0, Cars = 0, Drawn = 0;
	for (const FCoHCivAgent& A : Agents) if (!A.bDead) { (A.bCar ? Cars : People)++; if (A.Vis != INDEX_NONE) ++Drawn; }
	FString Awake;
	for (const FCoHCivZone& Z : Zones) if (Z.bActive) Awake += (Awake.IsEmpty() ? TEXT("") : TEXT(", ")) + Z.Name;
	return FString::Printf(TEXT("Original civilians %s: %d people and %d vehicles about (%d drawn) in %s."),
		bEnabled ? TEXT("on") : TEXT("off"), People, Cars, Drawn, Awake.IsEmpty() ? TEXT("no zone yet") : *Awake);
}

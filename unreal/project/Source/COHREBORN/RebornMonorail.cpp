#include "RebornMonorail.h"

#include "Components/SplineComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"

ARebornMonorail::ARebornMonorail()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;   // move bases before characters
	bReplicates = true;
	bAlwaysRelevant = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	RootComponent->SetMobility(EComponentMobility::Movable);
}

USplineComponent* ARebornMonorail::TrackSpline() const
{
	return Track ? Track->FindComponentByClass<USplineComponent>() : nullptr;
}

void ARebornMonorail::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	BuildCars();
	if (USplineComponent* S = TrackSpline())
	{
		// editor preview: train at its first stop (or the line start)
		float D = 0.f;
		if (Stops.Num())
		{
			D = S->GetDistanceAlongSplineAtSplineInputKey(S->FindInputKeyClosestToWorldLocation(Stops[0].Location));
		}
		PlaceCars(D, 0.f, 1.f);
	}
}

void ARebornMonorail::BuildCars()
{
	for (UStaticMeshComponent* C : Cars)
	{
		if (C)
		{
			C->DestroyComponent();
		}
	}
	for (UStaticMeshComponent* C : Doors)
	{
		if (C)
		{
			C->DestroyComponent();
		}
	}
	Cars.Reset();
	Doors.Reset();
	for (int32 i = 0; i < NumCars; ++i)
	{
		UStaticMesh* Mesh = (i == 0 || i == NumCars - 1) && NoseMesh ? NoseMesh.Get() : CarMesh.Get();
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this, NAME_None, RF_Transient);
		C->SetMobility(EComponentMobility::Movable);
		C->SetStaticMesh(Mesh);
		C->SetCollisionProfileName(TEXT("BlockAll"));
		C->SetCanEverAffectNavigation(false);
		C->SetupAttachment(RootComponent);
		C->RegisterComponent();
		Cars.Add(C);
		for (float X : DoorX)
		{
			for (int32 Side = 0; Side < 2; ++Side)
			{
				for (int32 Leaf = 0; Leaf < 2; ++Leaf)
				{
					UStaticMeshComponent* D = NewObject<UStaticMeshComponent>(this, NAME_None, RF_Transient);
					D->SetMobility(EComponentMobility::Movable);
					D->SetStaticMesh(DoorMesh);
					D->SetCollisionProfileName(TEXT("BlockAll"));
					D->SetCanEverAffectNavigation(false);
					D->SetupAttachment(C);
					D->RegisterComponent();
					Doors.Add(D);
				}
			}
		}
	}
}

float ARebornMonorail::MoveTime(float Length) const
{
	// accelerate, cruise, brake (trapezoid; triangle for short hops)
	const float Ta = CruiseSpeed / Acceleration;
	const float Da = 0.5f * Acceleration * Ta * Ta;
	if (2.f * Da >= Length)
	{
		return 2.f * FMath::Sqrt(Length / Acceleration);
	}
	return 2.f * Ta + (Length - 2.f * Da) / CruiseSpeed;
}

float ARebornMonorail::TravelDistance(float E, float Length) const
{
	const float Total = MoveTime(Length);
	E = FMath::Clamp(E, 0.f, Total);
	const float Ta = FMath::Min(CruiseSpeed / Acceleration, Total / 2.f);
	const float Vmax = Acceleration * Ta;
	const float Da = 0.5f * Acceleration * Ta * Ta;
	if (E < Ta)
	{
		return 0.5f * Acceleration * E * E;
	}
	if (E > Total - Ta)
	{
		const float R = Total - E;
		return Length - 0.5f * Acceleration * R * R;
	}
	return Da + Vmax * (E - Ta);
}

void ARebornMonorail::BuildTimetable()
{
	Legs.Reset();
	USplineComponent* S = TrackSpline();
	if (!S)
	{
		return;
	}
	const float Len = S->GetSplineLength();
	const float Half = 0.5f * CarPitch * NumCars;
	for (FRebornMonorailStop& Stop : Stops)
	{
		Stop.Distance = S->GetDistanceAlongSplineAtSplineInputKey(S->FindInputKeyClosestToWorldLocation(Stop.Location));
	}
	Stops.Sort([](const FRebornMonorailStop& A, const FRebornMonorailStop& B) { return A.Distance < B.Distance; });
	// out along the line, then back: ends, stops in between
	TArray<TPair<float, int32>> Marks;
	Marks.Add({ Half, INDEX_NONE });
	for (int32 i = 0; i < Stops.Num(); ++i)
	{
		Marks.Add({ FMath::Clamp(Stops[i].Distance, Half, Len - Half), i });
	}
	Marks.Add({ Len - Half, INDEX_NONE });
	TArray<TPair<float, int32>> Route = Marks;
	for (int32 i = Marks.Num() - 2; i >= 0; --i)
	{
		Route.Add(Marks[i]);
	}
	float T = 0.f;
	for (int32 i = 0; i + 1 < Route.Num(); ++i)
	{
		FLeg L;
		L.From = Route[i].Key;
		L.To = Route[i + 1].Key;
		L.StopTo = Route[i + 1].Value;
		L.Start = T;
		L.Move = MoveTime(FMath::Abs(L.To - L.From));
		const bool End = (i + 1 == Route.Num() - 1) || (i + 1 == Marks.Num() - 1);
		L.Wait = L.StopTo != INDEX_NONE ? DwellSeconds : (End ? TurnaroundSeconds : 0.f);
		T += L.Move + L.Wait;
		Legs.Add(L);
	}
	Cycle = T;
}

void ARebornMonorail::Evaluate(double Time, float& OutDist, float& OutDoors, int32& OutStop, int32& OutNext) const
{
	OutDist = 0.f;
	OutDoors = 0.f;
	OutStop = INDEX_NONE;
	OutNext = INDEX_NONE;
	if (Legs.Num() == 0 || Cycle <= 0.f)
	{
		return;
	}
	const float T = FMath::Fmod(float(Time), Cycle);
	for (int32 i = 0; i < Legs.Num(); ++i)
	{
		const FLeg& L = Legs[i];
		if (T > L.Start + L.Move + L.Wait && i + 1 < Legs.Num())
		{
			continue;
		}
		const float E = T - L.Start;
		const float Length = FMath::Abs(L.To - L.From);
		const float Sign = L.To >= L.From ? 1.f : -1.f;
		OutNext = L.StopTo;
		if (E <= L.Move)
		{
			OutDist = L.From + Sign * TravelDistance(E, Length);
		}
		else
		{
			OutDist = L.To;
			OutStop = L.StopTo;
			const float W = E - L.Move;
			// doors: open over 2 s after arriving, close 4 s before leaving
			OutDoors = L.StopTo == INDEX_NONE ? 0.f
				: FMath::Clamp(FMath::Min(W / 2.f, (L.Wait - W - 2.f) / 2.f), 0.f, 1.f);
		}
		return;
	}
}

void ARebornMonorail::PlaceCars(float Dist, float DoorOpen, float Direction)
{
	USplineComponent* S = TrackSpline();
	if (!S || Cars.Num() == 0)
	{
		return;
	}
	const float Len = S->GetSplineLength();
	int32 DoorIdx = 0;
	for (int32 i = 0; i < Cars.Num(); ++i)
	{
		const float Offset = (float(i) - 0.5f * float(Cars.Num() - 1)) * CarPitch;
		const float D = FMath::Clamp(Dist + Offset, 0.f, Len);
		const FVector P = S->GetLocationAtDistanceAlongSpline(D, ESplineCoordinateSpace::World);
		FVector Fwd = S->GetDirectionAtDistanceAlongSpline(D, ESplineCoordinateSpace::World);
		Fwd.Z = 0.f;
		Fwd.Normalize();
		// end cars face outwards: nose at the front of each end
		const bool Front = i == Cars.Num() - 1;
		const FRotator R = (Front ? Fwd : -Fwd).Rotation();
		Cars[i]->SetWorldLocationAndRotation(P, R, false, nullptr, ETeleportType::None);
		for (float X : DoorX)
		{
			for (int32 Side = 0; Side < 2; ++Side)
			{
				for (int32 Leaf = 0; Leaf < 2; ++Leaf)
				{
					const float Y = (Side ? -1.f : 1.f) * 146.f;
					const float Slide = (Leaf ? 1.f : -1.f) * (41.f + DoorOpen * DoorSlide);
					Doors[DoorIdx++]->SetRelativeLocation(FVector(X + Slide, Y, 95.f));
				}
			}
		}
	}
}

void ARebornMonorail::BeginPlay()
{
	Super::BeginPlay();
	BuildCars();
	BuildTimetable();
}

void ARebornMonorail::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const AGameStateBase* GS = GetWorld() ? GetWorld()->GetGameState() : nullptr;
	const double Now = GS ? GS->GetServerWorldTimeSeconds() : GetWorld()->GetTimeSeconds();
	float Dist, Open;
	Evaluate(Now, Dist, Open, AtStop, NextStop);
	PlaceCars(Dist, Open, 1.f);
}

FText ARebornMonorail::CurrentStopName() const
{
	return Stops.IsValidIndex(AtStop) ? Stops[AtStop].Name : FText::GetEmpty();
}

FText ARebornMonorail::NextStopName() const
{
	return Stops.IsValidIndex(NextStop) ? Stops[NextStop].Name : FText::FromString(TEXT("End of the line"));
}


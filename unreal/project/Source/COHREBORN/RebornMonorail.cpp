#include "RebornMonorail.h"

#include "Components/SplineComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "CoHHeroCharacter.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Net/UnrealNetwork.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

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
	StartOffset = 0.f;
	if (bStartAtFirstStop)
	{
		for (const FLeg& L : Legs)
		{
			if (L.StopTo != INDEX_NONE)
			{
				StartOffset = L.Start + L.Move;
				break;
			}
		}
	}
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
	const double Now = (GS ? GS->GetServerWorldTimeSeconds() : GetWorld()->GetTimeSeconds()) + StartOffset;
	float Dist, Open;
	Evaluate(Now, Dist, Open, AtStop, NextStop);
	PlaceCars(Dist, Open, 1.f);
	// riders must move after the cars each frame, or the floor slides out
	// from under them: make every player's movement tick wait for the train
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		const ACharacter* C = It->Get() ? Cast<ACharacter>(It->Get()->GetPawn()) : nullptr;
		if (UCharacterMovementComponent* Move = C ? C->GetCharacterMovement() : nullptr)
		{
			bool bHas = false;
			for (const FTickPrerequisite& P : Move->PrimaryComponentTick.GetPrerequisites())
			{
				bHas |= P.PrerequisiteObject.Get() == this;
			}
			if (!bHas)
			{
				Move->AddTickPrerequisiteActor(this);
			}
		}
	}
	TickTravel(Dist);
	UpdateMenu();
}

void ARebornMonorail::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARebornMonorail, Destination);
}

bool ARebornMonorail::IsAboard(const APawn* Pawn) const
{
	const ACharacter* C = Cast<ACharacter>(Pawn);
	if (!C || !C->GetCharacterMovement())
	{
		return false;
	}
	const UPrimitiveComponent* Base = C->GetCharacterMovement()->GetMovementBase();
	for (const UStaticMeshComponent* Car : Cars)
	{
		if (Base == Car)
		{
			return true;
		}
	}
	return false;
}

void ARebornMonorail::ChooseDestination(int32 Index, APawn* Who)
{
	if (!HasAuthority() || !Destinations.IsValidIndex(Index) || Destinations[Index].Map.IsNull())
	{
		return;
	}
	Destination = Index;
	OnRep_Destination();
}

void ARebornMonorail::OnRep_Destination()
{
	HideMenu();
}

void ARebornMonorail::TickTravel(float Dist)
{
	// Server: heading into the start-of-track portal with a destination picked
	// and someone aboard -> everyone rides to that zone (group travel).
	if (!HasAuthority() || bTravelling || !Destinations.IsValidIndex(Destination) || AtStop != INDEX_NONE)
	{
		return;
	}
	// either end of the line is a tunnel portal into the next zones
	USplineComponent* S = TrackSpline();
	const float Len = S ? S->GetSplineLength() : 0.f;
	const float Half = 0.5f * CarPitch * NumCars;
	if (Dist - Half > 3000.f && Len - Half - Dist > 3000.f)
	{
		return;     // still out in the city
	}
	bool Aboard = false;
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (const APlayerController* PC = It->Get())
		{
			Aboard |= IsAboard(PC->GetPawn());
		}
	}
	if (!Aboard)
	{
		return;
	}
	bTravelling = true;
	const FString Dest = Destinations[Destination].Map.ToSoftObjectPath().GetLongPackageName();
	const FString Ride = RideMap.IsNull() ? Dest : RideMap.ToSoftObjectPath().GetLongPackageName();
	UE_LOG(LogTemp, Log, TEXT("Monorail: riding to %s via %s"), *Dest, *Ride);
	GetWorld()->ServerTravel(FString::Printf(TEXT("%s?Dest=%s?listen"), *Ride, *Dest));
}

void ARebornMonorail::UpdateMenu()
{
	// Client: standing in the train at a stop with no destination yet -> menu
	APlayerController* PC = GEngine ? GEngine->GetFirstLocalPlayerController(GetWorld()) : nullptr;
	const bool Aboard = PC && AtStop != INDEX_NONE && IsAboard(PC->GetPawn());
	if (!Aboard)
	{
		bMenuDismissed = false;     // ask again next time
	}
	const bool Want = Aboard && Destination == INDEX_NONE && !bMenuDismissed;
	if (Want && !Menu.IsValid())
	{
		ShowMenu(PC);
	}
	else if (!Want && Menu.IsValid())
	{
		HideMenu();
	}
}

void ARebornMonorail::ShowMenu(APlayerController* PC)
{
	if (!GEngine || !GEngine->GameViewport)
	{
		return;
	}
	MenuPlayer = PC;
	TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
	Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)
		[SNew(STextBlock).Text(FText::FromString(TEXT("PARAGON CITY MONORAIL"))).Font(FCoreStyle::GetDefaultFontStyle("Bold", 20))];
	Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 14)
		[SNew(STextBlock).Text(FText::FromString(TEXT("Choose your destination. The train leaves when the doors close.")))];
	for (int32 i = 0; i < Destinations.Num(); ++i)
	{
		const bool bOpen = !Destinations[i].Map.IsNull();
		const FText Label = bOpen ? Destinations[i].Name
			: FText::FromString(Destinations[i].Name.ToString() + TEXT("  (coming soon)"));
		Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 8)
			[SNew(SButton).IsEnabled(bOpen).Text(Label).OnClicked_Lambda([this, i]
			{
				if (MenuPlayer.IsValid())
				{
					if (ACoHHeroCharacter* Hero = Cast<ACoHHeroCharacter>(MenuPlayer->GetPawn()))
					{
						Hero->ServerChooseMonorailDestination(this, i);
					}
				}
				bMenuDismissed = true;
				HideMenu();
				return FReply::Handled();
			})];
	}
	Rows->AddSlot().AutoHeight()[SNew(SButton).Text(FText::FromString(TEXT("Just riding"))).OnClicked_Lambda([this]
	{
		bMenuDismissed = true;
		HideMenu();
		return FReply::Handled();
	})];
	Menu = SNew(SOverlay) + SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
		[SNew(SBox).WidthOverride(440)[SNew(SBorder).Padding(22).BorderBackgroundColor(FLinearColor(.02f, .05f, .12f, .97f))[Rows]]];
	GEngine->GameViewport->AddViewportWidgetContent(Menu.ToSharedRef(), 90);
	PC->bShowMouseCursor = true;
	FInputModeGameAndUI Mode;
	Mode.SetWidgetToFocus(Menu);
	Mode.SetHideCursorDuringCapture(false);
	PC->SetInputMode(Mode);
}

void ARebornMonorail::HideMenu()
{
	if (Menu.IsValid() && GEngine && GEngine->GameViewport)
	{
		GEngine->GameViewport->RemoveViewportWidgetContent(Menu.ToSharedRef());
	}
	Menu.Reset();
	if (MenuPlayer.IsValid())
	{
		MenuPlayer->SetInputMode(FInputModeGameOnly());
		MenuPlayer->bShowMouseCursor = false;
	}
}


FText ARebornMonorail::CurrentStopName() const
{
	return Stops.IsValidIndex(AtStop) ? Stops[AtStop].Name : FText::GetEmpty();
}

FText ARebornMonorail::NextStopName() const
{
	return Stops.IsValidIndex(NextStop) ? Stops[NextStop].Name : FText::FromString(TEXT("End of the line"));
}


#include "RebornRideDirector.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/GameModeBase.h"
#include "Kismet/GameplayStatics.h"

ARebornRideDirector::ARebornRideDirector()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

void ARebornRideDirector::BeginPlay()
{
	Super::BeginPlay();
	if (const AGameModeBase* GM = GetWorld()->GetAuthGameMode())
	{
		Destination = UGameplayStatics::ParseOption(GM->OptionsString, TEXT("Dest"));
	}
	// tunnel: each section is a floor, two walls, a roof and a light band,
	// built from one box mesh; sections scroll past the stationary train
	if (!WallMesh)
	{
		return;
	}
	auto Box = [this](USceneComponent* Parent, const FVector& Loc, const FVector& Scale, UMaterialInterface* Mat)
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetMobility(EComponentMobility::Movable);
		C->SetStaticMesh(WallMesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetupAttachment(Parent);
		C->SetRelativeLocation(Loc);
		C->SetRelativeScale3D(Scale);
		if (Mat)
		{
			C->SetMaterial(0, Mat);
		}
		C->RegisterComponent();
	};
	const float L = SectionLength / 100.f;     // the box mesh is 100 cm
	for (int32 i = 0; i < Sections; ++i)
	{
		USceneComponent* Ring = NewObject<USceneComponent>(this);
		Ring->SetMobility(EComponentMobility::Movable);
		Ring->SetupAttachment(RootComponent);
		Ring->SetRelativeLocation(FVector((i - Sections / 2) * SectionLength, 0, 0));
		Ring->RegisterComponent();
		Box(Ring, FVector(0, 0, -250), FVector(L, 9.f, 0.5f), WallMaterial);
		Box(Ring, FVector(0, 450, 300), FVector(L, 0.5f, 11.f), WallMaterial);
		Box(Ring, FVector(0, -450, 300), FVector(L, 0.5f, 11.f), WallMaterial);
		Box(Ring, FVector(0, 0, 850), FVector(L, 9.f, 0.5f), WallMaterial);
		Box(Ring, FVector(0, 420, 400), FVector(L * 0.2f, 0.1f, 0.15f), LightMaterial);
		Box(Ring, FVector(0, -420, 400), FVector(L * 0.2f, 0.1f, 0.15f), LightMaterial);
		Rings.Add(Ring);
	}
}

void ARebornRideDirector::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Elapsed += DeltaSeconds;
	const float Span = SectionLength * Sections;
	for (USceneComponent* R : Rings)
	{
		FVector P = R->GetRelativeLocation();
		P.X -= Speed * DeltaSeconds;
		if (P.X < -Span / 2)
		{
			P.X += Span;
		}
		R->SetRelativeLocation(P);
	}
	if (HasAuthority() && !bLeft && Elapsed > RideSeconds && !Destination.IsEmpty())
	{
		bLeft = true;
		GetWorld()->ServerTravel(FString::Printf(TEXT("%s?Arrive=Monorail?listen"), *Destination));
	}
}

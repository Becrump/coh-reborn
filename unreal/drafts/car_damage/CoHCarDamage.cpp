#include "CoHCarDamage.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Net/UnrealNetwork.h"
#include "NiagaraComponent.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "TimerManager.h"

UCoHCarDamageComponent::UCoHCarDamageComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(true);
	FireEffect = TSoftObjectPtr<UNiagaraSystem>(FSoftObjectPath(TEXT("/Game/FireEffectVFX/VFX/NS_FireEffect.NS_FireEffect")));
	CrackedGlass = TSoftObjectPtr<UMaterialInterface>(FSoftObjectPath(TEXT("/Game/AtlasPark4/CitySampleCars/Damage/MI_CSCar_GlassCracked.MI_CSCar_GlassCracked")));
	DeadLights = TSoftObjectPtr<UMaterialInterface>(FSoftObjectPath(TEXT("/Game/AtlasPark4/CitySampleCars/Damage/MI_CSCar_LightsDead.MI_CSCar_LightsDead")));
}

void UCoHCarDamageComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(UCoHCarDamageComponent, Stage);
}

UCoHCarDamageComponent* UCoHCarDamageComponent::For(AActor* Car, bool bCreate)
{
	if (!Car)
	{
		return nullptr;
	}
	UCoHCarDamageComponent* D = Car->FindComponentByClass<UCoHCarDamageComponent>();
	if (!D && bCreate && Car->HasAuthority() && Car->ActorHasTag(TEXT("CitySampleCar")))
	{
		D = NewObject<UCoHCarDamageComponent>(Car, TEXT("CarDamage"));
		D->RegisterComponent();
		Car->AddInstanceComponent(D);
	}
	return D;
}

UStaticMeshComponent* UCoHCarDamageComponent::Body() const
{
	return GetOwner() ? GetOwner()->FindComponentByClass<UStaticMeshComponent>() : nullptr;
}

void UCoHCarDamageComponent::BeginPlay()
{
	Super::BeginPlay();
	Health = MaxHealth;
	if (UStaticMeshComponent* B = Body())
	{
		if (GetOwner()->HasAuthority())
		{
			B->SetNotifyRigidBodyCollision(true);
			B->OnComponentHit.AddDynamic(this, &UCoHCarDamageComponent::OnBodyHit);
		}
	}
	if (Stage != ECoHCarStage::Intact)
	{
		ApplyLook();
	}
}

void UCoHCarDamageComponent::OnBodyHit(UPrimitiveComponent*, AActor* OtherActor, UPrimitiveComponent*, FVector NormalImpulse, const FHitResult& HitResult)
{
	// crashes, falls and other cars landing on it; a sleeping car resting on
	// the road produces no impulse, so this stays quiet
	const UWorld* W = GetWorld();
	const float Impulse = NormalImpulse.Size();
	if (!W || Impulse < HitThreshold || W->GetTimeSeconds() < NextHitTime)
	{
		return;
	}
	NextHitTime = W->GetTimeSeconds() + 0.25f;
	Hit((Impulse - HitThreshold) / 100000.f * HitDamagePer100k, HitResult.ImpactPoint);
}

void UCoHCarDamageComponent::Hit(float Amount, FVector From)
{
	AActor* Owner = GetOwner();
	if (!Owner || !Owner->HasAuthority() || Amount <= 0.f || Stage == ECoHCarStage::Wrecked)
	{
		return;
	}
	LastFrom = From;
	Health = FMath::Max(0.f, Health - Amount);
	const float F = Health / FMath::Max(1.f, MaxHealth);
	const ECoHCarStage Want = Health <= 0.f ? ECoHCarStage::Wrecked
		: F < SmashedBelow ? ECoHCarStage::Smashed
		: F < DentedBelow ? ECoHCarStage::Dented
		: ECoHCarStage::Intact;
	if (Want <= Stage)
	{
		return;
	}
	Stage = Want;
	if (Stage == ECoHCarStage::Wrecked)
	{
		// the blast: away from the hit, mostly up, with a tumble
		if (UStaticMeshComponent* B = Body())
		{
			FVector Away = Owner->GetActorLocation() - From;
			Away.Z = 0.f;
			const FVector Dir = (Away.GetSafeNormal() * 0.45f + FVector::UpVector).GetSafeNormal();
			B->AddImpulse(Dir * WreckLaunch, NAME_None, true);
			B->AddAngularImpulseInDegrees(FVector(FMath::FRandRange(-1.f, 1.f), FMath::FRandRange(-1.f, 1.f), 0.f) * 120.f, NAME_None, true);
		}
	}
	ApplyLook();   // server / listen host; clients get it from OnRep_Stage
	Owner->ForceNetUpdate();
}

void UCoHCarDamageComponent::OnRep_Stage()
{
	ApplyLook();
}

UMaterialInstanceDynamic* UCoHCarDamageComponent::Paint()
{
	if (PaintMID)
	{
		return PaintMID;
	}
	UStaticMeshComponent* B = Body();
	if (!B)
	{
		return nullptr;
	}
	for (int32 i = 0; i < B->GetNumMaterials(); ++i)
	{
		UMaterialInterface* M = B->GetMaterial(i);
		const UMaterial* Base = M ? M->GetBaseMaterial() : nullptr;
		if (Base && Base->GetName().Contains(TEXT("CarPaint")))
		{
			PaintMID = B->CreateDynamicMaterialInstance(i, M);
			return PaintMID;
		}
	}
	return nullptr;
}

void UCoHCarDamageComponent::ApplyLook()
{
	UStaticMeshComponent* B = Body();
	if (!B || Shown == Stage)
	{
		return;
	}
	// stages only go up; apply every step in between so a car that jumps
	// straight to Wrecked still gets the glass and lights
	for (uint8 S = uint8(Shown) + 1; S <= uint8(Stage); ++S)
	{
		const ECoHCarStage Step = ECoHCarStage(S);
		UMaterialInstanceDynamic* P = Paint();
		if (Step == ECoHCarStage::Dented && P)
		{
			P->SetScalarParameterValue(TEXT("Primer Threshold PI"), 0.55f);
			P->SetScalarParameterValue(TEXT("Metal Threshold PI"), 0.85f);
			P->SetScalarParameterValue(TEXT("Dirt Amt PI"), 0.6f);
			P->SetScalarParameterValue(TEXT("DirtSplatter Amt PI"), 0.5f);
		}
		else if (Step == ECoHCarStage::Smashed)
		{
			if (P)
			{
				P->SetScalarParameterValue(TEXT("Primer Threshold PI"), 0.35f);
				P->SetScalarParameterValue(TEXT("Metal Threshold PI"), 0.65f);
				P->SetScalarParameterValue(TEXT("Dirt Amt PI"), 0.85f);
			}
			UMaterialInterface* Glass = CrackedGlass.LoadSynchronous();
			UMaterialInterface* Dark = DeadLights.LoadSynchronous();
			// slot names survive the merge (veh_glass, veh_window, veh_light ...);
			// the materials on them are per-vehicle instances
			const TArray<FName> Slots = B->GetMaterialSlotNames();
			for (int32 i = 0; i < B->GetNumMaterials(); ++i)
			{
				const UMaterialInterface* M = B->GetMaterial(i);
				const FString N = (M ? M->GetName() : FString()) + TEXT("|") + (Slots.IsValidIndex(i) ? Slots[i].ToString() : FString());
				if (N.Contains(TEXT("Glass_Inner")))
				{
					continue;   // inner lens backs stay as they are (Contains ignores case)
				}
				const bool bLight = N.Contains(TEXT("Light")) || N.Contains(TEXT("Bulb")) || N.Contains(TEXT("_Red")) || N.Contains(TEXT("Amber"));
				if (bLight && Dark)
				{
					B->SetMaterial(i, Dark);
				}
				else if (!bLight && Glass && (N.Contains(TEXT("Glass")) || N.Contains(TEXT("Window")) || N.Contains(TEXT("Windshield"))))
				{
					B->SetMaterial(i, Glass);
				}
			}
		}
		else if (Step == ECoHCarStage::Wrecked)
		{
			if (P)
			{
				P->SetVectorParameterValue(TEXT("BaseColor"), FLinearColor(0.018f, 0.016f, 0.014f, 0.f));
				P->SetVectorParameterValue(TEXT("Metal Color PI"), FLinearColor(0.06f, 0.045f, 0.035f, 1.f));
				P->SetVectorParameterValue(TEXT("Dirt Color PI"), FLinearColor(0.02f, 0.02f, 0.02f, 1.f));
				P->SetScalarParameterValue(TEXT("Primer Threshold PI"), 0.2f);
				P->SetScalarParameterValue(TEXT("Metal Threshold PI"), 0.4f);
				P->SetScalarParameterValue(TEXT("Dirt Amt PI"), 1.f);
				P->SetScalarParameterValue(TEXT("Dust Amt PI"), 1.f);
				P->SetScalarParameterValue(TEXT("ClearcoatIntensity"), 0.f);
			}
			if (UNiagaraSystem* Sys = FireEffect.LoadSynchronous())
			{
				const FVector Top(0.f, 0.f, B->Bounds.BoxExtent.Z * 0.9f);
				Fire = UNiagaraFunctionLibrary::SpawnSystemAttached(Sys, B, NAME_None, Top, FRotator::ZeroRotator,
					FVector(1.6f), EAttachLocation::KeepRelativeOffset, true, ENCPoolMethod::None, true, true);
			}
			if (UWorld* W = GetWorld())
			{
				W->GetTimerManager().SetTimer(FireTimer, this, &UCoHCarDamageComponent::StopFire, BurnSeconds, false);
			}
		}
	}
	Shown = Stage;
}

void UCoHCarDamageComponent::StopFire()
{
	if (Fire)
	{
		Fire->Deactivate();   // lets the flames die out, then the component goes
	}
}

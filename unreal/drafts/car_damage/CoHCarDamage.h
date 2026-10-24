// Parked / knocked-out City Sample cars that take damage in stages.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "CoHCarDamage.generated.h"

class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UNiagaraSystem;
class UNiagaraComponent;

/** Damage stages, in order. */
UENUM(BlueprintType)
enum class ECoHCarStage : uint8
{
	Intact,
	Dented,     // primer and bare metal show through the paint, grime
	Smashed,    // windows cracked white, lights dark, a lean
	Wrecked     // burnt black, on fire, thrown by the blast
};

/**
 * Health and damage stages for a physics car (the City Sample parked cars and
 * traffic cars knocked off the road). The server takes damage (powers via
 * Hit(), heavy physics impacts) and replicates the stage; every machine then
 * builds the look locally: a dynamic instance of the car paint, swapped glass
 * and light materials, and the fire effect. Nothing ticks.
 */
UCLASS(ClassGroup = (CoH), meta = (BlueprintSpawnableComponent))
class COHREBORN_API UCoHCarDamageComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UCoHCarDamageComponent();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CoH|Car")
	float MaxHealth = 400.f;

	/** Health fractions at which the car becomes dented / smashed (wrecked at 0). */
	UPROPERTY(EditAnywhere, Category = "CoH|Car")
	float DentedBelow = 0.75f;
	UPROPERTY(EditAnywhere, Category = "CoH|Car")
	float SmashedBelow = 0.4f;

	/** Physics hits: impulses (kg cm/s) above this hurt; damage per 100000 above it. */
	UPROPERTY(EditAnywhere, Category = "CoH|Car")
	float HitThreshold = 400000.f;
	UPROPERTY(EditAnywhere, Category = "CoH|Car")
	float HitDamagePer100k = 30.f;

	/** Velocity change (cm/s) the wreck blast gives the car. */
	UPROPERTY(EditAnywhere, Category = "CoH|Car")
	float WreckLaunch = 700.f;

	/** Seconds the wreck burns before only the burnt shell stays. */
	UPROPERTY(EditAnywhere, Category = "CoH|Car")
	float BurnSeconds = 45.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Car")
	TSoftObjectPtr<UNiagaraSystem> FireEffect;
	UPROPERTY(EditAnywhere, Category = "CoH|Car")
	TSoftObjectPtr<UMaterialInterface> CrackedGlass;
	UPROPERTY(EditAnywhere, Category = "CoH|Car")
	TSoftObjectPtr<UMaterialInterface> DeadLights;

	/** Server: take Amount damage; From (world) gives the blast direction when it wrecks. */
	UFUNCTION(BlueprintCallable, Category = "CoH|Car")
	void Hit(float Amount, FVector From);

	UFUNCTION(BlueprintPure, Category = "CoH|Car")
	ECoHCarStage GetStage() const { return Stage; }

	UFUNCTION(BlueprintPure, Category = "CoH|Car")
	float GetHealth() const { return Health; }

	/** Finds (or on the server adds) the damage component of a car actor. */
	static UCoHCarDamageComponent* For(AActor* Car, bool bCreate);

	virtual void BeginPlay() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:
	UPROPERTY(ReplicatedUsing = OnRep_Stage, VisibleInstanceOnly, Category = "CoH|Car")
	ECoHCarStage Stage = ECoHCarStage::Intact;

	UPROPERTY(VisibleInstanceOnly, Category = "CoH|Car")
	float Health = 0.f;

	UFUNCTION()
	void OnRep_Stage();

	UFUNCTION()
	void OnBodyHit(UPrimitiveComponent* HitComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& HitResult);

private:
	void ApplyLook();
	UStaticMeshComponent* Body() const;
	UMaterialInstanceDynamic* Paint();
	void StopFire();

	ECoHCarStage Shown = ECoHCarStage::Intact;
	FVector LastFrom = FVector::ZeroVector;
	float NextHitTime = 0.f;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> PaintMID;

	UPROPERTY(Transient)
	TObjectPtr<UNiagaraComponent> Fire;

	FTimerHandle FireTimer;
};

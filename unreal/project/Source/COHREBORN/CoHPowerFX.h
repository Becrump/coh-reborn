// Placeholder power visuals: glowing bolts, bursts and cones in the power's
// element colour. Spawned locally on every machine (never replicated); the
// real Niagara effects per power and theme replace these later through the
// same calls.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CoHPowers.h"
#include "CoHPowerFX.generated.h"

class UStaticMeshComponent;
class UMaterialInstanceDynamic;

UCLASS(NotPlaceable, Transient)
class COHREBORN_API ACoHPowerFX : public AActor
{
	GENERATED_BODY()
public:
	ACoHPowerFX();

	/** Projectile from From to To after Delay; Radius > 0 bursts on arrival. */
	static void Bolt(AActor* Owner, FVector From, FVector To, FLinearColor Colour, float Delay, float Radius);
	/** Expanding sphere at Where. */
	static void Burst(AActor* Owner, FVector Where, float Radius, FLinearColor Colour, float Life, float Delay);
	/** Flat fan in front of the caster. */
	static void Cone(AActor* Owner, FVector From, FVector Dir, float Range, float Arc, FLinearColor Colour, float Delay);
	/** World position of a body part, for where a power comes from. */
	static FVector EmitterLocation(const AActor* Owner, ECoHEmitter Emitter);
	/** Socket name on the hero skeleton for an emitter point (emit_eyes...). */
	static FName SocketFor(ECoHEmitter Emitter);

	virtual void Tick(float DeltaSeconds) override;

private:
	static ACoHPowerFX* Make(AActor* Owner, FVector Where, FLinearColor Colour, bool bSphere);
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Mesh;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> Mat;
	FVector From, To;
	FVector StartScale = FVector(0.2f), EndScale = FVector(0.2f);
	float Delay = 0, Travel = 0, Life = 0.5f, Age = 0, BurstRadius = 0;
	FLinearColor Colour;
	bool bMoving = false;
};

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CoHTargetRing.generated.h"

class UProceduralMeshComponent;
class UMaterialInstanceDynamic;

/** The glowing ring on the ground under the local hero's current target, as in
 *  the original game: red under foes, green under allies, blue under contacts.
 *  Local only (each player sees their own selection) and hidden when nothing is
 *  selected. The hero spawns one and feeds it the target every frame. */
UCLASS(NotPlaceable, Transient)
class COHREBORN_API ACoHTargetRing : public AActor
{
	GENERATED_BODY()
public:
	ACoHTargetRing();
	virtual void Tick(float DeltaSeconds) override;

	/** Follow InTarget (null hides the ring). Viewer is the hero whose
	 *  selection it is: foe or friend is judged from their side. */
	void Follow(AActor* InTarget, const AActor* InViewer);

	static const FLinearColor FoeColour, FriendColour, ContactColour;

private:
	UPROPERTY(VisibleAnywhere) TObjectPtr<UProceduralMeshComponent> Ring;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> Mat;
	TWeakObjectPtr<AActor> Target;
	TWeakObjectPtr<const AActor> Viewer;
	float Age = 0.f;
	void BuildMesh();
};

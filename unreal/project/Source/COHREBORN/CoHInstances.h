// One CoH model placed many times (trees, bushes, fence posts, War Wall
// panels...): a single actor holding all copies as instances, so it renders
// in one batch and the whole set can be swapped by changing one mesh.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CoHInstances.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;

UCLASS()
class COHREBORN_API ACoHInstances : public AActor
{
	GENERATED_BODY()

public:
	ACoHInstances();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CoH")
	TObjectPtr<UHierarchicalInstancedStaticMeshComponent> Instances;

	/** Replace the mesh and all instances (world-space transforms). */
	UFUNCTION(BlueprintCallable, Category = "CoH")
	void SetInstances(UStaticMesh* Mesh, const TArray<FTransform>& Transforms);

	/** Swap the mesh, keeping every placement (e.g. new trees). */
	UFUNCTION(BlueprintCallable, Category = "CoH")
	void SwapMesh(UStaticMesh* Mesh);
};

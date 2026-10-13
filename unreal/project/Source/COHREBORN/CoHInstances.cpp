#include "CoHInstances.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"

ACoHInstances::ACoHInstances()
{
	Instances = CreateDefaultSubobject<UHierarchicalInstancedStaticMeshComponent>(TEXT("Instances"));
	RootComponent = Instances;
	Instances->SetMobility(EComponentMobility::Static);
}

void ACoHInstances::SetInstances(UStaticMesh* Mesh, const TArray<FTransform>& Transforms)
{
	Modify();
	Instances->Modify();
	Instances->ClearInstances();
	Instances->SetStaticMesh(Mesh);
	SetActorTransform(FTransform::Identity);
	Instances->AddInstances(Transforms, false, true);
}

void ACoHInstances::SwapMesh(UStaticMesh* Mesh)
{
	Modify();
	Instances->Modify();
	Instances->SetStaticMesh(Mesh);
}

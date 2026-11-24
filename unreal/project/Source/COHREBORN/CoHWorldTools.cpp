// Editor-only world tools, as console commands (Python cannot reach these engine classes).
//
//   coh.World.AddPartitions   adds the "Far" and "Ground" runtime partitions to the open World
//                             Partition level (docs/zones/city_playable.md). Safe to run again:
//                             a partition that is there keeps its place and gets these settings.
//                             It does not save: save the level afterwards.
#include "CoreMinimal.h"

#if WITH_EDITOR
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "UObject/UnrealType.h"
#include "WorldPartition/WorldPartition.h"
#include "WorldPartition/RuntimeHashSet/RuntimePartitionLHGrid.h"
#include "WorldPartition/RuntimeHashSet/WorldPartitionRuntimeHashSet.h"

static void CoHAddPartitions(const TArray<FString>& Args, UWorld* World)
{
	UWorldPartition* WP = World ? World->GetWorldPartition() : nullptr;
	UWorldPartitionRuntimeHashSet* Hash = WP ? Cast<UWorldPartitionRuntimeHashSet>(WP->RuntimeHash) : nullptr;
	const FArrayProperty* Prop = Hash ? FindFProperty<FArrayProperty>(Hash->GetClass(), TEXT("RuntimePartitions")) : nullptr;
	const FStructProperty* Inner = Prop ? CastField<FStructProperty>(Prop->Inner) : nullptr;
	if (!Inner || Inner->Struct != FRuntimePartitionDesc::StaticStruct())
	{
		UE_LOG(LogTemp, Error, TEXT("CoH partitions: %s has no runtime hash set"), World ? *World->GetMapName() : TEXT("no world"));
		return;
	}
	TArray<FRuntimePartitionDesc>& Parts = *Prop->ContainerPtrToValuePtr<TArray<FRuntimePartitionDesc>>(Hash);
	const URuntimePartition* Main = Parts.Num() ? Parts[0].MainLayer.Get() : nullptr;
	struct FWanted { FName Name; uint32 Cell; int32 Range; };
	const FWanted Wanted[] = { { TEXT("Far"), 102400, 204800 }, { TEXT("Ground"), 25600, 102400 } };
	const FUInt32Property* CellProp = FindFProperty<FUInt32Property>(URuntimePartitionLHGrid::StaticClass(), TEXT("CellSize"));
	if (!CellProp) { UE_LOG(LogTemp, Error, TEXT("CoH partitions: no CellSize property in this engine")); return; }
	Hash->Modify();
	for (const FWanted& W : Wanted)
	{
		FRuntimePartitionDesc* Desc = Parts.FindByPredicate([&](const FRuntimePartitionDesc& D) { return D.Name == W.Name; });
		if (!Desc) { Desc = &Parts.AddDefaulted_GetRef(); Desc->Name = W.Name; }
		URuntimePartitionLHGrid* Grid = Cast<URuntimePartitionLHGrid>(Desc->MainLayer);
		if (!Grid)
		{
			Grid = NewObject<URuntimePartitionLHGrid>(Hash, NAME_None);
			Grid->SetDefaultValues();
			if (Main) Grid->BoundsMethod = Main->BoundsMethod;
			Desc->MainLayer = Grid;
		}
		Grid->Name = W.Name;
		CellProp->SetPropertyValue_InContainer(Grid, W.Cell);      // private in the engine class
		Grid->LoadingRange = W.Range;
	}
	Hash->MarkPackageDirty();
	for (const FRuntimePartitionDesc& D : Parts)
	{
		const URuntimePartitionLHGrid* G = Cast<URuntimePartitionLHGrid>(D.MainLayer);
		UE_LOG(LogTemp, Log, TEXT("CoH partitions: %s cell %u loading range %d, %d HLOD setups"), *D.Name.ToString(),
			G ? CellProp->GetPropertyValue_InContainer(G) : 0, D.MainLayer ? D.MainLayer->LoadingRange : 0, D.HLODSetups.Num());
	}
}

static FAutoConsoleCommandWithWorldAndArgs GCoHAddPartitionsCommand(
	TEXT("coh.World.AddPartitions"),
	TEXT("Editor: add the Far and Ground runtime partitions to the open World Partition level (save it afterwards)."),
	FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&CoHAddPartitions));
#endif

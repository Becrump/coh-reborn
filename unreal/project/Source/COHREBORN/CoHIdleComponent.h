// Random idles and standing poses for CoH characters, played the way the
// original sequencer did: each pose is a small graph of moves, and whenever
// a move's clip ends the next one is picked at random from its CycleMove
// list (a move listed twice is twice as likely), blending over the move's
// Interpolate frames. Graphs come from `python -m coh2unreal.idles`; the
// clips are the per-move animations character.py exports with --idles.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/EngineTypes.h"
#include "CoHIdleComponent.generated.h"

class UAnimSequence;
class USkeletalMeshComponent;
class UCoHIdleAnimInstance;

/** One step of a timed pose loop: hold Pose for MinSeconds..MaxSeconds. */
USTRUCT(BlueprintType)
struct FCoHPoseStep
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CoH Idle")
	FName Pose;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CoH Idle")
	float MinSeconds = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CoH Idle")
	float MaxSeconds = 30.f;
};

UCLASS(ClassGroup = (CoH), meta = (BlueprintSpawnableComponent))
class COHREBORN_API UCoHIdleComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UCoHIdleComponent();

	/** idles.json written by coh2unreal.idles (or copied next to the characters). */
	UPROPERTY(EditAnywhere, Category = "CoH Idle")
	FFilePath GraphJson;

	/** Sequencer type of this character's skeleton: male, fem or huge. */
	UPROPERTY(EditAnywhere, Category = "CoH Idle")
	FString SeqType = TEXT("male");

	/** AnimList pose to hold (Ready, ArmsCrossed, Wall_Lean, Lookout...).
	 *  Empty: pick one from PosePool, or from the group's spawn counts. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CoH Idle")
	FName Pose;

	/** Poses to choose from when Pose is empty (empty = every pose in the file
	 *  that needs no prop or partner, weighted by how often spawns used it). */
	UPROPERTY(EditAnywhere, Category = "CoH Idle")
	TArray<FName> PosePool;

	/** Timed pose loop, like the spawn defs' Loop("ArmsCrossed(Timer(Rand(2,67))),
	 *  DoNothing(AnimList(Threaten),Timer(Rand(2,8))),..."): each pose is held
	 *  for a random time, then the next, forever. Overrides Pose when set. */
	UPROPERTY(EditAnywhere, Category = "CoH Idle")
	TArray<FCoHPoseStep> PoseLoop;

	/** Chance (0-1) that a character with no Pose or PoseLoop runs one of the
	 *  file's original timed loops instead of holding one pose. */
	UPROPERTY(EditAnywhere, Category = "CoH Idle", meta = (ClampMin = "0", ClampMax = "1"))
	float FileLoopChance = 0.f;

	/** Content folder holding the imported clips; a clip is found by its move
	 *  name (exact, or as the end of the asset name after an underscore). */
	UPROPERTY(EditAnywhere, Category = "CoH Idle", meta = (ContentDir))
	FDirectoryPath ClipFolder;

	/** Clips by move name; filled from ClipFolder at BeginPlay, or set by hand. */
	UPROPERTY(EditAnywhere, Category = "CoH Idle")
	TMap<FName, TObjectPtr<UAnimSequence>> Clips;

	/** Each character's speed is scaled by a random factor in 1 +/- this. */
	UPROPERTY(EditAnywhere, Category = "CoH Idle", meta = (ClampMin = "0", ClampMax = "0.5"))
	float PlayRateJitter = 0.08f;

	/** Shortest blend between moves, seconds (CoH's default 5 frames is 0.17 s). */
	UPROPERTY(EditAnywhere, Category = "CoH Idle", meta = (ClampMin = "0"))
	float MinBlendTime = 0.25f;

	/** 0 = a different random sequence every play. */
	UPROPERTY(EditAnywhere, Category = "CoH Idle")
	int32 Seed = 0;

	/** Switch pose (blends in from the current move). Returns false if the
	 *  pose is not in the file or none of its clips were found. */
	UFUNCTION(BlueprintCallable, Category = "CoH Idle")
	bool SetPose(FName NewPose);

	/** Stop or resume idling, e.g. while combat animation takes over. */
	UFUNCTION(BlueprintCallable, Category = "CoH Idle")
	void SetIdleActive(bool bActive);

	UFUNCTION(BlueprintPure, Category = "CoH Idle")
	FName GetCurrentMove() const;

protected:
	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType,
		FActorComponentTickFunction* ThisTickFunction) override;

private:
	struct FState
	{
		FName Move;
		float PlayRate = 1.f;
		float BlendTime = 0.f;
		TArray<int32> Next;
		TArray<float> Weight;
	};
	struct FGraph
	{
		FName Pose;
		int32 SpawnCount = 0;
		bool bNeedsProp = false;
		TArray<int32> Entries;
		TArray<FState> States;
	};

	bool LoadGraphs();
	void NextLoopStep();
	void FindClips();
	void PlayState(int32 Index, bool bRandomStart);
	int32 PickNext(const FState& S);

	TArray<FGraph> Graphs;
	TArray<TArray<FCoHPoseStep>> FileLoops;
	int32 LoopStep = INDEX_NONE;
	float LoopTimeLeft = 0.f;
	int32 GraphIndex = INDEX_NONE;
	int32 StateIndex = INDEX_NONE;
	float RateScale = 1.f;
	bool bIdleActive = true;
	FRandomStream Rng;

	UPROPERTY(Transient)
	TObjectPtr<USkeletalMeshComponent> Mesh;
	UPROPERTY(Transient)
	TObjectPtr<UCoHIdleAnimInstance> Anim;
};

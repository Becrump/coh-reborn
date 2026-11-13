// Low-spec support (docs/performance.md): first-run hardware auto-detect,
// street lamp and tree/prop distance limits that follow the graphics preset,
// and a built-in benchmark (console "coh.bench 60", or -cohbench=60 on the
// command line) that writes FPS, GPU time, RAM and VRAM to Saved/Logs/coh_bench.txt.
#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "Subsystems/WorldSubsystem.h"
#include "CoHPerformance.generated.h"

class ULevel;
class UInstancedStaticMeshComponent;

/** What the graphics card reports (Windows, through DXGI). */
struct FCoHGpuInfo
{
	FString Name;
	uint64 DedicatedBytes = 0;   // the card's own memory (VRAM)
	uint64 UsedBytes = 0;        // what this game uses right now
	uint64 BudgetBytes = 0;      // what Windows lets this game use
	bool bValid = false;
};

UCLASS()
class COHREBORN_API UCoHPerformance : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;

	/** Street lamp lights: 0 glow only (no light), 1 near (40 m, no shadows),
	 *  2 far (100 m, shadows), 3 all (as placed). Saved. */
	static int32 LampLevel();
	static void SetLampLevel(UWorld* World, int32 Level);

	/** Trees and small props drawn out to: 0 100 m, 1 200 m, 2 400 m, 3 as placed. Saved. */
	static int32 PropLevel();
	static void SetPropLevel(UWorld* World, int32 Level);

	/** One preset for everything: Unreal scalability (0 Low .. 3 Epic) plus
	 *  lamps, tree distance and civilian/traffic density to match. */
	static void ApplyPreset(UWorld* World, int32 Quality, bool bSave = true);

	/** Unreal's hardware benchmark, then a cap by graphics memory
	 *  (under 6 GB: no Lumen, medium textures; under 3 GB or a laptop chip: Low). */
	static int32 AutoDetect(UWorld* World);

	static FCoHGpuInfo QueryGpu();
	/** One line for the settings screen: GPU, VRAM used of total, RAM. */
	static FString HardwareLine();

	/** Measure for Seconds while the camera turns slowly; append the result to
	 *  Saved/Logs/coh_bench.txt (and quit afterwards when bQuit). */
	void StartBench(float Seconds, bool bQuit);
	bool IsBenchRunning() const { return BenchTick.IsValid(); }

	/** re-apply lamp and tree limits to every loaded level */
	void ApplyToWorld();

private:
	void ApplyToLevel(ULevel* Level);
	void OnLevelAdded(ULevel* Level, UWorld* InWorld);
	bool TickBench(float Delta);
	void FinishBench();

	FDelegateHandle LevelAddedHandle;
	FTSTicker::FDelegateHandle BenchTick;
	FTSTicker::FDelegateHandle BenchDelay;

	/** cull distances as placed, so "as placed" can put them back */
	TMap<TWeakObjectPtr<UInstancedStaticMeshComponent>, FIntPoint> OriginalCull;

	TArray<float> BenchFrameMs;
	TArray<float> BenchGpuMs;
	float BenchSeconds = 0.f;
	float BenchElapsed = 0.f;
	bool bBenchQuit = false;
	uint64 BenchPeakVram = 0;
};

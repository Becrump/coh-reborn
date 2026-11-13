// Automated fly-through for streaming tests (docs/performance.md).
// Console "coh.flythrough <path file> [speed cm/s] [quit]", or on the command line
// -cohflythrough=<path file> [-cohflyspeed=2500] [-cohflywarmup=20] [-cohflyout=<summary file>].
// Moves the player along a waypoint path (one "X,Y,Z" line per point, world cm) at a fixed
// speed, ignoring collision, and logs every frame to Saved/Logs/coh_flythrough.csv:
// frame ms, GPU ms, position, streamed cells loaded/visible, whether streaming has caught up,
// RAM and VRAM. Hitches over 50 ms are listed with their position. One summary line is
// appended to the summary file (default Saved/Logs/coh_bench.txt).
#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "Subsystems/WorldSubsystem.h"
#include "CoHFlythrough.generated.h"

UCLASS()
class COHREBORN_API UCoHFlythrough : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;

	/** false if the path file has fewer than two points */
	bool Start(const FString& PathFile, float SpeedCmPerSec, bool bQuit);
	bool IsRunning() const { return Tick.IsValid(); }

private:
	bool TickFly(float Delta);
	void Finish(const TCHAR* Why);
	FVector PointAt(float Distance, FVector& OutDir) const;

	FTSTicker::FDelegateHandle Tick;
	FTSTicker::FDelegateHandle Delay;

	TArray<FVector> Points;
	TArray<float> CumLen;          // distance along the path at each point
	FString PathName;
	float Speed = 2500.f;
	float Travelled = 0.f;
	float Elapsed = 0.f;
	bool bQuit = false;

	TArray<float> FrameMs;
	TArray<FString> CsvRows;
	TArray<FString> Hitches;
	int32 FramesStreaming = 0;     // frames where streaming had not caught up
	int32 MaxCellsLoaded = 0;
	uint64 PeakVram = 0;
	uint64 PeakRam = 0;
};

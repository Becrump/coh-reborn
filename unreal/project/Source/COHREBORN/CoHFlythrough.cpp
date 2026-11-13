#include "CoHFlythrough.h"
#include "CoHPerformance.h"
#include "Engine/Engine.h"
#include "Engine/LevelStreaming.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMemory.h"
#include "HAL/PlatformMisc.h"
#include "Misc/CommandLine.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "RHI.h"
#include "WorldPartition/WorldPartitionSubsystem.h"

static constexpr float CoHFlyHitchMs = 50.f;

static double CoHFlyGB(uint64 Bytes) { return double(Bytes) / (1024.0 * 1024.0 * 1024.0); }

bool UCoHFlythrough::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UCoHFlythrough::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	FString File;
	if (InWorld.GetMapName().Contains(TEXT("Entry")) || !FParse::Value(FCommandLine::Get(), TEXT("cohflythrough="), File))
		return;
	float Spd = 2500.f, Warmup = 20.f;
	FParse::Value(FCommandLine::Get(), TEXT("cohflyspeed="), Spd);
	FParse::Value(FCommandLine::Get(), TEXT("cohflywarmup="), Warmup);
	// let the first cells, textures and shaders settle before moving
	Delay = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateWeakLambda(this, [this, File, Spd](float)
	{
		Delay.Reset();
		if (!Start(File, Spd, true)) FPlatformMisc::RequestExit(false, TEXT("coh.flythrough"));
		return false;
	}), FMath::Max(1.f, Warmup));
}

void UCoHFlythrough::Deinitialize()
{
	if (Delay.IsValid()) FTSTicker::GetCoreTicker().RemoveTicker(Delay);
	if (Tick.IsValid()) FTSTicker::GetCoreTicker().RemoveTicker(Tick);
	Super::Deinitialize();
}

bool UCoHFlythrough::Start(const FString& PathFile, float SpeedCmPerSec, bool bInQuit)
{
	if (Tick.IsValid()) return true;
	TArray<FString> Lines;
	FString Path = PathFile;
	if (FPaths::IsRelative(Path)) Path = FPaths::ProjectDir() / Path;
	Points.Reset();
	if (FFileHelper::LoadFileToStringArray(Lines, *Path))
	{
		for (const FString& L : Lines)
		{
			TArray<FString> P;
			L.TrimStartAndEnd().ParseIntoArray(P, TEXT(","));
			if (P.Num() >= 3 && !L.StartsWith(TEXT("#")))
				Points.Add(FVector(FCString::Atod(*P[0]), FCString::Atod(*P[1]), FCString::Atod(*P[2])));
		}
	}
	if (Points.Num() < 2)
	{
		UE_LOG(LogTemp, Error, TEXT("coh.flythrough: need at least two X,Y,Z points in %s"), *Path);
		return false;
	}
	CumLen.SetNum(Points.Num());
	CumLen[0] = 0.f;
	for (int32 i = 1; i < Points.Num(); ++i) CumLen[i] = CumLen[i - 1] + FVector::Dist(Points[i - 1], Points[i]);

	PathName = FPaths::GetBaseFilename(Path);
	Speed = FMath::Max(100.f, SpeedCmPerSec);
	Travelled = Elapsed = 0.f;
	bQuit = bInQuit;
	FrameMs.Reset();
	CsvRows.Reset();
	Hitches.Reset();
	FramesStreaming = MaxCellsLoaded = 0;
	PeakVram = PeakRam = 0;
	CsvRows.Add(TEXT("t_s,frame_ms,gpu_ms,x,y,z,cells_loaded,cells_visible,streaming_done,ram_gb,vram_gb"));

	if (UWorld* World = GetWorld())
		if (APlayerController* PC = World->GetFirstPlayerController())
			if (ACharacter* C = Cast<ACharacter>(PC->GetPawn()))
				if (UCharacterMovementComponent* M = C->GetCharacterMovement())
					M->SetMovementMode(MOVE_Flying);   // no falling between teleports

	UE_LOG(LogTemp, Display, TEXT("coh.flythrough: %s, %d points, %.1f km at %.0f m/s"),
		*PathName, Points.Num(), CumLen.Last() / 100000.f, Speed / 100.f);
	Tick = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UCoHFlythrough::TickFly));
	return true;
}

FVector UCoHFlythrough::PointAt(float Distance, FVector& OutDir) const
{
	int32 i = 1;
	while (i < Points.Num() - 1 && CumLen[i] < Distance) ++i;
	const float SegLen = FMath::Max(1.f, CumLen[i] - CumLen[i - 1]);
	const float A = FMath::Clamp((Distance - CumLen[i - 1]) / SegLen, 0.f, 1.f);
	OutDir = (Points[i] - Points[i - 1]).GetSafeNormal();
	return FMath::Lerp(Points[i - 1], Points[i], A);
}

bool UCoHFlythrough::TickFly(float Delta)
{
	UWorld* World = GetWorld();
	if (!World) { Tick.Reset(); return false; }
	Elapsed += Delta;
	Travelled += Speed * Delta;

	FVector Dir;
	const FVector Pos = PointAt(Travelled, Dir);
	if (APlayerController* PC = World->GetFirstPlayerController())
	{
		if (APawn* P = PC->GetPawn())
			P->SetActorLocation(Pos, false, nullptr, ETeleportType::TeleportPhysics);
		if (!Dir.IsNearlyZero())
			PC->SetControlRotation(FRotator(-10.f, Dir.Rotation().Yaw, 0.f));
	}

	// streamed World Partition cells (and level instances) currently loaded / shown
	int32 Loaded = 0, Visible = 0;
	for (ULevelStreaming* LS : World->GetStreamingLevels())
	{
		if (!LS) continue;
		if (LS->IsLevelLoaded()) ++Loaded;
		if (LS->IsLevelVisible()) ++Visible;
	}
	MaxCellsLoaded = FMath::Max(MaxCellsLoaded, Loaded);
	bool bDone = true;
	if (UWorldPartitionSubsystem* WP = World->GetSubsystem<UWorldPartitionSubsystem>())
		bDone = WP->IsAllStreamingCompleted();
	if (!bDone) ++FramesStreaming;

	const float Ms = Delta * 1000.f;
	const float Gpu = FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles(0));
	FrameMs.Add(Ms);
	const FPlatformMemoryStats Mem = FPlatformMemory::GetStats();
	PeakRam = FMath::Max<uint64>(PeakRam, Mem.UsedPhysical);
	uint64 Vram = 0;
	if ((FrameMs.Num() % 30) == 1)
	{
		Vram = UCoHPerformance::QueryGpu().UsedBytes;
		PeakVram = FMath::Max(PeakVram, Vram);
	}
	CsvRows.Add(FString::Printf(TEXT("%.2f,%.1f,%.1f,%.0f,%.0f,%.0f,%d,%d,%d,%.2f,%s"),
		Elapsed, Ms, Gpu, Pos.X, Pos.Y, Pos.Z, Loaded, Visible, bDone ? 1 : 0, CoHFlyGB(Mem.UsedPhysical),
		Vram ? *FString::Printf(TEXT("%.2f"), CoHFlyGB(Vram)) : TEXT("")));
	if (Ms > CoHFlyHitchMs && FrameMs.Num() > 1)
		Hitches.Add(FString::Printf(TEXT("%.0f ms at %.0f s (X %.0f m, Y %.0f m)"), Ms, Elapsed, Pos.X / 100.f, Pos.Y / 100.f));

	if (Travelled < CumLen.Last()) return true;
	Tick.Reset();
	Finish(TEXT("end of path"));
	return false;
}

void UCoHFlythrough::Finish(const TCHAR* Why)
{
	UWorld* World = GetWorld();
	TArray<float> Sorted = FrameMs;
	Sorted.Sort();
	double Sum = 0.0;
	for (float Ms : FrameMs) Sum += Ms;
	const int32 N = FMath::Max(1, FrameMs.Num());
	const double Avg = Sum / N;
	const float P99 = Sorted.Num() ? Sorted[FMath::Clamp(FMath::FloorToInt(Sorted.Num() * 0.99f), 0, Sorted.Num() - 1)] : 0.f;
	const float Worst = Sorted.Num() ? Sorted.Last() : 0.f;
	const FCoHGpuInfo Gpu = UCoHPerformance::QueryGpu();

	const FString Csv = FPaths::ProjectLogDir() / TEXT("coh_flythrough.csv");
	FFileHelper::SaveStringArrayToFile(CsvRows, *Csv);
	if (Hitches.Num())
		FFileHelper::SaveStringArrayToFile(Hitches, *(FPaths::ProjectLogDir() / TEXT("coh_flythrough_hitches.txt")));

	const FString Line = FString::Printf(
		TEXT("%s | FLYTHROUGH %s | map %s | %.1f km at %.0f m/s in %.0f s | avg %.1f FPS (%.1f ms), 1%% low %.1f FPS, worst %.0f ms | ")
		TEXT("hitches >%.0f ms: %d | streaming behind %.0f%% of frames, max %d cells loaded | ")
		TEXT("VRAM peak %.2f of %.1f GB | RAM peak %.2f of %u GB | %s | csv %s\n"),
		*FDateTime::Now().ToString(TEXT("%Y-%m-%d %H:%M")), *PathName, World ? *World->GetMapName() : TEXT("?"),
		CumLen.Num() ? CumLen.Last() / 100000.f : 0.f, Speed / 100.f, Elapsed,
		1000.0 / FMath::Max(0.001, Avg), Avg, 1000.f / FMath::Max(0.001f, P99), Worst,
		CoHFlyHitchMs, Hitches.Num(), 100.0 * FramesStreaming / N, MaxCellsLoaded,
		CoHFlyGB(FMath::Max(PeakVram, Gpu.UsedBytes)), CoHFlyGB(Gpu.DedicatedBytes),
		CoHFlyGB(PeakRam), FPlatformMemory::GetConstants().TotalPhysicalGB, Why, *Csv);

	FString Out = FPaths::ProjectLogDir() / TEXT("coh_bench.txt");
	FParse::Value(FCommandLine::Get(), TEXT("cohflyout="), Out);
	FFileHelper::SaveStringToFile(Line, *Out, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), FILEWRITE_Append);
	UE_LOG(LogTemp, Display, TEXT("coh.flythrough: %s"), *Line);
	if (bQuit) FPlatformMisc::RequestExit(false, TEXT("coh.flythrough"));
}

// ---------------------------------------------------------------- console

static void CoHFlythroughCommand(const TArray<FString>& Args, UWorld* World)
{
	if (!Args.Num()) { UE_LOG(LogTemp, Warning, TEXT("coh.flythrough <path file> [speed cm/s] [quit]")); return; }
	const float Spd = Args.Num() > 1 ? FCString::Atof(*Args[1]) : 2500.f;
	if (UCoHFlythrough* Self = World ? World->GetSubsystem<UCoHFlythrough>() : nullptr)
		Self->Start(Args[0], Spd, Args.Num() > 2 && Args[2] == TEXT("quit"));
}
static FAutoConsoleCommandWithWorldAndArgs CoHFlythroughCmd(TEXT("coh.flythrough"),
	TEXT("coh.flythrough <path file> [speed cm/s] [quit]: fly a waypoint path, log frame time, hitches, streaming, RAM, VRAM to Saved/Logs/coh_flythrough.csv"),
	FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&CoHFlythroughCommand));

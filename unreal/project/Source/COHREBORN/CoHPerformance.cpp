#include "CoHPerformance.h"
#include "CoHLifeManager.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/LocalLightComponent.h"
#include "Engine/Engine.h"
#include "Engine/Level.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameUserSettings.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMemory.h"
#include "HAL/PlatformMisc.h"
#include "Misc/CommandLine.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "RHI.h"

#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include <dxgi1_4.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

// names are prefixed CoHPerf: the module builds in unity mode
static const TCHAR* CoHPerfSection = TEXT("CoH.CitySettings");
static const FName CoHPerfShadowTag(TEXT("CoHPerfShadowOff"));
static constexpr float CoHPerfMeshSmallRadius = 2000.f;   // 20 m: trees and props, not buildings
static bool GCoHPerfDetected = false;

// ---------------------------------------------------------------- settings

static int32 CoHPerfReadLevel(const TCHAR* Key)
{
	int32 Level = 3;
	GConfig->GetInt(CoHPerfSection, Key, Level, GGameUserSettingsIni);
	return FMath::Clamp(Level, 0, 3);
}

int32 UCoHPerformance::LampLevel() { return CoHPerfReadLevel(TEXT("LampLights")); }
int32 UCoHPerformance::PropLevel() { return CoHPerfReadLevel(TEXT("PropDistance")); }

void UCoHPerformance::SetLampLevel(UWorld* World, int32 Level)
{
	GConfig->SetInt(CoHPerfSection, TEXT("LampLights"), FMath::Clamp(Level, 0, 3), GGameUserSettingsIni);
	if (UCoHPerformance* Self = World ? World->GetSubsystem<UCoHPerformance>() : nullptr) Self->ApplyToWorld();
}

void UCoHPerformance::SetPropLevel(UWorld* World, int32 Level)
{
	GConfig->SetInt(CoHPerfSection, TEXT("PropDistance"), FMath::Clamp(Level, 0, 3), GGameUserSettingsIni);
	if (UCoHPerformance* Self = World ? World->GetSubsystem<UCoHPerformance>() : nullptr) Self->ApplyToWorld();
}

static void CoHPerfSetDensity(UWorld* World, float Crowd, float Traffic)
{
	if (World)
		for (TActorIterator<ACoHLifeManager> It(World); It; ++It) { It->CrowdDensity = Crowd; It->TrafficDensity = Traffic; }
	GConfig->SetFloat(CoHPerfSection, TEXT("CrowdDensity"), Crowd, GGameUserSettingsIni);
	GConfig->SetFloat(CoHPerfSection, TEXT("TrafficDensity"), Traffic, GGameUserSettingsIni);
}

/** settings Unreal will not take from Scalability.ini, set from the chosen levels:
 *  Nanite detail follows view distance, the ray tracing scene only at Cinematic lighting */
static void CoHPerfApplyCodeCVars()
{
	UGameUserSettings* S = UGameUserSettings::GetGameUserSettings();
	if (!S) return;
	static const int32 PixelsPerEdge[] = {4, 2, 1, 1, 1};
	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("r.Nanite.MaxPixelsPerEdge")))
		V->Set(PixelsPerEdge[FMath::Clamp(S->GetViewDistanceQuality(), 0, 4)], ECVF_SetByGameSetting);
	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("r.RayTracing.Enable")))
		V->Set(S->GetGlobalIlluminationQuality() >= 4 ? 1 : 0, ECVF_SetByGameSetting);
}

/** lamps, trees and city life that go with a quality level */
static void CoHPerfApplyDerived(UWorld* World, int32 Quality)
{
	static const float Crowd[] = {.35f, .65f, 1.f, 1.f};
	static const float Traffic[] = {.4f, .7f, 1.f, 1.f};
	static const int32 Lamps[] = {1, 1, 2, 3};
	static const int32 Props[] = {0, 1, 2, 3};
	Quality = FMath::Clamp(Quality, 0, 3);
	CoHPerfApplyCodeCVars();
	CoHPerfSetDensity(World, Crowd[Quality], Traffic[Quality]);
	GConfig->SetInt(CoHPerfSection, TEXT("LampLights"), Lamps[Quality], GGameUserSettingsIni);
	GConfig->SetInt(CoHPerfSection, TEXT("PropDistance"), Props[Quality], GGameUserSettingsIni);
	if (UCoHPerformance* Self = World ? World->GetSubsystem<UCoHPerformance>() : nullptr)
		Self->ApplyToWorld();
}

void UCoHPerformance::ApplyPreset(UWorld* World, int32 Quality, bool bSave)
{
	Quality = FMath::Clamp(Quality, 0, 3);
	if (UGameUserSettings* S = UGameUserSettings::GetGameUserSettings())
	{
		S->SetOverallScalabilityLevel(Quality);
		S->ApplyNonResolutionSettings();
		if (bSave) S->SaveSettings();
	}
	CoHPerfApplyDerived(World, Quality);
	if (bSave) GConfig->Flush(false, GGameUserSettingsIni);
}

// ---------------------------------------------------------------- hardware

FCoHGpuInfo UCoHPerformance::QueryGpu()
{
	FCoHGpuInfo Out;
#if PLATFORM_WINDOWS
	IDXGIFactory4* Factory = nullptr;
	if (FAILED(CreateDXGIFactory1(__uuidof(IDXGIFactory4), (void**)&Factory)) || !Factory) return Out;
	IDXGIAdapter1* Adapter = nullptr;
	for (UINT I = 0; Factory->EnumAdapters1(I, &Adapter) != DXGI_ERROR_NOT_FOUND; ++I)
	{
		DXGI_ADAPTER_DESC1 Desc;
		// the game runs on the card with the most memory (skip Microsoft's software adapter)
		if (SUCCEEDED(Adapter->GetDesc1(&Desc)) && !(Desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE)
			&& (uint64)Desc.DedicatedVideoMemory > Out.DedicatedBytes)
		{
			Out.Name = FString(Desc.Description).TrimStartAndEnd();
			Out.DedicatedBytes = Desc.DedicatedVideoMemory;
			IDXGIAdapter3* Adapter3 = nullptr;
			if (SUCCEEDED(Adapter->QueryInterface(__uuidof(IDXGIAdapter3), (void**)&Adapter3)) && Adapter3)
			{
				DXGI_QUERY_VIDEO_MEMORY_INFO Info;
				if (SUCCEEDED(Adapter3->QueryVideoMemoryInfo(0, DXGI_MEMORY_SEGMENT_GROUP_LOCAL, &Info)))
				{
					Out.UsedBytes = Info.CurrentUsage;
					Out.BudgetBytes = Info.Budget;
				}
				Adapter3->Release();
			}
			Out.bValid = true;
		}
		Adapter->Release();
	}
	Factory->Release();
#endif
	return Out;
}

static double CoHPerfGB(uint64 Bytes) { return double(Bytes) / (1024.0 * 1024.0 * 1024.0); }

FString UCoHPerformance::HardwareLine()
{
	const FCoHGpuInfo Gpu = QueryGpu();
	const FPlatformMemoryStats Mem = FPlatformMemory::GetStats();
	FString Line = Gpu.bValid
		? FString::Printf(TEXT("%s: %.1f of %.1f GB video memory"), *Gpu.Name, CoHPerfGB(Gpu.UsedBytes), CoHPerfGB(Gpu.DedicatedBytes))
		: FString(TEXT("Graphics card: unknown"));
	Line += FString::Printf(TEXT("  |  RAM %.1f of %u GB"), CoHPerfGB(Mem.UsedPhysical), FPlatformMemory::GetConstants().TotalPhysicalGB);
	return Line;
}

int32 UCoHPerformance::AutoDetect(UWorld* World)
{
	UGameUserSettings* S = UGameUserSettings::GetGameUserSettings();
	if (!S) return 2;
	S->RunHardwareBenchmark();
	S->ApplyHardwareBenchmarkResults();
	int32 Quality = FMath::Min3(S->GetShadowQuality(), S->GetGlobalIlluminationQuality(), S->GetViewDistanceQuality());
	Quality = FMath::Clamp(Quality, 0, 3);

	// the benchmark measures speed, not memory: the city's textures and
	// Lumen need room, so small cards are capped (Robert's 8 GB card ran out at Epic)
	const FCoHGpuInfo Gpu = QueryGpu();
	const double VramGB = CoHPerfGB(Gpu.DedicatedBytes);
	if (Gpu.bValid && VramGB < 3.0)
	{
		Quality = 0;                                         // laptop / built-in graphics
		S->SetOverallScalabilityLevel(0);
		S->SetResolutionScaleValueEx(67.f);
	}
	else if (Gpu.bValid && VramGB < 6.0)
	{
		Quality = FMath::Min(Quality, 1);
		S->SetTextureQuality(FMath::Min(S->GetTextureQuality(), 1));
		S->SetGlobalIlluminationQuality(FMath::Min(S->GetGlobalIlluminationQuality(), 1));
		S->SetReflectionQuality(FMath::Min(S->GetReflectionQuality(), 1));
		S->SetShadowQuality(FMath::Min(S->GetShadowQuality(), 1));
	}
	else if (Gpu.bValid && VramGB < 10.0)
	{
		Quality = FMath::Min(Quality, 2);                    // High is the 8 GB preset
		if (S->GetOverallScalabilityLevel() == 3) S->SetOverallScalabilityLevel(2);
	}
	S->ApplyNonResolutionSettings();
	S->ApplyResolutionSettings(false);
	S->SaveSettings();
	CoHPerfApplyDerived(World, Quality);
	GConfig->Flush(false, GGameUserSettingsIni);
	UE_LOG(LogTemp, Display, TEXT("CoH graphics auto-detect: %s, %.1f GB VRAM, CPU score %.0f, GPU score %.0f -> quality %d"),
		*Gpu.Name, VramGB, S->GetLastCPUBenchmarkResult(), S->GetLastGPUBenchmarkResult(), Quality);
	return Quality;
}

// ---------------------------------------------------------------- world

bool UCoHPerformance::ShouldCreateSubsystem(UObject* Outer) const
{
	return !IsRunningDedicatedServer() && Super::ShouldCreateSubsystem(Outer);
}

bool UCoHPerformance::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UCoHPerformance::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	UWorld* World = &InWorld;

	if (!GCoHPerfDetected)
	{
		GCoHPerfDetected = true;
		int32 Forced = -1;
		if (FParse::Value(FCommandLine::Get(), TEXT("cohquality="), Forced))
			ApplyPreset(World, Forced, false);              // test runs leave the player's settings alone
		else if (UGameUserSettings* S = UGameUserSettings::GetGameUserSettings())
			if (S->GetLastCPUBenchmarkResult() < 0.f)       // never measured: first start on this PC
				AutoDetect(World);
			else
				CoHPerfApplyCodeCVars();                     // saved settings: Nanite / ray tracing to match
	}

	if (!LevelAddedHandle.IsValid())
	{
		LevelAddedHandle = FWorldDelegates::LevelAddedToWorld.AddUObject(this, &UCoHPerformance::OnLevelAdded);

		float Seconds = 0.f;
		if (!World->GetMapName().Contains(TEXT("Entry")) && FParse::Value(FCommandLine::Get(), TEXT("cohbench="), Seconds) && Seconds > 0.f)
		{
			// let the streamed cells, textures and shaders settle before measuring
			float Warmup = 20.f;
			FParse::Value(FCommandLine::Get(), TEXT("cohbenchwarmup="), Warmup);
			BenchDelay = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateWeakLambda(this, [this, Seconds](float)
			{
				BenchDelay.Reset();
				StartBench(Seconds, true);
				return false;
			}), FMath::Max(1.f, Warmup));
		}
	}
	ApplyToWorld();
}

void UCoHPerformance::Deinitialize()
{
	if (LevelAddedHandle.IsValid()) FWorldDelegates::LevelAddedToWorld.Remove(LevelAddedHandle);
	if (BenchTick.IsValid()) FTSTicker::GetCoreTicker().RemoveTicker(BenchTick);
	if (BenchDelay.IsValid()) FTSTicker::GetCoreTicker().RemoveTicker(BenchDelay);
	BenchTick.Reset();
	BenchDelay.Reset();
	Super::Deinitialize();
}

void UCoHPerformance::OnLevelAdded(ULevel* Level, UWorld* InWorld)
{
	if (InWorld == GetWorld()) ApplyToLevel(Level);
}

void UCoHPerformance::ApplyToWorld()
{
	if (UWorld* World = GetWorld())
		for (ULevel* Level : World->GetLevels())
			ApplyToLevel(Level);
}

static void CoHPerfApplyLamp(ULocalLightComponent* Light, int32 Level)
{
	static const float Distance[] = {0.f, 4000.f, 10000.f, 0.f};
	const bool bHadShadows = Light->CastShadows || Light->ComponentTags.Contains(CoHPerfShadowTag);
	const bool bShadows = bHadShadows && Level >= 2;
	Light->SetVisibility(Level > 0);
	Light->MaxDrawDistance = Distance[Level];
	Light->MaxDistanceFadeRange = Distance[Level] > 0.f ? 1500.f : 0.f;
	if (bHadShadows && !bShadows) Light->ComponentTags.AddUnique(CoHPerfShadowTag);
	else Light->ComponentTags.Remove(CoHPerfShadowTag);
	Light->SetCastShadows(bShadows);
	Light->MarkRenderStateDirty();
}

void UCoHPerformance::ApplyToLevel(ULevel* Level)
{
	if (!Level) return;
	const int32 Lamps = LampLevel();
	const int32 Props = PropLevel();
	static const int32 PropCull[] = {10000, 20000, 40000, 0};

	TArray<ULocalLightComponent*> Lights;
	TArray<UInstancedStaticMeshComponent*> Instanced;
	for (AActor* Actor : Level->Actors)
	{
		if (!IsValid(Actor) || Actor->IsA<APawn>()) continue;

		// street lamps (BP_RebornStreetLamp) and station lamps (ACoHStationLamp)
		if (Actor->GetClass()->GetName().Contains(TEXT("Lamp")))
		{
			Actor->GetComponents(Lights);
			for (ULocalLightComponent* Light : Lights) CoHPerfApplyLamp(Light, Lamps);
		}

		// trees, bushes, props: instanced meshes small enough not to be buildings
		Actor->GetComponents(Instanced);
		for (UInstancedStaticMeshComponent* Ism : Instanced)
		{
			const UStaticMesh* Mesh = Ism->GetStaticMesh();
			if (!Mesh || Mesh->GetBounds().SphereRadius * Ism->GetComponentScale().GetMax() > CoHPerfMeshSmallRadius) continue;
			const FIntPoint* Saved = OriginalCull.Find(Ism);
			const FIntPoint Orig = Saved ? *Saved : FIntPoint(Ism->InstanceStartCullDistance, Ism->InstanceEndCullDistance);
			if (!Saved) OriginalCull.Add(Ism, Orig);
			const int32 Cap = PropCull[Props];
			if (Cap == 0) { Ism->SetCullDistances(Orig.X, Orig.Y); continue; }
			const int32 End = Orig.Y > 0 ? FMath::Min(Orig.Y, Cap) : Cap;
			const int32 Start = Orig.X > 0 ? FMath::Min(Orig.X, End) : End * 4 / 5;   // fade out over the last fifth
			Ism->SetCullDistances(Start, End);
		}
	}
}

// ---------------------------------------------------------------- benchmark

void UCoHPerformance::StartBench(float Seconds, bool bQuit)
{
	if (BenchTick.IsValid()) return;
	BenchFrameMs.Reset();
	BenchGpuMs.Reset();
	BenchSeconds = FMath::Max(5.f, Seconds);
	BenchElapsed = 0.f;
	bBenchQuit = bQuit;
	BenchPeakVram = 0;
	UE_LOG(LogTemp, Display, TEXT("coh.bench: measuring for %.0f s"), BenchSeconds);
	BenchTick = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UCoHPerformance::TickBench));
}

bool UCoHPerformance::TickBench(float Delta)
{
	UWorld* World = GetWorld();
	if (!World) { BenchTick.Reset(); return false; }
	BenchElapsed += Delta;
	BenchFrameMs.Add(Delta * 1000.f);
	BenchGpuMs.Add(FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles(0)));
	if ((BenchFrameMs.Num() % 30) == 0) BenchPeakVram = FMath::Max(BenchPeakVram, QueryGpu().UsedBytes);

	// a slow full turn, so the numbers cover the whole view and not one wall
	if (APlayerController* PC = World->GetFirstPlayerController())
		PC->SetControlRotation(PC->GetControlRotation() + FRotator(0.f, 360.f / 30.f * Delta, 0.f));

	if (BenchElapsed < BenchSeconds) return true;
	BenchTick.Reset();
	FinishBench();
	return false;
}

void UCoHPerformance::FinishBench()
{
	UWorld* World = GetWorld();
	TArray<float> Sorted = BenchFrameMs;
	Sorted.Sort();
	double Sum = 0.0, GpuSum = 0.0;
	for (float Ms : BenchFrameMs) Sum += Ms;
	for (float Ms : BenchGpuMs) GpuSum += Ms;
	const int32 N = FMath::Max(1, BenchFrameMs.Num());
	const double AvgMs = Sum / N;
	const float Worst1 = Sorted.Num() ? Sorted[FMath::Clamp(FMath::FloorToInt(Sorted.Num() * 0.99f), 0, Sorted.Num() - 1)] : 0.f;

	UGameUserSettings* S = UGameUserSettings::GetGameUserSettings();
	float NormScale = 100.f, Scale = 100.f, MinScale = 0.f, MaxScale = 100.f;
	if (S) S->GetResolutionScaleInformationEx(NormScale, Scale, MinScale, MaxScale);
	const FIntPoint Res = S ? S->GetScreenResolution() : FIntPoint::ZeroValue;
	const FCoHGpuInfo Gpu = QueryGpu();
	const FPlatformMemoryStats Mem = FPlatformMemory::GetStats();
	const int32 Overall = S ? S->GetOverallScalabilityLevel() : -1;
	static const TCHAR* Names[] = {TEXT("Low"), TEXT("Medium"), TEXT("High"), TEXT("Epic"), TEXT("Cinematic")};

	const FString Line = FString::Printf(
		TEXT("%s | map %s | preset %s | lamps %d, trees %d | %dx%d at %.0f%% | avg %.1f FPS (%.1f ms), 1%% low %.1f FPS | GPU %.1f ms | ")
		TEXT("VRAM %.2f GB now, %.2f GB peak, card %.1f GB (budget %.1f) | RAM %.2f GB, peak %.2f GB of %u GB | %s | %s\n"),
		*FDateTime::Now().ToString(TEXT("%Y-%m-%d %H:%M")), World ? *World->GetMapName() : TEXT("?"),
		Overall >= 0 && Overall <= 4 ? Names[Overall] : TEXT("Custom"), LampLevel(), PropLevel(),
		Res.X, Res.Y, Scale, 1000.0 / FMath::Max(0.001, AvgMs), AvgMs, 1000.f / FMath::Max(0.001f, Worst1),
		GpuSum / FMath::Max(1, BenchGpuMs.Num()),
		CoHPerfGB(Gpu.UsedBytes), CoHPerfGB(FMath::Max(BenchPeakVram, Gpu.UsedBytes)), CoHPerfGB(Gpu.DedicatedBytes), CoHPerfGB(Gpu.BudgetBytes),
		CoHPerfGB(Mem.UsedPhysical), CoHPerfGB(Mem.PeakUsedPhysical), FPlatformMemory::GetConstants().TotalPhysicalGB,
		*Gpu.Name, *FPlatformMisc::GetCPUBrand().TrimStartAndEnd());

	FString Out = FPaths::ProjectLogDir() / TEXT("coh_bench.txt");
	FParse::Value(FCommandLine::Get(), TEXT("cohbenchout="), Out);
	FFileHelper::SaveStringToFile(Line, *Out, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), FILEWRITE_Append);
	UE_LOG(LogTemp, Display, TEXT("coh.bench: %s"), *Line);
	if (GEngine && World) GEngine->Exec(World, TEXT("memreport -full"));   // detail: Saved/Profiling/MemReports
	if (bBenchQuit) FPlatformMisc::RequestExit(false, TEXT("coh.bench"));
}

// ---------------------------------------------------------------- console

static void CoHPerfBenchCommand(const TArray<FString>& Args, UWorld* World)
{
	const float Seconds = Args.Num() ? FCString::Atof(*Args[0]) : 60.f;
	if (UCoHPerformance* Self = World ? World->GetSubsystem<UCoHPerformance>() : nullptr)
		Self->StartBench(Seconds, Args.Num() > 1 && Args[1] == TEXT("quit"));
}
static FAutoConsoleCommandWithWorldAndArgs CoHPerfBenchCmd(TEXT("coh.bench"),
	TEXT("coh.bench [seconds] [quit]: measure FPS, GPU time, RAM and VRAM while the camera turns; appends to Saved/Logs/coh_bench.txt"),
	FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&CoHPerfBenchCommand));

static void CoHPerfPresetCommand(const TArray<FString>& Args, UWorld* World)
{
	if (Args.Num()) UCoHPerformance::ApplyPreset(World, FCString::Atoi(*Args[0]), false);
}
static FAutoConsoleCommandWithWorldAndArgs CoHPerfPresetCmd(TEXT("coh.preset"),
	TEXT("coh.preset 0-3: Low/Medium/High/Epic with lamps, trees and city life to match (not saved)"),
	FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&CoHPerfPresetCommand));

static void CoHPerfLampsCommand(const TArray<FString>& Args, UWorld* World)
{
	if (Args.Num()) UCoHPerformance::SetLampLevel(World, FCString::Atoi(*Args[0]));
}
static FAutoConsoleCommandWithWorldAndArgs CoHPerfLampsCmd(TEXT("coh.lamps"),
	TEXT("coh.lamps 0-3: street lamp lights glow only / 40 m / 100 m with shadows / all"),
	FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&CoHPerfLampsCommand));

static void CoHPerfPropsCommand(const TArray<FString>& Args, UWorld* World)
{
	if (Args.Num()) UCoHPerformance::SetPropLevel(World, FCString::Atoi(*Args[0]));
}
static FAutoConsoleCommandWithWorldAndArgs CoHPerfPropsCmd(TEXT("coh.trees"),
	TEXT("coh.trees 0-3: trees and props drawn to 100 / 200 / 400 m / as placed"),
	FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&CoHPerfPropsCommand));

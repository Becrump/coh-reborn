// The original power effects (docs/power-effects.md), played from the
// converter's fx_library.json / power_fx.json with the game's own rules: a
// C++ port of coh2unreal.fxsim, which ports partUpdateSystem
// (Game/src/graphics/FX/particle.c) and the effect timeline of fx.c.
//
// UCoHFxLibrary loads the libraries (player powers and the enemy kit) once.
// ACoHFxRunner plays one effect on a character with a target: conditions
// (Time, PrimeHit), events (Create / Local on a bone, Start moving by its
// behavior and tracking the magnet, Posit, Destroy, LifeSpan, ChildFx,
// Sound, alternate pivots) and particle systems (spawn rate, burst, burble,
// emission shapes, velocity, jitter, gravity, drag, magnetism, stickiness,
// size expansion, fades, colour path, flipbooks, streaks, blend modes).
//
// Particles are simulated at the game's 30 ticks per second on every
// machine (never replicated) and drawn as camera-facing quads in one
// procedural mesh per system, with the master particle materials under
// /Game/CoH/FX/Particle (one per blend mode, the texture as a parameter).
// Not yet: effect meshes (geoms), TriggerBits / Cycle conditions, physics
// debris, power colour themes.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "CoHEffects.generated.h"

class FJsonObject;
class UProceduralMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UTexture2D;
class USoundBase;
class USoundAttenuation;

/** A .part system with the engine defaults filled in (game units: feet, ticks). */
struct FCoHPart
{
	float NewPerFrame = 0, Burst = 0, Burble = 0, BurbleFrequency = 1, BurbleThreshold = 0;
	int32 BurbleType = 0, KillOnZero = 0, EmissionType = 0, ExpandType = 0, ColorChangeType = 0;
	bool bLocal = false, bFadeImmediately = false;
	float MoveScale = 0, EmissionLifeSpan = 0, EmissionLifeSpanJitter = 0, EmissionRadius = 0, EmissionHeight = 0;
	FVector EmissionStartJitter = FVector::ZeroVector, InitialVelocity = FVector::ZeroVector, InitialVelocityJitter = FVector::ZeroVector, VelocityJitter = FVector::ZeroVector;
	int32 Spin = 0, SpinJitter = 0, OrientationJitter = 0;
	float Magnetism = 0, Gravity = 0, Drag = 0, Stickiness = 0;
	float Alpha = 255, FadeInBy = 0, FadeOutStart = 0, FadeOutBy = 30;
	float StartSize = 1, StartSizeJitter = 0, EndSize = 1, ExpandRate = 0;
	int32 StreakType = 0, StreakOrient = 0, StreakDirection = 0;
	float StreakScale = 1;
	int32 AnimFrames = 0; float AnimPace = 0;
	FString Blend, Texture;
	TArray<FVector3f> ColorPath;      // rgb 0..255 per tick of age
};

/** A behavior (.bhvr) with an event's overrides applied. */
struct FCoHBhvr
{
	FVector StartJitter = FVector::ZeroVector, InitialVelocity = FVector::ZeroVector, InitialVelocityJitter = FVector::ZeroVector, PositionOffset = FVector::ZeroVector;
	float Gravity = 0, Drag = 0, TrackRate = 0;
};

UCLASS(Config = Game)
class COHREBORN_API UCoHFxLibrary : public UGameInstanceSubsystem
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	static UCoHFxLibrary* Get(const UObject* WorldContext);

	/** Folders with fx_library.json and power_fx.json (player and enemy).
	 *  Default: <out>/fx and <out>/enemies/fx next to the rules. */
	UPROPERTY(Config) TArray<FString> FxDirs;
	UPROPERTY(Config) FString TextureRoot = TEXT("/Game/CoH/FX/Textures");
	UPROPERTY(Config) FString SoundRoot = TEXT("/Game/CoH/FX/Sounds");
	UPROPERTY(Config) FString MaterialRoot = TEXT("/Game/CoH/FX/Particle");
	UPROPERTY(Config) FString GeomRoot = TEXT("/Game/CoH/FX/Geoms");

	TSharedPtr<FJsonObject> Fx(const FString& Path) const;
	const FCoHPart* Part(const FString& Path);
	FCoHBhvr Behavior(const FString& Path, const TSharedPtr<FJsonObject>& Override) const;
	/** Alternate pivots of an effect model (4x3 game matrices, feet). */
	const TArray<TArray<float>>* AltPivots(const FString& Geom) const;
	/** The effects of a power (power_fx.json): ActivationFX, AttackFX, HitFX ... */
	TSharedPtr<FJsonObject> PowerFx(FName Power) const;
	UMaterialInterface* Material(const FString& Texture, const FString& Blend);
	/** A visible effect model (weapons, beams): /Game/CoH/FX/Geoms/<name>, or null. */
	class UStaticMesh* GeomMesh(const FString& Geom);
	/** Its material: M_CoHGeom with the model's first texture. */
	UMaterialInterface* GeomMaterial(const FString& Geom);
	USoundBase* Sound(const FString& Name);
	USoundAttenuation* Attenuation(float RadiusFeet);
	bool IsLoaded() const { return FxTable.Num() > 0; }

	/** Plays an effect on Owner (with Target); returns the runner or null. */
	static class ACoHFxRunner* Play(AActor* Owner, const FString& Path, AActor* Target, float Delay = 0.f);
	/** Plays a power's start effects now and its hit effect on the target at the hit. */
	static bool PlayPower(AActor* Owner, FName Power, AActor* Target, float HitDelay);

private:
	TMap<FString, TSharedPtr<FJsonObject>> FxTable, PartJson, BhvrJson, Geoms, Textures, Sounds, PowerTable;
	/** Parts by path; heap-held so the pointers systems keep stay valid as the cache grows. */
	TMap<FString, TUniquePtr<FCoHPart>> PartCache;
	UPROPERTY() TMap<FString, TObjectPtr<UMaterialInstanceDynamic>> MatCache;
	UPROPERTY() TMap<FString, TObjectPtr<UMaterialInterface>> Masters;
	UPROPERTY() TMap<FString, TObjectPtr<USoundBase>> SoundCache;
	UPROPERTY() TMap<int32, TObjectPtr<USoundAttenuation>> AttenCache;
	UPROPERTY() TMap<FString, TObjectPtr<class UStaticMesh>> GeomCache;
	UPROPERTY() TMap<FString, TObjectPtr<UMaterialInterface>> GeomMatCache;
};

UCLASS(NotPlaceable, Transient)
class COHREBORN_API ACoHFxRunner : public AActor
{
	GENERATED_BODY()
public:
	ACoHFxRunner();
	void Start(const FString& Path, AActor* InOwner, AActor* InTarget);
	virtual void Tick(float DeltaSeconds) override;
	/** Ends the effect: systems stop spawning and fade out. */
	void Stop();

	struct FGeo;
	struct FSystem;
	struct FRun;
private:
	void Step();
	void Draw();
	TArray<TSharedPtr<FRun>> Runs;
	UPROPERTY(Transient) TArray<TObjectPtr<UProceduralMeshComponent>> Pool;
	float Accum = 0.f;
	int32 Ticks = 0;
};

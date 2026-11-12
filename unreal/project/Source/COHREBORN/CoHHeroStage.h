// The Hero Corps terminal's 3D stage (docs/lobby.md): a pedestal on the
// frontend map with the chosen hero standing on it, idling, lit like a
// briefing room, with two searchlights sweeping through the haze behind.
//
// Everything is built from engine basic shapes and light components in code,
// so the empty frontend map (/Engine/Maps/Entry) needs no assets. UCoHFrontend
// spawns it when the HQ opens and makes its camera the view.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CoHHeroStage.generated.h"

class ACoHHeroCharacter;
class UCameraComponent;
class USpotLightComponent;
class UPointLightComponent;
class UStaticMeshComponent;
class UExponentialHeightFogComponent;

UCLASS(Config = Game)
class COHREBORN_API ACoHHeroStage : public AActor
{
	GENERATED_BODY()

public:
	ACoHHeroStage();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	/** Put this hero file on the pedestal (empty = the default hero). */
	void ShowHero(const FString& HeroFile);
	ACoHHeroCharacter* Hero() const { return StageHero; }
	FString ShownHero() const { return Shown; }

	/** Mouse drag on the terminal: turn the hero (degrees). */
	void Turn(float Degrees);
	/** Face the camera again. */
	void ResetTurn();
	/** "Play on hero": the hero turns side-on and uses the power at a dummy. */
	void PlayPower(FName Power);

	// ---- tuning (DefaultGame.ini [/Script/COHREBORN.CoHHeroStage]); the
	// light values are guesses until the first run on the PC
	/** Fixed camera exposure, EV100 (higher = darker). */
	UPROPERTY(Config) float ExposureEV = 4.5f;
	UPROPERTY(Config) float KeyCandela = 220.f;
	UPROPERTY(Config) float RimCandela = 420.f;
	UPROPERTY(Config) float FillCandela = 40.f;
	UPROPERTY(Config) float SearchlightCandela = 2500.f;
	UPROPERTY(Config) float CameraDistance = 640.f;
	UPROPERTY(Config) float CameraFOV = 40.f;
	/** The hero turns a little away from the camera at rest (degrees). */
	UPROPERTY(Config) float RestYaw = -18.f;

private:
	void Build();

	UPROPERTY() TObjectPtr<USceneComponent> Root;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Floor;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Pedestal;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Ring;
	UPROPERTY() TObjectPtr<UCameraComponent> Camera;
	UPROPERTY() TObjectPtr<USpotLightComponent> Key;
	UPROPERTY() TObjectPtr<USpotLightComponent> Rim;
	UPROPERTY() TObjectPtr<UPointLightComponent> Fill;
	UPROPERTY() TObjectPtr<UPointLightComponent> Under;
	UPROPERTY() TArray<TObjectPtr<USpotLightComponent>> Searchlights;
	UPROPERTY() TObjectPtr<UExponentialHeightFogComponent> Fog;
	UPROPERTY(Transient) TObjectPtr<ACoHHeroCharacter> StageHero;

	FString Shown;
	bool bShownOnce = false;
	float Yaw = 0.f;            // the player's turn, added to RestYaw
	float PowerFaceTime = 0.f;  // seconds left side-on after "Play on hero"
	float Time = 0.f;
};

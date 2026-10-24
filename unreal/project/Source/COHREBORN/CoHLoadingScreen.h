#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "CoHLoadingScreen.generated.h"

struct FSlateDynamicImageBrush;

/**
 * Full-screen loading screen shown while a map loads (including the first
 * map at startup). Uses the MoviePlayer so it keeps drawing while the game
 * thread is blocked. The image is a plain PNG under Content/Splash (not an
 * imported asset), so it needs no editor step; swap the file to change it.
 * MoviePlayer is off in the editor, so test with Standalone Game or a build.
 */
UCLASS(Config = Game)
class COHREBORN_API UCoHLoadingScreen : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	/** Image relative to the project's Content folder. */
	UPROPERTY(Config)
	FString ImagePath = TEXT("Splash/LoadingScreen.png");

	/** Keep the art up at least this long so fast loads don't flash it. */
	UPROPERTY(Config)
	float MinimumDisplaySeconds = 2.f;

private:
	void HandlePreLoadMap(const FString& MapName);

	TSharedPtr<FSlateDynamicImageBrush> Brush;
	FDelegateHandle PreLoadMapHandle;
};

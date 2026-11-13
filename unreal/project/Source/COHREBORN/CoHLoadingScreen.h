#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Containers/Ticker.h"
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

	/** After the map loads, the city streams in around the player (World
	 *  Partition): the art stays up until that is done, at most this long. */
	UPROPERTY(Config)
	float MaxStreamingWaitSeconds = 240.f;

private:
	void HandlePreLoadMap(const FString& MapName);
	void HandlePostLoadMap(UWorld* World);
	bool TickStreaming(float DeltaTime);
	void HideStreamingCover();
	TSharedRef<SWidget> MakeScreen(const FText& Label) const;

	FDelegateHandle PostLoadMapHandle;
	FTSTicker::FDelegateHandle StreamingTicker;
	TSharedPtr<SWidget> StreamingCover;
	TWeakObjectPtr<UWorld> StreamingWorld;
	double StreamingStart = 0.0;

	TSharedPtr<FSlateDynamicImageBrush> Brush;
	FDelegateHandle PreLoadMapHandle;
};

#include "CoHLoadingScreen.h"

#include "MoviePlayer.h"
#include "Misc/Paths.h"
#include "Styling/CoreStyle.h"
#include "Styling/SlateBrush.h"
#include "UObject/UObjectGlobals.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Images/SThrobber.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SScaleBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformTime.h"
#include "WorldPartition/WorldPartition.h"
#include "WorldPartition/WorldPartitionSubsystem.h"

void UCoHLoadingScreen::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	if (IsRunningDedicatedServer())
	{
		return;
	}
	// LoadingScreen.png is 1920x1080; Slate reads the file itself on first draw.
	const FString FullPath = FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / ImagePath);
	Brush = MakeShared<FSlateDynamicImageBrush>(FName(*FullPath), FVector2D(1920.f, 1080.f));
	PreLoadMapHandle = FCoreUObjectDelegates::PreLoadMap.AddUObject(this, &UCoHLoadingScreen::HandlePreLoadMap);
	PostLoadMapHandle = FCoreUObjectDelegates::PostLoadMapWithWorld.AddUObject(this, &UCoHLoadingScreen::HandlePostLoadMap);
}

void UCoHLoadingScreen::Deinitialize()
{
	FCoreUObjectDelegates::PreLoadMap.Remove(PreLoadMapHandle);
	FCoreUObjectDelegates::PostLoadMapWithWorld.Remove(PostLoadMapHandle);
	HideStreamingCover();
	Brush.Reset();
	Super::Deinitialize();
}

void UCoHLoadingScreen::HandlePreLoadMap(const FString& MapName)
{
	if (!IsMoviePlayerEnabled() || !Brush.IsValid())
	{
		return;
	}

	TSharedRef<SWidget> Screen = MakeScreen(NSLOCTEXT("CoH", "Loading", "LOADING"));

	FLoadingScreenAttributes Attributes;
	Attributes.bAutoCompleteWhenLoadingCompletes = true;
	Attributes.MinimumLoadingScreenDisplayTime = MinimumDisplaySeconds;
	Attributes.WidgetLoadingScreen = Screen;
	GetMoviePlayer()->SetupLoadingScreen(Attributes);
}

TSharedRef<SWidget> UCoHLoadingScreen::MakeScreen(const FText& Label) const
{
	return
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SBorder)
			.BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush"))
			.BorderBackgroundColor(FLinearColor::Black)
		]
		+ SOverlay::Slot()
		[
			SNew(SScaleBox)
			.Stretch(EStretch::ScaleToFit)
			[
				SNew(SImage).Image(Brush.Get())
			]
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Right)
		.VAlign(VAlign_Bottom)
		.Padding(48.f)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(0.f, 0.f, 12.f, 0.f)
			[
				SNew(SThrobber)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text(Label)
				.Font(FCoreStyle::GetDefaultFontStyle("Bold", 20))
				.ColorAndOpacity(FLinearColor::White)
				.ShadowOffset(FVector2D(2.f, 2.f))
			]
		];

}

// The map is loaded, but a World Partition city still streams in around the
// player, and until it does a joining client sees a black screen (minutes on a
// busy PC). Keep the art up, with what it is waiting for, until it is done.
void UCoHLoadingScreen::HandlePostLoadMap(UWorld* World)
{
	HideStreamingCover();
	if (!World || !World->IsGameWorld() || !World->GetWorldPartition() || !Brush.IsValid()) return;
	UGameViewportClient* VC = World->GetGameViewport();
	if (!VC) return;
	StreamingWorld = World;
	StreamingStart = FPlatformTime::Seconds();
	StreamingCover = MakeScreen(NSLOCTEXT("CoH", "LoadingCity", "LOADING THE CITY"));
	VC->AddViewportWidgetContent(StreamingCover.ToSharedRef(), 1000);
	StreamingTicker = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UCoHLoadingScreen::TickStreaming), 0.5f);
}

bool UCoHLoadingScreen::TickStreaming(float DeltaTime)
{
	UWorld* World = StreamingWorld.Get();
	const double Waited = FPlatformTime::Seconds() - StreamingStart;
	if (!World) { HideStreamingCover(); return false; }
	const APlayerController* LocalPC = World->GetFirstPlayerController();
	const bool bPawn = LocalPC && LocalPC->GetPawn();
	const UWorldPartitionSubsystem* WP = World->GetSubsystem<UWorldPartitionSubsystem>();
	const bool bStreamed = !WP || WP->IsStreamingCompleted();
	if ((bPawn && bStreamed) || Waited > MaxStreamingWaitSeconds)
	{
		UE_LOG(LogTemp, Log, TEXT("CoH loading: city ready after %.0f s%s"), Waited, (bPawn && bStreamed) ? TEXT("") : TEXT(" (gave up waiting)"));
		HideStreamingCover();
		return false;
	}
	return true;
}

void UCoHLoadingScreen::HideStreamingCover()
{
	if (StreamingTicker.IsValid()) { FTSTicker::GetCoreTicker().RemoveTicker(StreamingTicker); StreamingTicker.Reset(); }
	if (StreamingCover.IsValid())
	{
		if (UWorld* World = StreamingWorld.Get())
			if (UGameViewportClient* VC = World->GetGameViewport()) VC->RemoveViewportWidgetContent(StreamingCover.ToSharedRef());
		StreamingCover.Reset();
	}
	StreamingWorld.Reset();
}

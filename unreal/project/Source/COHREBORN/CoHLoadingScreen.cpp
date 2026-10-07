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
}

void UCoHLoadingScreen::Deinitialize()
{
	FCoreUObjectDelegates::PreLoadMap.Remove(PreLoadMapHandle);
	Brush.Reset();
	Super::Deinitialize();
}

void UCoHLoadingScreen::HandlePreLoadMap(const FString& MapName)
{
	if (!IsMoviePlayerEnabled() || !Brush.IsValid())
	{
		return;
	}

	TSharedRef<SWidget> Screen =
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
				.Text(NSLOCTEXT("CoH", "Loading", "LOADING"))
				.Font(FCoreStyle::GetDefaultFontStyle("Bold", 20))
				.ColorAndOpacity(FLinearColor::White)
				.ShadowOffset(FVector2D(2.f, 2.f))
			]
		];

	FLoadingScreenAttributes Attributes;
	Attributes.bAutoCompleteWhenLoadingCompletes = true;
	Attributes.MinimumLoadingScreenDisplayTime = MinimumDisplaySeconds;
	Attributes.WidgetLoadingScreen = Screen;
	GetMoviePlayer()->SetupLoadingScreen(Attributes);
}

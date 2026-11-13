#include "CoHGraphicsMenu.h"
#include "CoHLifeManager.h"
#include "CoHPerformance.h"
#include "CoHHeroCharacter.h"
#include "Engine/Engine.h"
#include "Engine/PostProcessVolume.h"
#include "Materials/MaterialInterface.h"
#include "Engine/GameViewportClient.h"
#include "EngineUtils.h"
#include "GameFramework/GameUserSettings.h"
#include "GameFramework/PlayerController.h"
#include "Misc/ConfigCacheIni.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

void UCoHGraphicsMenu::ApplyQuality(int32 Quality)
{
    // scalability plus lamps, tree distance and city life to match (CoHPerformance)
    UCoHPerformance::ApplyPreset(Player.IsValid() ? Player->GetWorld() : nullptr, Quality);
}

void UCoHGraphicsMenu::ApplyDensity(float Crowd, float Traffic)
{
    Crowd = FMath::Clamp(Crowd, 0.f, 1.f);
    Traffic = FMath::Clamp(Traffic, 0.f, 1.f);
    if (Player.IsValid())
        for (TActorIterator<ACoHLifeManager> It(Player->GetWorld()); It; ++It)
        { It->CrowdDensity = Crowd; It->TrafficDensity = Traffic; }
    GConfig->SetFloat(TEXT("CoH.CitySettings"), TEXT("CrowdDensity"), Crowd, GGameUserSettingsIni);
    GConfig->SetFloat(TEXT("CoH.CitySettings"), TEXT("TrafficDensity"), Traffic, GGameUserSettingsIni);
}

static const TCHAR* ComicAssets[] = {
    TEXT("/Game/CoH/Materials/MI_CoH_Comic.MI_CoH_Comic"),
    TEXT("/Game/CoH/Materials/MI_CoH_Comic_Strong.MI_CoH_Comic_Strong"),
    TEXT("/Game/CoH/Materials/MI_CoH_Comic_Vibrant.MI_CoH_Comic_Vibrant")};

int32 UCoHGraphicsMenu::SavedComic()
{
    int32 Mode = 3;                  // vibrant by default
    GConfig->GetInt(TEXT("CoH.CitySettings"), TEXT("ComicLook"), Mode, GGameUserSettingsIni);
    return FMath::Clamp(Mode, 0, 3);
}

void UCoHGraphicsMenu::ApplyComic(UObject* WorldContext, int32 Mode)
{
    Mode = FMath::Clamp(Mode, 0, 3);
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (World)
    {
        UMaterialInterface* Light = LoadObject<UMaterialInterface>(nullptr, ComicAssets[0]);
        UMaterialInterface* Strong = LoadObject<UMaterialInterface>(nullptr, ComicAssets[1]);
        UMaterialInterface* Vibrant = LoadObject<UMaterialInterface>(nullptr, ComicAssets[2]);
        for (TActorIterator<APostProcessVolume> It(World); It; ++It)
            for (FWeightedBlendable& B : It->Settings.WeightedBlendables.Array)
                if (B.Object && (B.Object == Light || B.Object == Strong || B.Object == Vibrant))
                {
                    B.Object = Mode == 2 && Strong ? Strong : Mode == 3 && Vibrant ? Vibrant : Light;
                    B.Weight = Mode == 0 ? 0.f : 1.f;
                }
    }
    GConfig->SetInt(TEXT("CoH.CitySettings"), TEXT("ComicLook"), Mode, GGameUserSettingsIni);
}

void UCoHGraphicsMenu::Close()
{
    if (Panel.IsValid() && GEngine && GEngine->GameViewport)
        GEngine->GameViewport->RemoveViewportWidgetContent(Panel.ToSharedRef());
    Panel.Reset();
    if (Player.IsValid())
    {
        ACoHHeroCharacter::RestoreGameInput(Player.Get());
    }
    if (auto* Settings = UGameUserSettings::GetGameUserSettings()) Settings->SaveSettings();
    GConfig->Flush(false, GGameUserSettingsIni);
}

void UCoHGraphicsMenu::Toggle(APlayerController* Controller)
{
    if (Panel.IsValid()) { Close(); return; }
    if (!Controller || !GEngine || !GEngine->GameViewport) return;
    Player = Controller;
    TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)
        [SNew(STextBlock).Text(FText::FromString(TEXT("GRAPHICS & CITY LIFE"))).Font(FCoreStyle::GetDefaultFontStyle("Bold", 22))];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)
        [SNew(STextBlock).Text_Lambda([Controller] {
            return FText::FromString(FString::Printf(TEXT("%.0f FPS  |  F10 opens settings"), 1.f / FMath::Max(.001f, Controller->GetWorld()->GetDeltaSeconds())));
        })];
    // which card, how much of its memory the game uses (refreshed once a second)
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)
        [SNew(STextBlock).AutoWrapText(true).ColorAndOpacity(FLinearColor(.7f, .78f, .85f)).Text_Lambda([] {
            static double Next = 0.0; static FString Line;
            if (FPlatformTime::Seconds() >= Next) { Line = UCoHPerformance::HardwareLine(); Next = FPlatformTime::Seconds() + 1.0; }
            return FText::FromString(Line);
        })];
    Rows->AddSlot().AutoHeight()[SNew(STextBlock).Text_Lambda([] {
        const int32 Q = UGameUserSettings::GetGameUserSettings()->GetOverallScalabilityLevel();
        const TCHAR* N[] = {TEXT("Low"), TEXT("Medium"), TEXT("High"), TEXT("Epic"), TEXT("Cinematic")};
        return FText::FromString(FString::Printf(TEXT("Quality: %s"), Q >= 0 && Q <= 4 ? N[Q] : TEXT("Custom")));
    })];
    TSharedRef<SHorizontalBox> Presets = SNew(SHorizontalBox);
    const TCHAR* Names[] = {TEXT("Low"), TEXT("Medium"), TEXT("High"), TEXT("Epic")};
    for (int32 I = 0; I < 4; ++I)
        Presets->AddSlot().FillWidth(1).Padding(2)
            [SNew(SButton).Text(FText::FromString(Names[I])).OnClicked_Lambda([this, I] { ApplyQuality(I); return FReply::Handled(); })];
    Presets->AddSlot().FillWidth(1.3f).Padding(2)
        [SNew(SButton).Text(FText::FromString(TEXT("Auto"))).ToolTipText(FText::FromString(TEXT("Measure this PC and pick a preset")))
            .OnClicked_Lambda([Controller] { UCoHPerformance::AutoDetect(Controller->GetWorld()); return FReply::Handled(); })];
    Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 12)[Presets];
    // street lamps and trees: the two city costs a weaker PC feels first
    Rows->AddSlot().AutoHeight()[SNew(STextBlock).Text_Lambda([] {
        const TCHAR* L[] = {TEXT("glow only"), TEXT("near (40 m)"), TEXT("far (100 m, shadows)"), TEXT("all")};
        return FText::FromString(FString::Printf(TEXT("Street lamp lights: %s"), L[UCoHPerformance::LampLevel()]));
    })];
    TSharedRef<SHorizontalBox> LampRow = SNew(SHorizontalBox);
    const TCHAR* LampNames[] = {TEXT("Glow"), TEXT("Near"), TEXT("Far"), TEXT("All")};
    for (int32 I = 0; I < 4; ++I)
        LampRow->AddSlot().FillWidth(1).Padding(2)
            [SNew(SButton).Text(FText::FromString(LampNames[I])).OnClicked_Lambda([Controller, I] { UCoHPerformance::SetLampLevel(Controller->GetWorld(), I); return FReply::Handled(); })];
    Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 12)[LampRow];
    Rows->AddSlot().AutoHeight()[SNew(STextBlock).Text_Lambda([] {
        const TCHAR* P[] = {TEXT("100 m"), TEXT("200 m"), TEXT("400 m"), TEXT("as placed")};
        return FText::FromString(FString::Printf(TEXT("Trees and props drawn to: %s"), P[UCoHPerformance::PropLevel()]));
    })];
    TSharedRef<SHorizontalBox> PropRow = SNew(SHorizontalBox);
    const TCHAR* PropNames[] = {TEXT("100 m"), TEXT("200 m"), TEXT("400 m"), TEXT("Max")};
    for (int32 I = 0; I < 4; ++I)
        PropRow->AddSlot().FillWidth(1).Padding(2)
            [SNew(SButton).Text(FText::FromString(PropNames[I])).OnClicked_Lambda([Controller, I] { UCoHPerformance::SetPropLevel(Controller->GetWorld(), I); return FReply::Handled(); })];
    Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 12)[PropRow];
    Rows->AddSlot().AutoHeight()[SNew(STextBlock).Text_Lambda([] {
        float N, V, Min, Max;
        UGameUserSettings::GetGameUserSettings()->GetResolutionScaleInformationEx(N,V,Min,Max);
        return FText::FromString(FString::Printf(TEXT("Render scale: %.0f%%"), V));
    })];
    Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 18)
        [SNew(SSlider).Value_Lambda([] { float N, V, Min, Max; UGameUserSettings::GetGameUserSettings()->GetResolutionScaleInformationEx(N,V,Min,Max); return (V - 50.f) / 50.f; })
            .OnValueChanged_Lambda([](float V) { auto* S = UGameUserSettings::GetGameUserSettings(); S->SetResolutionScaleValueEx(50.f + V * 50.f); S->ApplyNonResolutionSettings(); })];
    Rows->AddSlot().AutoHeight()[SNew(STextBlock).Text_Lambda([] {
        const TCHAR* C[] = {TEXT("off"), TEXT("light comic"), TEXT("strong comic"), TEXT("vibrant comic")};
        return FText::FromString(FString::Printf(TEXT("Comic look: %s"), C[SavedComic()]));
    })];
    TSharedRef<SHorizontalBox> Comic = SNew(SHorizontalBox);
    const TCHAR* ComicNames[] = {TEXT("Off"), TEXT("Light"), TEXT("Strong"), TEXT("Vibrant")};
    for (int32 I = 0; I < 4; ++I)
        Comic->AddSlot().FillWidth(1).Padding(2)
            [SNew(SButton).Text(FText::FromString(ComicNames[I])).OnClicked_Lambda([Controller, I] { ApplyComic(Controller, I); return FReply::Handled(); })];
    Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 18)[Comic];
    Rows->AddSlot().AutoHeight()[SNew(STextBlock).Text(FText::FromString(TEXT("Civilian density")))];
    Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 18)[SNew(SSlider).Value_Lambda([] { float C = 1.f; GConfig->GetFloat(TEXT("CoH.CitySettings"), TEXT("CrowdDensity"), C, GGameUserSettingsIni); return C; }).OnValueChanged_Lambda([this](float V) {
        float T = 1.f; GConfig->GetFloat(TEXT("CoH.CitySettings"), TEXT("TrafficDensity"), T, GGameUserSettingsIni); ApplyDensity(V, T);
    })];
    Rows->AddSlot().AutoHeight()[SNew(STextBlock).Text(FText::FromString(TEXT("Traffic density")))];
    Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 18)[SNew(SSlider).Value_Lambda([] { float T = 1.f; GConfig->GetFloat(TEXT("CoH.CitySettings"), TEXT("TrafficDensity"), T, GGameUserSettingsIni); return T; }).OnValueChanged_Lambda([this](float V) {
        float C = 1.f; GConfig->GetFloat(TEXT("CoH.CitySettings"), TEXT("CrowdDensity"), C, GGameUserSettingsIni); ApplyDensity(C, V);
    })];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)[SNew(SButton).Text_Lambda([] {
        const float Cap = UGameUserSettings::GetGameUserSettings()->GetFrameRateLimit();
        return FText::FromString(Cap > 0 ? FString::Printf(TEXT("FPS cap: %.0f (click to change)"), Cap) : TEXT("FPS cap: Unlimited (click to change)"));
    }).OnClicked_Lambda([] { auto* S = UGameUserSettings::GetGameUserSettings(); const float C = S->GetFrameRateLimit(); S->SetFrameRateLimit(C == 30 ? 60 : C == 60 ? 120 : C == 120 ? 0 : 30); S->ApplyNonResolutionSettings(); return FReply::Handled(); })];
    // window mode and resolution: a smaller screen is the biggest saving on a weak card
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)[SNew(SButton).Text_Lambda([] {
        auto* S = UGameUserSettings::GetGameUserSettings();
        const EWindowMode::Type M = S->GetFullscreenMode();
        const FIntPoint R = S->GetScreenResolution();
        return FText::FromString(FString::Printf(TEXT("Display: %s %dx%d (click to change mode)"),
            M == EWindowMode::Fullscreen ? TEXT("fullscreen") : M == EWindowMode::WindowedFullscreen ? TEXT("borderless") : TEXT("window"), R.X, R.Y));
    }).OnClicked_Lambda([] {
        auto* S = UGameUserSettings::GetGameUserSettings();
        const EWindowMode::Type M = S->GetFullscreenMode();
        S->SetFullscreenMode(M == EWindowMode::Windowed ? EWindowMode::WindowedFullscreen : M == EWindowMode::WindowedFullscreen ? EWindowMode::Fullscreen : EWindowMode::Windowed);
        if (S->GetFullscreenMode() == EWindowMode::WindowedFullscreen) S->SetScreenResolution(S->GetDesktopResolution());
        S->ApplyResolutionSettings(false);
        return FReply::Handled();
    })];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)[SNew(SButton).Text(FText::FromString(TEXT("Resolution: next size"))).OnClicked_Lambda([] {
        auto* S = UGameUserSettings::GetGameUserSettings();
        const FIntPoint Desk = S->GetDesktopResolution();
        const FIntPoint Sizes[] = {{1280, 720}, {1600, 900}, {1920, 1080}, {2560, 1440}, {3840, 2160}};
        TArray<FIntPoint> Fit;
        for (const FIntPoint& Z : Sizes) if (Z.X <= Desk.X && Z.Y <= Desk.Y) Fit.Add(Z);
        if (Fit.Num() == 0) Fit.Add(Desk);
        const int32 At = Fit.IndexOfByKey(S->GetScreenResolution());
        S->SetScreenResolution(Fit[(At + 1) % Fit.Num()]);
        if (S->GetFullscreenMode() == EWindowMode::WindowedFullscreen) S->SetFullscreenMode(EWindowMode::Windowed);
        S->ApplyResolutionSettings(false);
        return FReply::Handled();
    })];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 18)[SNew(SCheckBox)
        .IsChecked_Lambda([] { return UGameUserSettings::GetGameUserSettings()->IsVSyncEnabled() ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; })
        .OnCheckStateChanged_Lambda([](ECheckBoxState C) { auto* S = UGameUserSettings::GetGameUserSettings(); S->SetVSyncEnabled(C == ECheckBoxState::Checked); S->ApplyNonResolutionSettings(); })
        [SNew(STextBlock).Text(FText::FromString(TEXT("VSync")))]];
    Rows->AddSlot().AutoHeight()[SNew(SButton).Text(FText::FromString(TEXT("Save & return to game"))).OnClicked_Lambda([this] { Close(); return FReply::Handled(); })];
    Panel = SNew(SOverlay) + SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
        [SNew(SBox).WidthOverride(500).MaxDesiredHeight(660)[SNew(SBorder).Padding(24).BorderBackgroundColor(FLinearColor(.025f,.045f,.065f,.98f))
            [SNew(SScrollBox) + SScrollBox::Slot()[Rows]]]];   // scrolls on a 720p screen
    GEngine->GameViewport->AddViewportWidgetContent(Panel.ToSharedRef(), 100);
    Controller->bShowMouseCursor = true;
    FInputModeGameAndUI Mode;
    Mode.SetWidgetToFocus(Panel); Mode.SetHideCursorDuringCapture(false);
    Controller->SetInputMode(Mode);
}

#include "CoHGraphicsMenu.h"
#include "CoHLifeManager.h"
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
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

void UCoHGraphicsMenu::ApplyQuality(int32 Quality)
{
    if (auto* Settings = UGameUserSettings::GetGameUserSettings())
    {
        Settings->SetOverallScalabilityLevel(FMath::Clamp(Quality, 0, 3));
        Settings->ApplyNonResolutionSettings();
        Settings->SaveSettings();
    }
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
    float Crowd = 1.f, Traffic = 1.f;
    GConfig->GetFloat(TEXT("CoH.CitySettings"), TEXT("CrowdDensity"), Crowd, GGameUserSettingsIni);
    GConfig->GetFloat(TEXT("CoH.CitySettings"), TEXT("TrafficDensity"), Traffic, GGameUserSettingsIni);
    TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)
        [SNew(STextBlock).Text(FText::FromString(TEXT("GRAPHICS & CITY LIFE"))).Font(FCoreStyle::GetDefaultFontStyle("Bold", 22))];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)
        [SNew(STextBlock).Text_Lambda([Controller] {
            return FText::FromString(FString::Printf(TEXT("%.0f FPS  |  F10 opens settings"), 1.f / FMath::Max(.001f, Controller->GetWorld()->GetDeltaSeconds())));
        })];
    TSharedRef<SHorizontalBox> Presets = SNew(SHorizontalBox);
    const TCHAR* Names[] = {TEXT("Low"), TEXT("Medium"), TEXT("High"), TEXT("Epic")};
    for (int32 I = 0; I < 4; ++I)
        Presets->AddSlot().FillWidth(1).Padding(2)
            [SNew(SButton).Text(FText::FromString(Names[I])).OnClicked_Lambda([this, I] { ApplyQuality(I); return FReply::Handled(); })];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)[Presets];
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
    Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 18)[SNew(SSlider).Value(Crowd).OnValueChanged_Lambda([this](float V) {
        float T = 1.f; GConfig->GetFloat(TEXT("CoH.CitySettings"), TEXT("TrafficDensity"), T, GGameUserSettingsIni); ApplyDensity(V, T);
    })];
    Rows->AddSlot().AutoHeight()[SNew(STextBlock).Text(FText::FromString(TEXT("Traffic density")))];
    Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 18)[SNew(SSlider).Value(Traffic).OnValueChanged_Lambda([this](float V) {
        float C = 1.f; GConfig->GetFloat(TEXT("CoH.CitySettings"), TEXT("CrowdDensity"), C, GGameUserSettingsIni); ApplyDensity(C, V);
    })];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)[SNew(SButton).Text_Lambda([] {
        const float Cap = UGameUserSettings::GetGameUserSettings()->GetFrameRateLimit();
        return FText::FromString(Cap > 0 ? FString::Printf(TEXT("FPS cap: %.0f (click to change)"), Cap) : TEXT("FPS cap: Unlimited (click to change)"));
    }).OnClicked_Lambda([] { auto* S = UGameUserSettings::GetGameUserSettings(); const float C = S->GetFrameRateLimit(); S->SetFrameRateLimit(C == 30 ? 60 : C == 60 ? 120 : C == 120 ? 0 : 30); S->ApplyNonResolutionSettings(); return FReply::Handled(); })];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 18)[SNew(SCheckBox)
        .IsChecked_Lambda([] { return UGameUserSettings::GetGameUserSettings()->IsVSyncEnabled() ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; })
        .OnCheckStateChanged_Lambda([](ECheckBoxState C) { auto* S = UGameUserSettings::GetGameUserSettings(); S->SetVSyncEnabled(C == ECheckBoxState::Checked); S->ApplyNonResolutionSettings(); })
        [SNew(STextBlock).Text(FText::FromString(TEXT("VSync")))]];
    Rows->AddSlot().AutoHeight()[SNew(SButton).Text(FText::FromString(TEXT("Save & return to game"))).OnClicked_Lambda([this] { Close(); return FReply::Handled(); })];
    Panel = SNew(SOverlay) + SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
        [SNew(SBox).WidthOverride(460)[SNew(SBorder).Padding(24).BorderBackgroundColor(FLinearColor(.025f,.045f,.065f,.98f))[Rows]]];
    GEngine->GameViewport->AddViewportWidgetContent(Panel.ToSharedRef(), 100);
    Controller->bShowMouseCursor = true;
    FInputModeGameAndUI Mode;
    Mode.SetWidgetToFocus(Panel); Mode.SetHideCursorDuringCapture(false);
    Controller->SetInputMode(Mode);
}

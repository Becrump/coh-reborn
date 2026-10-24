// Player HUD for the power system (Slate, built in code like the monorail
// menu): health / endurance, the target window with con colour, a 10-slot
// power tray with recharge timers, floating combat numbers, and the Power
// Browser (P) that lists every archetype, power set and power so a tester
// can put any power on the tray.
#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Blueprint/UserWidget.h"
#include "CoHPowerUI.generated.h"

class APlayerController;
class UCoHPowerComponent;
class SScrollBox;
class STextBlock;
struct FSlateBrush;

class COHREBORN_API SCoHHud : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHHud) {}
		SLATE_ARGUMENT(TWeakObjectPtr<APlayerController>, Player)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	virtual ~SCoHHud() override;

	void ToggleBrowser();
	/** The customize panel (emitter point, theme, the two power colours) with a live preview:
	 *  it opens whenever a power is chosen, from the browser or the level-up pick. */
	void OpenCustomize(FName Power, bool bReturnToBrowser);
	void CloseCustomize();
	bool IsCustomizeOpen() const;
	bool IsBrowserOpen() const;
	/** Animation test bench (F8): every clip on the hero skeleton. */
	void ToggleBench();
	virtual void Tick(const FGeometry& Geometry, const double Time, const float Dt) override;
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& Geometry, const FSlateRect& Culling,
		FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle& Style, bool bParentEnabled) const override;

private:
	UCoHPowerComponent* Me() const;
	UCoHPowerComponent* TargetComp() const;
	const FSlateBrush* IconFor(FName Power);
	const FSlateBrush* IconByName(const FString& Icon);
	TSharedRef<SWidget> MakeSlot(int32 Index);
	TSharedRef<SWidget> MakeBar(TFunction<float()> Fraction, FLinearColor Colour, TFunction<FText()> Label);
	TSharedRef<SWidget> MakeBrowser();
	TSharedRef<SWidget> MakeCustomize();
	TSharedPtr<SWidget> Customize;
	FName CustomPower;
	bool bCustomBack = false;
	void ShowSets(const FString& Category);
	void ShowPowers(const FString& SetId);
	/** The open level-up pick: only what the original rules allow. */
	void ShowPicks();
	class UCoHHeroProgress* Progress() const;
	void OnText(AActor* Who, const FString& Text, FLinearColor Colour);
	void SetCursor(bool bOn);
	TSharedRef<SWidget> MakeBench();
	void FillBench();
	void SelectClip(const FSoftObjectPath& Clip);
	void AssignClip(FName Power);
	FName SlotPower(int32 Slot) const;
	TSharedPtr<SWidget> Bench;
	TSharedPtr<SScrollBox> ClipList;
	TArray<FSoftObjectPath> Clips;
	FSoftObjectPath SelectedClip;
	FString ClipFilter;

	TWeakObjectPtr<APlayerController> Player;
	TMap<FString, TSharedPtr<FSlateBrush>> Brushes;
	TSharedPtr<SWidget> Browser;
	TSharedPtr<SScrollBox> SetList, PowerList;
	TSharedPtr<STextBlock> BrowserTitle;
	int32 SelectedSlot = 0;
	FDelegateHandle TextHandle;

	struct FFloat { TWeakObjectPtr<AActor> Who; FString Text; FLinearColor Colour; float Age = 0; float Drift = 0; };
	TArray<FFloat> Floats;
};


/** UMG wrapper: the HUD as a UserWidget, so it can be added with
 *  CreateWidget / AddToViewport and placed inside designer-made UMG screens. */
UCLASS()
class COHREBORN_API UCoHHudWidget : public UUserWidget
{
	GENERATED_BODY()
public:
	void ToggleBrowser() { if (Hud) Hud->ToggleBrowser(); }
	void ToggleBench() { if (Hud) Hud->ToggleBench(); }
protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void ReleaseSlateResources(bool bReleaseChildren) override;
private:
	TSharedPtr<SCoHHud> Hud;
};

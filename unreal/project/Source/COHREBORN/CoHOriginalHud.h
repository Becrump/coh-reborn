// The original City of Heroes HUD windows, ported from Game/src/UI:
// the status window (uiStatus.c: health, endurance, XP ring, level),
// the target window (uiTarget.c), the power tray (uiTray.c) and the
// inspiration tray, inside the original window system (uiWindows.c:
// default layout from uiWindows_init.c, frames, jelly tabs with child
// buttons, drag by the jelly, positions saved per player).
//
// It draws like the original: immediate mode, every frame, in the original
// pixel units, with the original art (FCoHUIArt). It needs Content/UI; without
// it SCoHHud keeps its plain test HUD.
#pragma once

#include "CoreMinimal.h"
#include "Widgets/SLeafWidget.h"
#include "CoHUIArt.h"

class APlayerController;
class UCoHPowerComponent;
class UCoHHeroProgress;
struct FSlateBrush;

class COHREBORN_API SCoHOriginalHud : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHOriginalHud) {}
		SLATE_ARGUMENT(TWeakObjectPtr<APlayerController>, Player)
		/** A tray slot was clicked (bCtrl: the auto-attack lock, as Ctrl + number). */
		SLATE_ARGUMENT(TFunction<void(int32 Slot, bool bCtrl)>, OnSlotClicked)
		/** The slot the Power Browser will fill, or -1. */
		SLATE_ARGUMENT(TFunction<int32()>, SelectedSlot)
		/** A power's icon (the existing power database lookup). */
		SLATE_ARGUMENT(TFunction<const FSlateBrush*(FName)>, IconFor)
		/** A child button that runs a command: "powers", "enhancements"... */
		SLATE_ARGUMENT(TFunction<void(const FString&)>, OnCommand)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	/** Puts every window back where the original game puts it. */
	void ResetLayout();
	void ToggleWindow(int32 Id);

	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(1, 1); }
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& Geometry, const FSlateRect& Culling,
		FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle& Style, bool bParentEnabled) const override;
	virtual FReply OnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event) override;
	virtual FReply OnMouseButtonUp(const FGeometry& Geometry, const FPointerEvent& Event) override;
	virtual FReply OnMouseMove(const FGeometry& Geometry, const FPointerEvent& Event) override;

	// window ids (the original WDW_ names)
	enum EWdw : int32 { WDW_STAT_BARS, WDW_TARGET, WDW_TRAY, WDW_INSPIRATION, WDW_COUNT };

private:
	enum class EH : uint8 { Left, Center, Right };
	enum class EV : uint8 { Top, Middle, Bottom };
	struct FChild { FString Name; int32 Wdw = -1; FString Command; };
	struct FWin
	{
		FString Key;
		EH H = EH::Left; EV V = EV::Top;
		float XOff = 0, YOff = 0, Wd = 0, Ht = 0;   // the anchor offset, as window_defaults[]
		int32 Radius = 0;                          // def radius + PIX3
		bool bOpen = true;
		bool bStatusJelly = false;                 // the status window's own jelly art
		TArray<FChild> Children;
		// runtime
		float Opacity = 0.3f;
		TArray<float> ChildOpacity;
	};
	struct FGlow { int32 Mode = 0; float Last = 1.f, Scale = 0.f; };
	struct FHit { FBox2f Box; int32 Kind = 0; int32 A = 0; int32 B = 0; };
	enum EHitKind : int32 { HitJelly = 1, HitChild, HitSlot, HitInspiration };

	UCoHPowerComponent* Me() const;
	UCoHPowerComponent* TargetComp() const;
	UCoHHeroProgress* Progress() const;

	FVector2f UpperLeft(const FWin& W, const FVector2f& Screen) const;
	void SetUpperLeft(FWin& W, const FVector2f& TopLeft, const FVector2f& Screen);
	void Load();
	void Save(const FWin& W) const;

	void DrawJelly(FCoHPainter& P, int32 Id, const FVector2f& Screen, float Dt) const;
	void DrawStatus(FCoHPainter& P, const FVector2f& Screen, float Dt) const;
	void DrawHealthBar(FCoHPainter& P, float X, float Y, float Z, float Width, float Pct, uint32 Frame, uint32 BarColor, bool bHealth, FGlow& G, float Dt) const;
	void DrawExperience(FCoHPainter& P, float X, float Y, float Z, float Wd, uint32 Color, uint32 Back, float Dt) const;
	void DrawTarget(FCoHPainter& P, const FVector2f& Screen) const;
	void DrawTray(FCoHPainter& P, const FVector2f& Screen, float Dt) const;
	void DrawInspirations(FCoHPainter& P, const FVector2f& Screen) const;
	const FCoHTex* Icon(FName Power) const;

	TWeakObjectPtr<APlayerController> Player;
	TFunction<void(int32, bool)> OnSlotClicked;
	TFunction<int32()> SelectedSlot;
	TFunction<const FSlateBrush*(FName)> IconFor;
	TFunction<void(const FString&)> OnCommand;

	mutable TArray<FWin> Wins;
	mutable TArray<FHit> Hits;
	mutable FVector2f LastScreen = FVector2f(1920, 1080);
	mutable FVector2f Mouse = FVector2f(-1, -1);
	mutable FGlow HealthGlow, EndGlow, XPGlow;
	mutable float Heart = 0.f;
	mutable float NotifyTimer = 0.f;
	mutable float SpinAngle = 0.f;
	mutable TArray<float> SlotScale;
	mutable TMap<const FSlateBrush*, TUniquePtr<FCoHTex>> IconTex;
	bool bMouseDown = false;
	int32 Dragging = -1;
	FVector2f DragRel;
	uint32 Color = 0x3399ffff;      // DEFAULT_HERO_WINDOW_COLOR
	uint32 BackColor = 0x00000088;
};

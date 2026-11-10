#include "CoHOriginalHud.h"

#include "CoHHeroProgress.h"
#include "CoHPowers.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"
#include "Layout/Geometry.h"
#include "Misc/App.h"
#include "Misc/ConfigCacheIni.h"
#include "Styling/SlateBrush.h"

// The original constants (uiWindows_init.h, uiUtil.h, uiStatus.c, uiTray.h, uiTarget.c)
namespace CoHOriginalUI
{
	constexpr int32 PIX2 = 2, PIX3 = 3, R4 = 4, R10 = 10, R22 = 22;
	constexpr float JELLY_HT = 18.f;
	constexpr float JELLY_FADE_SPEED = 0.05f;
	constexpr float JELLY_MIN_OPACITY = 0.3f;
	constexpr float JELLY_MOUSE_OPACITY = 0.5f;
	constexpr float CHILD_BUTTON_SPACE = 7.f;
	constexpr float CHILD_OPACITY = 0.5f;

	constexpr float HEALTH_YOFF = 19.f, HEALTH_XOFF = 77.f, BAR_HT = 10.f;
	constexpr float XP_INSET = 10.f, XP_WD = 222.f, XP_Y = 43.f;
	constexpr uint32 EMPTY_HOLE_CLR = 0x061132ff, DEBT_HOLE_CLR = 0x580000ff, XP_COLOR = 0xd36efdff;
	constexpr uint32 FULL_HEALTH_COLOR = 0x50eb34ff, MED_HEALTH_COLOR = 0xebff20ff, LOW_HEALTH_COLOR = 0xf72200ff;
	constexpr uint32 FULL_ENDURANCE_COLOR = 0x0005ffff, LOW_ENDURANCE_COLOR = 0x000588ff;
	constexpr float MAX_HEARTBEAT_HEALTH_PERCENTAGE = 0.2f;
	constexpr float GLOW_FADE_SPEED = 5.f, GLOW_MOVE_SPEED = 60.f;

	constexpr float BOX_SIDE = 40.f, TRAY_YOFF = 5.f, DEFAULT_TRAY_HT = 50.f, ARROW_OFFSET = 7.f;
	constexpr float ICON_SCALE_SPEED = 0.1f;
	constexpr int32 TRAY_SLOTS = 10;

	constexpr float TXT_HT = 20.f, CONN_SPACER = 2.f, BAR_WD = 116.f;

	constexpr uint32 CLR_WHITE = 0xffffffff, CLR_BLACK = 0x000000ff, CLR_RED = 0xff0000ff, CLR_BLUE = 0x0000ffff, CLR_GREEN = 0x00ff00ff;

	enum { GLOW_NONE, GLOW_FADE_IN, GLOW_MOVE, GLOW_FADE_OUT };

	uint32 WithAlpha(uint32 C, float A) { return (C & 0xffffff00) | (uint32)FMath::Clamp(FMath::RoundToInt(255.f * A), 0, 255); }

	uint32 ToRgba(const FLinearColor& L)
	{
		const FColor C = L.ToFColor(true);
		return (uint32(C.R) << 24) | (uint32(C.G) << 16) | (uint32(C.B) << 8) | uint32(C.A);
	}

	uint32 HealthColor(float Pct)
	{
		// getHealthColor, uiStatus.c
		if (Pct > 0.6f) return FULL_HEALTH_COLOR;
		if (Pct > 0.4f) return CoHLerpColor((Pct - 0.4f) / 0.2f, MED_HEALTH_COLOR, FULL_HEALTH_COLOR);
		if (Pct > 0.2f) return CoHLerpColor((Pct - 0.2f) / 0.2f, LOW_HEALTH_COLOR, MED_HEALTH_COLOR);
		return LOW_HEALTH_COLOR;
	}

	uint32 EnduranceColor(float Pct)
	{
		if (Pct > 0.7f) return FULL_ENDURANCE_COLOR;
		if (Pct > 0.3f) return CoHLerpColor((Pct - 0.3f) / 0.4f, LOW_ENDURANCE_COLOR, FULL_ENDURANCE_COLOR);
		return LOW_ENDURANCE_COLOR;
	}

	/** handleGlowState, uiUtilGame.c. Step is TIMESTEP (30ths of a second). */
	void HandleGlow(int32& Mode, float& Last, float Pct, float& Glow, float Speed, float Step)
	{
		const float Sign = Last < Pct ? 1.f : -1.f;
		switch (Mode)
		{
		case GLOW_NONE:
			if (Last != Pct) Mode = GLOW_FADE_IN; else Last = Pct;
			break;
		case GLOW_FADE_IN:
			Glow += Step / GLOW_FADE_SPEED;
			if (Glow > 1.f) { Glow = 1.f; Mode = GLOW_MOVE; }
			break;
		case GLOW_MOVE:
			Last += Sign * Step / Speed;
			if ((Sign < 0 && Last < Pct) || Last < 0 || (Sign > 0 && Last > Pct)) { Last = Pct; Mode = GLOW_FADE_OUT; }
			break;
		case GLOW_FADE_OUT:
		default:
			Last = Pct;
			Glow -= Step / GLOW_FADE_SPEED;
			if (Glow < 0.f) { Glow = 0.f; Mode = GLOW_NONE; }
			break;
		}
	}

	const FCoHTex* Art(const TCHAR* Name) { return FCoHUIArt::Get().Tex(Name); }
}
using namespace CoHOriginalUI;

// ---------------------------------------------------------------------------
// setup

void SCoHOriginalHud::Construct(const FArguments& InArgs)
{
	Player = InArgs._Player;
	OnSlotClicked = InArgs._OnSlotClicked;
	SelectedSlot = InArgs._SelectedSlot;
	IconFor = InArgs._IconFor;
	OnCommand = InArgs._OnCommand;
	SlotScale.Init(1.f, TRAY_SLOTS);
	ResetLayout();
	Load();
}

void SCoHOriginalHud::ResetLayout()
{
	// window_defaults[], uiWindows_init.c (the windows built so far)
	Wins.SetNum(WDW_COUNT);
	auto Def = [this](int32 Id, const TCHAR* Key, EH H, EV V, float X, float Y, float Wd, float Ht, int32 Radius, bool bOpen)
	{
		FWin& W = Wins[Id];
		W = FWin();
		W.Key = Key; W.H = H; W.V = V; W.XOff = X; W.YOff = Y; W.Wd = Wd; W.Ht = Ht;
		W.Radius = Radius + PIX3; W.bOpen = bOpen;
	};
	Def(WDW_STAT_BARS, TEXT("StatBars"), EH::Right, EV::Top, 0, 0, 330, 65, 0, true);
	Def(WDW_TARGET, TEXT("Target"), EH::Left, EV::Top, 0, 0, 236, 66, R22, true);
	Def(WDW_TRAY, TEXT("Tray"), EH::Right, EV::Bottom, 0, 0, 440, DEFAULT_TRAY_HT, R22, true);
	Def(WDW_INSPIRATION, TEXT("Inspiration"), EH::Right, EV::Bottom, 0, -200, 196, 52, R10, true);

	Wins[WDW_STAT_BARS].bStatusJelly = true;
	Wins[WDW_STAT_BARS].Children = {
		{ TEXT("Chat"), -1, TEXT("chat") }, { TEXT("Tray"), WDW_TRAY, TEXT("") }, { TEXT("Target"), WDW_TARGET, TEXT("") },
		{ TEXT("Nav"), -1, TEXT("nav") }, { TEXT("Menu"), -1, TEXT("menu") } };
	Wins[WDW_TARGET].Children = { { TEXT("Action"), -1, TEXT("targetoptions") } };
	Wins[WDW_TRAY].Children = {
		{ TEXT("Powers"), -1, TEXT("powers") }, { TEXT("Inspirations"), WDW_INSPIRATION, TEXT("") },
		{ TEXT("Enhancements"), -1, TEXT("enhancements") }, { TEXT("Salvage"), -1, TEXT("salvage") },
		{ TEXT("Recipes"), -1, TEXT("recipe") }, { TEXT("+"), -1, TEXT("showNewTray") } };
	for (FWin& W : Wins) W.ChildOpacity.Init(CHILD_OPACITY, W.Children.Num());
}

void SCoHOriginalHud::Load()
{
	if (!GConfig) return;
	for (FWin& W : Wins)
	{
		const FString S = TEXT("CoHUI.") + W.Key;
		GConfig->GetFloat(*S, TEXT("XOff"), W.XOff, GGameUserSettingsIni);
		GConfig->GetFloat(*S, TEXT("YOff"), W.YOff, GGameUserSettingsIni);
		GConfig->GetBool(*S, TEXT("Open"), W.bOpen, GGameUserSettingsIni);
		int32 H = (int32)W.H, V = (int32)W.V;
		GConfig->GetInt(*S, TEXT("HAnchor"), H, GGameUserSettingsIni);
		GConfig->GetInt(*S, TEXT("VAnchor"), V, GGameUserSettingsIni);
		W.H = (EH)FMath::Clamp(H, 0, 2);
		W.V = (EV)FMath::Clamp(V, 0, 2);
	}
}

void SCoHOriginalHud::Save(const FWin& W) const
{
	if (!GConfig) return;
	const FString S = TEXT("CoHUI.") + W.Key;
	GConfig->SetFloat(*S, TEXT("XOff"), W.XOff, GGameUserSettingsIni);
	GConfig->SetFloat(*S, TEXT("YOff"), W.YOff, GGameUserSettingsIni);
	GConfig->SetBool(*S, TEXT("Open"), W.bOpen, GGameUserSettingsIni);
	GConfig->SetInt(*S, TEXT("HAnchor"), (int32)W.H, GGameUserSettingsIni);
	GConfig->SetInt(*S, TEXT("VAnchor"), (int32)W.V, GGameUserSettingsIni);
	GConfig->Flush(false, GGameUserSettingsIni);
}

void SCoHOriginalHud::ToggleWindow(int32 Id)
{
	if (!Wins.IsValidIndex(Id)) return;
	Wins[Id].bOpen = !Wins[Id].bOpen;
	Save(Wins[Id]);
}

UCoHPowerComponent* SCoHOriginalHud::Me() const
{
	const APlayerController* PC = Player.Get();
	return PC ? UCoHPowerComponent::Of(PC->GetPawn()) : nullptr;
}

UCoHPowerComponent* SCoHOriginalHud::TargetComp() const
{
	const UCoHPowerComponent* C = Me();
	return C ? UCoHPowerComponent::Of(C->Target.Get()) : nullptr;
}

UCoHHeroProgress* SCoHOriginalHud::Progress() const
{
	const APlayerController* PC = Player.Get();
	return PC ? UCoHHeroProgress::Of(PC->GetPawn()) : nullptr;
}

const FCoHTex* SCoHOriginalHud::Icon(FName Power) const
{
	const FSlateBrush* B = (IconFor && !Power.IsNone()) ? IconFor(Power) : nullptr;
	if (!B) return FCoHUIArt::Get().Tex(TEXT("Power_Missing"));
	if (const TUniquePtr<FCoHTex>* Hit = IconTex.Find(B)) return Hit->Get();
	// not owned: the power UI keeps its brushes alive
	TUniquePtr<FCoHTex> Tex = MakeUnique<FCoHTex>();
	Tex->External = B;
	Tex->W = Tex->H = 32.f;   // the original power icons are 32 px
	return IconTex.Add(B, MoveTemp(Tex)).Get();
}

// ---------------------------------------------------------------------------
// layout: loc.xp/yp is the anchor point on the screen; the window's matching
// corner (or centre) sits on it, as window_init places them

FVector2f SCoHOriginalHud::UpperLeft(const FWin& W, const FVector2f& Screen) const
{
	float X = W.XOff, Y = W.YOff;
	if (W.H == EH::Right) X = Screen.X + W.XOff - W.Wd;
	else if (W.H == EH::Center) X = Screen.X / 2 + W.XOff - W.Wd / 2;
	if (W.V == EV::Bottom) Y = Screen.Y + W.YOff - W.Ht;
	else if (W.V == EV::Middle) Y = Screen.Y / 2 + W.YOff - W.Ht / 2;
	// keep it on screen, with room for the jelly
	X = FMath::Clamp(X, 0.f, FMath::Max(0.f, Screen.X - W.Wd));
	Y = FMath::Clamp(Y, 0.f, FMath::Max(0.f, Screen.Y - W.Ht));
	return FVector2f(X, Y);
}

void SCoHOriginalHud::SetUpperLeft(FWin& W, const FVector2f& TL, const FVector2f& Screen)
{
	const float X = FMath::Clamp(TL.X, 0.f, FMath::Max(0.f, Screen.X - W.Wd));
	const float Y = FMath::Clamp(TL.Y, 0.f, FMath::Max(0.f, Screen.Y - W.Ht));
	// re-anchor to the nearest side, as the original does when a window is moved
	W.H = X + W.Wd / 2 < Screen.X / 3 ? EH::Left : (X + W.Wd / 2 > Screen.X * 2 / 3 ? EH::Right : EH::Center);
	W.V = Y + W.Ht / 2 < Screen.Y / 2 ? EV::Top : EV::Bottom;
	W.XOff = W.H == EH::Left ? X : (W.H == EH::Right ? X + W.Wd - Screen.X : X + W.Wd / 2 - Screen.X / 2);
	W.YOff = W.V == EV::Top ? Y : Y + W.Ht - Screen.Y;
}

// ---------------------------------------------------------------------------
// paint

int32 SCoHOriginalHud::OnPaint(const FPaintArgs& Args, const FGeometry& Geometry, const FSlateRect& Culling,
	FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle& Style, bool bParentEnabled) const
{
	if (!Me()) return Layer;
	const FVector2f Screen = FVector2f(Geometry.GetLocalSize());
	LastScreen = Screen;
	const float Dt = FMath::Min(FApp::GetDeltaTime(), 0.1);
	Hits.Reset();

	FCoHPainter P;
	if (Wins[WDW_STAT_BARS].bOpen) DrawStatus(P, Screen, Dt);
	if (Wins[WDW_TARGET].bOpen) DrawTarget(P, Screen);
	if (Wins[WDW_TRAY].bOpen) DrawTray(P, Screen, Dt);
	if (Wins[WDW_INSPIRATION].bOpen) DrawInspirations(P, Screen);
	for (int32 i = 0; i < WDW_COUNT; ++i)
		if (Wins[i].bOpen) DrawJelly(P, i, Screen, Dt);
	return P.Flush(Geometry, Out, Layer);
}

void SCoHOriginalHud::DrawJelly(FCoHPainter& P, int32 Id, const FVector2f& Screen, float Dt) const
{
	// window_drawJelly + window_childButton, uiWindows.c (the plain case: no docked child)
	FWin& W = Wins[Id];
	const float Step = Dt * 30.f;
	const FVector2f TL = UpperLeft(W, Screen);
	const float X = TL.X, Y = TL.Y, Wd = W.Wd, Ht = W.Ht, Z = 50.f;
	const bool bBelow = !W.bStatusJelly && Y < Screen.Y / 8 && Y + Ht < Screen.Y - JELLY_HT;

	FBox2f Box;
	if (W.bStatusJelly)
	{
		const FCoHTex* J = Art(TEXT("Jelly_healthbar_HP_END_Only"));
		Box = FBox2f(FVector2f(X, Y), FVector2f(X + J->W, Y + J->H));
		P.Sprite(J, X, Y + 1, Z - 1, 1, 1, WithAlpha(Color, W.Opacity));
	}
	else
	{
		const bool bLarge = W.Radius > R10 + PIX3;
		const FCoHTex* L = Art(bLarge ? TEXT("Jelly_lg_end_L") : TEXT("Jelly_sm_end_L"));
		const FCoHTex* R = Art(bLarge ? TEXT("Jelly_lg_end_R") : TEXT("Jelly_sm_end_R"));
		const FCoHTex* Meat = Art(TEXT("Jelly_meat"));
		const float Ty = bBelow ? Y + Ht + JELLY_HT / 2 : Y - JELLY_HT / 2;
		const uint32 C = WithAlpha(Color, W.Opacity);
		P.Sprite(L, X, Ty - L->H / 2, Z - 1, 1, 1, C);
		P.Sprite(R, X + Wd - R->W, Ty - R->H / 2, Z - 1, 1, 1, C);
		P.Sprite(Meat, X + L->W, Ty - Meat->H / 2, Z - 1, (Wd - (L->W + R->W)) / Meat->W, 1, C);
		Box = bBelow ? FBox2f(FVector2f(X, Y + Ht), FVector2f(X + Wd, Y + Ht + JELLY_HT))
		             : FBox2f(FVector2f(X, Y - JELLY_HT), FVector2f(X + Wd, Y));
	}

	// opacity: brighter under the mouse and while dragged
	const bool bOver = Box.IsInsideOrOn(Mouse);
	const float Goal = Dragging == Id ? 1.f : (bOver ? JELLY_MOUSE_OPACITY : JELLY_MIN_OPACITY);
	W.Opacity = W.Opacity < Goal ? FMath::Min(Goal, W.Opacity + Step * JELLY_FADE_SPEED) : FMath::Max(Goal, W.Opacity - Step * JELLY_FADE_SPEED);

	// child buttons (childButton_getCenter)
	float Tx = X + (FMath::Min(13, W.Radius) + CHILD_BUTTON_SPACE);
	float Cy = bBelow ? Y + Ht + JELLY_HT / 2 : Y - JELLY_HT / 2;
	if (W.bStatusJelly) { Cy = Y + 12; Tx += 10 + 30; }
	for (int32 i = 0; i < W.Children.Num(); ++i)
	{
		const FChild& Ch = W.Children[i];
		const float Tw = FCoHPainter::TextWidth(ECoHFont::Game, 12, 1, Ch.Name);
		const float Cx = Tx + Tw / 2;
		const FBox2f CB(FVector2f(Cx - (Tw + CHILD_BUTTON_SPACE) / 2, Cy - JELLY_HT / 2), FVector2f(Cx + (Tw + CHILD_BUTTON_SPACE) / 2, Cy + JELLY_HT / 2));
		float& Op = W.ChildOpacity[i];
		if (CB.IsInsideOrOn(Mouse)) Op = FMath::Min(1.f, Op + Step * JELLY_FADE_SPEED * 2);
		else Op = FMath::Max(CHILD_OPACITY, Op - Step * JELLY_FADE_SPEED);
		uint32 Clr = WithAlpha(CLR_WHITE, Op);
		if (Ch.Command.IsEmpty() && Wins.IsValidIndex(Ch.Wdw) && Wins[Ch.Wdw].bOpen) Clr = CLR_GREEN;
		P.Text(ECoHFont::Game, 12, Cx, Cy, Z + 1, 1, Clr, Ch.Name, CoHText::CenterX | CoHText::CenterY);
		Hits.Add({ CB, HitChild, Id, i });
		Tx += Tw + CHILD_BUTTON_SPACE;
	}
	Hits.Add({ Box, HitJelly, Id, 0 });
}

void SCoHOriginalHud::DrawHealthBar(FCoHPainter& P, float X, float Y, float Z, float Width, float Pct, uint32 Frame, uint32 BarColor, bool bHealth, FGlow& G, float Dt) const
{
	// drawHealthBar, uiStatus.c
	const float Step = Dt * 30.f;
	Pct = FMath::Clamp(Pct, 0.f, 1.f);
	HandleGlow(G.Mode, G.Last, Pct, G.Scale, GLOW_MOVE_SPEED, Step);
	Pct = G.Last;

	if (bHealth && Pct > 0.f && Pct <= MAX_HEARTBEAT_HEALTH_PERCENTAGE)
	{
		// drawHeartBeatGlow: a pulse that quickens as health falls
		const float Speed = 1.f + 0.5f * (MAX_HEARTBEAT_HEALTH_PERCENTAGE - Pct);
		Heart = FMath::Fmod(Heart + Step * Speed, 8 * PI);
		const float Sc = (1.f - FMath::Cos(Heart)) * 0.5f * (Heart < 4 * PI ? 1.f : 0.f) * 0.6f;
		const FCoHTex* L = Art(TEXT("healthbar_heartglow_L"));
		const FCoHTex* M = Art(TEXT("healthbar_heartglow_MID"));
		const FCoHTex* R = Art(TEXT("healthbar_heartglow_R"));
		const float Wd = Pct * (Width - 8), Gy = Y + 4;
		P.Sprite(L, X + (5 - Sc * L->W), Gy + (1 - Sc * L->H / 2), Z, Sc, Sc, BarColor);
		P.Sprite(M, X + 5, Gy + (1 - Sc * M->H / 2), Z, (Wd - 5) / M->W, Sc, BarColor);
		P.Sprite(R, X + Wd, Gy + (1 - Sc * R->H / 2), Z, Sc, Sc, BarColor);
	}

	P.Bar(X, Y, Z, Width, 1, Pct, G.Scale, BarColor);

	// drawHealthBarFrame
	const FCoHTex* Left = Art(TEXT("healthbar_framemain_L"));
	const FCoHTex* Right = Art(TEXT("healthbar_framemain_R"));
	const FCoHTex* Pipe = Art(TEXT("healthbar_framemain_horiz"));
	const float FZ = Z - 2;
	P.Sprite(Left, X, Y, FZ, 1, 1, Frame);
	P.Sprite(Right, X + (Width - Right->W), Y, FZ, 1, 1, Frame);
	P.Sprite(Pipe, X + Left->W, Y + 2, FZ, (Width - (Left->W + Right->W)) / Pipe->W, 1, Frame);
	P.Sprite(Pipe, X + Left->W, Y - 2 + (Left->H - Pipe->H), FZ, (Width - (Left->W + Right->W)) / Pipe->W, 1, Frame);
	P.Box(X + 2 + Pipe->W, Y + Pipe->H + 2, FZ - 10, Width - 4 * Pipe->W, Left->H - 4 * Pipe->H, 0x00000088);

	P.Sprite(Art(bHealth ? TEXT("healthbar_label_hp") : TEXT("healthbar_label_end")), X + 5, Y + 4, Z + 2, 1, 1, 0xffffff88);
}

void SCoHOriginalHud::DrawExperience(FCoHPainter& P, float X, float Y, float Z, float Wd, uint32 Frame, uint32 Back, float Dt) const
{
	// drawExperienceFrame + drawExperience (the steady state), uiStatus.c
	const UCoHHeroProgress* H = Progress();
	const FCoHTex* Left = Art(TEXT("healthbar_framemain_L"));
	const FCoHTex* Pipe = Art(TEXT("healthbar_framemain_horiz"));
	const FCoHTex* Ring = Art(TEXT("healthbar_exp_ring"));
	const FCoHTex* Black = Art(TEXT("healthbar_exp_black"));
	const float FZ = Z + 10;

	P.Sprite(Left, X + XP_INSET, Y + XP_Y, FZ, 1, 1, Frame);
	P.Sprite(Art(TEXT("healthbar_label_xp")), X + XP_INSET + 4, Y + XP_Y + 3, FZ + 6, 1, 1, 0xffffff88);
	P.Sprite(Pipe, X + XP_INSET + Left->W, Y + XP_Y + 2, FZ, (XP_WD - Left->W) / Pipe->W, 1, Frame);
	P.Sprite(Pipe, X + XP_INSET + Left->W, Y + XP_Y - 2 + (Left->H - Pipe->H), FZ, (XP_WD - Left->W) / Pipe->W, 1, Frame);
	P.Box(X + XP_INSET + 4, Y + XP_Y + 4, FZ - 15, XP_WD - 5, Left->H - 8, Back);
	// the bridge between the bar and the ring
	P.Sprite(Pipe, X + XP_INSET + XP_WD, Y + XP_Y + 2, FZ, 8 / Pipe->W, 1, Frame);
	P.Sprite(Pipe, X + XP_INSET + XP_WD, Y + XP_Y - 2 + (Left->H - Pipe->H), FZ, 20 / Pipe->W, 1, Frame);
	P.Sprite(Ring, X + Wd - Ring->W, Y, FZ + 10, 1, 1, Frame);
	P.Sprite(Black, X + Wd - Ring->W, Y, FZ - 1, 1, 1, Back);

	int32 Into = 0, Span = 1, Debt = 0;
	if (H && H->bHasRecord) { H->XPBar(Into, Span); Debt = H->Hero.Debt; }
	Span = FMath::Max(Span, 1);
	const float PerTick = Span / 10.f;
	const int32 Ticks = FMath::Clamp(FMath::FloorToInt((float)Into / Span * 10.f), 0, 10);
	const float IntoTick = Into - Ticks * PerTick;
	int32 DebtTicks = FMath::FloorToInt((Debt + IntoTick) / PerTick);
	float Pct = FMath::Clamp(IntoTick / PerTick, 0.f, 1.f);

	HandleGlow(XPGlow.Mode, XPGlow.Last, Pct, XPGlow.Scale, GLOW_MOVE_SPEED, Dt * 30.f);
	Pct = XPGlow.Last;
	P.Bar(X + XP_INSET, Y + XP_Y, Z, XP_WD, 1, Pct, XPGlow.Scale, XP_COLOR);
	if (Debt > 0)
		P.Bar(X + XP_INSET + Pct * (XP_WD - 8), Y + XP_Y, Z + 10, FMath::Min(1.f - Pct, Debt / PerTick) * (XP_WD - 8 + 18), 1, 1.f, 0.f, DEBT_HOLE_CLR);

	for (int32 i = 0; i < 10; ++i)
	{
		uint32 Clr = CLR_WHITE;
		FString Name;
		if (i < Ticks) Name = FString::Printf(TEXT("healthbar_exp_dot_%02d"), i + 1);
		else
		{
			Name = FString::Printf(TEXT("healthbar_exp_dot_empty_%02d"), i + 1);
			if (DebtTicks > 0) { Clr = DEBT_HOLE_CLR; --DebtTicks; }
			else Clr = EMPTY_HOLE_CLR;
		}
		P.Sprite(FCoHUIArt::Get().Tex(Name), X + Wd - 64.3f, Y + 0.5f, Z + 13, 1, 1, Clr);
	}
}

void SCoHOriginalHud::DrawStatus(FCoHPainter& P, const FVector2f& Screen, float Dt) const
{
	// statusWindow, uiStatus.c (no inherent meter: Blaster-style)
	const UCoHPowerComponent* C = Me();
	const UCoHHeroProgress* H = Progress();
	const FWin& W = Wins[WDW_STAT_BARS];
	const FVector2f TL = UpperLeft(W, Screen);
	const float X = TL.X, Y = TL.Y, Z = 10.f, Wd = W.Wd;

	P.Sprite(Art(TEXT("Align_Status_Hero")), X + 2, Y + 9, Z + 25, 1, 1, CLR_WHITE);

	const float Hp = C->MaxHealth > 0 ? C->Health / C->MaxHealth : 0.f;
	const float End = C->MaxEndurance > 0 ? C->Endurance / C->MaxEndurance : 0.f;
	DrawHealthBar(P, X + 34, Y + HEALTH_YOFF, Z + 25, Wd - HEALTH_XOFF, Hp, Color, HealthColor(Hp), true, HealthGlow, Dt);
	DrawHealthBar(P, X + 34, Y + HEALTH_YOFF + BAR_HT, Z + 25, Wd - HEALTH_XOFF, End, Color, EnduranceColor(End), false, EndGlow, Dt);
	DrawExperience(P, X + 35, Y, Z, Wd - 35, Color, BackColor, Dt);

	// status_notify: the level in the ring, and the blinking notice
	const float Nx = X + Wd - 32, Ny = Y + 32;
	P.Text(ECoHFont::Title, 12, Nx - 1, Ny + 1, Z + 15, 1, CLR_WHITE, FString::FromInt(C->Level), CoHText::CenterX | CoHText::CenterY);
	const FCoHTex* Notice = nullptr;
	if (C->IsDefeated()) Notice = Art(TEXT("healthbar_notify_hospital"));
	else if (H && (H->CanTrain() || H->PicksOpen() > 0)) Notice = Art(TEXT("healthbar_notify_levelup"));
	if (Notice)
	{
		NotifyTimer = FMath::Fmod(NotifyTimer + Dt * 30.f * 0.1f, 6 * PI);
		const uint32 A = (uint32)(192.f * (FMath::Sin(NotifyTimer) + 1) / 2 + 63);
		P.Sprite(Notice, Nx - Notice->W / 2, Ny - Notice->H / 2, Z + 15, 1, 1, 0xffffff00 | A);
	}
}

void SCoHOriginalHud::DrawTarget(FCoHPainter& P, const FVector2f& Screen) const
{
	// targetWindow, uiTarget.c
	const FWin& W = Wins[WDW_TARGET];
	const FVector2f TL = UpperLeft(W, Screen);
	const float X = TL.X, Y = TL.Y, Z = 10.f, Wd = W.Wd, Ht = W.Ht;
	P.Frame(PIX3, R22, X, Y, Z - 2, Wd, Ht, 1, Color, BackColor);

	const UCoHPowerComponent* Me_ = Me();
	const UCoHPowerComponent* Tg = TargetComp();
	if (!Tg) return;

	P.Clip(X + PIX3, Y + PIX3, Wd - PIX3 * 2, Ht - PIX3 * 2);
	const uint32 Con = ToRgba(UCoHPowerComponent::ConColour(Me_->Level, Tg->Level));
	// brightenColor(&txt, 30)
	uint32 Txt = Con;
	for (int32 Shift = 8; Shift < 32; Shift += 8)
		Txt = (Txt & ~(0xffu << Shift)) | (uint32(FMath::Min(255u, ((Txt >> Shift) & 0xff) + 30u)) << Shift);

	float Ty = Y + TXT_HT;
	P.Text(ECoHFont::Game, 12, X + Wd / 2, Ty - 4, Z, 1, Txt, Tg->DisplayName, CoHText::CenterX);

	// drawConningArrows: one arrow per level above (or below, turned over)
	Ty += CONN_SPACER;
	const FCoHTex* Arrow = Art(TEXT("Conning_arrow"));
	int32 Diff = Tg->Level - Me_->Level;
	const float Angle = Diff < 0 ? PI : 0.f;
	Diff = FMath::Abs(Diff);
	const float Ax = X + Wd / 2, Ay = Ty - 4;
	if (Diff == 1) P.Rotated(Arrow, Ax - Arrow->W / 2, Ay, Z, 1, 1, Con, Angle);
	else if (Diff == 2) { P.Rotated(Arrow, Ax, Ay, Z, 1, 1, Con, Angle); P.Rotated(Arrow, Ax - Arrow->W, Ay, Z, 1, 1, Con, Angle); }
	else if (Diff >= 3)
	{
		P.Rotated(Arrow, Ax - Arrow->W / 2, Ay, Z, 1, 1, Con, Angle);
		P.Rotated(Arrow, Ax + Arrow->W / 2, Ay, Z, 1, 1, Con, Angle);
		P.Rotated(Arrow, Ax - Arrow->W / 2 - Arrow->W, Ay, Z, 1, 1, Con, Angle);
	}
	Ty += CONN_SPACER + Arrow->H + 4;

	// level on the left, as for critters
	P.Text(ECoHFont::Game, 9, X + PIX3 + (Wd - BAR_WD) / 4, Ty + 12, Z, 1, CLR_WHITE, FString::Printf(TEXT("Level %d"), Tg->Level), CoHText::CenterX);

	const float Bx = X + (Wd - BAR_WD) / 2;
	const bool bDead = Tg->IsDefeated();
	P.Capsule(Bx, Ty, Z + 1, BAR_WD, 1, Color, CLR_BLACK, CLR_RED, bDead || Tg->MaxHealth <= 0 ? 0.f : Tg->Health / Tg->MaxHealth);
	Ty += 10;
	P.Capsule(Bx, Ty, Z + 1, BAR_WD, 1, Color, CLR_BLACK, CLR_BLUE, bDead || Tg->MaxEndurance <= 0 ? 0.f : Tg->Endurance / Tg->MaxEndurance);
	P.NoClip();
}

void SCoHOriginalHud::DrawTray(FCoHPainter& P, const FVector2f& Screen, float Dt) const
{
	// trayWindow + trayslot_Display + trayslot_drawIcon + tray_drawArrows, uiTray.c (one tray)
	const UCoHPowerComponent* C = Me();
	const FWin& W = Wins[WDW_TRAY];
	const FVector2f TL = UpperLeft(W, Screen);
	const float X = TL.X, TrayY = TL.Y, Z = 10.f, Wd = W.Wd;
	const float Step = Dt * 30.f;
	P.Frame(PIX3, R22, X, TrayY, Z, Wd, DEFAULT_TRAY_HT, 1, Color, BackColor);

	const FCoHTex* PowerRing = Art(TEXT("tray_ring_power"));
	const FCoHTex* Hole = Art(TEXT("EnhncTray_RingHole"));
	const FCoHTex* Spin = Art(TEXT("tray_ring_endurancemeter"));
	const FCoHTex* AutoExec = Art(TEXT("tray_ring_iconovr_autoexecute"));
	const FCoHTex* Highlight = Art(TEXT("tray_ring_iconovr_highlight"));
	const int32 Selected = SelectedSlot ? SelectedSlot() : -1;
	SpinAngle = FMath::Fmod(SpinAngle + Dt * 2.f * PI / 3.f, 2 * PI);

	for (int32 i = 0; i < TRAY_SLOTS; ++i)
	{
		const float Xp = X + 35 + i * BOX_SIDE + BOX_SIDE / 2;
		const float Yp = TrayY + BOX_SIDE / 2 + TRAY_YOFF;
		const FBox2f Box(FVector2f(Xp - BOX_SIDE / 2, Yp - BOX_SIDE / 2), FVector2f(Xp + BOX_SIDE / 2, Yp + BOX_SIDE / 2));
		const bool bOver = Box.IsInsideOrOn(Mouse);
		Hits.Add({ Box, HitSlot, i, 0 });

		const int32 Num = (i + 1) % 10;
		const FCoHTex* NumT = FCoHUIArt::Get().Tex(FString::Printf(TEXT("tray_ring_number_%d"), Num));
		P.Sprite(NumT, Xp - BOX_SIDE / 2, Yp + (BOX_SIDE / 2 - NumT->H), Z + 3, 1, 1, CLR_WHITE);

		const FName Power = C->Tray.IsValidIndex(i) ? C->Tray[i] : NAME_None;
		if (Power.IsNone())
		{
			const float Sc = bOver && bMouseDown ? 0.9f : 1.f;
			P.Sprite(PowerRing, Xp - Sc * PowerRing->W / 2, Yp - Sc * PowerRing->H / 2, Z + 2, Sc, Sc, Color);
			const float HoleSc = 0.5f * Sc;
			P.Sprite(Hole, Xp - HoleSc * Hole->W / 2, Yp - HoleSc * Hole->H / 2, Z + 1, HoleSc, HoleSc, 0xffffff66);
		}
		else
		{
			// the icon shrinks while the power recharges and grows back (trayslot_Timer)
			const float Left = C->RechargeLeft(Power);
			const float Total = FMath::Max(C->RechargeTotal(Power), 0.01f);
			float Sc = Left > 0.f ? 1.f - FMath::Clamp(Left / Total, 0.f, 1.f) : 1.f;
			const bool bCooling = Sc < 1.f;
			Sc = Sc / 2 + 0.5f;
			float& S = SlotScale[i];
			S = S > Sc ? FMath::Max(Sc, S - Step * ICON_SCALE_SPEED) : FMath::Min(Sc, S + Step * ICON_SCALE_SPEED);
			const uint32 Clr = bCooling ? 0xffffff66 : CLR_WHITE;
			float Hover = 1.f;
			if (bOver) { Hover *= 0.9f; if (bMouseDown) Hover *= 0.9f; }

			const FCoHTex* Ic = Icon(Power);
			const float IcSc = S * Hover * (32.f / Ic->W);
			P.Sprite(Ic, Xp - Ic->W * IcSc / 2, Yp - Ic->W * IcSc / 2, Z + 2, IcSc, IcSc, Clr);

			if (C->IsToggleOn(Power))
				P.Rotated(Spin, Xp - Spin->W / 2, Yp - Spin->W / 2, Z + 5, 1, 1, Clr, SpinAngle);
			if (!C->AutoPower.IsNone() && C->AutoPower == Power)
				P.Sprite(AutoExec, Xp - AutoExec->W * S / 2, Yp - AutoExec->W * S / 2, Z, S, S, Clr);
		}
		if (Selected == i)
			P.Sprite(Highlight, Xp - Highlight->W / 2, Yp - Highlight->W / 2, Z + 4, 1, 1, 0xffd040ff);
	}

	// tray number with the switch arrows (one tray for now)
	const FCoHTex* LArrow = Art(TEXT("teamup_arrow_contract"));
	const FCoHTex* RArrow = Art(TEXT("teamup_arrow_expand"));
	const float Ay = TrayY + TRAY_YOFF + PowerRing->W / 2;
	P.Sprite(LArrow, X + (ARROW_OFFSET - 3), Ay - LArrow->H / 2, Z, 1, 1, WithAlpha(Color, 0x88 / 255.f));
	P.Text(ECoHFont::Title, 18, X + LArrow->W + (ARROW_OFFSET * 2 - 3), Ay + 8, Z, 1, 0xffffff88, TEXT("1"), CoHText::CenterX);
	P.Sprite(RArrow, X + (ARROW_OFFSET * 4 - 2), Ay - RArrow->H / 2, Z, 1, 1, WithAlpha(Color, 0x88 / 255.f));
}

void SCoHOriginalHud::DrawInspirations(FCoHPainter& P, const FVector2f& Screen) const
{
	// inspirationWindow, uiInspiration.c: a 4-wide grid of rings
	const UCoHHeroProgress* H = Progress();
	FWin& W = Wins[WDW_INSPIRATION];
	const int32 Count = H && H->bHasRecord ? H->Hero.Inspirations.Num() : 0;
	const int32 Rows = FMath::Clamp((Count + 3) / 4, 1, 3);
	W.Ht = 4 + Rows * 48;
	const FVector2f TL = UpperLeft(W, Screen);
	const float X = TL.X, Y = TL.Y, Z = 10.f;
	P.Frame(PIX3, R10, X, Y, Z, W.Wd, W.Ht, 1, Color, BackColor);

	const FCoHTex* Ring = Art(TEXT("tray_ring_inspiration"));
	for (int32 r = 0; r < Rows; ++r)
		for (int32 c = 0; c < 4; ++c)
		{
			const int32 Index = r * 4 + c;
			const float Xp = X + 26 + c * 48, Yp = Y + 26 + r * 48;
			if (Index < Count)
			{
				const FCoHTex* Ic = Icon(H->Hero.Inspirations[Index]);
				const FBox2f Box(FVector2f(Xp - 20, Yp - 20), FVector2f(Xp + 20, Yp + 20));
				const float Sc = (Box.IsInsideOrOn(Mouse) ? 0.9f : 1.f) * (32.f / Ic->W);
				P.Sprite(Ic, Xp - Ic->W * Sc / 2, Yp - Ic->H * Sc / 2, Z + 2, Sc, Sc, CLR_WHITE);
				Hits.Add({ Box, HitInspiration, Index, 0 });
			}
			else
				P.Sprite(Ring, Xp - Ring->W / 2, Yp - Ring->H / 2, Z + 2, 1, 1, Color);
		}
}

// ---------------------------------------------------------------------------
// input: anything not over a window is left to the game

FReply SCoHOriginalHud::OnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event)
{
	Mouse = FVector2f(Geometry.AbsoluteToLocal(Event.GetScreenSpacePosition()));
	if (Event.GetEffectingButton() != EKeys::LeftMouseButton) return FReply::Unhandled();
	// last drawn is on top: check from the end
	for (int32 i = Hits.Num() - 1; i >= 0; --i)
	{
		const FHit& Hit = Hits[i];
		if (!Hit.Box.IsInsideOrOn(Mouse)) continue;
		bMouseDown = true;
		switch (Hit.Kind)
		{
		case HitJelly:
			Dragging = Hit.A;
			DragRel = Mouse - UpperLeft(Wins[Hit.A], LastScreen);
			return FReply::Handled().CaptureMouse(SharedThis(this));
		case HitChild:
		{
			const FChild& Ch = Wins[Hit.A].Children[Hit.B];
			if (Ch.Command.IsEmpty()) ToggleWindow(Ch.Wdw);
			else if (OnCommand) OnCommand(Ch.Command);
			return FReply::Handled();
		}
		case HitSlot:
			if (OnSlotClicked) OnSlotClicked(Hit.A, Event.IsControlDown());
			return FReply::Handled();
		case HitInspiration:
			if (UCoHHeroProgress* H = Progress()) H->UseInspiration(Hit.A);
			return FReply::Handled();
		default:
			break;
		}
	}
	// a click inside a window frame is the window's, not the world's
	for (int32 i = 0; i < WDW_COUNT; ++i)
	{
		const FWin& W = Wins[i];
		if (!W.bOpen || W.bStatusJelly) continue;
		const FVector2f TL = UpperLeft(W, LastScreen);
		if (FBox2f(TL, TL + FVector2f(W.Wd, W.Ht)).IsInsideOrOn(Mouse)) return FReply::Handled();
	}
	return FReply::Unhandled();
}

FReply SCoHOriginalHud::OnMouseButtonUp(const FGeometry& Geometry, const FPointerEvent& Event)
{
	bMouseDown = false;
	if (Dragging >= 0)
	{
		Save(Wins[Dragging]);
		Dragging = -1;
		return FReply::Handled().ReleaseMouseCapture();
	}
	return FReply::Unhandled();
}

FReply SCoHOriginalHud::OnMouseMove(const FGeometry& Geometry, const FPointerEvent& Event)
{
	Mouse = FVector2f(Geometry.AbsoluteToLocal(Event.GetScreenSpacePosition()));
	if (Dragging >= 0)
	{
		SetUpperLeft(Wins[Dragging], Mouse - DragRel, LastScreen);
		return FReply::Handled();
	}
	return FReply::Unhandled();
}

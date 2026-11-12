// The HQ look shared by the lobby (SCoHLobby) and the Hero Corps terminal
// (SCoHTerminal): colours, fonts, buttons, glass panels, painted widgets.
#pragma once

#include "Brushes/SlateDynamicImageBrush.h"
#include "Brushes/SlateNoResource.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "CoHFrontend.h"
#include "CoHUIArt.h"
#include "Engine/Texture2D.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Misc/Paths.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"
#include "Styling/SlateTypes.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SUniformGridPanel.h"
#include "Widgets/Layout/SWidgetSwitcher.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SLeafWidget.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

// =================================================================== style
// One look for the whole HQ: deep navy glass, CoH blue holo lines (0x3399ff,
// the original UI's frame tint), gold for the actions that start play.
namespace HQ
{
	inline FLinearColor C(uint32 Hex, float A = 1.f)
	{
		FLinearColor L(FColor((Hex >> 16) & 255, (Hex >> 8) & 255, Hex & 255));
		L.A = A;
		return L;
	}
	inline FLinearColor Blue(float A = 1.f)  { return C(0x3399ff, A); }
	inline FLinearColor Sky(float A = 1.f)   { return C(0x7cc4ff, A); }
	inline FLinearColor Gold(float A = 1.f)  { return C(0xffb21e, A); }
	inline FLinearColor Green(float A = 1.f) { return C(0x3ddc84, A); }
	inline FLinearColor Red(float A = 1.f)   { return C(0xff6b6b, A); }
	inline FLinearColor Ink()   { return C(0xe6f0ff); }
	inline FLinearColor Muted() { return C(0x9fb6d6); }
	inline FLinearColor Dim()   { return C(0x7f95b5); }
	inline FLinearColor Grey()  { return C(0x7f8ea6); }
	inline FLinearColor Night(float A = 1.f) { return C(0x040913, A); }
	inline FLinearColor Clear() { return FLinearColor::Transparent; }

	// Red Circle (the original title font), Mont for the rest; Roboto when the UI art isn't copied in
	inline FSlateFontInfo Title(float Px) { return FCoHUIArt::Get().Font(ECoHFont::Title, Px, false); }
	inline FSlateFontInfo Bold(float Px)  { return FCoHUIArt::Get().Font(ECoHFont::GameBold, Px, false); }
	inline FSlateFontInfo Body(float Px)  { return FCoHUIArt::Get().Font(ECoHFont::Game, Px, false); }
	inline FSlateFontInfo Label(float Px = 12.f)
	{
		FSlateFontInfo F = Bold(Px);
		F.LetterSpacing = 260;
		return F;
	}

	inline const FSlateBrush* White() { return FCoreStyle::Get().GetBrush("WhiteBrush"); }

	inline const FSlateBrush* Box(const FLinearColor& Fill, const FLinearColor& Line = FLinearColor::Transparent, float Radius = 4.f, float Width = 1.f)
	{
		static TMap<FString, TUniquePtr<FSlateRoundedBoxBrush>> Cache;
		const FString Key = FString::Printf(TEXT("%s|%s|%.1f|%.1f"), *Fill.ToString(), *Line.ToString(), Radius, Width);
		if (const TUniquePtr<FSlateRoundedBoxBrush>* Hit = Cache.Find(Key)) return Hit->Get();
		return Cache.Add(Key, MakeUnique<FSlateRoundedBoxBrush>(Fill, Radius, Line, Width)).Get();
	}

	enum class EBtn : uint8 { Primary, Secondary, Danger, Count };

	inline const FButtonStyle& BtnStyle(EBtn Kind)
	{
		static FButtonStyle Styles[(int32)EBtn::Count];
		static bool bMade = false;
		if (!bMade)
		{
			bMade = true;
			const FMargin Pad(18, 10), Down(18, 11, 18, 9);
			const FSlateBrush* Off = Box(C(0x0a1426, .55f), Sky(.15f));
			Styles[(int32)EBtn::Primary] = FButtonStyle()
				.SetNormal(*Box(Gold())).SetHovered(*Box(C(0xffcf5a))).SetPressed(*Box(C(0xe08a00))).SetDisabled(*Off)
				.SetNormalPadding(Pad).SetPressedPadding(Down);
			Styles[(int32)EBtn::Secondary] = FButtonStyle()
				.SetNormal(*Box(Blue(.12f), Sky(.5f))).SetHovered(*Box(Blue(.28f), Sky())).SetPressed(*Box(Blue(.4f), Sky())).SetDisabled(*Off)
				.SetNormalPadding(Pad).SetPressedPadding(Down);
			Styles[(int32)EBtn::Danger] = FButtonStyle()
				.SetNormal(*Box(C(0x280810, .6f), C(0xff7878, .45f))).SetHovered(*Box(C(0x501018, .8f), C(0xff7878, .85f)))
				.SetPressed(*Box(C(0x601420, .9f), C(0xff7878))).SetDisabled(*Off)
				.SetNormalPadding(Pad).SetPressedPadding(Down);
		}
		return Styles[(int32)Kind];
	}

	inline const FButtonStyle& Bare()
	{
		static FButtonStyle S = FButtonStyle()
			.SetNormal(FSlateNoResource()).SetHovered(FSlateNoResource()).SetPressed(FSlateNoResource()).SetDisabled(FSlateNoResource())
			.SetNormalPadding(FMargin(0)).SetPressedPadding(FMargin(0));
		return S;
	}

	inline const FEditableTextBoxStyle& InputStyle()
	{
		static FEditableTextBoxStyle S = FEditableTextBoxStyle(FCoreStyle::Get().GetWidgetStyle<FEditableTextBoxStyle>("NormalEditableTextBox"))
			.SetBackgroundImageNormal(*Box(C(0x040c1a, .85f), Sky(.4f)))
			.SetBackgroundImageHovered(*Box(C(0x040c1a, .9f), Sky(.7f)))
			.SetBackgroundImageFocused(*Box(C(0x040c1a, .95f), Sky(), 4.f, 1.5f))
			.SetBackgroundImageReadOnly(*Box(C(0x040c1a, .5f), Sky(.2f)))
			.SetPadding(FMargin(14, 11))
			.SetForegroundColor(FSlateColor(Ink()));
		return S;
	}

	inline TSharedRef<STextBlock> Text(const FString& S, const FSlateFontInfo& Font, const FLinearColor& Color)
	{
		return SNew(STextBlock).Text(FText::FromString(S)).Font(Font).ColorAndOpacity(FSlateColor(Color));
	}

	inline TSharedRef<SWidget> ButtonT(TAttribute<FText> Caption, EBtn Kind, FOnClicked OnClick, TAttribute<bool> Enabled = true, float FontPx = 15.f, float MinHeight = 44.f)
	{
		const FLinearColor TextColor = Kind == EBtn::Primary ? C(0x1b0d00) : Kind == EBtn::Danger ? C(0xffc9c9) : C(0xcfe6ff);
		return SNew(SBox).MinDesiredHeight(MinHeight)
			[
				SNew(SButton)
				.ButtonStyle(&BtnStyle(Kind))
				.IsEnabled(Enabled)
				.OnClicked(OnClick)
				.HAlign(HAlign_Center).VAlign(VAlign_Center)
				[
					SNew(STextBlock).Text(Caption).Font(Label(FontPx))
					.ColorAndOpacity_Lambda([TextColor, Enabled] { return FSlateColor(Enabled.Get() ? TextColor : Dim()); })
				]
			];
	}

	inline TSharedRef<SWidget> Button(const FString& Caption, EBtn Kind, FOnClicked OnClick, TAttribute<bool> Enabled = true, float FontPx = 15.f, float MinHeight = 44.f)
	{
		return ButtonT(TAttribute<FText>(FText::FromString(Caption)), Kind, OnClick, Enabled, FontPx, MinHeight);
	}

	/** A button whose frame shows selection: tabs, choice chips, cards. */
	inline TSharedRef<SWidget> Selectable(TSharedRef<SWidget> Content, TAttribute<bool> Selected, FOnClicked OnClick,
		const FSlateBrush* On, const FSlateBrush* Off, const FSlateBrush* Hover, FMargin Pad, TAttribute<bool> Enabled = true)
	{
		TSharedRef<TWeakPtr<SButton>> Self = MakeShared<TWeakPtr<SButton>>();
		TSharedRef<SButton> B = SNew(SButton)
			.ButtonStyle(&Bare())
			.ContentPadding(0)
			.IsEnabled(Enabled)
			.OnClicked(OnClick)
			[
				SNew(SBorder)
				.Padding(Pad)
				.BorderImage_Lambda([Self, Selected, On, Off, Hover]
				{
					if (Selected.Get()) return On;
					const TSharedPtr<SButton> P = Self->Pin();
					return P.IsValid() && P->IsHovered() && P->IsEnabled() ? Hover : Off;
				})
				[
					Content
				]
			];
		*Self = B;
		return B;
	}

	inline TSharedRef<SEditableTextBox> Input(const FString& Initial, const FString& Hint, bool bPassword = false)
	{
		return SNew(SEditableTextBox)
			.Style(&InputStyle())
			.Text(FText::FromString(Initial))
			.HintText(FText::FromString(Hint))
			.Font(Body(18))
			.IsPassword(bPassword)
			.ForegroundColor(FSlateColor(Ink()));
	}

	inline TSharedRef<SWidget> Field(const FString& Caption, TSharedRef<SWidget> Content)
	{
		return SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 6)[Text(Caption, Label(12), Muted())]
			+ SVerticalBox::Slot().AutoHeight()[Content];
	}

	inline TSharedRef<SWidget> Check(const FString& Caption, TAttribute<ECheckBoxState> State, FOnCheckStateChanged OnChanged)
	{
		return SNew(SCheckBox)
			.IsChecked(State)
			.OnCheckStateChanged(OnChanged)
			[
				SNew(SBox).Padding(FMargin(6, 0, 0, 0))[Text(Caption, Body(16), C(0xcfe0f6))]
			];
	}

	inline TSharedRef<SWidget> Kicker(const FString& Small, const FString& Big)
	{
		return SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight()[Text(Small, Label(12), Sky())]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)[Text(Big, Title(36), Ink())];
	}

	inline FLinearColor ArchetypeColor(const FString& Class)
	{
		static const TMap<FString, uint32> Map = {
			{TEXT("Class_Blaster"), 0xe2561c}, {TEXT("Class_Controller"), 0x3399ff}, {TEXT("Class_Defender"), 0x3ddc84},
			{TEXT("Class_Scrapper"), 0xff4d6d}, {TEXT("Class_Tanker"), 0x8a97a8}, {TEXT("Class_Brute"), 0xc0392b},
			{TEXT("Class_Corruptor"), 0x9b59b6}, {TEXT("Class_Dominator"), 0xe67e22}, {TEXT("Class_Mastermind"), 0x6c5ce7},
			{TEXT("Class_Stalker"), 0x4a6278}, {TEXT("Class_Peacebringer"), 0xf1c40f}, {TEXT("Class_Warshade"), 0x7e57c2}};
		const uint32* Hex = Map.Find(Class);
		return C(Hex ? *Hex : 0x7cc4ff);
	}

	inline FString Ago(const FDateTime& When)
	{
		if (When <= FDateTime::MinValue()) return TEXT("Never seen online");
		const FTimespan D = FDateTime::UtcNow() - When;
		if (D.GetTotalMinutes() < 2) return TEXT("Last seen just now");
		if (D.GetTotalHours() < 1) return FString::Printf(TEXT("Last seen %d min ago"), (int32)D.GetTotalMinutes());
		if (D.GetTotalDays() < 1) return FString::Printf(TEXT("Last seen %d h ago"), (int32)D.GetTotalHours());
		return FString::Printf(TEXT("Last seen %d days ago"), (int32)D.GetTotalDays());
	}

	// ---- painting helpers (local units)
	inline void Lines(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, TArray<FVector2f> P, const FLinearColor& Col, float Thick = 1.f)
	{
		FSlateDrawElement::MakeLines(Out, Layer, G.ToPaintGeometry(), MoveTemp(P), ESlateDrawEffect::None, Col, true, Thick);
	}

	inline void Arc(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, FVector2f Center, float R, float A0, float A1, const FLinearColor& Col, float Thick)
	{
		TArray<FVector2f> P;
		const int32 Seg = FMath::Max(2, FMath::CeilToInt(FMath::Abs(A1 - A0) / (PI / 32.f)));
		for (int32 i = 0; i <= Seg; ++i)
		{
			const float A = FMath::Lerp(A0, A1, (float)i / Seg);
			P.Add(Center + FVector2f(FMath::Cos(A), FMath::Sin(A)) * R);
		}
		Lines(Out, Layer, G, MoveTemp(P), Col, Thick);
	}

	inline void Rect(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, FVector2f Pos, FVector2f Size, const FSlateBrush* Brush, const FLinearColor& Col)
	{
		FSlateDrawElement::MakeBox(Out, Layer, G.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), Brush, ESlateDrawEffect::None, Col);
	}

	struct FStop { float At; FLinearColor Col; };

	/** Gradient whose stops run along X (bAlongX) or along Y. Stops are (fraction, color). */
	inline void Gradient(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, FVector2f Pos, FVector2f Size, bool bAlongX,
		std::initializer_list<FStop> Stops)
	{
		TArray<FSlateGradientStop> S;
		for (const FStop& St : Stops)
			S.Add(FSlateGradientStop(bAlongX ? FVector2D(St.At * Size.X, 0) : FVector2D(0, St.At * Size.Y), St.Col));
		// Orient_Vertical: vertical stop lines, so the colour changes along X
		FSlateDrawElement::MakeGradient(Out, Layer, G.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), MoveTemp(S),
			bAlongX ? Orient_Vertical : Orient_Horizontal);
	}
}

// =================================================================== little painted widgets
using FCoHPaintFn = TFunction<void(const FGeometry&, FSlateWindowElementList&, int32, double)>;

/** A leaf that paints with a lambda (emblem, holo rings, spinner, ticker, corner brackets). */
class SCoHCanvas : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHCanvas) : _Size(FVector2D(1, 1)) {}
		SLATE_ARGUMENT(FVector2D, Size)
		SLATE_ARGUMENT(FCoHPaintFn, Painter)
	SLATE_END_ARGS()

	void Construct(const FArguments& A)
	{
		Size = A._Size;
		Painter = A._Painter;
		SetVisibility(EVisibility::HitTestInvisible);
	}
	virtual FVector2D ComputeDesiredSize(float) const override { return Size; }
	virtual int32 OnPaint(const FPaintArgs&, const FGeometry& Geometry, const FSlateRect&, FSlateWindowElementList& Out,
		int32 Layer, const FWidgetStyle&, bool) const override
	{
		if (Painter) Painter(Geometry, Out, Layer, FSlateApplication::Get().GetCurrentTime());
		return Layer + 4;
	}

private:
	FVector2D Size;
	FCoHPaintFn Painter;
};

inline TSharedRef<SWidget> Corners()
{
	return SNew(SCoHCanvas).Painter([](const FGeometry& G, FSlateWindowElementList& Out, int32 L, double)
	{
		const FVector2f S = FVector2f(G.GetLocalSize());
		const float K = 26.f, T = 3.f;
		const FLinearColor Col = HQ::Blue();
		HQ::Lines(Out, L, G, {{0, K}, {0, 0}, {K, 0}}, Col, T);
		HQ::Lines(Out, L, G, {{S.X - K, 0}, {S.X, 0}, {S.X, K}}, Col, T);
		HQ::Lines(Out, L, G, {{0, S.Y - K}, {0, S.Y}, {K, S.Y}}, Col, T);
		HQ::Lines(Out, L, G, {{S.X - K, S.Y}, {S.X, S.Y}, {S.X, S.Y - K}}, Col, T);
	});
}

/** Glass console panel with the blue corner brackets. */
inline TSharedRef<SWidget> Panel(TSharedRef<SWidget> Content, FMargin Pad, const FLinearColor& Fill = HQ::C(0x061020, .80f))
{
	return SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SBorder).BorderImage(HQ::Box(Fill, HQ::Sky(.35f), 6.f, 1.f)).Padding(Pad)[Content]
		]
		+ SOverlay::Slot()[Corners()];
}

inline TSharedRef<SWidget> Emblem(float Scale = 1.f)
{
	return SNew(SCoHCanvas).Size(FVector2D(40, 46) * Scale).Painter([Scale](const FGeometry& G, FSlateWindowElementList& Out, int32 L, double)
	{
		auto P = [Scale](float X, float Y) { return FVector2f(X, Y) * Scale; };
		// shield
		TArray<FVector2f> Shield = {P(20, 2), P(37, 8), P(37, 22)};
		for (int32 i = 1; i <= 8; ++i) { const float t = i / 8.f; Shield.Add(FMath::Lerp(FMath::Lerp(P(37, 22), P(34, 36), t), FMath::Lerp(P(34, 36), P(20, 44), t), t)); }
		for (int32 i = 1; i <= 8; ++i) { const float t = i / 8.f; Shield.Add(FMath::Lerp(FMath::Lerp(P(20, 44), P(6, 36), t), FMath::Lerp(P(6, 36), P(3, 22), t), t)); }
		Shield.Append({P(3, 8), P(20, 2)});
		HQ::Lines(Out, L, G, Shield, HQ::Blue(), 2.f * Scale);
		// star
		TArray<FVector2f> Star;
		for (int32 i = 0; i <= 10; ++i)
		{
			const float A = -HALF_PI + i * PI / 5.f;
			const float R = (i % 2 ? 4.5f : 11.f) * Scale;
			Star.Add(P(20, 21) + FVector2f(FMath::Cos(A), FMath::Sin(A)) * R);
		}
		HQ::Lines(Out, L + 1, G, Star, HQ::Gold(), 2.5f * Scale);
	});
}

inline TSharedRef<SWidget> Spinner(float Size)
{
	return SNew(SCoHCanvas).Size(FVector2D(Size, Size)).Painter([](const FGeometry& G, FSlateWindowElementList& Out, int32 L, double T)
	{
		const FVector2f S = FVector2f(G.GetLocalSize());
		const FVector2f C = S * .5f;
		const float R = S.X * .5f - 4.f;
		HQ::Arc(Out, L, G, C, R, 0, TWO_PI, HQ::Blue(.2f), 4.f);
		const float A = (float)FMath::Fmod(T * 5.5, (double)TWO_PI);
		HQ::Arc(Out, L + 1, G, C, R, A, A + PI * .55f, HQ::Blue(), 4.f);
		const float B = -(float)FMath::Fmod(T * 3.9, (double)TWO_PI);
		HQ::Arc(Out, L + 1, G, C, R - 18.f, B, B + PI * .45f, HQ::Gold(), 3.f);
	});
}


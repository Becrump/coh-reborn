#include "SCoHLobby.h"

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
	static FLinearColor C(uint32 Hex, float A = 1.f)
	{
		FLinearColor L(FColor((Hex >> 16) & 255, (Hex >> 8) & 255, Hex & 255));
		L.A = A;
		return L;
	}
	static FLinearColor Blue(float A = 1.f)  { return C(0x3399ff, A); }
	static FLinearColor Sky(float A = 1.f)   { return C(0x7cc4ff, A); }
	static FLinearColor Gold(float A = 1.f)  { return C(0xffb21e, A); }
	static FLinearColor Green(float A = 1.f) { return C(0x3ddc84, A); }
	static FLinearColor Red(float A = 1.f)   { return C(0xff6b6b, A); }
	static FLinearColor Ink()   { return C(0xe6f0ff); }
	static FLinearColor Muted() { return C(0x9fb6d6); }
	static FLinearColor Dim()   { return C(0x7f95b5); }
	static FLinearColor Grey()  { return C(0x7f8ea6); }
	static FLinearColor Night(float A = 1.f) { return C(0x040913, A); }
	static FLinearColor Clear() { return FLinearColor::Transparent; }

	// Red Circle (the original title font), Mont for the rest; Roboto when the UI art isn't copied in
	static FSlateFontInfo Title(float Px) { return FCoHUIArt::Get().Font(ECoHFont::Title, Px, false); }
	static FSlateFontInfo Bold(float Px)  { return FCoHUIArt::Get().Font(ECoHFont::GameBold, Px, false); }
	static FSlateFontInfo Body(float Px)  { return FCoHUIArt::Get().Font(ECoHFont::Game, Px, false); }
	static FSlateFontInfo Label(float Px = 12.f)
	{
		FSlateFontInfo F = Bold(Px);
		F.LetterSpacing = 260;
		return F;
	}

	static const FSlateBrush* White() { return FCoreStyle::Get().GetBrush("WhiteBrush"); }

	static const FSlateBrush* Box(const FLinearColor& Fill, const FLinearColor& Line = FLinearColor::Transparent, float Radius = 4.f, float Width = 1.f)
	{
		static TMap<FString, TUniquePtr<FSlateRoundedBoxBrush>> Cache;
		const FString Key = FString::Printf(TEXT("%s|%s|%.1f|%.1f"), *Fill.ToString(), *Line.ToString(), Radius, Width);
		if (const TUniquePtr<FSlateRoundedBoxBrush>* Hit = Cache.Find(Key)) return Hit->Get();
		return Cache.Add(Key, MakeUnique<FSlateRoundedBoxBrush>(Fill, Radius, Line, Width)).Get();
	}

	enum class EBtn : uint8 { Primary, Secondary, Danger, Count };

	static const FButtonStyle& BtnStyle(EBtn Kind)
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

	static const FButtonStyle& Bare()
	{
		static FButtonStyle S = FButtonStyle()
			.SetNormal(FSlateNoResource()).SetHovered(FSlateNoResource()).SetPressed(FSlateNoResource()).SetDisabled(FSlateNoResource())
			.SetNormalPadding(FMargin(0)).SetPressedPadding(FMargin(0));
		return S;
	}

	static const FEditableTextBoxStyle& InputStyle()
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

	static TSharedRef<STextBlock> Text(const FString& S, const FSlateFontInfo& Font, const FLinearColor& Color)
	{
		return SNew(STextBlock).Text(FText::FromString(S)).Font(Font).ColorAndOpacity(FSlateColor(Color));
	}

	static TSharedRef<SWidget> ButtonT(TAttribute<FText> Caption, EBtn Kind, FOnClicked OnClick, TAttribute<bool> Enabled = true, float FontPx = 15.f, float MinHeight = 44.f)
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

	static TSharedRef<SWidget> Button(const FString& Caption, EBtn Kind, FOnClicked OnClick, TAttribute<bool> Enabled = true, float FontPx = 15.f, float MinHeight = 44.f)
	{
		return ButtonT(TAttribute<FText>(FText::FromString(Caption)), Kind, OnClick, Enabled, FontPx, MinHeight);
	}

	/** A button whose frame shows selection: tabs, choice chips, cards. */
	static TSharedRef<SWidget> Selectable(TSharedRef<SWidget> Content, TAttribute<bool> Selected, FOnClicked OnClick,
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

	static TSharedRef<SEditableTextBox> Input(const FString& Initial, const FString& Hint, bool bPassword = false)
	{
		return SNew(SEditableTextBox)
			.Style(&InputStyle())
			.Text(FText::FromString(Initial))
			.HintText(FText::FromString(Hint))
			.Font(Body(18))
			.IsPassword(bPassword)
			.ForegroundColor(FSlateColor(Ink()));
	}

	static TSharedRef<SWidget> Field(const FString& Caption, TSharedRef<SWidget> Content)
	{
		return SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 6)[Text(Caption, Label(12), Muted())]
			+ SVerticalBox::Slot().AutoHeight()[Content];
	}

	static TSharedRef<SWidget> Check(const FString& Caption, TAttribute<ECheckBoxState> State, FOnCheckStateChanged OnChanged)
	{
		return SNew(SCheckBox)
			.IsChecked(State)
			.OnCheckStateChanged(OnChanged)
			[
				SNew(SBox).Padding(FMargin(6, 0, 0, 0))[Text(Caption, Body(16), C(0xcfe0f6))]
			];
	}

	static TSharedRef<SWidget> Kicker(const FString& Small, const FString& Big)
	{
		return SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight()[Text(Small, Label(12), Sky())]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)[Text(Big, Title(36), Ink())];
	}

	static FLinearColor ArchetypeColor(const FString& Class)
	{
		static const TMap<FString, uint32> Map = {
			{TEXT("Class_Blaster"), 0xe2561c}, {TEXT("Class_Controller"), 0x3399ff}, {TEXT("Class_Defender"), 0x3ddc84},
			{TEXT("Class_Scrapper"), 0xff4d6d}, {TEXT("Class_Tanker"), 0x8a97a8}, {TEXT("Class_Brute"), 0xc0392b},
			{TEXT("Class_Corruptor"), 0x9b59b6}, {TEXT("Class_Dominator"), 0xe67e22}, {TEXT("Class_Mastermind"), 0x6c5ce7},
			{TEXT("Class_Stalker"), 0x4a6278}, {TEXT("Class_Peacebringer"), 0xf1c40f}, {TEXT("Class_Warshade"), 0x7e57c2}};
		const uint32* Hex = Map.Find(Class);
		return C(Hex ? *Hex : 0x7cc4ff);
	}

	static FString Ago(const FDateTime& When)
	{
		if (When <= FDateTime::MinValue()) return TEXT("Never seen online");
		const FTimespan D = FDateTime::UtcNow() - When;
		if (D.GetTotalMinutes() < 2) return TEXT("Last seen just now");
		if (D.GetTotalHours() < 1) return FString::Printf(TEXT("Last seen %d min ago"), (int32)D.GetTotalMinutes());
		if (D.GetTotalDays() < 1) return FString::Printf(TEXT("Last seen %d h ago"), (int32)D.GetTotalHours());
		return FString::Printf(TEXT("Last seen %d days ago"), (int32)D.GetTotalDays());
	}

	// ---- painting helpers (local units)
	static void Lines(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, TArray<FVector2f> P, const FLinearColor& Col, float Thick = 1.f)
	{
		FSlateDrawElement::MakeLines(Out, Layer, G.ToPaintGeometry(), MoveTemp(P), ESlateDrawEffect::None, Col, true, Thick);
	}

	static void Arc(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, FVector2f Center, float R, float A0, float A1, const FLinearColor& Col, float Thick)
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

	static void Rect(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, FVector2f Pos, FVector2f Size, const FSlateBrush* Brush, const FLinearColor& Col)
	{
		FSlateDrawElement::MakeBox(Out, Layer, G.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), Brush, ESlateDrawEffect::None, Col);
	}

	struct FStop { float At; FLinearColor Col; };

	/** Gradient whose stops run along X (bAlongX) or along Y. Stops are (fraction, color). */
	static void Gradient(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, FVector2f Pos, FVector2f Size, bool bAlongX,
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

static TSharedRef<SWidget> Corners()
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
static TSharedRef<SWidget> Panel(TSharedRef<SWidget> Content, FMargin Pad, const FLinearColor& Fill = HQ::C(0x061020, .80f))
{
	return SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SBorder).BorderImage(HQ::Box(Fill, HQ::Sky(.35f), 6.f, 1.f)).Padding(Pad)[Content]
		]
		+ SOverlay::Slot()[Corners()];
}

static TSharedRef<SWidget> Emblem(float Scale = 1.f)
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

static TSharedRef<SWidget> Spinner(float Size)
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

// =================================================================== construct
void SCoHLobby::Construct(const FArguments& InArgs)
{
	F = InArgs._Frontend;
	if (F.IsValid())
	{
		const FString Path = FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / F->BackdropImage);
		if (FPaths::FileExists(Path)) Backdrop = MakeShared<FSlateDynamicImageBrush>(FName(*Path), BackdropSize);
		if (UTexture2D* T = F->GlowTexture()) { GlowBrush.SetResourceObject(T); GlowBrush.ImageSize = FVector2D(128, 128); }
		if (UTexture2D* T = F->BeamTexture()) { BeamBrush.SetResourceObject(T); BeamBrush.ImageSize = FVector2D(32, 256); }
	}

	TSharedRef<SWidget> Ticker = SNew(SCoHCanvas).Size(FVector2D(100, 46)).Painter([this](const FGeometry& G, FSlateWindowElementList& Out, int32 L, double T)
	{
		FString Line;
		if (F.IsValid())
			for (const FString& N : F->NewsLines) Line += N + TEXT("     ·     ");
		if (Line.IsEmpty()) return;
		const FSlateFontInfo Font = HQ::Body(15);
		const float W = FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Line, Font).X;
		if (W <= 1.f) return;
		const float X = -(float)FMath::Fmod(T * 60.0, (double)W);
		const float Y = (G.GetLocalSize().Y - 20.f) * .5f;
		for (float Px = X; Px < G.GetLocalSize().X; Px += W)
			FSlateDrawElement::MakeText(Out, L, G.ToPaintGeometry(FVector2f(W, 24.f), FSlateLayoutTransform(FVector2f(Px, Y))), Line, Font,
				ESlateDrawEffect::None, HQ::C(0xaac4e6));
	});

	ChildSlot
	[
		SNew(SOverlay)

		// ---- top bar
		+ SOverlay::Slot().VAlign(VAlign_Top)
		[
			MakeTopBar()
		]

		// ---- console + right column
		+ SOverlay::Slot().Padding(40, 108, 40, 72)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(.64f)
			[
				Panel(
					SNew(SVerticalBox)
					// error banner
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 14)
					[
						SNew(SBorder)
						.Visibility_Lambda([this] { return F.IsValid() && !F->LastError().IsEmpty() ? EVisibility::Visible : EVisibility::Collapsed; })
						.BorderImage(HQ::Box(HQ::C(0x3a0c12, .85f), HQ::Red(.7f), 4.f, 1.f))
						.Padding(FMargin(16, 10))
						[
							SNew(SHorizontalBox)
							+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
							[
								SNew(STextBlock).Font(HQ::Bold(16)).ColorAndOpacity(FSlateColor(HQ::C(0xffd6d6))).AutoWrapText(true)
								.Text_Lambda([this] { return FText::FromString(F.IsValid() ? F->LastError() : FString()); })
							]
							+ SHorizontalBox::Slot().AutoWidth().Padding(12, 0, 0, 0)
							[
								HQ::Button(TEXT("DISMISS"), HQ::EBtn::Danger, FOnClicked::CreateLambda([this] { if (F.IsValid()) F->ClearError(); return FReply::Handled(); }), true, 12.f, 36.f)
							]
						]
					]
					+ SVerticalBox::Slot().FillHeight(1)
					[
						SNew(SWidgetSwitcher)
						.WidgetIndex_Lambda([this] { return (int32)Tab; })
						+ SWidgetSwitcher::Slot()[MakeJoinPage()]
						+ SWidgetSwitcher::Slot()[MakeHostPage()]
						+ SWidgetSwitcher::Slot()[MakeRosterPage()]
						+ SWidgetSwitcher::Slot()[MakeSettingsPage()]
					],
					FMargin(34, 28))
			]
			+ SHorizontalBox::Slot().FillWidth(.36f).Padding(32, 0, 0, 0)
			[
				MakeRightColumn()
			]
		]

		// ---- news ticker
		+ SOverlay::Slot().VAlign(VAlign_Bottom)
		[
			SNew(SBox).HeightOverride(46)
			[
				SNew(SBorder).BorderImage(HQ::Box(HQ::C(0x060e1c, .9f), HQ::Sky(.25f), 0.f, 1.f)).Padding(0)
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().AutoWidth()
					[
						SNew(SBorder).BorderImage(HQ::Box(HQ::Blue(), HQ::Clear(), 0.f, 0.f)).Padding(FMargin(18, 0)).VAlign(VAlign_Center)
						[
							HQ::Text(TEXT("PARAGON NEWS"), HQ::Label(13), HQ::C(0x03101f))
						]
					]
					+ SHorizontalBox::Slot().FillWidth(1).Padding(20, 0, 0, 0)
					[
						SNew(SBox).Clipping(EWidgetClipping::ClipToBounds)[Ticker]
					]
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(18, 0)
					[
						HQ::Text(FString::Printf(TEXT("NET v%d"), CoHLobby::NetVersion), HQ::Label(11), HQ::C(0x6f84a3))
					]
				]
			]
		]

		// ---- connecting / launching
		+ SOverlay::Slot()
		[
			MakeConnecting()
		]

		// ---- dialogs
		+ SOverlay::Slot()
		[
			SNew(SBorder)
			.Visibility_Lambda([this] { return bModal ? EVisibility::Visible : EVisibility::Collapsed; })
			.BorderImage(HQ::White())
			.BorderBackgroundColor(HQ::C(0x02060e, .74f))
			.HAlign(HAlign_Center).VAlign(VAlign_Center)
			[
				SAssignNew(ModalHost, SBox).WidthOverride(560)
			]
		]
	];

	// keep painting: the backdrop, rings and ticker move every frame
	RegisterActiveTimer(0.f, FWidgetActiveTimerDelegate::CreateLambda([](double, float) { return EActiveTimerReturnType::Continue; }));
	Rebuild();
}

// =================================================================== background
int32 SCoHLobby::OnPaint(const FPaintArgs& Args, const FGeometry& Geometry, const FSlateRect& Culling,
	FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle& Style, bool bParentEnabled) const
{
	const FVector2f S = FVector2f(Geometry.GetLocalSize());
	const double T = FSlateApplication::Get().GetCurrentTime();
	int32 L = Layer;

	// night
	HQ::Rect(Out, L, Geometry, FVector2f::ZeroVector, S, HQ::White(), HQ::C(0x050a14));

	// the city through the HQ windows, drifting very slowly
	if (Backdrop.IsValid())
	{
		const float Scale = FMath::Max(S.X / BackdropSize.X, S.Y / BackdropSize.Y) * 1.04f;
		const FVector2f Size(BackdropSize.X * Scale, BackdropSize.Y * Scale);
		const float Drift = (float)FMath::Sin(T * .05) * Size.X * .015f;
		const FVector2f Pos((S.X - Size.X) * .5f + Drift, (S.Y - Size.Y) * .3f);
		HQ::Rect(Out, L + 1, Geometry, Pos, Size, Backdrop.Get(), FLinearColor(.62f, .62f, .66f, 1.f));
	}

	// searchlights sweeping the sky
	if (BeamBrush.GetResourceObject())
	{
		struct FBeam { float X, Period, Phase; FLinearColor Col; };
		const FBeam Beams[] = {{.79f, 9.f, 0.f, HQ::C(0xffd678, .26f)}, {.90f, 12.f, 2.f, HQ::Sky(.24f)}, {.70f, 15.f, 4.f, HQ::Sky(.12f)}};
		for (const FBeam& B : Beams)
		{
			const FVector2f Size(110.f, S.Y * .75f);
			const FVector2f Pos(S.X * B.X - Size.X * .5f, S.Y * .5f - Size.Y);
			const float Swing = (float)FMath::Sin((T + B.Phase) * TWO_PI / B.Period);
			FSlateDrawElement::MakeRotatedBox(Out, L + 2, Geometry.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), &BeamBrush,
				ESlateDrawEffect::None, FMath::DegreesToRadians(-2.f + Swing * 13.f),
				TOptional<FVector2f>(FVector2f(Size.X * .5f, Size.Y)), FSlateDrawElement::RelativeToElement, B.Col);
		}
	}

	// darken the console side, and the top and bottom edges
	HQ::Gradient(Out, L + 3, Geometry, FVector2f::ZeroVector, S, true,
		{{0.f, HQ::Night(.96f)}, {.52f, HQ::Night(.86f)}, {.76f, HQ::Night(.42f)}, {1.f, HQ::Night(.7f)}});
	HQ::Gradient(Out, L + 3, Geometry, FVector2f::ZeroVector, S, false,
		{{0.f, HQ::Night(.85f)}, {.16f, HQ::Night(0.f)}, {.80f, HQ::Night(0.f)}, {1.f, HQ::Night(.95f)}});

	// holo grid
	for (float X = 0; X < S.X; X += 40.f) HQ::Lines(Out, L + 4, Geometry, {{X, 0}, {X, S.Y}}, HQ::Blue(.06f), 1.f);
	for (float Y = 0; Y < S.Y; Y += 40.f) HQ::Lines(Out, L + 4, Geometry, {{0, Y}, {S.X, Y}}, HQ::Blue(.06f), 1.f);

	// scanner sweep
	const float Band = 130.f;
	const float SweepY = (float)FMath::Fmod(T / 7.0, 1.0) * (S.Y + Band) - Band;
	HQ::Gradient(Out, L + 4, Geometry, FVector2f(0, SweepY), FVector2f(S.X, Band), false,
		{{0.f, HQ::Blue(0.f)}, {.5f, HQ::Blue(.08f)}, {1.f, HQ::Blue(0.f)}});

	return SCompoundWidget::OnPaint(Args, Geometry, Culling, Out, L + 5, Style, bParentEnabled);
}

void SCoHLobby::Tick(const FGeometry& Geometry, const double CurrentTime, const float DeltaTime)
{
	SCompoundWidget::Tick(Geometry, CurrentTime, DeltaTime);
	if (F.IsValid() && F->ServersRevision() != BuiltRevision) Rebuild();
}

FReply SCoHLobby::OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Key)
{
	if (Key.GetKey() == EKeys::Escape && bModal)
	{
		CloseModal();
		return FReply::Handled();
	}
	return SCompoundWidget::OnKeyDown(Geometry, Key);
}

// =================================================================== top bar
FText SCoHLobby::HeroChipText() const
{
	const FCoHHeroCard* C = F.IsValid() ? F->ChosenHeroCard() : nullptr;
	return FText::FromString(C ? C->Name : TEXT("Starter hero"));
}

TSharedRef<SWidget> SCoHLobby::MakeTopBar()
{
	TSharedRef<SHorizontalBox> Tabs = SNew(SHorizontalBox);
	const TCHAR* Names[] = {TEXT("JOIN FRIENDS"), TEXT("HOST A SERVER"), TEXT("HERO ROSTER"), TEXT("SETTINGS")};
	for (int32 i = 0; i < 4; ++i)
	{
		const ETab Me = (ETab)i;
		Tabs->AddSlot().AutoWidth().Padding(0, 0, 6, 0)
		[
			HQ::Selectable(
				SNew(STextBlock).Text(FText::FromString(Names[i])).Font(HQ::Label(14))
				.ColorAndOpacity_Lambda([this, Me] { return FSlateColor(Tab == Me ? FLinearColor::White : HQ::Muted()); }),
				TAttribute<bool>::CreateLambda([this, Me] { return Tab == Me; }),
				FOnClicked::CreateLambda([this, Me] { Tab = Me; return FReply::Handled(); }),
				HQ::Box(HQ::Blue(.38f), HQ::Blue(), 4.f, 1.f), HQ::Box(HQ::Clear(), HQ::Clear(), 4.f, 0.f), HQ::Box(HQ::Blue(.14f), HQ::Sky(.3f), 4.f, 1.f),
				FMargin(18, 12))
		];
	}

	TSharedRef<SWidget> Chip = HQ::Selectable(
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
		[
			SNew(SBox).WidthOverride(38).HeightOverride(38)
			[
				SNew(SBorder).BorderImage(HQ::Box(FLinearColor::White, HQ::Clear(), 19.f, 0.f))
				.BorderBackgroundColor_Lambda([this]
				{
					const FCoHHeroCard* C = F.IsValid() ? F->ChosenHeroCard() : nullptr;
					return FSlateColor(HQ::ArchetypeColor(C ? C->Class : FString(TEXT("Class_Blaster"))));
				})
				.HAlign(HAlign_Center).VAlign(VAlign_Center)
				[
					SNew(STextBlock).Font(HQ::Title(20)).ColorAndOpacity(FSlateColor(HQ::C(0x10080a)))
					.Text_Lambda([this] { const FString N = HeroChipText().ToString(); return FText::FromString(N.Left(1).ToUpper()); })
				]
			]
		]
		+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12, 0, 4, 0)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight()
			[
				SNew(STextBlock).Font(HQ::Bold(16)).ColorAndOpacity(FSlateColor(HQ::Ink())).Text_Lambda([this] { return HeroChipText(); })
			]
			+ SVerticalBox::Slot().AutoHeight()
			[
				SNew(STextBlock).Font(HQ::Body(13)).ColorAndOpacity(FSlateColor(HQ::C(0xffd38a))).Text_Lambda([this]
				{
					const FCoHHeroCard* C = F.IsValid() ? F->ChosenHeroCard() : nullptr;
					return FText::FromString(C ? FString::Printf(TEXT("Level %d %s"), C->Level, *C->ArchetypeName()) : FString(TEXT("Pick one in the Hero Roster")));
				})
			]
		],
		false,
		FOnClicked::CreateLambda([this] { Tab = ETab::Roster; return FReply::Handled(); }),
		nullptr, HQ::Box(HQ::C(0x281a04, .6f), HQ::Gold(.45f), 26.f, 1.f), HQ::Box(HQ::C(0x3a2808, .8f), HQ::Gold(.9f), 26.f, 1.f),
		FMargin(6, 6, 18, 6));

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight()
		[
			SNew(SBox).HeightOverride(84)
			[
				SNew(SBorder).BorderImage(HQ::Box(HQ::C(0x081224, .78f), HQ::Clear(), 0.f, 0.f)).Padding(FMargin(36, 0)).VAlign(VAlign_Center)
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[Emblem()]
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(14, 0, 0, 0)
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot().AutoHeight()[HQ::Text(TEXT("PARAGON HQ"), HQ::Title(28), HQ::Ink())]
						+ SVerticalBox::Slot().AutoHeight().Padding(0, 2, 0, 0)[HQ::Text(TEXT("MISSION CONTROL  ·  CITY OF HEROES REBORN"), HQ::Label(11), HQ::Sky())]
					]
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(48, 0, 0, 0)[Tabs]
					+ SHorizontalBox::Slot().FillWidth(1)
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[Chip]
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(22, 0, 0, 0)
					[
						SNew(STextBlock).Font(HQ::Label(15)).ColorAndOpacity(FSlateColor(HQ::Muted()))
						.Text_Lambda([] { return FText::FromString(FDateTime::Now().ToString(TEXT("%H:%M"))); })
					]
				]
			]
		]
		+ SVerticalBox::Slot().AutoHeight()
		[
			SNew(SBox).HeightOverride(1)[SNew(SImage).Image(HQ::White()).ColorAndOpacity(FSlateColor(HQ::Sky(.28f)))]
		];
}

// =================================================================== join page
const FCoHServerEntry* SCoHLobby::Server(int32 Index) const
{
	return F.IsValid() && F->Servers().IsValidIndex(Index) ? &F->Servers()[Index] : nullptr;
}

TSharedRef<SWidget> SCoHLobby::MakeJoinPage()
{
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 20)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Bottom)[HQ::Kicker(TEXT("ALLIED BASES"), TEXT("Join a friend's server"))]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Bottom).Padding(10, 0, 0, 0)
			[
				HQ::Button(TEXT("ADD SERVER"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { OpenServerEditor(INDEX_NONE); return FReply::Handled(); }), true, 13.f)
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Bottom).Padding(10, 0, 0, 0)
			[
				HQ::Button(TEXT("DIRECT CONNECT"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { OpenDirectConnect(); return FReply::Handled(); }), true, 13.f)
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Bottom).Padding(10, 0, 0, 0)
			[
				HQ::Button(TEXT("REFRESH"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { if (F.IsValid()) F->RefreshNow(); return FReply::Handled(); }), true, 13.f)
			]
		]
		+ SVerticalBox::Slot().FillHeight(1)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()[SAssignNew(ServerRows, SVerticalBox)]
			+ SScrollBox::Slot().Padding(0, 14, 0, 10)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[HQ::Text(TEXT("FOUND ON YOUR NETWORK"), HQ::Label(12), HQ::Sky())]
				+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center).Padding(14, 0, 0, 0)
				[
					SNew(SBox).HeightOverride(1)[SNew(SImage).Image(HQ::White()).ColorAndOpacity(FSlateColor(HQ::Sky(.25f)))]
				]
			]
			+ SScrollBox::Slot()[SAssignNew(LanRows, SVerticalBox)]
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 12, 0, 0)
		[
			SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::Dim())).AutoWrapText(true)
			.Text(FText::FromString(TEXT("Status is checked every few seconds with a small UDP ping on the game port + 1 (7778). "
				"Friends over the internet: everyone on the same Tailscale network, or the host forwards UDP 7777 and 7778.")))
		];
}

namespace
{
	FLinearColor StateColor(const FCoHServerEntry& E)
	{
		switch (E.State)
		{
		case FCoHServerEntry::EState::Online:     return E.Info.Version == CoHLobby::NetVersion ? HQ::Green() : HQ::Red();
		case FCoHServerEntry::EState::Checking:   return HQ::Gold();
		case FCoHServerEntry::EState::BadAddress: return HQ::Red();
		default:                                  return HQ::Grey();
		}
	}

	FString StateText(const FCoHServerEntry& E)
	{
		switch (E.State)
		{
		case FCoHServerEntry::EState::Online:     return E.Info.Version == CoHLobby::NetVersion ? TEXT("ONLINE") : TEXT("OTHER VERSION");
		case FCoHServerEntry::EState::Checking:   return TEXT("CHECKING");
		case FCoHServerEntry::EState::BadAddress: return TEXT("UNKNOWN ADDRESS");
		default:                                  return TEXT("OFFLINE");
		}
	}

	FString DetailText(const FCoHServerEntry& E)
	{
		switch (E.State)
		{
		case FCoHServerEntry::EState::Online:
			if (E.Info.Version != CoHLobby::NetVersion) return TEXT("Different game build: update to play together");
			return E.Info.Heroes.Num() ? FString::Join(E.Info.Heroes, TEXT(", ")) : FString(TEXT("Nobody on yet"));
		case FCoHServerEntry::EState::Checking:   return TEXT("Waiting for a reply");
		case FCoHServerEntry::EState::BadAddress: return TEXT("Can't find that PC name. Check the address.");
		default:                                  return HQ::Ago(E.LastSeen);
		}
	}

	float Pulse(double Speed = 3.5) { return .65f + .35f * (float)FMath::Sin(FSlateApplication::Get().GetCurrentTime() * Speed); }

	/** Status light, player pips and ping bars shared by saved and LAN rows. */
	TSharedRef<SWidget> Dot(TFunction<FLinearColor()> Color, TFunction<bool()> Pulsing)
	{
		return SNew(SBox).WidthOverride(14).HeightOverride(14).VAlign(VAlign_Center)
			[
				SNew(SImage).Image(HQ::Box(FLinearColor::White, HQ::Clear(), 7.f, 0.f))
				.ColorAndOpacity_Lambda([Color, Pulsing] { FLinearColor C = Color(); if (Pulsing()) C.A = Pulse(); return FSlateColor(C); })
			];
	}

	TSharedRef<SWidget> Pips(TFunction<int32()> Players, TFunction<int32()> Max)
	{
		TSharedRef<SHorizontalBox> Row = SNew(SHorizontalBox);
		for (int32 k = 0; k < 8; ++k)
			Row->AddSlot().AutoWidth().Padding(0, 0, 4, 0)
			[
				SNew(SBox).WidthOverride(14).HeightOverride(8)
				.Visibility_Lambda([Max, k] { return k < FMath::Clamp(Max(), 1, 8) ? EVisibility::Visible : EVisibility::Collapsed; })
				[
					SNew(SImage).Image(HQ::Box(FLinearColor::White, HQ::Clear(), 2.f, 0.f))
					.ColorAndOpacity_Lambda([Players, k] { return FSlateColor(k < Players() ? HQ::Blue() : HQ::Sky(.18f)); })
				]
			];
		return Row;
	}

	TSharedRef<SWidget> PingBars(TFunction<float()> Ping)
	{
		TSharedRef<SHorizontalBox> Row = SNew(SHorizontalBox);
		for (int32 k = 1; k <= 4; ++k)
			Row->AddSlot().AutoWidth().VAlign(VAlign_Bottom).Padding(0, 0, 3, 0)
			[
				SNew(SBox).WidthOverride(5).HeightOverride(5.f + k * 4.f)
				[
					SNew(SImage).Image(HQ::White()).ColorAndOpacity_Lambda([Ping, k]
					{
						const float P = Ping();
						const int32 Bars = P <= 0.f ? 0 : P < 40.f ? 4 : P < 80.f ? 3 : P < 150.f ? 2 : 1;
						return FSlateColor(k <= Bars ? HQ::Green() : HQ::Sky(.2f));
					})
				]
			];
		Row->AddSlot().AutoWidth().VAlign(VAlign_Bottom).Padding(6, 0, 0, 0)
		[
			SNew(STextBlock).Font(HQ::Body(13)).ColorAndOpacity(FSlateColor(HQ::C(0x8fa6c6)))
			.Text_Lambda([Ping] { const float P = Ping(); return FText::FromString(P > 0.f ? FString::Printf(TEXT("%d ms"), FMath::RoundToInt(P)) : FString()); })
		];
		return Row;
	}
}

TSharedRef<SWidget> SCoHLobby::MakeServerRow(int32 Index)
{
	auto E = [this, Index]() { return Server(Index); };
	return SNew(SBorder)
		.BorderImage(HQ::Box(HQ::C(0x0a1a32, .62f), HQ::Sky(.22f), 5.f, 1.f))
		.Padding(FMargin(18, 14))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 18, 0)
			[
				Dot([E] { const FCoHServerEntry* S = E(); return S ? StateColor(*S) : HQ::Grey(); },
					[E] { const FCoHServerEntry* S = E(); return S && S->State != FCoHServerEntry::EState::Offline; })
			]
			// name, address, who's on
			+ SHorizontalBox::Slot().FillWidth(1.6f).VAlign(VAlign_Center)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().AutoWidth()
					[
						SNew(STextBlock).Font(HQ::Bold(20)).ColorAndOpacity(FSlateColor(HQ::Ink()))
						.Text_Lambda([E] { const FCoHServerEntry* S = E(); return FText::FromString(S ? S->Name : FString()); })
					]
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(10, 0, 0, 0)
					[
						SNew(SBorder)
						.Visibility_Lambda([E] { const FCoHServerEntry* S = E(); return S && S->State == FCoHServerEntry::EState::Online && S->Info.bLocked ? EVisibility::Visible : EVisibility::Collapsed; })
						.BorderImage(HQ::Box(HQ::Gold(.12f), HQ::Gold(.7f), 3.f, 1.f)).Padding(FMargin(6, 1))
						[
							SNew(STextBlock).Font(HQ::Label(10)).ColorAndOpacity(FSlateColor(HQ::Gold()))
							.Text_Lambda([E] { const FCoHServerEntry* S = E(); return FText::FromString(S && !S->Password.IsEmpty() ? TEXT("PASSWORD SAVED") : TEXT("PASSWORD")); })
						]
					]
				]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 3, 0, 0)
				[
					SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::C(0x8fa6c6)))
					.Text_Lambda([E]
					{
						const FCoHServerEntry* S = E();
						if (!S) return FText();
						FString A = FString::Printf(TEXT("%s : %d"), *S->Host, S->Port);
						if (!S->ResolvedIp.IsEmpty() && S->ResolvedIp != S->Host) A += TEXT("   (") + S->ResolvedIp + TEXT(")");
						return FText::FromString(A);
					})
				]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 3, 0, 0)
				[
					SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::C(0xaac4e6)))
					.Text_Lambda([E] { const FCoHServerEntry* S = E(); return FText::FromString(S ? DetailText(*S) : FString()); })
				]
			]
			// state + zone
			+ SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center).Padding(12, 0)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()
				[
					SNew(STextBlock).Font(HQ::Label(13))
					.ColorAndOpacity_Lambda([E] { const FCoHServerEntry* S = E(); return FSlateColor(S ? StateColor(*S) : HQ::Grey()); })
					.Text_Lambda([E] { const FCoHServerEntry* S = E(); return FText::FromString(S ? StateText(*S) : FString()); })
				]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)
				[
					SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::C(0x8fa6c6)))
					.Text_Lambda([E] { const FCoHServerEntry* S = E(); return FText::FromString(S && S->State == FCoHServerEntry::EState::Online ? S->Info.Zone : FString()); })
				]
			]
			// heroes on
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12, 0)
			[
				SNew(SBox).WidthOverride(150)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()
					[
						Pips([E] { const FCoHServerEntry* S = E(); return S && S->State == FCoHServerEntry::EState::Online ? S->Info.Players : 0; },
							[E] { const FCoHServerEntry* S = E(); return S && S->State == FCoHServerEntry::EState::Online ? S->Info.MaxPlayers : 7; })
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 6, 0, 0)
					[
						SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::C(0x8fa6c6)))
						.Text_Lambda([E]
						{
							const FCoHServerEntry* S = E();
							return FText::FromString(S && S->State == FCoHServerEntry::EState::Online
								? FString::Printf(TEXT("%d / %d heroes"), S->Info.Players, S->Info.MaxPlayers) : FString(TEXT("- / -")));
						})
					]
				]
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12, 0)
			[
				SNew(SBox).WidthOverride(92)
				[
					PingBars([E] { const FCoHServerEntry* S = E(); return S && S->State == FCoHServerEntry::EState::Online ? S->PingMs : 0.f; })
				]
			]
			// actions
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12, 0, 0, 0)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()
				[
					SNew(SBox).WidthOverride(132)
					[
						HQ::ButtonT(
							TAttribute<FText>::CreateLambda([E]
							{
								const FCoHServerEntry* S = E();
								if (!S) return FText();
								if (S->CanJoin()) return FText::FromString(TEXT("JOIN"));
								return FText::FromString(S->State == FCoHServerEntry::EState::Checking ? TEXT("...") : S->State == FCoHServerEntry::EState::Online ? TEXT("UPDATE") : TEXT("OFFLINE"));
							}),
							HQ::EBtn::Primary,
							FOnClicked::CreateLambda([this, Index]
							{
								const FCoHServerEntry* S = Server(Index);
								if (!S || !F.IsValid()) return FReply::Handled();
								if (S->Info.bLocked && S->Password.IsEmpty()) OpenPassword(Index, false);
								else F->Join(Index, FString(), false);
								return FReply::Handled();
							}),
							TAttribute<bool>::CreateLambda([E] { const FCoHServerEntry* S = E(); return S && S->CanJoin(); }),
							16.f, 46.f)
					]
				]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 6, 0, 0).HAlign(HAlign_Center)
				[
					SNew(SButton).ButtonStyle(&HQ::Bare())
					.OnClicked_Lambda([this, Index] { OpenServerEditor(Index); return FReply::Handled(); })
					[
						HQ::Text(TEXT("EDIT"), HQ::Label(11), HQ::Sky(.85f))
					]
				]
			]
		];
}

TSharedRef<SWidget> SCoHLobby::MakeLanRow(int32 Index)
{
	auto L = [this, Index]() -> const FCoHLanServer* { return F.IsValid() && F->LanServers().IsValidIndex(Index) ? &F->LanServers()[Index] : nullptr; };
	const FCoHLanServer* Now = L();
	const FString Ip = Now ? Now->Ip : FString();
	const int32 Port = Now && Now->Info.GamePort > 0 ? Now->Info.GamePort : CoHLobby::DefaultGamePort;
	const FString Name = Now ? Now->Info.Name : FString();
	return SNew(SBorder)
		.BorderImage(HQ::Box(HQ::C(0x0a1a32, .35f), HQ::Sky(.35f), 5.f, 1.f))
		.Padding(FMargin(18, 12))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 18, 0)
			[
				Dot([] { return HQ::Green(); }, [] { return true; })
			]
			+ SHorizontalBox::Slot().FillWidth(1.6f).VAlign(VAlign_Center)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()[HQ::Text(Name, HQ::Bold(18), HQ::Ink())]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 3, 0, 0)[HQ::Text(FString::Printf(TEXT("%s : %d"), *Ip, Port), HQ::Body(14), HQ::C(0x8fa6c6))]
			]
			+ SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center).Padding(12, 0)
			[
				SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::C(0x8fa6c6)))
				.Text_Lambda([L]
				{
					const FCoHLanServer* S = L();
					return FText::FromString(S ? FString::Printf(TEXT("%s   %d / %d heroes%s"), *S->Info.Zone, S->Info.Players, S->Info.MaxPlayers, S->Info.bLocked ? TEXT("   PASSWORD") : TEXT("")) : FString());
				})
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12, 0)
			[
				SNew(SBox).WidthOverride(92)[PingBars([L] { const FCoHLanServer* S = L(); return S ? S->PingMs : 0.f; })]
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12, 0, 0, 0)
			[
				HQ::Button(TEXT("SAVE"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this, Name, Ip, Port]
				{
					if (F.IsValid()) F->AddServer(Name, FString::Printf(TEXT("%s:%d"), *Ip, Port), FString(), false);
					return FReply::Handled();
				}), true, 13.f)
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(10, 0, 0, 0)
			[
				SNew(SBox).WidthOverride(110)
				[
					HQ::Button(TEXT("JOIN"), HQ::EBtn::Primary, FOnClicked::CreateLambda([this, Index, L]
					{
						const FCoHLanServer* S = L();
						if (!S || !F.IsValid()) return FReply::Handled();
						if (S->Info.bLocked) OpenPassword(Index, true);
						else F->JoinLan(Index, FString());
						return FReply::Handled();
					}),
					TAttribute<bool>::CreateLambda([L] { const FCoHLanServer* S = L(); return S && S->Info.Version == CoHLobby::NetVersion; }), 15.f)
				]
			]
		];
}

// =================================================================== host page
TSharedRef<SWidget> SCoHLobby::MakeHostPage()
{
	FCoHHostSettings Init;
	if (F.IsValid()) Init = F->HostSettings();
	HostName = HQ::Input(Init.ServerName, TEXT("Name your server"));
	HostPassword = SNew(SEditableTextBox)
		.Style(&HQ::InputStyle())
		.Text(FText::FromString(Init.Password))
		.HintText(FText::FromString(TEXT("Leave empty for an open server")))
		.Font(HQ::Body(18))
		.ForegroundColor(FSlateColor(HQ::Ink()))
		.IsPassword_Lambda([this] { return !bShowHostPassword; });

	// max heroes
	TSharedRef<SHorizontalBox> Max = SNew(SHorizontalBox);
	for (int32 n = 2; n <= 7; ++n)
		Max->AddSlot().AutoWidth().Padding(0, 0, 6, 0)
		[
			SNew(SBox).WidthOverride(54).HeightOverride(46)
			[
				HQ::Selectable(
					SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Center)[HQ::Text(FString::FromInt(n), HQ::Bold(18), HQ::Ink())],
					TAttribute<bool>::CreateLambda([this, n] { return F.IsValid() && F->HostSettings().MaxPlayers == n; }),
					FOnClicked::CreateLambda([this, n] { if (F.IsValid()) F->HostSettings().MaxPlayers = n; return FReply::Handled(); }),
					HQ::Box(HQ::Blue(.42f), HQ::Blue(), 4.f, 1.f), HQ::Box(HQ::C(0x040c1a, .6f), HQ::Sky(.3f), 4.f, 1.f), HQ::Box(HQ::Blue(.18f), HQ::Sky(.6f), 4.f, 1.f),
					FMargin(0))
			]
		];

	// start zone
	TSharedRef<SUniformGridPanel> ZoneGrid = SNew(SUniformGridPanel).SlotPadding(FMargin(0, 0, 8, 8));
	if (F.IsValid())
		for (int32 z = 0; z < F->Zones.Num(); ++z)
		{
			const FCoHZoneChoice Zc = F->Zones[z];
			ZoneGrid->AddSlot(z % 3, z / 3)
			[
				HQ::Selectable(
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()[HQ::Text(Zc.Name, HQ::Bold(17), Zc.bReady ? HQ::Ink() : HQ::C(0x6f84a3))]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 2, 0, 0)[HQ::Text(Zc.bReady ? TEXT("Ready") : TEXT("After zone import"), HQ::Body(13), Zc.bReady ? HQ::C(0xffd38a) : HQ::C(0x6f84a3))],
					TAttribute<bool>::CreateLambda([this, z] { return F.IsValid() && F->HostSettings().Zone == z; }),
					FOnClicked::CreateLambda([this, z] { if (F.IsValid()) F->HostSettings().Zone = z; return FReply::Handled(); }),
					HQ::Box(HQ::Gold(.12f), HQ::Gold(), 4.f, 2.f), HQ::Box(HQ::C(0x040c1a, .5f), HQ::Sky(.2f), 4.f, 1.f), HQ::Box(HQ::Blue(.14f), HQ::Sky(.5f), 4.f, 1.f),
					FMargin(14, 12), Zc.bReady)
			];
		}

	// tell your friends
	TSharedRef<SVerticalBox> Addresses = SNew(SVerticalBox);
	const TArray<FCoHLocalAddress> Local = F.IsValid() ? F->LocalAddresses() : TArray<FCoHLocalAddress>();
	for (const FCoHLocalAddress& A : Local)
	{
		const bool bTail = A.Kind == TEXT("Tailscale");
		const FString Note = bTail ? TEXT("Tailscale: works over the internet") : A.Kind == TEXT("Home network") ? TEXT("Home network only") : TEXT("Internet: needs UDP 7777 and 7778 forwarded");
		const FString Ip = A.Ip;
		Addresses->AddSlot().AutoHeight().Padding(0, 0, 0, 8)
		[
			SNew(SBorder).BorderImage(bTail ? HQ::Box(HQ::Green(.1f), HQ::Green(.45f), 4.f, 1.f) : HQ::Box(HQ::Blue(.08f), HQ::Sky(.3f), 4.f, 1.f)).Padding(FMargin(12, 8))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()[HQ::Text(Ip, HQ::Bold(18), HQ::Ink())]
					+ SVerticalBox::Slot().AutoHeight()[HQ::Text(Note, HQ::Body(13), bTail ? HQ::C(0x8de0b2) : HQ::Muted())]
				]
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
				[
					HQ::Button(TEXT("COPY"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([Ip] { FPlatformApplicationMisc::ClipboardCopy(*Ip); return FReply::Handled(); }), true, 12.f, 36.f)
				]
			]
		];
	}
	if (Local.Num() == 0)
		Addresses->AddSlot().AutoHeight()[HQ::Text(TEXT("No network address found."), HQ::Body(15), HQ::Muted())];

	auto Launch = [this]()
	{
		if (!F.IsValid()) return FReply::Handled();
		FCoHHostSettings S = F->HostSettings();
		S.ServerName = HostName->GetText().ToString().TrimStartAndEnd();
		if (S.ServerName.IsEmpty()) S.ServerName = TEXT("My Base");
		S.Password = HostPassword->GetText().ToString();
		F->Host(S);
		return FReply::Handled();
	};

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 22)[HQ::Kicker(TEXT("LAUNCH BAY"), TEXT("Host a server for your friends"))]
		+ SVerticalBox::Slot().FillHeight(1)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(1.25f).Padding(0, 0, 28, 0)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 16)[HQ::Field(TEXT("SERVER NAME"), HostName.ToSharedRef())]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 16)
				[
					HQ::Field(TEXT("PASSWORD (OPTIONAL)"),
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot().FillWidth(1)[HostPassword.ToSharedRef()]
						+ SHorizontalBox::Slot().AutoWidth().Padding(8, 0, 0, 0)
						[
							SNew(SBox).WidthOverride(86)
							[
								HQ::ButtonT(TAttribute<FText>::CreateLambda([this] { return FText::FromString(bShowHostPassword ? TEXT("HIDE") : TEXT("SHOW")); }),
									HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { bShowHostPassword = !bShowHostPassword; return FReply::Handled(); }), true, 12.f)
							]
						])
				]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 16)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 6)
					[
						SNew(STextBlock).Font(HQ::Label(12)).ColorAndOpacity(FSlateColor(HQ::Muted()))
						.Text_Lambda([this] { return FText::FromString(FString::Printf(TEXT("MAX HEROES  ·  %d"), F.IsValid() ? F->HostSettings().MaxPlayers : 7)); })
					]
					+ SVerticalBox::Slot().AutoHeight()[Max]
				]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 12)[HQ::Field(TEXT("START ZONE"), ZoneGrid)]
				+ SVerticalBox::Slot().AutoHeight()
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 24, 0)
					[
						HQ::Check(TEXT("Show on local network"),
							TAttribute<ECheckBoxState>::CreateLambda([this] { return F.IsValid() && F->HostSettings().bShowOnLan ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }),
							FOnCheckStateChanged::CreateLambda([this](ECheckBoxState S) { if (F.IsValid()) F->HostSettings().bShowOnLan = S == ECheckBoxState::Checked; }))
					]
					+ SHorizontalBox::Slot().AutoWidth()
					[
						HQ::Check(TEXT("Remember these settings"),
							TAttribute<ECheckBoxState>::CreateLambda([this] { return F.IsValid() && F->HostSettings().bRemember ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }),
							FOnCheckStateChanged::CreateLambda([this](ECheckBoxState S) { if (F.IsValid()) F->HostSettings().bRemember = S == ECheckBoxState::Checked; }))
					]
				]
			]
			+ SHorizontalBox::Slot().FillWidth(1.f)
			[
				SNew(SBorder).BorderImage(HQ::Box(HQ::C(0x040c1a, .55f), HQ::Sky(.25f), 5.f, 1.f)).Padding(18)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()[HQ::Text(TEXT("TELL YOUR FRIENDS"), HQ::Label(12), HQ::Sky())]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 8, 0, 12)
					[
						SNew(STextBlock).Font(HQ::Body(15)).ColorAndOpacity(FSlateColor(HQ::C(0xaac4e6))).AutoWrapText(true)
						.Text(FText::FromString(TEXT("Friends add one of these under Join Friends. Game port 7777.")))
					]
					+ SVerticalBox::Slot().AutoHeight()[Addresses]
					+ SVerticalBox::Slot().FillHeight(1)
					+ SVerticalBox::Slot().AutoHeight()
					[
						SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::Dim())).AutoWrapText(true)
						.Text(FText::FromString(TEXT("You play on the server you host. When you return to HQ the server closes and your friends come back to their HQ.")))
					]
				]
			]
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 18, 0, 0)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
			[
				SNew(STextBlock).Font(HQ::Body(15)).ColorAndOpacity(FSlateColor(HQ::Muted()))
				.Text_Lambda([this] { return FText::FromString(TEXT("Playing as ") + HeroChipText().ToString() + TEXT(". Change in Hero Roster.")); })
			]
			+ SHorizontalBox::Slot().AutoWidth()
			[
				SNew(SBox).WidthOverride(300)
				[
					HQ::Button(TEXT("LAUNCH SERVER"), HQ::EBtn::Primary, FOnClicked::CreateLambda(Launch), true, 21.f, 64.f)
				]
			]
		];
}

// =================================================================== roster
TSharedRef<SWidget> SCoHLobby::MakeRosterPage()
{
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 20)[HQ::Kicker(TEXT("HERO ROSTER"), TEXT("Pick who you play"))]
		+ SVerticalBox::Slot().FillHeight(1)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()[SAssignNew(HeroGrid, SUniformGridPanel).SlotPadding(FMargin(0, 0, 16, 16)).MinDesiredSlotHeight(210)]
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 12, 0, 0)
		[
			SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::Dim())).AutoWrapText(true)
			.Text(FText::FromString(TEXT("Heroes are saved on this PC (Saved/Heroes). Whoever hosts keeps a backup copy each time you play on their server.")))
		];
}

TSharedRef<SWidget> SCoHLobby::MakeHeroCard(int32 Index)
{
	// Index -1: the starter (whatever -Hero= or the config's HeroFile gives)
	FCoHHeroCard C;
	if (Index >= 0 && F.IsValid() && F->Heroes().IsValidIndex(Index)) C = F->Heroes()[Index];
	const FString File = Index >= 0 ? C.File : FString();
	const FString Name = Index >= 0 ? C.Name : FString(TEXT("Starter hero"));
	const FString Line1 = Index >= 0 ? FString::Printf(TEXT("Level %d %s %s"), C.Level, *C.Origin, *C.ArchetypeName()) : FString(TEXT("The game's default test hero"));
	const FString Line2 = Index >= 0 ? C.SetsLine() : FString(TEXT("Good for a quick look around"));
	const FLinearColor Badge = Index >= 0 ? HQ::ArchetypeColor(C.Class) : HQ::Sky();

	return HQ::Selectable(
		SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight()
		[
			SNew(SBox).WidthOverride(64).HeightOverride(64).HAlign(HAlign_Left)
			[
				SNew(SBorder).BorderImage(HQ::Box(Badge, HQ::Clear(), 32.f, 0.f)).HAlign(HAlign_Center).VAlign(VAlign_Center)
				[
					HQ::Text(Name.Left(1).ToUpper(), HQ::Title(32), HQ::C(0x0b0b10))
				]
			]
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 12, 0, 0)[HQ::Text(Name, HQ::Bold(22), HQ::Ink())]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)[HQ::Text(Line1, HQ::Body(15), HQ::C(0xffd38a))]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)
		[
			SNew(STextBlock).Text(FText::FromString(Line2)).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::C(0x8fa6c6))).AutoWrapText(true)
		],
		TAttribute<bool>::CreateLambda([this, File] { return F.IsValid() && F->ChosenHero() == File; }),
		FOnClicked::CreateLambda([this, File] { if (F.IsValid()) F->ChooseHero(File); return FReply::Handled(); }),
		HQ::Box(HQ::C(0x3a2808, .7f), HQ::Gold(), 6.f, 2.f), HQ::Box(HQ::C(0x0a1a32, .6f), HQ::Sky(.25f), 6.f, 1.f), HQ::Box(HQ::C(0x12284a, .8f), HQ::Sky(.65f), 6.f, 1.f),
		FMargin(22));
}

// =================================================================== settings
TSharedRef<SWidget> SCoHLobby::MakeSettingsPage()
{
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 16)[HQ::Kicker(TEXT("SETTINGS"), TEXT("Graphics and city life"))]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 18)
		[
			SNew(STextBlock).Font(HQ::Body(16)).ColorAndOpacity(FSlateColor(HQ::C(0xaac4e6))).AutoWrapText(true)
			.Text(FText::FromString(TEXT("The same panel as F10 in game: quality preset, render scale, comic look, crowd and traffic density, FPS cap and VSync. Saved on this PC.")))
		]
		+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Left)
		[
			HQ::Button(TEXT("OPEN GRAPHICS SETTINGS"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { if (F.IsValid()) F->OpenGraphics(); return FReply::Handled(); }), true, 14.f, 48.f)
		];
}

// =================================================================== right column
TSharedRef<SWidget> SCoHLobby::MakeRightColumn()
{
	TSharedRef<SWidget> Ring = SNew(SCoHCanvas).Size(FVector2D(340, 340)).Painter([this](const FGeometry& G, FSlateWindowElementList& Out, int32 L, double T)
	{
		const FVector2f S = FVector2f(G.GetLocalSize());
		const FVector2f C = S * .5f;
		const float R = FMath::Min(S.X, S.Y) * .5f - 10.f;
		if (GlowBrush.GetResourceObject())
			HQ::Rect(Out, L, G, C - FVector2f(R, R) * 1.15f, FVector2f(R, R) * 2.3f, &GlowBrush, HQ::Blue(.22f));
		HQ::Arc(Out, L + 1, G, C, R, 0, TWO_PI, HQ::Sky(.35f), 1.f);
		// dashed ring, slow turn
		const float Spin = (float)FMath::Fmod(T * TWO_PI / 30.0, (double)TWO_PI);
		for (int32 i = 0; i < 48; ++i)
		{
			const float A = Spin + i * TWO_PI / 48.f;
			HQ::Arc(Out, L + 1, G, C, R * .9f, A, A + TWO_PI / 48.f * .5f, HQ::Sky(.55f), 2.f);
		}
		// scanner arc, fast the other way
		const float Back = -(float)FMath::Fmod(T * TWO_PI / 6.0, (double)TWO_PI);
		HQ::Arc(Out, L + 2, G, C, R * .77f, Back, Back + PI * .5f, HQ::Blue(), 3.f);
		HQ::Arc(Out, L + 1, G, C, R * .77f, Back + PI * .5f, Back + PI, HQ::Blue(.35f), 3.f);
		// gold ring
		const float Gs = (float)FMath::Fmod(T * TWO_PI / 9.0, (double)TWO_PI);
		HQ::Arc(Out, L + 1, G, C, R * .63f, 0, TWO_PI, HQ::Gold(.25f), 1.f);
		HQ::Arc(Out, L + 2, G, C, R * .63f, Gs, Gs + PI * .35f, HQ::Gold(), 2.f);
		// tick marks
		for (int32 i = 0; i < 12; ++i)
		{
			const float A = i * TWO_PI / 12.f;
			const FVector2f D(FMath::Cos(A), FMath::Sin(A));
			HQ::Lines(Out, L + 1, G, {C + D * (R + 2.f), C + D * (R + 10.f)}, HQ::Sky(.6f), 1.5f);
		}
	});

	auto Online = [this](int32& Servers) -> int32
	{
		int32 Heroes = 0;
		Servers = 0;
		if (!F.IsValid()) return 0;
		for (const FCoHServerEntry& E : F->Servers())
			if (E.State == FCoHServerEntry::EState::Online) { Heroes += E.Info.Players; ++Servers; }
		for (const FCoHLanServer& L : F->LanServers()) { Heroes += L.Info.Players; ++Servers; }
		return Heroes;
	};

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
		[
			SNew(SOverlay)
			+ SOverlay::Slot()[Ring]
			+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
				[
					SNew(STextBlock).Font(HQ::Title(72)).ColorAndOpacity(FSlateColor(FLinearColor::White))
					.ShadowColorAndOpacity(HQ::Blue(.9f)).ShadowOffset(FVector2D(0, 0))
					.Text_Lambda([Online] { int32 S; return FText::AsNumber(Online(S)); })
				]
				+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)[HQ::Text(TEXT("HEROES ONLINE"), HQ::Label(12), HQ::C(0x9fd0ff))]
				+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0, 4, 0, 0)
				[
					SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::C(0x8fa6c6)))
					.Text_Lambda([Online] { int32 S; Online(S); return FText::FromString(FString::Printf(TEXT("on %d server%s"), S, S == 1 ? TEXT("") : TEXT("s"))); })
				]
			]
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 18, 0, 0)
		[
			SNew(SBorder).BorderImage(HQ::Box(HQ::C(0x061020, .78f), HQ::Sky(.3f), 5.f, 1.f)).Padding(FMargin(20, 18))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 10)[HQ::Text(TEXT("HQ FEED"), HQ::Label(12), HQ::Sky())]
				+ SVerticalBox::Slot().AutoHeight()[SAssignNew(FeedRows, SVerticalBox)]
			]
		]
		+ SVerticalBox::Slot().FillHeight(1)
		+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Right)
		[
			SNew(SBox).WidthOverride(180)
			[
				HQ::Button(TEXT("EXIT GAME"), HQ::EBtn::Danger, FOnClicked::CreateLambda([this] { if (F.IsValid()) F->QuitGame(); return FReply::Handled(); }), true, 13.f, 46.f)
			]
		];
}

TSharedRef<SWidget> SCoHLobby::MakeConnecting()
{
	return SNew(SBorder)
		.Visibility_Lambda([this] { return F.IsValid() && F->IsConnecting() ? EVisibility::Visible : EVisibility::Collapsed; })
		.BorderImage(HQ::White())
		.BorderBackgroundColor(HQ::C(0x02060e, .84f))
		.HAlign(HAlign_Center).VAlign(VAlign_Center)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
			[
				SNew(SOverlay)
				+ SOverlay::Slot()[Spinner(150)]
				+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)[Emblem(1.1f)]
			]
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0, 22, 0, 0)
			[
				SNew(STextBlock).Font(HQ::Title(30)).ColorAndOpacity(FSlateColor(HQ::Ink()))
				.Text_Lambda([this] { return FText::FromString((TEXT("HEADING TO ") + (F.IsValid() ? F->ConnectingTo() : FString())).ToUpper()); })
			]
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0, 10, 0, 0)
			[
				SNew(STextBlock).Font(HQ::Body(16))
				.ColorAndOpacity_Lambda([] { return FSlateColor(HQ::Muted().CopyWithNewOpacity(Pulse(4.0))); })
				.Text(FText::FromString(TEXT("Contacting the server, sending your hero, loading the zone")))
			]
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0, 22, 0, 0)
			[
				SNew(SBox).WidthOverride(160)
				[
					HQ::Button(TEXT("CANCEL"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { if (F.IsValid()) F->CancelJoin(); return FReply::Handled(); }), true, 13.f)
				]
			]
		];
}

// =================================================================== rebuild
void SCoHLobby::Rebuild()
{
	if (!F.IsValid()) return;
	BuiltRevision = F->ServersRevision();

	if (ServerRows.IsValid())
	{
		ServerRows->ClearChildren();
		for (int32 i = 0; i < F->Servers().Num(); ++i)
			ServerRows->AddSlot().AutoHeight().Padding(0, 0, 0, 10)[MakeServerRow(i)];
		if (F->Servers().Num() == 0)
			ServerRows->AddSlot().AutoHeight().Padding(0, 10)
			[
				SNew(STextBlock).Font(HQ::Body(17)).ColorAndOpacity(FSlateColor(HQ::Muted())).AutoWrapText(true)
				.Text(FText::FromString(TEXT("No saved servers yet. Add a friend's address (their Tailscale IP or PC name), or host your own.")))
			];
	}
	if (LanRows.IsValid())
	{
		LanRows->ClearChildren();
		for (int32 i = 0; i < F->LanServers().Num(); ++i)
			LanRows->AddSlot().AutoHeight().Padding(0, 0, 0, 10)[MakeLanRow(i)];
		if (F->LanServers().Num() == 0)
			LanRows->AddSlot().AutoHeight()[HQ::Text(TEXT("Nothing hosting on this network right now."), HQ::Body(15), HQ::Dim())];
	}
	if (FeedRows.IsValid())
	{
		FeedRows->ClearChildren();
		int32 Lines = 0;
		for (const FCoHServerEntry& E : F->Servers())
		{
			if (Lines >= 5) break;
			const bool bUp = E.State == FCoHServerEntry::EState::Online;
			if (E.State == FCoHServerEntry::EState::Checking) continue;
			const FString Msg = bUp
				? FString::Printf(TEXT("%s is up in %s (%d/%d)"), *E.Name, *E.Info.Zone, E.Info.Players, E.Info.MaxPlayers)
				: FString::Printf(TEXT("%s: %s"), *E.Name, *HQ::Ago(E.LastSeen).Replace(TEXT("Last seen"), TEXT("last seen")));
			FeedRows->AddSlot().AutoHeight().Padding(0, 0, 0, 8)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 10, 0)
				[
					SNew(SBox).WidthOverride(64)[HQ::Text(bUp ? TEXT("ONLINE") : TEXT("OFFLINE"), HQ::Label(11), bUp ? HQ::Green() : HQ::Grey())]
				]
				+ SHorizontalBox::Slot().FillWidth(1)
				[
					SNew(STextBlock).Text(FText::FromString(Msg)).Font(HQ::Body(15)).ColorAndOpacity(FSlateColor(bUp ? HQ::Ink() : HQ::C(0x9fb0c8))).AutoWrapText(true)
				]
			];
			++Lines;
		}
		if (Lines == 0)
			FeedRows->AddSlot().AutoHeight()[HQ::Text(TEXT("Quiet night in Paragon City."), HQ::Body(15), HQ::Dim())];
	}
	if (HeroGrid.IsValid())
	{
		HeroGrid->ClearChildren();
		int32 Cell = 0;
		HeroGrid->AddSlot(Cell % 3, Cell / 3)[MakeHeroCard(-1)];
		++Cell;
		for (int32 i = 0; i < F->Heroes().Num(); ++i, ++Cell)
			HeroGrid->AddSlot(Cell % 3, Cell / 3)[MakeHeroCard(i)];
		HeroGrid->AddSlot(Cell % 3, Cell / 3)
		[
			HQ::Selectable(
				SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Center)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)[HQ::Text(TEXT("+"), HQ::Title(48), HQ::C(0x9fd0ff))]
					+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)[HQ::Text(TEXT("NEW HERO"), HQ::Label(15), HQ::C(0x9fd0ff))]
				],
				false,
				FOnClicked::CreateLambda([this] { OpenNewHero(); return FReply::Handled(); }),
				nullptr, HQ::Box(HQ::C(0x040c1a, .4f), HQ::Sky(.4f), 6.f, 2.f), HQ::Box(HQ::Blue(.14f), HQ::Sky(.8f), 6.f, 2.f),
				FMargin(22))
		];
	}
}

// =================================================================== dialogs
static TSharedRef<SWidget> ModalFrame(const FString& Kicker, TAttribute<FText> Title, TSharedRef<SWidget> Body, bool bGold)
{
	return SNew(SBorder)
		.BorderImage(HQ::Box(HQ::C(0x0a1426, .97f), bGold ? HQ::Gold() : HQ::Sky(.8f), 6.f, 1.5f))
		.Padding(28)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight()[HQ::Text(Kicker, HQ::Label(12), bGold ? HQ::Gold() : HQ::Sky())]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 6, 0, 18)
			[
				SNew(STextBlock).Text(Title).Font(HQ::Title(28)).ColorAndOpacity(FSlateColor(HQ::Ink())).AutoWrapText(true)
			]
			+ SVerticalBox::Slot().AutoHeight()[Body]
		];
}

static TSharedRef<SWidget> ModalButtons(TSharedRef<SWidget> Left, TSharedRef<SWidget> Right, TSharedPtr<SWidget> Extra = nullptr)
{
	TSharedRef<SHorizontalBox> Row = SNew(SHorizontalBox);
	if (Extra.IsValid()) Row->AddSlot().AutoWidth()[Extra.ToSharedRef()];
	Row->AddSlot().FillWidth(1);
	Row->AddSlot().AutoWidth().Padding(0, 0, 10, 0)[Left];
	Row->AddSlot().AutoWidth()[SNew(SBox).MinDesiredWidth(130)[Right]];
	return Row;
}

void SCoHLobby::OpenModal(TSharedRef<SWidget> Content)
{
	ModalHost->SetContent(Content);
	bModal = true;
}

void SCoHLobby::CloseModal()
{
	bModal = false;
	ModalHost->SetContent(SNullWidget::NullWidget);
	ModalHost->SetWidthOverride(560.f);
	FSlateApplication::Get().SetKeyboardFocus(SharedThis(this));
}

void SCoHLobby::OpenPassword(int32 Index, bool bLan)
{
	FString Name;
	if (bLan) { if (F.IsValid() && F->LanServers().IsValidIndex(Index)) Name = F->LanServers()[Index].Info.Name; }
	else if (const FCoHServerEntry* S = Server(Index)) Name = S->Name;

	TSharedRef<SEditableTextBox> Pw = HQ::Input(FString(), TEXT("Password"), true);
	TSharedRef<bool> Remember = MakeShared<bool>(true);
	// weak: the text box's own Enter handler holds this
	const TWeakPtr<SEditableTextBox> WeakPw = Pw;
	auto Go = [this, Index, bLan, WeakPw, Remember]()
	{
		const TSharedPtr<SEditableTextBox> Box = WeakPw.Pin();
		const FString P = Box.IsValid() ? Box->GetText().ToString() : FString();
		CloseModal();
		if (F.IsValid())
		{
			if (bLan) F->JoinLan(Index, P);
			else F->Join(Index, P, *Remember);
		}
		return FReply::Handled();
	};
	Pw->SetOnTextCommitted(FOnTextCommitted::CreateLambda([Go](const FText&, ETextCommit::Type T) { if (T == ETextCommit::OnEnter) Go(); }));

	TSharedRef<SVerticalBox> Body = SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 14)[HQ::Field(TEXT("PASSWORD"), Pw)];
	if (!bLan)
		Body->AddSlot().AutoHeight().Padding(0, 0, 0, 18)
		[
			HQ::Check(TEXT("Remember for this server"),
				TAttribute<ECheckBoxState>::CreateLambda([Remember] { return *Remember ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }),
				FOnCheckStateChanged::CreateLambda([Remember](ECheckBoxState S) { *Remember = S == ECheckBoxState::Checked; }))
		];
	Body->AddSlot().AutoHeight()
	[
		ModalButtons(
			HQ::Button(TEXT("CANCEL"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { CloseModal(); return FReply::Handled(); }), true, 13.f),
			HQ::Button(TEXT("JOIN"), HQ::EBtn::Primary, FOnClicked::CreateLambda(Go), true, 15.f))
	];
	OpenModal(ModalFrame(TEXT("SECURE BASE"), FText::FromString(Name + TEXT(" needs a password")), Body, true));
	FSlateApplication::Get().SetKeyboardFocus(Pw);
}

void SCoHLobby::OpenServerEditor(int32 Index)
{
	const FCoHServerEntry* S = Index >= 0 ? Server(Index) : nullptr;
	TSharedRef<SEditableTextBox> Name = HQ::Input(S ? S->Name : FString(), TEXT("e.g. Robert's Base"));
	TSharedRef<SEditableTextBox> Addr = HQ::Input(S ? (S->Port == CoHLobby::DefaultGamePort ? S->Host : FString::Printf(TEXT("%s:%d"), *S->Host, S->Port)) : FString(),
		TEXT("Tailscale IP or PC name, :port optional"));
	TSharedRef<SEditableTextBox> Pw = HQ::Input(S ? S->Password : FString(), TEXT("Only if the server has one"), true);
	TSharedRef<bool> Remember = MakeShared<bool>(S ? S->bRemember : true);
	TSharedRef<FString> Error = MakeShared<FString>();

	auto Save = [this, Index, Name, Addr, Pw, Remember, Error]()
	{
		if (Addr->GetText().IsEmptyOrWhitespace()) { *Error = TEXT("Enter the server's address."); return FReply::Handled(); }
		if (F.IsValid())
		{
			if (Index >= 0) F->EditServer(Index, Name->GetText().ToString(), Addr->GetText().ToString(), Pw->GetText().ToString(), *Remember);
			else F->AddServer(Name->GetText().ToString(), Addr->GetText().ToString(), Pw->GetText().ToString(), *Remember);
		}
		CloseModal();
		return FReply::Handled();
	};

	TSharedPtr<SWidget> Remove;
	if (Index >= 0)
		Remove = HQ::Button(TEXT("REMOVE"), HQ::EBtn::Danger, FOnClicked::CreateLambda([this, Index]
		{
			if (F.IsValid()) F->RemoveServer(Index);
			CloseModal();
			return FReply::Handled();
		}), true, 13.f);

	TSharedRef<SWidget> Body = SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 14)[HQ::Field(TEXT("NAME"), Name)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 14)[HQ::Field(TEXT("ADDRESS"), Addr)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 14)[HQ::Field(TEXT("PASSWORD (OPTIONAL)"), Pw)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 12)
		[
			HQ::Check(TEXT("Remember the password"),
				TAttribute<ECheckBoxState>::CreateLambda([Remember] { return *Remember ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }),
				FOnCheckStateChanged::CreateLambda([Remember](ECheckBoxState St) { *Remember = St == ECheckBoxState::Checked; }))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 12)
		[
			SNew(STextBlock).Font(HQ::Body(15)).ColorAndOpacity(FSlateColor(HQ::Red()))
			.Text_Lambda([Error] { return FText::FromString(*Error); })
		]
		+ SVerticalBox::Slot().AutoHeight()
		[
			ModalButtons(
				HQ::Button(TEXT("CANCEL"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { CloseModal(); return FReply::Handled(); }), true, 13.f),
				HQ::Button(TEXT("SAVE"), HQ::EBtn::Primary, FOnClicked::CreateLambda(Save), true, 15.f),
				Remove)
		];
	OpenModal(ModalFrame(TEXT("ALLIED BASES"), FText::FromString(Index >= 0 ? TEXT("Edit server") : TEXT("Add a friend's server")), Body, false));
	FSlateApplication::Get().SetKeyboardFocus(Index >= 0 ? Name : Addr);
}

void SCoHLobby::OpenDirectConnect()
{
	TSharedRef<SEditableTextBox> Addr = HQ::Input(FString(), TEXT("IP or PC name, :port optional"));
	TSharedRef<SEditableTextBox> Pw = HQ::Input(FString(), TEXT("Only if the server has one"), true);
	auto Go = [this, Addr, Pw]()
	{
		if (Addr->GetText().IsEmptyOrWhitespace()) return FReply::Handled();
		const FString A = Addr->GetText().ToString(), P = Pw->GetText().ToString();
		CloseModal();
		if (F.IsValid()) F->JoinAddress(A, P);
		return FReply::Handled();
	};
	TSharedRef<SWidget> Body = SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 14)[HQ::Field(TEXT("ADDRESS"), Addr)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 10)[HQ::Field(TEXT("PASSWORD (OPTIONAL)"), Pw)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 18)
		[
			HQ::Text(TEXT("The server is saved to your list, so next time you'll see if it's up."), HQ::Body(14), HQ::Dim())
		]
		+ SVerticalBox::Slot().AutoHeight()
		[
			ModalButtons(
				HQ::Button(TEXT("CANCEL"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { CloseModal(); return FReply::Handled(); }), true, 13.f),
				HQ::Button(TEXT("CONNECT"), HQ::EBtn::Primary, FOnClicked::CreateLambda(Go), true, 15.f))
		];
	OpenModal(ModalFrame(TEXT("DIRECT CONNECT"), FText::FromString(TEXT("Connect by address")), Body, false));
	FSlateApplication::Get().SetKeyboardFocus(Addr);
}

void SCoHLobby::OpenNewHero()
{
	const TArray<FString> Classes = F.IsValid() ? F->StarterClasses() : TArray<FString>();
	TSharedRef<SEditableTextBox> Name = HQ::Input(FString(), TEXT("Hero name"));
	TSharedRef<FString> Pick = MakeShared<FString>(Classes.Num() ? Classes[0] : FString());
	TSharedRef<FString> Error = MakeShared<FString>();

	TSharedRef<SUniformGridPanel> Grid = SNew(SUniformGridPanel).SlotPadding(FMargin(0, 0, 8, 8));
	for (int32 i = 0; i < Classes.Num(); ++i)
	{
		const FString Cls = Classes[i];
		FCoHHeroCard Tmp;
		Tmp.Class = Cls;
		Grid->AddSlot(i % 3, i / 3)
		[
			HQ::Selectable(
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 8, 0)
				[
					SNew(SBox).WidthOverride(12).HeightOverride(12)[SNew(SImage).Image(HQ::Box(HQ::ArchetypeColor(Cls), HQ::Clear(), 6.f, 0.f))]
				]
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[HQ::Text(Tmp.ArchetypeName(), HQ::Bold(15), HQ::Ink())],
				TAttribute<bool>::CreateLambda([Pick, Cls] { return *Pick == Cls; }),
				FOnClicked::CreateLambda([Pick, Cls] { *Pick = Cls; return FReply::Handled(); }),
				HQ::Box(HQ::Gold(.14f), HQ::Gold(), 4.f, 1.5f), HQ::Box(HQ::C(0x040c1a, .6f), HQ::Sky(.25f), 4.f, 1.f), HQ::Box(HQ::Blue(.16f), HQ::Sky(.6f), 4.f, 1.f),
				FMargin(10, 9))
		];
	}

	auto Create = [this, Name, Pick, Error]()
	{
		FString Why;
		if (!F.IsValid()) return FReply::Handled();
		if (Pick->IsEmpty()) { *Error = TEXT("No archetype starters found."); return FReply::Handled(); }
		if (F->CreateHero(Name->GetText().ToString(), *Pick, Why)) CloseModal();
		else *Error = Why;
		return FReply::Handled();
	};

	TSharedRef<SVerticalBox> Body = SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 14)[HQ::Field(TEXT("NAME"), Name)];
	if (Classes.Num())
		Body->AddSlot().AutoHeight().Padding(0, 0, 0, 10)[HQ::Field(TEXT("ARCHETYPE"), Grid)];
	else
		Body->AddSlot().AutoHeight().Padding(0, 0, 0, 10)
		[
			SNew(STextBlock).Font(HQ::Body(15)).ColorAndOpacity(FSlateColor(HQ::Muted())).AutoWrapText(true)
			.Text(FText::FromString(TEXT("No archetype starters in the rules folder yet. Make them with tools/rules/coh_build.py starters (docs/hero-build.md).")))
		];
	Body->AddSlot().AutoHeight().Padding(0, 0, 0, 8)
	[
		HQ::Text(TEXT("Starts at level 1 with the archetype's classic sets. Power picks come with leveling."), HQ::Body(14), HQ::Dim())
	];
	Body->AddSlot().AutoHeight().Padding(0, 0, 0, 12)
	[
		SNew(STextBlock).Font(HQ::Body(15)).ColorAndOpacity(FSlateColor(HQ::Red())).Text_Lambda([Error] { return FText::FromString(*Error); })
	];
	Body->AddSlot().AutoHeight()
	[
		ModalButtons(
			HQ::Button(TEXT("CANCEL"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { CloseModal(); return FReply::Handled(); }), true, 13.f),
			HQ::Button(TEXT("CREATE"), HQ::EBtn::Primary, FOnClicked::CreateLambda(Create), true, 15.f))
	];
	ModalHost->SetWidthOverride(640.f);
	OpenModal(ModalFrame(TEXT("HERO ROSTER"), FText::FromString(TEXT("New hero")), Body, true));
	FSlateApplication::Get().SetKeyboardFocus(Name);
}

// =================================================================== in-game Esc panel
TSharedRef<SWidget> SCoHLobby::MakeLeaveMenu(bool bHost, FSimpleDelegate OnHQ, FSimpleDelegate OnQuit, FSimpleDelegate OnStay)
{
	return SNew(SBorder)
		.BorderImage(HQ::White())
		.BorderBackgroundColor(HQ::C(0x02060e, .6f))
		.HAlign(HAlign_Center).VAlign(VAlign_Center)
		[
			SNew(SBox).WidthOverride(460)
			[
				Panel(
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()[HQ::Text(TEXT("PARAGON HQ"), HQ::Label(12), HQ::Sky())]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 6, 0, 10)[HQ::Text(TEXT("Leave the city?"), HQ::Title(30), HQ::Ink())]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 20)
					[
						SNew(STextBlock).Font(HQ::Body(15)).ColorAndOpacity(FSlateColor(HQ::Muted())).AutoWrapText(true)
						.Text(FText::FromString(bHost
							? TEXT("You're hosting. Going back to HQ closes the server, and everyone returns to their own HQ. Your hero is saved.")
							: TEXT("Your hero is saved on this PC. You can rejoin from Join Friends.")))
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 10)
					[
						HQ::Button(bHost ? TEXT("CLOSE SERVER AND RETURN TO HQ") : TEXT("RETURN TO HQ"), HQ::EBtn::Primary,
							FOnClicked::CreateLambda([OnHQ] { OnHQ.ExecuteIfBound(); return FReply::Handled(); }), true, 15.f, 52.f)
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 10)
					[
						HQ::Button(TEXT("KEEP PLAYING"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([OnStay] { OnStay.ExecuteIfBound(); return FReply::Handled(); }), true, 14.f, 48.f)
					]
					+ SVerticalBox::Slot().AutoHeight()
					[
						HQ::Button(TEXT("QUIT GAME"), HQ::EBtn::Danger, FOnClicked::CreateLambda([OnQuit] { OnQuit.ExecuteIfBound(); return FReply::Handled(); }), true, 13.f, 44.f)
					],
					FMargin(30, 26))
			]
		];
}

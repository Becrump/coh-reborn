#include "SCoHTerminal.h"

#include "CoHHQStyle.h"
#include "CoHHeroCharacter.h"
#include "CoHHeroProgress.h"
#include "CoHHeroStage.h"
#include "CoHPowers.h"

namespace
{
	/** "Blaster_Ranged.Fire_Blast" -> "Fire Blast" */
	FString PrettySet(const FString& Id)
	{
		FString S = Id;
		int32 Dot;
		if (S.FindLastChar(TEXT('.'), Dot)) S = S.Mid(Dot + 1);
		return S.Replace(TEXT("_"), TEXT(" "));
	}

	const TCHAR* EmitterNames[] = {TEXT("RIGHT HAND"), TEXT("LEFT HAND"), TEXT("BOTH HANDS"), TEXT("EYES"), TEXT("CHEST"),
		TEXT("MOUTH"), TEXT("FEET"), TEXT("BACK"), TEXT("OVERHEAD")};

	struct FSwatch { const TCHAR* Name; uint32 Hex; };
	const FSwatch Swatches[] = {{TEXT("Default"), 0}, {TEXT("Classic fire"), 0xff7a1a}, {TEXT("Blue flame"), 0x3fa9ff},
		{TEXT("Hellfire green"), 0x53e07a}, {TEXT("Violet"), 0xb05cff}, {TEXT("White hot"), 0xfff4d6}, {TEXT("Crimson"), 0xe0233a},
		{TEXT("Gold"), 0xffc22e}};
}

// =================================================================== drag to turn
/** The open middle of the terminal: drag to turn the hero, double-click to face front. */
class SCoHDragTurn : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHDragTurn) {}
		SLATE_ARGUMENT(UCoHFrontend*, Frontend)
	SLATE_END_ARGS()

	void Construct(const FArguments& A) { F = A._Frontend; }
	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(1, 1); }
	virtual int32 OnPaint(const FPaintArgs&, const FGeometry&, const FSlateRect&, FSlateWindowElementList&, int32 Layer, const FWidgetStyle&, bool) const override
	{
		return Layer;
	}
	virtual FReply OnMouseButtonDown(const FGeometry&, const FPointerEvent& E) override
	{
		if (E.GetEffectingButton() != EKeys::LeftMouseButton) return FReply::Unhandled();
		return FReply::Handled().CaptureMouse(SharedThis(this));
	}
	virtual FReply OnMouseButtonUp(const FGeometry&, const FPointerEvent&) override
	{
		return HasMouseCapture() ? FReply::Handled().ReleaseMouseCapture() : FReply::Unhandled();
	}
	virtual FReply OnMouseMove(const FGeometry&, const FPointerEvent& E) override
	{
		if (!HasMouseCapture()) return FReply::Unhandled();
		// drag right: the hero's front follows the mouse to screen right
		if (ACoHHeroStage* S = F.IsValid() ? F->Stage() : nullptr) S->Turn(-E.GetCursorDelta().X * .45f);
		return FReply::Handled();
	}
	virtual FReply OnMouseButtonDoubleClick(const FGeometry&, const FPointerEvent&) override
	{
		if (ACoHHeroStage* S = F.IsValid() ? F->Stage() : nullptr) S->ResetTurn();
		return FReply::Handled();
	}
	virtual FCursorReply OnCursorQuery(const FGeometry&, const FPointerEvent&) const override
	{
		return FCursorReply::Cursor(EMouseCursor::GrabHand);
	}

private:
	TWeakObjectPtr<UCoHFrontend> F;
};

// =================================================================== construct
void SCoHTerminal::Construct(const FArguments& InArgs)
{
	F = InArgs._Frontend;
	OnCall = InArgs._OnCall;
	OnNewHero = InArgs._OnNewHero;

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot().VAlign(VAlign_Top)[MakeTopBar()]
		+ SOverlay::Slot().Padding(40, 108, 40, 72)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().AutoWidth()[SNew(SBox).WidthOverride(400)[MakeRoster()]]
			+ SHorizontalBox::Slot().FillWidth(1)[MakeCenter()]
			+ SHorizontalBox::Slot().AutoWidth()[SNew(SBox).WidthOverride(580)[MakeFile()]]
		]
	];
	Rebuild();
}

ACoHHeroCharacter* SCoHTerminal::Hero() const
{
	return F.IsValid() ? F->StageHero() : nullptr;
}

FString SCoHTerminal::HeroName() const
{
	const ACoHHeroCharacter* H = Hero();
	if (H && H->Progress && H->Progress->bHasRecord) return H->Progress->Hero.Name;
	const FCoHHeroCard* C = F.IsValid() ? F->ChosenHeroCard() : nullptr;
	return C ? C->Name : FString(TEXT("Starter hero"));
}

void SCoHTerminal::Tick(const FGeometry& Geometry, const double CurrentTime, const float DeltaTime)
{
	SCompoundWidget::Tick(Geometry, CurrentTime, DeltaTime);
	if (!F.IsValid()) return;
	if (F->ServersRevision() != BuiltRevision || BuiltHero.Get() != Hero()) Rebuild();
}

// =================================================================== top bar
TSharedRef<SWidget> SCoHTerminal::MakeTopBar()
{
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
						+ SVerticalBox::Slot().AutoHeight()[HQ::Text(TEXT("HERO CORPS TERMINAL"), HQ::Title(28), HQ::Ink())]
						+ SVerticalBox::Slot().AutoHeight().Padding(0, 2, 0, 0)
						[
							HQ::Text(TEXT("FREEDOM CORPS NETWORK  ·  PARAGON CITY  ·  SECURE LINK"), HQ::Label(11), HQ::Sky())
						]
					]
					+ SHorizontalBox::Slot().FillWidth(1)
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 24, 0)
					[
						SNew(STextBlock).Font(HQ::Label(13))
						.ColorAndOpacity_Lambda([this]
						{
							int32 N = 0;
							if (F.IsValid()) for (const FCoHServerEntry& E : F->Servers()) N += E.State == FCoHServerEntry::EState::Online;
							return FSlateColor(N > 0 ? HQ::Green() : HQ::Dim());
						})
						.Text_Lambda([this]
						{
							int32 N = 0;
							if (F.IsValid()) for (const FCoHServerEntry& E : F->Servers()) N += E.State == FCoHServerEntry::EState::Online;
							return FText::FromString(N == 1 ? FString(TEXT("●  1 ALLIED SERVER ONLINE")) : FString::Printf(TEXT("●  %d ALLIED SERVERS ONLINE"), N));
						})
					]
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 10, 0)
					[
						HQ::Button(TEXT("SETTINGS"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { if (F.IsValid()) F->OpenGraphics(); return FReply::Handled(); }), true, 13.f, 40.f)
					]
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
					[
						HQ::Button(TEXT("EXIT"), HQ::EBtn::Danger, FOnClicked::CreateLambda([this] { if (F.IsValid()) F->QuitGame(); return FReply::Handled(); }), true, 13.f, 40.f)
					]
				]
			]
		]
		+ SVerticalBox::Slot().AutoHeight()
		[
			SNew(SBox).HeightOverride(1)[SNew(SImage).Image(HQ::White()).ColorAndOpacity(FSlateColor(HQ::Sky(.28f)))]
		];
}

// =================================================================== roster (left)
TSharedRef<SWidget> SCoHTerminal::MakeRoster()
{
	return Panel(
		SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 14)[HQ::Text(TEXT("YOUR HEROES"), HQ::Label(13), HQ::Sky())]
		+ SVerticalBox::Slot().FillHeight(1)
		[
			SNew(SScrollBox) + SScrollBox::Slot()[SAssignNew(RosterRows, SVerticalBox)]
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 14, 0, 0)
		[
			HQ::Button(TEXT("+  RECRUIT NEW HERO"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this] { OnNewHero.ExecuteIfBound(); return FReply::Handled(); }))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 12, 0, 0)
		[
			SNew(STextBlock).Font(HQ::Body(13)).ColorAndOpacity(FSlateColor(HQ::Dim())).AutoWrapText(true)
			.Text(FText::FromString(TEXT("Heroes live on this PC. Changes made here go to the host the next time you join a server.")))
		],
		FMargin(22, 22));
}

// =================================================================== center: the hero on the pedestal
TSharedRef<SWidget> SCoHTerminal::MakeCenter()
{
	return SNew(SOverlay)
		+ SOverlay::Slot()[SNew(SCoHDragTurn).Frontend(F.Get())]
		+ SOverlay::Slot().VAlign(VAlign_Top).HAlign(HAlign_Center).Padding(0, 6, 0, 0)
		[
			SNew(STextBlock).Visibility(EVisibility::HitTestInvisible).Font(HQ::Label(11)).ColorAndOpacity(FSlateColor(HQ::Sky(.7f)))
			.Text(FText::FromString(TEXT("DRAG TO TURN  ·  DOUBLE-CLICK TO FACE FRONT")))
		]
		+ SOverlay::Slot().VAlign(VAlign_Bottom).HAlign(HAlign_Center).Padding(0, 0, 0, 10)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
			[
				SNew(STextBlock).Visibility(EVisibility::HitTestInvisible).Font(HQ::Title(46)).ColorAndOpacity(FSlateColor(HQ::Ink()))
				.ShadowOffset(FVector2D(0, 2)).ShadowColorAndOpacity(HQ::Night(.9f))
				.Text_Lambda([this] { return FText::FromString(HeroName().ToUpper()); })
			]
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0, 2, 0, 16)
			[
				SNew(STextBlock).Visibility(EVisibility::HitTestInvisible).Font(HQ::Label(13)).ColorAndOpacity(FSlateColor(HQ::C(0xffd38a)))
				.ShadowOffset(FVector2D(0, 1)).ShadowColorAndOpacity(HQ::Night(.9f))
				.Text_Lambda([this]
				{
					const ACoHHeroCharacter* H = Hero();
					if (!H || !H->Progress || !H->Progress->bHasRecord) return FText::FromString(TEXT("HERO FILE NOT LOADED"));
					const FCoHHeroRecord& R = H->Progress->Hero;
					FCoHHeroCard C; C.Class = R.Class;
					FString Line = FString::Printf(TEXT("LEVEL %d  %s"), R.Level, *C.ArchetypeName().ToUpper());
					if (!R.Origin.IsEmpty()) Line += TEXT("  ·  ") + R.Origin.ToUpper();
					return FText::FromString(Line);
				})
			]
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
			[
				SNew(SBox).MinDesiredWidth(360)
				[
					HQ::ButtonT(TAttribute<FText>::CreateLambda([this] { return FText::FromString(TEXT("CALL ") + HeroName().ToUpper()); }),
						HQ::EBtn::Primary, FOnClicked::CreateLambda([this]
						{
							// unsaved power looks go with the hero
							if (bLooksChanged && F.IsValid()) { F->SaveStageLooks(); bLooksChanged = false; }
							OnCall.ExecuteIfBound();
							return FReply::Handled();
						}), true, 20.f, 60.f)
				]
			]
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0, 8, 0, 0)
			[
				SNew(STextBlock).Visibility(EVisibility::HitTestInvisible).Font(HQ::Body(13)).ColorAndOpacity(FSlateColor(HQ::Muted()))
				.Text(FText::FromString(TEXT("Then join a friend's server or host your own")))
			]
		];
}

// =================================================================== hero file (right)
TSharedRef<SWidget> SCoHTerminal::MakeFile()
{
	TSharedRef<SHorizontalBox> Tabs = SNew(SHorizontalBox);
	const TCHAR* Names[] = {TEXT("PROFILE"), TEXT("POWERS"), TEXT("NEMESIS FILE"), TEXT("DATABASE")};
	for (int32 i = 0; i < 4; ++i)
	{
		const EPage Me = (EPage)i;
		Tabs->AddSlot().AutoWidth().Padding(0, 0, 4, 0)
		[
			HQ::Selectable(
				SNew(STextBlock).Text(FText::FromString(Names[i])).Font(HQ::Label(12))
				.ColorAndOpacity_Lambda([this, Me] { return FSlateColor(Page == Me ? FLinearColor::White : HQ::Muted()); }),
				TAttribute<bool>::CreateLambda([this, Me] { return Page == Me; }),
				FOnClicked::CreateLambda([this, Me] { Page = Me; return FReply::Handled(); }),
				HQ::Box(HQ::Blue(.38f), HQ::Blue(), 4.f, 1.f), HQ::Box(HQ::Clear(), HQ::Clear(), 4.f, 0.f), HQ::Box(HQ::Blue(.14f), HQ::Sky(.3f), 4.f, 1.f),
				FMargin(14, 10))
		];
	}

	return Panel(
		SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 18)[Tabs]
		+ SVerticalBox::Slot().FillHeight(1)
		[
			SNew(SWidgetSwitcher)
			.WidgetIndex_Lambda([this] { return (int32)Page; })
			+ SWidgetSwitcher::Slot()[MakeProfile()]
			+ SWidgetSwitcher::Slot()[MakePowers()]
			+ SWidgetSwitcher::Slot()[SNew(SScrollBox) + SScrollBox::Slot()[SAssignNew(NemesisBox, SVerticalBox)]]
			+ SWidgetSwitcher::Slot()[SNew(SScrollBox) + SScrollBox::Slot()[SAssignNew(DatabaseBox, SVerticalBox)]]
		],
		FMargin(26, 22));
}

// ---- profile
TSharedRef<SWidget> SCoHTerminal::MakeProfile()
{
	auto Stat = [this](const FString& Name, TFunction<FString(const ACoHHeroCharacter&)> Value)
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(1)[HQ::Text(Name, HQ::Body(16), HQ::Muted())]
			+ SHorizontalBox::Slot().AutoWidth()
			[
				SNew(STextBlock).Font(HQ::Bold(16)).ColorAndOpacity(FSlateColor(HQ::Ink()))
				.Text_Lambda([this, Value] { const ACoHHeroCharacter* H = Hero(); return FText::FromString(H && H->Powers ? Value(*H) : FString(TEXT("-"))); })
			];
	};

	TSharedRef<SWidget> XPBar = SNew(SCoHCanvas).Size(FVector2D(100, 10)).Painter([this](const FGeometry& G, FSlateWindowElementList& Out, int32 L, double)
	{
		const FVector2f S = FVector2f(G.GetLocalSize());
		HQ::Rect(Out, L, G, FVector2f::ZeroVector, S, HQ::Box(HQ::C(0x0a1830, .9f), HQ::Sky(.3f), 5.f, 1.f), FLinearColor::White);
		const ACoHHeroCharacter* H = Hero();
		if (!H || !H->Progress || !H->Progress->bHasRecord) return;
		int32 Into = 0, Span = 1;
		H->Progress->XPBar(Into, Span);
		const float T = Span > 0 ? FMath::Clamp((float)Into / Span, 0.f, 1.f) : 1.f;
		if (T > 0.f) HQ::Rect(Out, L + 1, G, FVector2f::ZeroVector, FVector2f(S.X * T, S.Y), HQ::Box(HQ::Gold(), HQ::Clear(), 5.f, 0.f), FLinearColor::White);
	});

	return SNew(SScrollBox)
		+ SScrollBox::Slot()
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight()
			[
				SNew(STextBlock).Font(HQ::Title(34)).ColorAndOpacity(FSlateColor(HQ::Ink()))
				.Text_Lambda([this] { return FText::FromString(HeroName()); })
			]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)
			[
				SNew(STextBlock).Font(HQ::Body(16)).ColorAndOpacity(FSlateColor(HQ::Sky()))
				.Text_Lambda([this]
				{
					const ACoHHeroCharacter* H = Hero();
					if (!H || !H->Progress || !H->Progress->bHasRecord) return FText::GetEmpty();
					FCoHHeroCard C; C.Primary = H->Progress->Hero.Primary; C.Secondary = H->Progress->Hero.Secondary;
					return FText::FromString(C.SetsLine());
				})
			]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 22, 0, 8)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().FillWidth(1)[HQ::Text(TEXT("EXPERIENCE"), HQ::Label(12), HQ::Muted())]
				+ SHorizontalBox::Slot().AutoWidth()
				[
					SNew(STextBlock).Font(HQ::Label(12)).ColorAndOpacity(FSlateColor(HQ::Gold()))
					.Text_Lambda([this]
					{
						const ACoHHeroCharacter* H = Hero();
						if (!H || !H->Progress || !H->Progress->bHasRecord) return FText::GetEmpty();
						int32 Into = 0, Span = 0;
						H->Progress->XPBar(Into, Span);
						return FText::FromString(FString::Printf(TEXT("%d / %d TO LEVEL %d"), Into, Span, H->Progress->Hero.Level + 1));
					})
				]
			]
			+ SVerticalBox::Slot().AutoHeight()[XPBar]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 8, 0, 0)
			[
				SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::Muted()))
				.Text_Lambda([this]
				{
					const ACoHHeroCharacter* H = Hero();
					if (!H || !H->Progress || !H->Progress->bHasRecord) return FText::GetEmpty();
					const int32 Open = H->Progress->PicksOpen();
					FString S = Open > 0 ? FString::Printf(TEXT("%d power pick%s waiting: choose in game with P"), Open, Open == 1 ? TEXT("") : TEXT("s")) : FString(TEXT("No power picks waiting"));
					if (H->Progress->CanTrain()) S += TEXT("  ·  Ready to train (L in game)");
					return FText::FromString(S);
				})
			]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 26, 0, 10)[HQ::Text(TEXT("ATTRIBUTES"), HQ::Label(12), HQ::Sky())]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)[Stat(TEXT("Health"), [](const ACoHHeroCharacter& H) { return FString::Printf(TEXT("%.0f"), H.Powers->MaxHealth); })]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)[Stat(TEXT("Endurance"), [](const ACoHHeroCharacter& H) { return FString::Printf(TEXT("%.0f"), H.Powers->MaxEndurance); })]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)[Stat(TEXT("Regeneration"), [](const ACoHHeroCharacter& H) { return FString::Printf(TEXT("%.1f HP / s"), H.Powers->RegenPerSecond()); })]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)[Stat(TEXT("Recovery"), [](const ACoHHeroCharacter& H) { return FString::Printf(TEXT("%.1f End / s"), H.Powers->RecoveryPerSecond()); })]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)[Stat(TEXT("Influence"), [](const ACoHHeroCharacter& H) { return H.Progress ? FString::FormatAsNumber(H.Progress->Hero.Influence) : FString(); })]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)[Stat(TEXT("Debt"), [](const ACoHHeroCharacter& H) { return H.Progress ? FString::FormatAsNumber(H.Progress->Hero.Debt) : FString(); })]
		];
}

// ---- powers
const FSlateBrush* SCoHTerminal::PowerIcon(FName Power)
{
	if (const TSharedPtr<FSlateBrush>* Hit = IconBrushes.Find(Power)) return Hit->Get();
	TSharedPtr<FSlateBrush> B;
	UCoHPowerDatabase* DB = F.IsValid() ? UCoHPowerDatabase::Get(F.Get()) : nullptr;
	const FCoHPowerDef* P = DB ? DB->FindPower(Power) : nullptr;
	if (UTexture2D* T = P && !P->Icon.IsEmpty() ? DB->Icon(P->Icon) : nullptr)
	{
		B = MakeShared<FSlateBrush>();
		B->SetResourceObject(T);
		B->ImageSize = FVector2D(40, 40);
	}
	IconBrushes.Add(Power, B);
	return B.Get();
}

void SCoHTerminal::SetEmitter(int32 Emitter)
{
	ACoHHeroCharacter* H = Hero();
	if (!H || !H->Powers || SelectedPower.IsNone()) return;
	FCoHPowerStyle& S = H->Powers->Styles.FindOrAdd(SelectedPower);
	S.Emitter = (ECoHEmitter)FMath::Clamp(Emitter, 0, 8);
	S.bCustomEmitter = true;
	bLooksChanged = true;
	if (ACoHHeroStage* St = F->Stage()) St->PlayPower(SelectedPower);
}

void SCoHTerminal::SetTint(const FLinearColor& Tint)
{
	ACoHHeroCharacter* H = Hero();
	if (!H || !H->Powers || SelectedPower.IsNone()) return;
	H->Powers->Styles.FindOrAdd(SelectedPower).Tint = Tint;
	bLooksChanged = true;
	if (ACoHHeroStage* St = F->Stage()) St->PlayPower(SelectedPower);
}

TSharedRef<SWidget> SCoHTerminal::MakePowers()
{
	auto Def = [this]() -> const FCoHPowerDef*
	{
		UCoHPowerDatabase* DB = F.IsValid() ? UCoHPowerDatabase::Get(F.Get()) : nullptr;
		return DB && !SelectedPower.IsNone() ? DB->FindPower(SelectedPower) : nullptr;
	};

	TSharedRef<SUniformGridPanel> Deliveries = SNew(SUniformGridPanel).SlotPadding(FMargin(3));
	for (int32 i = 0; i < 9; ++i)
	{
		Deliveries->AddSlot(i % 3, i / 3)
		[
			HQ::Selectable(
				SNew(SBox).HAlign(HAlign_Center)[HQ::Text(EmitterNames[i], HQ::Label(11), HQ::C(0xcfe6ff))],
				TAttribute<bool>::CreateLambda([this, i]
				{
					const ACoHHeroCharacter* H = Hero();
					const FCoHPowerStyle* S = H && H->Powers ? H->Powers->Styles.Find(SelectedPower) : nullptr;
					return S && S->bCustomEmitter && (int32)S->Emitter == i;
				}),
				FOnClicked::CreateLambda([this, i] { SetEmitter(i); return FReply::Handled(); }),
				HQ::Box(HQ::Blue(.38f), HQ::Blue(), 4.f, 1.f), HQ::Box(HQ::C(0x0a1426, .6f), HQ::Sky(.2f), 4.f, 1.f), HQ::Box(HQ::Blue(.16f), HQ::Sky(.5f), 4.f, 1.f),
				FMargin(6, 9))
		];
	}

	TSharedRef<SHorizontalBox> Colors = SNew(SHorizontalBox);
	for (const FSwatch& W : Swatches)
	{
		const FLinearColor Tint = W.Hex ? HQ::C(W.Hex) : FLinearColor(0, 0, 0, 0);
		const FLinearColor Shown = W.Hex ? HQ::C(W.Hex) : HQ::C(0x22324a);
		Colors->AddSlot().AutoWidth().Padding(0, 0, 8, 0)
		[
			SNew(SBox).WidthOverride(40).HeightOverride(40).ToolTipText(FText::FromString(W.Name))
			[
				HQ::Selectable(
					SNew(SBorder).BorderImage(HQ::Box(Shown, HQ::Clear(), 14.f, 0.f)).Padding(0)
					[
						SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Center)[HQ::Text(W.Hex ? TEXT("") : TEXT("–"), HQ::Bold(14), HQ::Muted())]
					],
					TAttribute<bool>::CreateLambda([this, Tint]
					{
						const ACoHHeroCharacter* H = Hero();
						const FCoHPowerStyle* S = H && H->Powers ? H->Powers->Styles.Find(SelectedPower) : nullptr;
						return S ? S->Tint.Equals(Tint, .01f) : Tint.A <= 0.f;
					}),
					FOnClicked::CreateLambda([this, Tint] { SetTint(Tint); return FReply::Handled(); }),
					HQ::Box(HQ::Clear(), FLinearColor::White, 20.f, 2.5f), HQ::Box(HQ::Clear(), HQ::Clear(), 20.f, 0.f), HQ::Box(HQ::Clear(), HQ::Sky(.6f), 20.f, 1.5f),
					FMargin(3))
			]
		];
	}

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().FillHeight(.42f)
		[
			SNew(SScrollBox) + SScrollBox::Slot()[SAssignNew(PowerRows, SVerticalBox)]
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 14, 0, 0)
		[
			SNew(SBox).HeightOverride(1)[SNew(SImage).Image(HQ::White()).ColorAndOpacity(FSlateColor(HQ::Sky(.2f)))]
		]
		+ SVerticalBox::Slot().FillHeight(.58f).Padding(0, 14, 0, 0)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
					[
						SNew(STextBlock).Font(HQ::Title(26)).ColorAndOpacity(FSlateColor(HQ::Ink()))
						.Text_Lambda([Def] { const FCoHPowerDef* P = Def(); return FText::FromString(P ? P->Display : FString(TEXT("Pick a power"))); })
					]
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
					[
						HQ::Button(TEXT("PLAY ON HERO"), HQ::EBtn::Primary, FOnClicked::CreateLambda([this]
						{
							if (ACoHHeroStage* St = F.IsValid() ? F->Stage() : nullptr) St->PlayPower(SelectedPower);
							return FReply::Handled();
						}), TAttribute<bool>::CreateLambda([this] { return !SelectedPower.IsNone() && Hero() != nullptr; }), 13.f, 40.f)
					]
				]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 6, 0, 0)
				[
					SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::Muted())).AutoWrapText(true)
					.Text_Lambda([Def] { const FCoHPowerDef* P = Def(); return FText::FromString(P ? (P->Help.IsEmpty() ? P->Short : P->Help) : FString()); })
				]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 16, 0, 8)[HQ::Text(TEXT("DELIVERY (WHERE IT COMES FROM)"), HQ::Label(12), HQ::Sky())]
				+ SVerticalBox::Slot().AutoHeight()[Deliveries]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 16, 0, 8)[HQ::Text(TEXT("ELEMENT COLOR"), HQ::Label(12), HQ::Sky())]
				+ SVerticalBox::Slot().AutoHeight()[Colors]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 18, 0, 0)
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().AutoWidth()
					[
						HQ::Button(TEXT("SAVE TO HERO FILE"), HQ::EBtn::Secondary, FOnClicked::CreateLambda([this]
						{
							if (F.IsValid()) F->SaveStageLooks();
							bLooksChanged = false;
							return FReply::Handled();
						}), TAttribute<bool>::CreateLambda([this] { return bLooksChanged; }), 13.f, 40.f)
					]
					+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center).Padding(14, 0, 0, 0)
					[
						SNew(STextBlock).Font(HQ::Body(13)).ColorAndOpacity(FSlateColor(HQ::Dim())).AutoWrapText(true)
						.Text_Lambda([this] { return FText::FromString(bLooksChanged ? TEXT("Unsaved changes (Call also saves them)") : TEXT("Looks save to this PC")); })
					]
				]
			]
		];
}

void SCoHTerminal::RebuildPowers()
{
	if (!PowerRows.IsValid()) return;
	PowerRows->ClearChildren();
	const ACoHHeroCharacter* H = Hero();
	UCoHPowerDatabase* DB = F.IsValid() ? UCoHPowerDatabase::Get(F.Get()) : nullptr;
	if (!H || !H->Progress || !H->Progress->bHasRecord || !DB)
	{
		PowerRows->AddSlot().AutoHeight()[SNew(STextBlock).Font(HQ::Body(15)).ColorAndOpacity(FSlateColor(HQ::Muted())).AutoWrapText(true)
			.Text(FText::FromString(TEXT("The hero's powers show once the hero file and the game rules are loaded.")))];
		return;
	}
	// the powers the hero picked, in pick order
	TArray<FName> List;
	for (const FCoHHeroPick& P : H->Progress->Hero.Picks) if (DB->FindPower(P.Power)) List.AddUnique(P.Power);
	if (!List.Contains(SelectedPower)) SelectedPower = List.Num() ? List[0] : NAME_None;
	for (const FName& Id : List)
	{
		const FCoHPowerDef* P = DB->FindPower(Id);
		const FSlateBrush* Icon = PowerIcon(Id);
		PowerRows->AddSlot().AutoHeight().Padding(0, 0, 0, 4)
		[
			HQ::Selectable(
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 12, 0)
				[
					SNew(SBox).WidthOverride(34).HeightOverride(34)
					[
						Icon ? StaticCastSharedRef<SWidget>(SNew(SImage).Image(Icon))
							: StaticCastSharedRef<SWidget>(SNew(SBorder).BorderImage(HQ::Box(HQ::Blue(.25f), HQ::Sky(.4f), 17.f, 1.f)))
					]
				]
				+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[HQ::Text(P->Display, HQ::Bold(16), HQ::Ink())]
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[HQ::Text(PrettySet(P->SetId), HQ::Body(13), HQ::Dim())],
				TAttribute<bool>::CreateLambda([this, Id] { return SelectedPower == Id; }),
				FOnClicked::CreateLambda([this, Id]
				{
					SelectedPower = Id;
					if (ACoHHeroStage* St = F.IsValid() ? F->Stage() : nullptr) St->PlayPower(Id);
					return FReply::Handled();
				}),
				HQ::Box(HQ::Blue(.3f), HQ::Blue(), 4.f, 1.f), HQ::Box(HQ::C(0x0a1426, .5f), HQ::Clear(), 4.f, 0.f), HQ::Box(HQ::Blue(.14f), HQ::Sky(.35f), 4.f, 1.f),
				FMargin(10, 6))
		];
	}
}

// ---- nemesis file
void SCoHTerminal::RebuildNemesis()
{
	if (!NemesisBox.IsValid() || !F.IsValid()) return;
	NemesisBox->ClearChildren();
	const FString File = F->ChosenHero().IsEmpty() ? FString() : F->ChosenHero();
	const TArray<FCoHRivalCard> Rivals = F->Rivals(File);
	if (Rivals.Num() == 0)
	{
		NemesisBox->AddSlot().AutoHeight()[HQ::Text(TEXT("NEMESIS FILE"), HQ::Label(12), HQ::Sky())];
		NemesisBox->AddSlot().AutoHeight().Padding(0, 10, 0, 0)[HQ::Text(TEXT("No rivals on file"), HQ::Title(28), HQ::Ink())];
		NemesisBox->AddSlot().AutoHeight().Padding(0, 10, 0, 0)
		[
			SNew(STextBlock).Font(HQ::Body(15)).ColorAndOpacity(FSlateColor(HQ::Muted())).AutoWrapText(true)
			.Text(FText::FromString(TEXT("When a villain beats you, gets away, or holds a grudge, Freedom Corps opens a file on them here. "
				"Rivals climb from Marked to Supervillain until a hero ends their story.")))
		];
		return;
	}

	const FCoHRivalCard& N = Rivals[0];
	TSharedRef<SHorizontalBox> Track = SNew(SHorizontalBox);
	for (int32 s = 0; s <= 5; ++s)
	{
		const bool bReached = s <= N.Stage;
		Track->AddSlot().FillWidth(1).Padding(0, 0, s < 5 ? 4 : 0, 0)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight()
			[
				SNew(SBox).HeightOverride(6)[SNew(SBorder).BorderImage(HQ::Box(bReached ? HQ::Red() : HQ::C(0x1a2840), HQ::Clear(), 3.f, 0.f))]
			]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 6, 0, 0)
			[
				SNew(STextBlock).Font(HQ::Label(9)).ColorAndOpacity(FSlateColor(s == N.Stage ? HQ::Red() : HQ::Dim())).AutoWrapText(true)
				.Text(FText::FromString(FCoHRivalCard::StageName(s).ToUpper()))
			]
		];
	}

	FString Sub = N.Faction;
	if (!N.Rank.IsEmpty()) Sub += TEXT("  ·  ") + N.Rank;
	Sub += FString::Printf(TEXT("  ·  Level %d"), N.Level);
	NemesisBox->AddSlot().AutoHeight()[HQ::Text(N.bNemesis ? TEXT("NEMESIS FILE") : TEXT("RIVAL FILE"), HQ::Label(12), HQ::Red())];
	NemesisBox->AddSlot().AutoHeight().Padding(0, 8, 0, 0)[HQ::Text(N.Name, HQ::Title(36), HQ::Ink())];
	NemesisBox->AddSlot().AutoHeight().Padding(0, 2, 0, 0)[HQ::Text(Sub, HQ::Body(15), HQ::Muted())];
	NemesisBox->AddSlot().AutoHeight().Padding(0, 20, 0, 8)[HQ::Text(TEXT("RISE TO POWER"), HQ::Label(12), HQ::Sky())];
	NemesisBox->AddSlot().AutoHeight()[Track];
	NemesisBox->AddSlot().AutoHeight().Padding(0, 18, 0, 0)
	[
		HQ::Text(FString::Printf(TEXT("Grudge %d / 10   ·   %d arrest%s   ·   %s"), N.Grudge, N.Arrests, N.Arrests == 1 ? TEXT("") : TEXT("s"),
			N.Status.IsEmpty() ? TEXT("at large") : *N.Status), HQ::Bold(15), HQ::Ink())
	];
	if (N.History.Num())
	{
		NemesisBox->AddSlot().AutoHeight().Padding(0, 20, 0, 8)[HQ::Text(TEXT("ENCOUNTERS"), HQ::Label(12), HQ::Sky())];
		for (int32 i = 0; i < FMath::Min(8, N.History.Num()); ++i)
			NemesisBox->AddSlot().AutoHeight().Padding(0, 2)[HQ::Text(N.History[i], HQ::Body(14), HQ::Muted())];
	}
	if (Rivals.Num() > 1)
	{
		FString Others;
		for (int32 i = 1; i < Rivals.Num(); ++i)
			Others += (i > 1 ? TEXT(", ") : TEXT("")) + FString::Printf(TEXT("%s (%s, %s)"), *Rivals[i].Name, *Rivals[i].Faction, *FCoHRivalCard::StageName(Rivals[i].Stage));
		NemesisBox->AddSlot().AutoHeight().Padding(0, 20, 0, 0)
		[
			SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::C(0xffb0b0))).AutoWrapText(true)
			.Text(FText::FromString(TEXT("Also watching you: ") + Others))
		];
	}
}

// ---- database
void SCoHTerminal::RebuildDatabase()
{
	if (!DatabaseBox.IsValid() || !F.IsValid()) return;
	DatabaseBox->ClearChildren();
	FString Category;
	for (const FCoHDatabaseEntry& E : F->Database)
	{
		if (E.Category != Category)
		{
			Category = E.Category;
			DatabaseBox->AddSlot().AutoHeight().Padding(0, DatabaseBox->NumSlots() ? 18 : 0, 0, 8)[HQ::Text(Category.ToUpper(), HQ::Label(12), HQ::Sky())];
		}
		DatabaseBox->AddSlot().AutoHeight().Padding(0, 0, 0, 8)
		[
			SNew(SBorder).BorderImage(HQ::Box(HQ::C(0x0a1426, .6f), HQ::Sky(.18f), 4.f, 1.f)).Padding(FMargin(14, 10))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()[HQ::Text(E.Title, HQ::Bold(16), HQ::Ink())]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)
				[
					SNew(STextBlock).Font(HQ::Body(14)).ColorAndOpacity(FSlateColor(HQ::Muted())).AutoWrapText(true).Text(FText::FromString(E.Body))
				]
			]
		];
	}
	if (F->Database.Num() == 0)
		DatabaseBox->AddSlot().AutoHeight()[HQ::Text(TEXT("No entries (DefaultGame.ini, CoHFrontend Database)"), HQ::Body(15), HQ::Muted())];
}

// =================================================================== rebuild
void SCoHTerminal::Rebuild()
{
	if (!F.IsValid()) return;
	BuiltRevision = F->ServersRevision();
	BuiltHero = Hero();

	if (RosterRows.IsValid())
	{
		RosterRows->ClearChildren();
		auto Row = [this](const FString& File, const FString& Name, const FString& Class, const FString& Line)
		{
			const FLinearColor Col = HQ::ArchetypeColor(Class);
			RosterRows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)
			[
				HQ::Selectable(
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 12, 0)
					[
						SNew(SBox).WidthOverride(44).HeightOverride(44)
						[
							SNew(SBorder).BorderImage(HQ::Box(Col, HQ::Clear(), 22.f, 0.f)).HAlign(HAlign_Center).VAlign(VAlign_Center)
							[
								HQ::Text(Name.Left(1).ToUpper(), HQ::Title(22), HQ::C(0x10080a))
							]
						]
					]
					+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot().AutoHeight()[HQ::Text(Name, HQ::Bold(17), HQ::Ink())]
						+ SVerticalBox::Slot().AutoHeight().Padding(0, 2, 0, 0)[HQ::Text(Line, HQ::Body(13), HQ::Muted())]
					],
					TAttribute<bool>::CreateLambda([this, File] { return F.IsValid() && F->ChosenHero() == File; }),
					FOnClicked::CreateLambda([this, File]
					{
						if (!F.IsValid() || F->ChosenHero() == File) return FReply::Handled();
						// unsaved looks stay with the hero they were made on
						if (bLooksChanged) { F->SaveStageLooks(); bLooksChanged = false; }
						F->ChooseHero(File);
						return FReply::Handled();
					}),
					HQ::Box(HQ::Blue(.28f), HQ::Gold(.9f), 6.f, 1.5f), HQ::Box(HQ::C(0x0a1426, .55f), HQ::Sky(.15f), 6.f, 1.f), HQ::Box(HQ::Blue(.14f), HQ::Sky(.45f), 6.f, 1.f),
					FMargin(10, 8))
			];
		};
		for (const FCoHHeroCard& C : F->Heroes())
			Row(C.File, C.Name, C.Class, FString::Printf(TEXT("Level %d %s"), C.Level, *C.ArchetypeName()) + (C.Origin.IsEmpty() ? FString() : TEXT(" · ") + C.Origin));
		Row(FString(), TEXT("Starter hero"), TEXT("Class_Blaster"), TEXT("The test hero from the rules data"));
	}
	RebuildPowers();
	RebuildNemesis();
	RebuildDatabase();
}

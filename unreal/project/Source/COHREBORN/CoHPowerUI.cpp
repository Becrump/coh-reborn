#include "CoHPowerUI.h"
#include "CoHPowers.h"
#include "CoHHeroCharacter.h"
#include "CoHPowerFX.h"
#include "Animation/AnimSequence.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Engine/SkeletalMesh.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Engine/Texture2D.h"
#include "Fonts/SlateFontInfo.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SUniformGridPanel.h"
#include "Widgets/Notifications/SProgressBar.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

#define LOCTEXT_NAMESPACE "CoHHud"

static FSlateFontInfo Font(int32 Size, const char* Weight = "Regular")
{
	return FCoreStyle::GetDefaultFontStyle(Weight, Size);
}
static const FLinearColor Panel(0.02f, 0.04f, 0.09f, 0.82f);
static const FLinearColor Gold(1.f, 0.78f, 0.25f);

void SCoHHud::Construct(const FArguments& InArgs)
{
	Player = InArgs._Player;
	TextHandle = UCoHPowerComponent::OnCombatText.AddSP(this, &SCoHHud::OnText);

	TSharedRef<SHorizontalBox> Tray = SNew(SHorizontalBox);
	for (int32 i = 0; i < 10; ++i) Tray->AddSlot().AutoWidth().Padding(3.f)[MakeSlot(i)];

	ChildSlot
	[
		SNew(SOverlay)
		// health and endurance, top left
		+ SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Top).Padding(20.f)
		[
			SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(Panel).Padding(10.f)
			[
				SNew(SBox).WidthOverride(260.f)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()
					[
						SNew(STextBlock).Font(Font(13, "Bold")).ColorAndOpacity(Gold)
						.Text_Lambda([this] { const UCoHPowerComponent* C = Me(); return C ? FText::FromString(FString::Printf(TEXT("%s  ·  Level %d"), *C->DisplayName, C->Level)) : FText(); })
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 6, 0, 0)
					[ MakeBar([this] { const UCoHPowerComponent* C = Me(); return C && C->MaxHealth > 0 ? C->Health / C->MaxHealth : 0.f; }, FLinearColor(0.15f, 0.8f, 0.25f),
						[this] { const UCoHPowerComponent* C = Me(); return C ? FText::FromString(FString::Printf(TEXT("HP  %.0f / %.0f"), C->Health, C->MaxHealth)) : FText(); }) ]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)
					[ MakeBar([this] { const UCoHPowerComponent* C = Me(); return C && C->MaxEndurance > 0 ? C->Endurance / C->MaxEndurance : 0.f; }, FLinearColor(0.2f, 0.45f, 1.f),
						[this] { const UCoHPowerComponent* C = Me(); return C ? FText::FromString(FString::Printf(TEXT("END  %.0f / %.0f"), C->Endurance, C->MaxEndurance)) : FText(); }) ]
				]
			]
		]
		// target window, top centre
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Top).Padding(0, 20, 0, 0)
		[
			SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(Panel).Padding(10.f)
			.Visibility_Lambda([this] { return TargetComp() ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
			[
				SNew(SBox).WidthOverride(300.f)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()
					[
						SNew(STextBlock).Font(Font(14, "Bold"))
						.Text_Lambda([this] { const UCoHPowerComponent* T = TargetComp(); return T ? FText::FromString(FString::Printf(TEXT("%s  (%d)"), *T->DisplayName, T->Level)) : FText(); })
						.ColorAndOpacity_Lambda([this] { const UCoHPowerComponent* T = TargetComp(); const UCoHPowerComponent* C = Me(); return FSlateColor(T && C ? UCoHPowerComponent::ConColour(C->Level, T->Level) : FLinearColor::White); })
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 6, 0, 0)
					[ MakeBar([this] { const UCoHPowerComponent* T = TargetComp(); return T && T->MaxHealth > 0 ? T->Health / T->MaxHealth : 0.f; }, FLinearColor(0.85f, 0.15f, 0.1f),
						[this] { const UCoHPowerComponent* T = TargetComp(); return T ? FText::FromString(T->IsDefeated() ? TEXT("Defeated") : T->MezName().ToUpper()) : FText(); }) ]
				]
			]
		]
		// power tray, bottom centre
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Bottom).Padding(0, 0, 0, 24)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0, 0, 0, 4)
			[
				SNew(STextBlock).Font(Font(10)).ColorAndOpacity(FLinearColor(1, 1, 1, 0.7f))
				.Text(LOCTEXT("Help", "1-0 use power   Tab target   P powers   F8 animation bench"))
			]
			+ SVerticalBox::Slot().AutoHeight()
			[
				SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(Panel).Padding(6.f)[Tray]
			]
		]
		// power browser
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
		[
			SAssignNew(Browser, SBox).Visibility(EVisibility::Collapsed)[MakeBrowser()]
		]
		// animation test bench
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
		[
			SAssignNew(Bench, SBox).Visibility(EVisibility::Collapsed)[MakeBench()]
		]
	];
}

SCoHHud::~SCoHHud()
{
	UCoHPowerComponent::OnCombatText.Remove(TextHandle);
}

UCoHPowerComponent* SCoHHud::Me() const
{
	const APlayerController* PC = Player.Get();
	return PC ? UCoHPowerComponent::Of(PC->GetPawn()) : nullptr;
}

UCoHPowerComponent* SCoHHud::TargetComp() const
{
	const UCoHPowerComponent* C = Me();
	return C ? UCoHPowerComponent::Of(C->Target.Get()) : nullptr;
}

const FSlateBrush* SCoHHud::IconByName(const FString& Icon)
{
	if (Icon.IsEmpty()) return nullptr;
	if (const TSharedPtr<FSlateBrush>* B = Brushes.Find(Icon)) return B->Get();
	UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(Player.Get());
	UTexture2D* T = DB ? DB->Icon(Icon) : nullptr;
	TSharedPtr<FSlateBrush> B;
	if (T)
	{
		B = MakeShared<FSlateBrush>();
		B->SetResourceObject(T);
		B->ImageSize = FVector2D(48.f, 48.f);
	}
	Brushes.Add(Icon, B);
	return B.Get();
}

const FSlateBrush* SCoHHud::IconFor(FName Power)
{
	UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(Player.Get());
	const FCoHPowerDef* P = DB ? DB->FindPower(Power) : nullptr;
	return P ? IconByName(P->Icon) : nullptr;
}

TSharedRef<SWidget> SCoHHud::MakeBar(TFunction<float()> Fraction, FLinearColor Colour, TFunction<FText()> Label)
{
	return SNew(SBox).HeightOverride(18.f)
	[
		SNew(SOverlay)
		+ SOverlay::Slot()[ SNew(SProgressBar).FillColorAndOpacity(Colour).Percent_Lambda([Fraction] { return TOptional<float>(Fraction()); }) ]
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
		[ SNew(STextBlock).Font(Font(9, "Bold")).ShadowOffset(FVector2D(1, 1)).Text_Lambda([Label] { return Label(); }) ]
	];
}

TSharedRef<SWidget> SCoHHud::MakeSlot(int32 Index)
{
	auto PowerAt = [this, Index] { const UCoHPowerComponent* C = Me(); return C && C->Tray.IsValidIndex(Index) ? C->Tray[Index] : NAME_None; };
	return SNew(SBox).WidthOverride(52.f).HeightOverride(52.f)
	[
		SNew(SButton).ButtonStyle(FCoreStyle::Get(), "NoBorder").ContentPadding(0)
		.OnClicked_Lambda([this, Index]
		{
			if (IsBrowserOpen() || (Bench.IsValid() && Bench->GetVisibility() == EVisibility::Visible)) { SelectedSlot = Index; return FReply::Handled(); }
			if (UCoHPowerComponent* C = Me()) C->ActivateSlot(Index);
			return FReply::Handled();
		})
		[
			SNew(SOverlay)
			// frame: gold when chosen for the browser, green when a toggle is on
			+ SOverlay::Slot()
			[
				SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).Padding(2.f)
				.BorderBackgroundColor_Lambda([this, Index, PowerAt]
				{
					const UCoHPowerComponent* C = Me();
					if (IsBrowserOpen() && SelectedSlot == Index) return FSlateColor(Gold);
					if (C && C->IsToggleOn(PowerAt())) return FSlateColor(FLinearColor(0.2f, 1.f, 0.3f));
					return FSlateColor(FLinearColor(0.15f, 0.2f, 0.3f, 1.f));
				})
				[
					SNew(SOverlay)
					+ SOverlay::Slot()[ SNew(SImage).Image_Lambda([this, PowerAt] { return IconFor(PowerAt()); }) ]
					// recharge: dark wash that clears as the power recharges
					+ SOverlay::Slot()
					[
						SNew(SImage).Image(FCoreStyle::Get().GetBrush("WhiteBrush"))
						.ColorAndOpacity_Lambda([this, PowerAt]
						{
							const UCoHPowerComponent* C = Me(); const FName P = PowerAt();
							const float Left = C ? C->RechargeLeft(P) : 0.f;
							const float Total = C ? C->RechargeTotal(P) : 1.f;
							return FSlateColor(FLinearColor(0, 0, 0, Left > 0.f ? 0.25f + 0.5f * FMath::Clamp(Left / Total, 0.f, 1.f) : 0.f));
						})
					]
				]
			]
			+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
			[
				SNew(STextBlock).Font(Font(14, "Bold")).ShadowOffset(FVector2D(1, 1))
				.Text_Lambda([this, PowerAt] { const UCoHPowerComponent* C = Me(); const float L = C ? C->RechargeLeft(PowerAt()) : 0.f; return L > 0.f ? FText::AsNumber(FMath::CeilToInt(L)) : FText(); })
			]
			+ SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Top).Padding(4, 2)
			[ SNew(STextBlock).Font(Font(9, "Bold")).ShadowOffset(FVector2D(1, 1)).Text(FText::AsNumber((Index + 1) % 10)) ]
		]
	];
}

TSharedRef<SWidget> SCoHHud::MakeBrowser()
{
	// every set the test hero owns (hero_all_sets.json), grouped by category
	TSharedRef<SScrollBox> Cats = SNew(SScrollBox);
	if (UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(Player.Get()))
	{
		TArray<FString> Seen;
		for (const FCoHHeroSet& H : DB->HeroSets)
		{
			if (Seen.Contains(H.Category)) continue;
			Seen.Add(H.Category);
			const FString Cat = H.Category;
			Cats->AddSlot()
			[
				SNew(SButton).OnClicked_Lambda([this, Cat] { ShowSets(Cat); return FReply::Handled(); })
				[ SNew(STextBlock).Font(Font(10, "Bold")).Text(FText::FromString(Cat.Replace(TEXT("_"), TEXT(" ")))) ]
			];
		}
	}
	return SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.02f, 0.03f, 0.07f, 0.95f)).Padding(14.f)
	[
		SNew(SBox).WidthOverride(1000.f).HeightOverride(620.f)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight()
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().FillWidth(1.f)
				[ SAssignNew(BrowserTitle, STextBlock).Font(Font(16, "Bold")).ColorAndOpacity(Gold).Text(LOCTEXT("Title", "Powers: pick a category")) ]
				+ SHorizontalBox::Slot().AutoWidth().Padding(6, 0)
				[
					SNew(SButton).OnClicked_Lambda([this] { if (UCoHPowerComponent* C = Me()) C->SetTray(SelectedSlot, NAME_None); return FReply::Handled(); })
					[ SNew(STextBlock).Text(LOCTEXT("Clear", "Clear slot")) ]
				]
				+ SHorizontalBox::Slot().AutoWidth()
				[
					SNew(SButton).OnClicked_Lambda([this] { ToggleBrowser(); return FReply::Handled(); })
					[ SNew(STextBlock).Text(LOCTEXT("Close", "Close (P)")) ]
				]
			]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 10)
			[
				SNew(STextBlock).Font(Font(10)).ColorAndOpacity(FLinearColor(1, 1, 1, 0.75f))
				.Text_Lambda([this] { return FText::FromString(FString::Printf(TEXT("Click a power to put it in tray slot %d (click a tray slot to choose another)."), (SelectedSlot + 1) % 10)); })
			]
			+ SVerticalBox::Slot().FillHeight(1.f)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().FillWidth(0.24f).Padding(0, 0, 8, 0)[Cats]
				+ SHorizontalBox::Slot().FillWidth(0.28f).Padding(0, 0, 8, 0)[ SAssignNew(SetList, SScrollBox) ]
				+ SHorizontalBox::Slot().FillWidth(0.48f)[ SAssignNew(PowerList, SScrollBox) ]
			]
		]
	];
}

void SCoHHud::ShowSets(const FString& Category)
{
	UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(Player.Get());
	if (!DB || !SetList) return;
	SetList->ClearChildren();
	PowerList->ClearChildren();
	BrowserTitle->SetText(FText::FromString(Category.Replace(TEXT("_"), TEXT(" ")) + TEXT(": pick a power set")));
	for (const FCoHHeroSet& H : DB->HeroSets)
	{
		if (H.Category != Category) continue;
		const FString Id = H.Id;
		const FCoHPowerDef* First = H.Powers.Num() ? DB->FindPower(H.Powers[0]) : nullptr;
		const FString Icon = First ? First->Icon : FString();
		const FString Label = H.Element.IsEmpty() ? H.Name : FString::Printf(TEXT("%s  (%s)"), *H.Name, *H.Element);
		SetList->AddSlot()
		[
			SNew(SButton).OnClicked_Lambda([this, Id] { ShowPowers(Id); return FReply::Handled(); })
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().AutoWidth()[ SNew(SBox).WidthOverride(24).HeightOverride(24)[ SNew(SImage).Image(IconByName(Icon)) ] ]
				+ SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center).Padding(6, 0)[ SNew(STextBlock).Font(Font(11)).Text(FText::FromString(Label)) ]
			]
		];
	}
}

void SCoHHud::ShowPowers(const FString& SetId)
{
	UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(Player.Get());
	if (!DB || !PowerList) return;
	PowerList->ClearChildren();
	const FCoHHeroSet* H = DB->HeroSets.FindByPredicate([&](const FCoHHeroSet& X) { return X.Id == SetId; });
	if (!H) return;
	const FCoHPowerSetDef* S = DB->PowerSets.FindByPredicate([&](const FCoHPowerSetDef& X) { return X.Id == SetId; });
	for (const FName& PowerId : H->Powers)
	{
		const FCoHPowerDef* P = DB->FindPower(PowerId);
		int32 Avail = 1;
		if (S) for (const auto& E : S->Powers) if (E.Key == PowerId) Avail = E.Value;
		if (!P) continue;
		const FName Id = P->Id;
		const FString Info = FString::Printf(TEXT("Lvl %d · %s · %.1fs cast · %.0fs recharge · %.1f end · %.0f ft"), Avail,
			P->Type == TEXT("kToggle") ? TEXT("Toggle") : (P->Type == TEXT("kAuto") ? TEXT("Auto") : TEXT("Click")), P->Activate, P->Recharge, P->EndCost, P->Range);
		PowerList->AddSlot().Padding(0, 1)
		[
			SNew(SButton).ToolTipText(FText::FromString(P->Help))
			.OnClicked_Lambda([this, Id]
			{
				if (UCoHPowerComponent* C = Me())
				{
					C->SetTray(SelectedSlot, Id);
					SelectedSlot = (SelectedSlot + 1) % 10;
				}
				return FReply::Handled();
			})
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().AutoWidth()[ SNew(SBox).WidthOverride(36).HeightOverride(36)[ SNew(SImage).Image(IconByName(P->Icon)) ] ]
				+ SHorizontalBox::Slot().FillWidth(1.f).Padding(8, 0)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()[ SNew(STextBlock).Font(Font(11, "Bold")).Text(FText::FromString(P->Display)) ]
					+ SVerticalBox::Slot().AutoHeight()[ SNew(STextBlock).Font(Font(9)).ColorAndOpacity(FLinearColor(1, 1, 1, 0.75f)).Text(FText::FromString(P->Short)) ]
					+ SVerticalBox::Slot().AutoHeight()[ SNew(STextBlock).Font(Font(8)).ColorAndOpacity(FLinearColor(0.6f, 0.75f, 1.f)).Text(FText::FromString(Info)) ]
				]
			]
		];
	}
}

bool SCoHHud::IsBrowserOpen() const
{
	return Browser.IsValid() && Browser->GetVisibility() == EVisibility::Visible;
}

void SCoHHud::ToggleBrowser()
{
	if (!Browser) return;
	const bool bOpen = !IsBrowserOpen();
	Browser->SetVisibility(bOpen ? EVisibility::Visible : EVisibility::Collapsed);
	SetCursor(bOpen);
}

void SCoHHud::SetCursor(bool bOn)
{
	APlayerController* PC = Player.Get();
	if (!PC) return;
	PC->SetShowMouseCursor(bOn);
	if (bOn)
	{
		FInputModeGameAndUI Mode;
		Mode.SetHideCursorDuringCapture(false);
		Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		PC->SetInputMode(Mode);
	}
	else PC->SetInputMode(FInputModeGameOnly());
}

void SCoHHud::OnText(AActor* Who, const FString& Text, FLinearColor Colour)
{
	FFloat F;
	F.Who = Who; F.Text = Text; F.Colour = Colour; F.Drift = FMath::FRandRange(-30.f, 30.f);
	Floats.Add(F);
	if (Floats.Num() > 40) Floats.RemoveAt(0);
}

void SCoHHud::Tick(const FGeometry& Geometry, const double Time, const float Dt)
{
	SCompoundWidget::Tick(Geometry, Time, Dt);
	for (FFloat& F : Floats) F.Age += Dt;
	Floats.RemoveAll([](const FFloat& F) { return F.Age > 1.4f || !F.Who.IsValid(); });
}

int32 SCoHHud::OnPaint(const FPaintArgs& Args, const FGeometry& Geometry, const FSlateRect& Culling,
	FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle& Style, bool bParentEnabled) const
{
	int32 Top = SCompoundWidget::OnPaint(Args, Geometry, Culling, Out, Layer, Style, bParentEnabled);
	const APlayerController* PC = Player.Get();
	if (!PC) return Top;
	const FSlateFontInfo F = Font(18, "Bold");
	const float Scale = Geometry.Scale > 0.f ? Geometry.Scale : 1.f;
	for (const FFloat& Fl : Floats)
	{
		const AActor* Who = Fl.Who.Get();
		if (!Who) continue;
		FVector2D Screen;
		const FVector At = Who->GetActorLocation() + FVector(0, 0, 120.f + Fl.Age * 90.f);
		if (!PC->ProjectWorldLocationToScreen(At, Screen, true)) continue;
		const FVector2D Pos = Screen / Scale + FVector2D(Fl.Drift, 0);
		FLinearColor C = Fl.Colour; C.A = FMath::Clamp(1.4f - Fl.Age, 0.f, 1.f);
		FSlateDrawElement::MakeText(Out, Top + 1, Geometry.ToPaintGeometry(FVector2f(200.f, 30.f), FSlateLayoutTransform(FVector2f(Pos.X + 1, Pos.Y + 1))),
			Fl.Text, F, ESlateDrawEffect::None, FLinearColor(0, 0, 0, C.A));
		FSlateDrawElement::MakeText(Out, Top + 2, Geometry.ToPaintGeometry(FVector2f(200.f, 30.f), FSlateLayoutTransform(FVector2f(Pos.X, Pos.Y))),
			Fl.Text, F, ESlateDrawEffect::None, C);
	}
	return Top + 2;
}


// ------------------------------------------------------------------ animation test bench
FName SCoHHud::SlotPower(int32 Slot) const
{
	const UCoHPowerComponent* C = Me();
	return C && C->Tray.IsValidIndex(Slot) ? C->Tray[Slot] : NAME_None;
}

TSharedRef<SWidget> SCoHHud::MakeBench()
{
	auto Info = [this]
	{
		UAnimSequenceBase* A = Cast<UAnimSequenceBase>(SelectedClip.TryLoad());
		if (!A) return FText::FromString(TEXT("Pick a clip to play it on the hero."));
		bool bNotify = false;
		const float Rel = ACoHHeroCharacter::ReleaseTime(A, &bNotify);
		const UAnimSequence* Seq = Cast<UAnimSequence>(A);
		const double Fps = Seq ? Seq->GetSamplingFrameRate().AsDecimal() : 30.0;
		const UCoHPowerComponent* C = Me();
		const FName P = SlotPower(SelectedSlot);
		const FCoHPowerStyle* St = C ? C->Styles.Find(P) : nullptr;
		const ECoHEmitter E = St ? St->Emitter : ECoHEmitter::RightHand;
		return FText::FromString(FString::Printf(
			TEXT("%s\nLength %.2f s (%d frames at %.0f fps)\nRelease %.2f s = frame %d (%s)\nSocket for slot %d (%s): %s"),
			*A->GetName(), A->GetPlayLength(), FMath::RoundToInt(A->GetPlayLength() * Fps), Fps,
			Rel, FMath::RoundToInt(Rel * Fps), bNotify ? TEXT("from its CoHRelease notify") : TEXT("default 45%, add a CoHRelease notify to set it"),
			(SelectedSlot + 1) % 10, P.IsNone() ? TEXT("empty") : *P.ToString(), *ACoHPowerFX::SocketFor(E).ToString()));
	};
	return SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.02f, 0.03f, 0.07f, 0.95f)).Padding(14.f)
	[
		SNew(SBox).WidthOverride(900.f).HeightOverride(600.f)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight()
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().FillWidth(1.f)
				[ SNew(STextBlock).Font(Font(16, "Bold")).ColorAndOpacity(Gold).Text(LOCTEXT("BenchTitle", "Animation test bench")) ]
				+ SHorizontalBox::Slot().AutoWidth()
				[ SNew(SButton).OnClicked_Lambda([this] { ToggleBench(); return FReply::Handled(); })[ SNew(STextBlock).Text(LOCTEXT("BenchClose", "Close (F8)")) ] ]
			]
			+ SVerticalBox::Slot().AutoHeight().Padding(0, 6)
			[
				SNew(SEditableTextBox).HintText(LOCTEXT("BenchFilter", "Filter clips by name (attack, idle, taunt...)"))
				.OnTextChanged_Lambda([this](const FText& T) { ClipFilter = T.ToString(); FillBench(); })
			]
			+ SVerticalBox::Slot().FillHeight(1.f)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().FillWidth(0.5f).Padding(0, 0, 10, 0)[ SAssignNew(ClipList, SScrollBox) ]
				+ SHorizontalBox::Slot().FillWidth(0.5f)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()[ SNew(STextBlock).Font(Font(11)).AutoWrapText(true).Text_Lambda(Info) ]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 12, 0, 4)
					[ SNew(SButton).OnClicked_Lambda([this] { if (auto* H = Cast<ACoHHeroCharacter>(Player.IsValid() ? Player->GetPawn() : nullptr)) H->PreviewAnimation(SelectedClip.ToString()); return FReply::Handled(); })[ SNew(STextBlock).Text(LOCTEXT("BenchPlay", "Play again")) ] ]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)
					[ SNew(SButton).OnClicked_Lambda([this] { AssignClip(TEXT("Inherent.Inherent.Brawl")); return FReply::Handled(); })[ SNew(STextBlock).Text(LOCTEXT("BenchBrawl", "Use for Brawl")) ] ]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)
					[ SNew(SButton).OnClicked_Lambda([this] { AssignClip(TEXT("Blaster_Ranged.Fire_Blast.Flares")); return FReply::Handled(); })[ SNew(STextBlock).Text(LOCTEXT("BenchFlares", "Use for Flares")) ] ]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)
					[ SNew(SButton).OnClicked_Lambda([this] { AssignClip(SlotPower(SelectedSlot)); return FReply::Handled(); })
						[ SNew(STextBlock).Text_Lambda([this] { return FText::FromString(FString::Printf(TEXT("Use for tray slot %d's power"), (SelectedSlot + 1) % 10)); }) ] ]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)
					[
						SNew(SButton).OnClicked_Lambda([this]
						{
							// next emitter point for the selected slot's power
							if (UCoHPowerComponent* C = Me())
							{
								const FName P = SlotPower(SelectedSlot);
								if (!P.IsNone())
								{
									FCoHPowerStyle& S = C->Styles.FindOrAdd(P);
									S.Emitter = (ECoHEmitter)(((int32)S.Emitter + 1) % ((int32)ECoHEmitter::Overhead + 1));
								}
							}
							return FReply::Handled();
						})
						[ SNew(STextBlock).Text(LOCTEXT("BenchSocket", "Next emitter socket for that slot")) ]
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 10)
					[ SNew(STextBlock).Font(Font(9)).ColorAndOpacity(FLinearColor(1, 1, 1, 0.7f)).AutoWrapText(true)
						.Text(LOCTEXT("BenchHelp", "Click a tray slot to pick which power the buttons change. Gameplay timing always comes from the power: a clip is sped up or slowed to fit its cast time.")) ]
				]
			]
		]
	];
}

void SCoHHud::FillBench()
{
	if (!ClipList) return;
	ClipList->ClearChildren();
	int32 Shown = 0;
	for (const FSoftObjectPath& C : Clips)
	{
		const FString Name = C.GetAssetName();
		if (!ClipFilter.IsEmpty() && !Name.Contains(ClipFilter) && !C.ToString().Contains(ClipFilter)) continue;
		if (++Shown > 400) break;
		ClipList->AddSlot()
		[
			SNew(SButton).OnClicked_Lambda([this, C] { SelectClip(C); return FReply::Handled(); })
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()[ SNew(STextBlock).Font(Font(10, "Bold")).Text(FText::FromString(Name)) ]
				+ SVerticalBox::Slot().AutoHeight()[ SNew(STextBlock).Font(Font(8)).ColorAndOpacity(FLinearColor(1, 1, 1, 0.6f)).Text(FText::FromString(FPaths::GetPath(C.GetLongPackageName()))) ]
			]
		];
	}
}

void SCoHHud::SelectClip(const FSoftObjectPath& Clip)
{
	SelectedClip = Clip;
	if (auto* H = Cast<ACoHHeroCharacter>(Player.IsValid() ? Player->GetPawn() : nullptr)) H->PreviewAnimation(Clip.ToString());
}

void SCoHHud::AssignClip(FName Power)
{
	if (UCoHPowerComponent* C = Me())
		if (!Power.IsNone() && SelectedClip.IsValid()) C->SetPowerAnimation(Power, SelectedClip.ToString());
}

void SCoHHud::ToggleBench()
{
	if (!Bench) return;
	const bool bOpen = Bench->GetVisibility() != EVisibility::Visible;
	if (bOpen)
	{
		// every animation made for the hero's skeleton
		Clips.Reset();
		const ACharacter* H = Player.IsValid() ? Cast<ACharacter>(Player->GetPawn()) : nullptr;
		const USkeletalMesh* Mesh = H ? H->GetMesh()->GetSkeletalMeshAsset() : nullptr;
		const FString Skel = Mesh && Mesh->GetSkeleton() ? Mesh->GetSkeleton()->GetPathName() : FString();
		IAssetRegistry& AR = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry").Get();
		TArray<FAssetData> Found;
		AR.GetAssetsByClass(UAnimSequence::StaticClass()->GetClassPathName(), Found, true);
		for (const FAssetData& A : Found)
		{
			FString S;
			if (Skel.IsEmpty() || (A.GetTagValue(TEXT("Skeleton"), S) && S.Contains(Skel))) Clips.Add(A.GetSoftObjectPath());
		}
		Clips.Sort([](const FSoftObjectPath& A, const FSoftObjectPath& B) { return A.GetAssetName() < B.GetAssetName(); });
		FillBench();
		if (IsBrowserOpen()) Browser->SetVisibility(EVisibility::Collapsed);
	}
	Bench->SetVisibility(bOpen ? EVisibility::Visible : EVisibility::Collapsed);
	SetCursor(bOpen);
}

#undef LOCTEXT_NAMESPACE

TSharedRef<SWidget> UCoHHudWidget::RebuildWidget()
{
	return SAssignNew(Hud, SCoHHud).Player(GetOwningPlayer());
}

void UCoHHudWidget::ReleaseSlateResources(bool bReleaseChildren)
{
	Super::ReleaseSlateResources(bReleaseChildren);
	Hud.Reset();
}

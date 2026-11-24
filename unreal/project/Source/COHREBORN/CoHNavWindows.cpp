#include "CoHNavWindows.h"
#include "CoHStory.h"
#include "CoHBadges.h"
#include "CoHGameRules.h"
#include "CoHHeroProgress.h"
#include "Framework/Application/SlateApplication.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SLeafWidget.h"
#include "Widgets/SOverlay.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Text/STextBlock.h"

namespace CoHNav
{
	// the hero window colour (DEFAULT_HERO_WINDOW_COLOR 0x3399ff) and the original's text colours
	static const FLinearColor Frame(0.2f, 0.6f, 1.f);
	static const FLinearColor Back(0.f, 0.f, 0.f, 0.62f);
	static const FLinearColor Text(0.88f, 0.94f, 1.f);
	static const FLinearColor Dim(0.55f, 0.62f, 0.72f);
	static const FLinearColor Gold(1.f, 0.85f, 0.35f);
	static const FLinearColor Done(0.45f, 1.f, 0.45f);

	static TSharedRef<STextBlock> Label(const FString& T, FLinearColor C = Text, int32 Size = 11, bool bBold = false, bool bWrap = false)
	{
		return SNew(STextBlock).Text(FText::FromString(T)).ColorAndOpacity(C).AutoWrapText(bWrap)
			.Font(FCoreStyle::GetDefaultFontStyle(bBold ? "Bold" : "Regular", Size));
	}

	/** Compass bearing (degrees clockwise from map north) of a direction in the world.
	 *  Zones: map north = Unreal +Y, map east = Unreal -X (place_world.py). */
	static float Bearing(const FVector& D) { return FMath::RadiansToDegrees(FMath::Atan2(-D.X, D.Y)); }

	static FString Relationship(const FCoHStoryContact& C, int32 Points)
	{
		return Points >= C.CompleteCP ? TEXT("Complete") : Points >= C.ConfidantCP ? TEXT("Confidant") : Points >= C.FriendCP ? TEXT("Friend") : TEXT("Acquaintance");
	}

	static FString Category(const FString& C) { return C.StartsWith(TEXT("k")) ? C.Mid(1) : C; }
}

/** The compass strip (uiCompass.c): headings slide past as the camera turns, the waypoint is a gold mark. */
class SCoHNavCompass : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHNavCompass) {}
		SLATE_ARGUMENT(TWeakObjectPtr<UCoHStoryComponent>, Owner)
		SLATE_ARGUMENT(SCoHNavPanel*, Panel)
	SLATE_END_ARGS()
	void Construct(const FArguments& A) { Owner = A._Owner; Panel = A._Panel; SetVisibility(EVisibility::HitTestInvisible); }
	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(280, 54); }
	virtual int32 OnPaint(const FPaintArgs&, const FGeometry& G, const FSlateRect&, FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle&, bool) const override
	{
		const UCoHStoryComponent* C = Owner.Get();
		const APawn* Me = C ? Cast<APawn>(C->GetOwner()) : nullptr;
		if (!Me || !Panel) return Layer;
		const FSlateBrush* White = FCoreStyle::Get().GetBrush("WhiteBrush");
		const FVector2f Size = FVector2f(G.GetLocalSize());
		const float Strip = 26.f;
		FSlateDrawElement::MakeBox(Out, Layer, G.ToPaintGeometry(FVector2f(Size.X, Strip), FSlateLayoutTransform(FVector2f(0, 0))), White, ESlateDrawEffect::None, CoHNav::Back);
		FSlateDrawElement::MakeBox(Out, Layer + 1, G.ToPaintGeometry(FVector2f(Size.X, 1.5f), FSlateLayoutTransform(FVector2f(0, Strip - 1.5f))), White, ESlateDrawEffect::None, CoHNav::Frame);
		// the camera's heading
		const AController* PC = Me->GetController();
		const FRotator View = PC ? PC->GetControlRotation() : Me->GetActorRotation();
		const float Heading = CoHNav::Bearing(View.Vector());
		const float Half = Size.X * 0.5f, Span = 100.f;      // degrees shown each side
		auto XOf = [&](float Deg) { return Half + FMath::FindDeltaAngleDegrees(Heading, Deg) / Span * Half; };
		const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle("Bold", 10);
		const FSlateFontInfo Small = FCoreStyle::GetDefaultFontStyle("Regular", 8);
		static const TCHAR* Names[] = { TEXT("N"), TEXT("NE"), TEXT("E"), TEXT("SE"), TEXT("S"), TEXT("SW"), TEXT("W"), TEXT("NW") };
		for (int32 Deg = 0; Deg < 360; Deg += 15)
		{
			if (FMath::Abs(FMath::FindDeltaAngleDegrees(Heading, (float)Deg)) > Span) continue;
			const float X = XOf((float)Deg);
			const bool bMajor = Deg % 45 == 0;
			FSlateDrawElement::MakeBox(Out, Layer + 1, G.ToPaintGeometry(FVector2f(1.f, bMajor ? 8.f : 4.f), FSlateLayoutTransform(FVector2f(X, Strip - (bMajor ? 9.f : 5.f)))),
				White, ESlateDrawEffect::None, CoHNav::Frame);
			if (bMajor)
			{
				const FString N = Names[Deg / 45];
				FSlateDrawElement::MakeText(Out, Layer + 2, G.ToPaintGeometry(FVector2f(30.f, 16.f), FSlateLayoutTransform(FVector2f(X - 4.f * N.Len(), 1.f))), N, Font,
					ESlateDrawEffect::None, Deg == 0 ? CoHNav::Gold : CoHNav::Text);
			}
		}
		// the centre line
		FSlateDrawElement::MakeBox(Out, Layer + 3, G.ToPaintGeometry(FVector2f(2.f, Strip), FSlateLayoutTransform(FVector2f(Half - 1.f, 0))), White, ESlateDrawEffect::None, FLinearColor(1, 1, 1, 0.35f));
		// the waypoint: its mark on the strip (at the edge when behind), its name and distance below
		FVector Way; FString WayName;
		if (Panel->Waypoint(Way, WayName))
		{
			const FVector D = Way - Me->GetActorLocation();
			const float Delta = FMath::FindDeltaAngleDegrees(Heading, CoHNav::Bearing(D));
			const float X = FMath::Clamp(Half + Delta / Span * Half, 4.f, Size.X - 4.f);
			FSlateDrawElement::MakeBox(Out, Layer + 4, G.ToPaintGeometry(FVector2f(8.f, 8.f), FSlateLayoutTransform(FVector2f(X - 4.f, Strip - 12.f))), White, ESlateDrawEffect::None, CoHNav::Gold);
			const FString Line = FString::Printf(TEXT("%s  %d yds"), *WayName.Left(36), FMath::RoundToInt(D.Size() / 91.44f));
			FSlateDrawElement::MakeText(Out, Layer + 4, G.ToPaintGeometry(FVector2f(Size.X, 16.f), FSlateLayoutTransform(FVector2f(4.f, Strip + 3.f))), Line, Small,
				ESlateDrawEffect::None, CoHNav::Gold);
		}
		return Layer + 5;
	}
private:
	TWeakObjectPtr<UCoHStoryComponent> Owner;
	SCoHNavPanel* Panel = nullptr;
};

/** The map (uiMap.c): the city around the hero, north up. Zone outlines and names on the
 *  one-world map, the hero, teammates, contacts met and mission waypoints. Wheel zooms,
 *  a click sets the waypoint there. */
class SCoHNavMap : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHNavMap) {}
		SLATE_ARGUMENT(TWeakObjectPtr<UCoHStoryComponent>, Owner)
		SLATE_ARGUMENT(SCoHNavPanel*, Panel)
	SLATE_END_ARGS()
	void Construct(const FArguments& A) { Owner = A._Owner; Panel = A._Panel; }
	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(400, 400); }

	FVector2f ToScreen(const FVector& P, const FVector& Center, const FVector2f& Size) const
	{
		// map north = Unreal +Y (up), map east = Unreal -X (right)
		return FVector2f(Size.X * 0.5f - (P.X - Center.X) / Panel->MapScale, Size.Y * 0.5f - (P.Y - Center.Y) / Panel->MapScale);
	}
	FVector ToWorld(const FVector2f& S, const FVector& Center, const FVector2f& Size) const
	{
		return FVector(Center.X - (S.X - Size.X * 0.5f) * Panel->MapScale, Center.Y - (S.Y - Size.Y * 0.5f) * Panel->MapScale, Center.Z);
	}
	const APawn* Me() const { const UCoHStoryComponent* C = Owner.Get(); return C ? Cast<APawn>(C->GetOwner()) : nullptr; }

	virtual int32 OnPaint(const FPaintArgs&, const FGeometry& G, const FSlateRect& Cull, FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle&, bool) const override
	{
		const APawn* Hero = Me();
		const UCoHStoryComponent* C = Owner.Get();
		if (!Hero || !C || !Panel) return Layer;
		const FSlateBrush* White = FCoreStyle::Get().GetBrush("WhiteBrush");
		const FVector2f Size = FVector2f(G.GetLocalSize());
		const FVector Center = Hero->GetActorLocation();
		FSlateDrawElement::MakeBox(Out, Layer, G.ToPaintGeometry(), White, ESlateDrawEffect::None, FLinearColor(0.02f, 0.05f, 0.09f, 0.95f));
		const FSlateFontInfo Small = FCoreStyle::GetDefaultFontStyle("Regular", 8);
		const FSlateFontInfo Bold = FCoreStyle::GetDefaultFontStyle("Bold", 10);
		auto Inside = [&](const FVector2f& S) { return S.X >= 0 && S.Y >= 0 && S.X <= Size.X && S.Y <= Size.Y; };
		auto Dot = [&](const FVector2f& S, float R, const FLinearColor& Col, int32 L)
		{
			FSlateDrawElement::MakeBox(Out, L, G.ToPaintGeometry(FVector2f(R * 2, R * 2), FSlateLayoutTransform(S - FVector2f(R, R))), White, ESlateDrawEffect::None, Col);
		};
		auto Text = [&](const FVector2f& S, const FString& T, const FSlateFontInfo& F, const FLinearColor& Col, int32 L)
		{
			FSlateDrawElement::MakeText(Out, L, G.ToPaintGeometry(FVector2f(220.f, 16.f), FSlateLayoutTransform(S)), T, F, ESlateDrawEffect::None, Col);
		};
		// the zones (one-world map): outlines, names from the contacts' locations
		const UCoHGameRules* GR = UCoHGameRules::Get(Hero);
		const UCoHStory* St = UCoHStory::Get(Hero);
		if (GR && Hero->GetWorld() && Hero->GetWorld()->GetMapName().Contains(TEXT("ParagonCity")))
		{
			TMap<FString, FString> Names;
			if (St) for (const auto& KV : St->Contacts) if (!KV.Value.Zone.IsEmpty() && !KV.Value.Location.IsEmpty()) Names.FindOrAdd(KV.Value.Zone.ToLower(), KV.Value.Location);
			for (const auto& R : GR->ZoneRects)
			{
				const FVector2f A = ToScreen(FVector(R.Value.Min.X, R.Value.Min.Y, 0), Center, Size);
				const FVector2f B = ToScreen(FVector(R.Value.Max.X, R.Value.Max.Y, 0), Center, Size);
				const FVector2f Lo(FMath::Min(A.X, B.X), FMath::Min(A.Y, B.Y)), Hi(FMath::Max(A.X, B.X), FMath::Max(A.Y, B.Y));
				if (Hi.X < 0 || Hi.Y < 0 || Lo.X > Size.X || Lo.Y > Size.Y) continue;
				TArray<FVector2f> Pts = { Lo, FVector2f(Hi.X, Lo.Y), Hi, FVector2f(Lo.X, Hi.Y), Lo };
				FSlateDrawElement::MakeLines(Out, Layer + 1, G.ToPaintGeometry(), Pts, ESlateDrawEffect::None, FLinearColor(0.2f, 0.6f, 1.f, 0.7f), true, 1.5f);
				const FString* N = Names.Find(R.Key.ToLower());
				const FVector2f Mid((Lo.X + Hi.X) * 0.5f, (Lo.Y + Hi.Y) * 0.5f);
				Text(FVector2f(FMath::Clamp(Mid.X - 40.f, 2.f, Size.X - 90.f), FMath::Clamp(Mid.Y, 2.f, Size.Y - 16.f)), N ? *N : R.Key, Bold, FLinearColor(0.55f, 0.8f, 1.f, 0.8f), Layer + 2);
			}
		}
		// contacts met (gold), turn-ins ready (green)
		if (const UCoHHeroProgress* P = C->Progress())
		{
			if (St)
				for (const FCoHContactState& X : P->Hero.Story.Contacts)
					if (const FCoHStoryContact* D = St->Contact(X.Contact))
					{
						if (D->Pos.IsZero()) continue;
						const FVector2f S = ToScreen(D->Pos, Center, Size);
						if (!Inside(S)) continue;
						const bool bReady = P->Hero.Story.Tasks.ContainsByPredicate([&](const FCoHTaskState& T) { return T.Contact == D->Id && T.bComplete; });
						Dot(S, 4.f, bReady ? CoHNav::Done : CoHNav::Gold, Layer + 3);
						if (Panel->MapScale < 600.f) Text(S + FVector2f(6, -7), D->Name, Small, CoHNav::Gold, Layer + 3);
					}
			// mission waypoints (red)
			for (const FCoHTaskState& T : P->Hero.Story.Tasks)
				if (!T.Waypoint.IsZero() && !T.bComplete)
				{
					const FVector2f S = ToScreen(T.Waypoint, Center, Size);
					if (!Inside(S)) continue;
					Dot(S, 5.f, FLinearColor(1.f, 0.25f, 0.2f), Layer + 3);
				}
		}
		// the set waypoint
		FVector Way; FString WayName;
		if (Panel->Waypoint(Way, WayName))
		{
			const FVector2f S = ToScreen(Way, Center, Size);
			if (Inside(S)) { Dot(S, 6.f, FLinearColor::White, Layer + 4); Dot(S, 4.f, CoHNav::Gold, Layer + 5); }
		}
		// teammates and other heroes (light blue), the hero (white, with its facing)
		for (TActorIterator<APawn> It(Hero->GetWorld()); It; ++It)
			if (*It != Hero && UCoHHeroProgress::Of(*It))
			{
				const FVector2f S = ToScreen(It->GetActorLocation(), Center, Size);
				if (Inside(S)) Dot(S, 4.f, FLinearColor(0.5f, 0.85f, 1.f), Layer + 5);
			}
		const FVector2f Mid = Size * 0.5f;
		Dot(Mid, 5.f, FLinearColor::White, Layer + 6);
		const FVector F = Hero->GetActorForwardVector();
		TArray<FVector2f> Dir = { Mid, Mid + FVector2f(-F.X, -F.Y) * 14.f };
		FSlateDrawElement::MakeLines(Out, Layer + 6, G.ToPaintGeometry(), Dir, ESlateDrawEffect::None, FLinearColor::White, true, 2.f);
		Text(FVector2f(4, Size.Y - 16), FString::Printf(TEXT("N up   %d m across   wheel: zoom   click: waypoint"), FMath::RoundToInt(Size.X * Panel->MapScale / 100.f)), Small, CoHNav::Dim, Layer + 6);
		return Layer + 7;
	}
	virtual FReply OnMouseWheel(const FGeometry& G, const FPointerEvent& E) override
	{
		if (Panel) Panel->MapScale = FMath::Clamp(Panel->MapScale * (E.GetWheelDelta() > 0 ? 0.8f : 1.25f), 25.f, 20000.f);
		return FReply::Handled();
	}
	virtual FReply OnMouseButtonDown(const FGeometry& G, const FPointerEvent& E) override
	{
		const APawn* Hero = Me();
		UCoHStoryComponent* C = Owner.Get();
		if (!Hero || !C || !Panel) return FReply::Unhandled();
		const FVector2f Local = FVector2f(G.AbsoluteToLocal(E.GetScreenSpacePosition()));
		C->NavWaypoint = ToWorld(Local, Hero->GetActorLocation(), FVector2f(G.GetLocalSize()));
		C->NavWaypointName = TEXT("Map waypoint");
		return FReply::Handled();
	}
private:
	TWeakObjectPtr<UCoHStoryComponent> Owner;
	SCoHNavPanel* Panel = nullptr;
};

void SCoHNavPanel::Construct(const FArguments& Args)
{
	Owner = Args._Owner;
	const FSlateBrush* White = FCoreStyle::Get().GetBrush("WhiteBrush");
	TSharedRef<SHorizontalBox> Tabs = SNew(SHorizontalBox);
	for (const auto& T : { TPair<FString, FString>(TEXT("contacts"), TEXT("Contacts")), TPair<FString, FString>(TEXT("missions"), TEXT("Missions")),
		TPair<FString, FString>(TEXT("clues"), TEXT("Clues")), TPair<FString, FString>(TEXT("souvenirs"), TEXT("Souvenirs")), TPair<FString, FString>(TEXT("badges"), TEXT("Badges")), TPair<FString, FString>(TEXT("map"), TEXT("Map")) })
		Tabs->AddSlot().AutoWidth().Padding(0, 0, 3, 0)[TabButton(T.Key, T.Value)];
	ChildSlot
	[
		SNew(SOverlay)
		// the compass, top centre (window_defaults: WDW_COMPASS, centre-top, open)
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Top).Padding(0, 6, 0, 0)
		[
			SAssignNew(Compass, SBox).WidthOverride(280).HeightOverride(54).Visibility(EVisibility::HitTestInvisible)
			[
				SNew(SCoHNavCompass).Owner(Owner).Panel(this)
			]
		]
		// the window its tabs open
		+ SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Center).Padding(0, 0, 40, 0)
		[
			SAssignNew(Window, SBox).WidthOverride(440).HeightOverride(520).Visibility(EVisibility::Collapsed)
			[
				SNew(SBorder).BorderImage(White).BorderBackgroundColor(CoHNav::Frame).Padding(1.5f)
				[
					SNew(SBorder).BorderImage(White).BorderBackgroundColor(FLinearColor(0.01f, 0.02f, 0.05f, 0.9f)).Padding(10)
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 6)
						[
							SNew(SHorizontalBox)
							+ SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center)
							[
								SAssignNew(Title, STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Bold", 14)).ColorAndOpacity(CoHNav::Frame)
							]
							+ SHorizontalBox::Slot().AutoWidth()
							[
								SNew(SButton).ButtonColorAndOpacity(FLinearColor(0.5f, 0.15f, 0.15f)).ContentPadding(FMargin(6, 1))
								.OnClicked_Lambda([this]() { Window->SetVisibility(EVisibility::Collapsed); return FReply::Handled(); })
								[CoHNav::Label(TEXT("X"), FLinearColor::White, 10, true)]
							]
						]
						+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)[Tabs]
						+ SVerticalBox::Slot().FillHeight(1.f)[SAssignNew(Body, SVerticalBox)]
					]
				]
			]
		]
	];
}

TSharedRef<SWidget> SCoHNavPanel::TabButton(const FString& Id, const FString& Label)
{
	return SNew(SButton).ContentPadding(FMargin(8, 2))
		.ButtonColorAndOpacity_Lambda([this, Id]() { return FSlateColor(Tab == Id ? FLinearColor(0.2f, 0.6f, 1.f) : FLinearColor(0.12f, 0.2f, 0.35f)); })
		.OnClicked_Lambda([this, Id]() { Tab = Id; Selected.Reset(); Rebuild(); return FReply::Handled(); })
		[CoHNav::Label(Label, FLinearColor::White, 10, true)];
}

bool SCoHNavPanel::IsOpen() const { return Window.IsValid() && Window->GetVisibility() == EVisibility::Visible; }

void SCoHNavPanel::Toggle(const FString& NewTab)
{
	const FString T = NewTab.IsEmpty() ? Tab : NewTab.ToLower();
	if (IsOpen() && T == Tab) { Window->SetVisibility(EVisibility::Collapsed); return; }
	Tab = T; Selected.Reset();
	Window->SetVisibility(EVisibility::Visible);
	Rebuild();
}

void SCoHNavPanel::ToggleCompass()
{
	Compass->SetVisibility(Compass->GetVisibility() == EVisibility::Collapsed ? EVisibility::HitTestInvisible : EVisibility::Collapsed);
}

bool SCoHNavPanel::Waypoint(FVector& Out, FString& Name) const
{
	const UCoHStoryComponent* C = Owner.Get();
	if (!C) return false;
	if (!C->NavWaypoint.IsZero()) { Out = C->NavWaypoint; Name = C->NavWaypointName; return true; }
	// the original points the compass at the active mission
	if (!C->TaskForceWaypoint.IsZero()) { Out = C->TaskForceWaypoint; Name = TEXT("Task force"); return true; }
	const UCoHHeroProgress* P = C->Progress();
	if (!P || !P->bHasRecord) return false;
	for (const FCoHTaskState& S : P->Hero.Story.Tasks)
		if (!S.Waypoint.IsZero() && !S.bComplete) { Out = S.Waypoint; Name = S.Text; return true; }
	return false;
}

void SCoHNavPanel::Tick(const FGeometry& G, const double Now, const float Dt)
{
	SCompoundWidget::Tick(G, Now, Dt);
	// a picked waypoint is cleared on arrival (20 yards), as the original's
	if (UCoHStoryComponent* C = Owner.Get())
		if (!C->NavWaypoint.IsZero())
			if (const AActor* Me = C->GetOwner())
				if (FVector::Dist2D(Me->GetActorLocation(), C->NavWaypoint) < 1830.f) { C->NavWaypoint = FVector::ZeroVector; C->NavWaypointName.Reset(); }
	if (!IsOpen()) return;
	const FString Sig = Signature();
	if (Sig != LastSig) Rebuild();
}

FString SCoHNavPanel::Signature() const
{
	const UCoHStoryComponent* C = Owner.Get();
	const UCoHHeroProgress* P = C ? C->Progress() : nullptr;
	if (!P || !P->bHasRecord || Tab == TEXT("map")) return Tab + (P && P->bHasRecord ? TEXT("+") : TEXT(""));
	const FCoHStoryProgress& S = P->Hero.Story;
	FString Out = FString::Printf(TEXT("%s|%s|%d|%d|%d|%d|%d|%d|%s|%s|"), *Tab, *Selected, bEarnedOnly ? 1 : 0, S.Contacts.Num(), S.Clues.Num(), S.Souvenirs.Num(),
		P->Hero.Badges.Owned.Num(), P->Hero.Level, *C->TaskForceLine, *C->NavWaypointName);
	for (const FCoHContactState& X : S.Contacts) Out += FString::FromInt(X.Points) + TEXT(",");
	for (const FCoHTaskState& T : S.Tasks) Out += T.Text + FString::Printf(TEXT("%d/%d%d;"), T.Progress, T.Needed, T.bComplete ? 1 : 0);
	return Out;
}

TSharedRef<SWidget> SCoHNavPanel::Row(const FString& Key, const FString& Head, const FString& Sub, const FString& Detail, FLinearColor Colour, const FVector* Way, const FString& WayName)
{
	const bool bSel = !Key.IsEmpty() && Selected == Key;
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight()[CoHNav::Label(Head, Colour, 11, true, true)];
	if (!Sub.IsEmpty()) Box->AddSlot().AutoHeight()[CoHNav::Label(Sub, CoHNav::Dim, 9, false, true)];
	if (bSel && !Detail.IsEmpty()) Box->AddSlot().AutoHeight().Padding(0, 4, 0, 0)[CoHNav::Label(Detail, CoHNav::Text, 10, false, true)];
	if (bSel && Way && !Way->IsZero())
	{
		const FVector W = *Way;
		Box->AddSlot().AutoHeight().HAlign(HAlign_Left).Padding(0, 4, 0, 0)
		[
			SNew(SButton).ContentPadding(FMargin(6, 1)).ButtonColorAndOpacity(FLinearColor(0.45f, 0.35f, 0.05f))
			.OnClicked_Lambda([this, W, WayName]()
			{
				if (UCoHStoryComponent* C = Owner.Get())
				{
					const bool bSame = C->NavWaypoint.Equals(W, 1.f);
					C->NavWaypoint = bSame ? FVector::ZeroVector : W;
					C->NavWaypointName = bSame ? FString() : WayName;
				}
				return FReply::Handled();
			})
			[CoHNav::Label(TEXT("Set waypoint"), FLinearColor::White, 9, true)]
		];
	}
	return SNew(SButton).ButtonColorAndOpacity(bSel ? FLinearColor(0.1f, 0.25f, 0.45f, 0.9f) : FLinearColor(0.05f, 0.08f, 0.14f, 0.6f)).ContentPadding(FMargin(6, 4))
		.OnClicked_Lambda([this, Key]() { Selected = Selected == Key ? FString() : Key; Rebuild(); return FReply::Handled(); })
		[Box];
}

void SCoHNavPanel::Rebuild()
{
	LastSig = Signature();
	if (!Body.IsValid()) return;
	Body->ClearChildren();
	static const TMap<FString, FString> Titles = { { TEXT("contacts"), TEXT("Contacts") }, { TEXT("missions"), TEXT("Missions") },
		{ TEXT("clues"), TEXT("Clues") }, { TEXT("souvenirs"), TEXT("Souvenirs") }, { TEXT("badges"), TEXT("Badges") }, { TEXT("map"), TEXT("Map") } };
	const FString* T = Titles.Find(Tab);
	Title->SetText(FText::FromString(T ? *T : Tab));
	const UCoHStoryComponent* C = Owner.Get();
	const UCoHHeroProgress* P = C ? C->Progress() : nullptr;
	if (!P || !P->bHasRecord) { Body->AddSlot().AutoHeight()[CoHNav::Label(TEXT("No hero loaded."), CoHNav::Dim)]; return; }
	if (Tab == TEXT("map")) { Body->AddSlot().FillHeight(1.f)[SNew(SCoHNavMap).Owner(Owner).Panel(this)]; return; }
	TSharedRef<SScrollBox> Scroll = SNew(SScrollBox);
	if (Tab == TEXT("contacts")) BuildContacts(*Scroll);
	else if (Tab == TEXT("clues")) BuildClues(*Scroll, false);
	else if (Tab == TEXT("souvenirs")) BuildClues(*Scroll, true);
	else if (Tab == TEXT("badges")) BuildBadges(*Scroll);
	else BuildMissions(*Scroll);
	Body->AddSlot().FillHeight(1.f)[Scroll];
}

void SCoHNavPanel::BuildContacts(SScrollBox& Scroll)
{
	const UCoHStoryComponent* C = Owner.Get();
	const UCoHStory* S = UCoHStory::Get(C);
	const FCoHStoryProgress& Pr = C->Progress()->Hero.Story;
	if (!S || Pr.Contacts.Num() == 0) { Scroll.AddSlot()[CoHNav::Label(TEXT("You have no contacts yet. Talk to the contacts in Atlas Park."), CoHNav::Dim, 10, false, true)]; return; }
	// the original sorts by relationship then name; contacts with a task to turn in first
	TArray<const FCoHContactState*> List;
	for (const FCoHContactState& X : Pr.Contacts) if (S->Contact(X.Contact)) List.Add(&X);
	List.Sort([S](const FCoHContactState& A, const FCoHContactState& B) { return S->Contact(A.Contact)->Name < S->Contact(B.Contact)->Name; });
	for (const FCoHContactState* X : List)
	{
		const FCoHStoryContact& D = *S->Contact(X->Contact);
		const bool bReady = Pr.Tasks.ContainsByPredicate([&](const FCoHTaskState& T) { return T.Contact == D.Id && T.bComplete; });
		const bool bBusy = Pr.Tasks.ContainsByPredicate([&](const FCoHTaskState& T) { return T.Contact == D.Id; });
		FString Sub = D.Profession + TEXT(" - ") + D.Location + TEXT(" - ") + CoHNav::Relationship(D, X->Points);
		if (bReady) Sub += TEXT(" - mission complete, return");
		else if (bBusy) Sub += TEXT(" - mission in progress");
		const FString Detail = D.Description.IsEmpty() ? FString() : C->Fill(D.Description, &D).Left(600);
		Scroll.AddSlot().Padding(0, 1)[Row(D.Id, D.Name, Sub, Detail, bReady ? CoHNav::Done : CoHNav::Gold, &D.Pos, D.Name)];
	}
}

void SCoHNavPanel::BuildMissions(SScrollBox& Scroll)
{
	const UCoHStoryComponent* C = Owner.Get();
	const UCoHStory* S = UCoHStory::Get(C);
	const FCoHStoryProgress& Pr = C->Progress()->Hero.Story;
	if (!C->TaskForceLine.IsEmpty())
	{
		const FVector W = C->TaskForceWaypoint;
		Scroll.AddSlot().Padding(0, 1)[Row(TEXT("#tf"), TEXT("Task force"), C->TaskForceLine, FString(), CoHNav::Gold, &W, TEXT("Task force"))];
	}
	if (Pr.Tasks.Num() == 0 && C->TaskForceLine.IsEmpty()) { Scroll.AddSlot()[CoHNav::Label(TEXT("You have no missions. Your contacts have work for you."), CoHNav::Dim, 10, false, true)]; return; }
	for (const FCoHTaskState& T : Pr.Tasks)
	{
		const FCoHStoryTask* D = S ? S->Task(T.Task) : nullptr;
		const FCoHStoryContact* Who = S ? S->Contact(T.Contact) : nullptr;
		FString Sub = Who ? TEXT("From ") + Who->Name : FString();
		if (T.Needed > 1 && !T.bComplete) Sub += FString::Printf(TEXT("%s%d of %d"), Sub.IsEmpty() ? TEXT("") : TEXT(" - "), T.Progress, T.Needed);
		if (T.bComplete) Sub += Sub.IsEmpty() ? TEXT("Complete: return to your contact") : TEXT(" - complete: return to your contact");
		const FString Detail = D ? C->Fill(T.bComplete ? D->Return : D->Active.IsEmpty() ? D->SendOff : D->Active, Who).Left(800) : FString();
		// a finished mission points back at its contact
		const FVector Way = T.bComplete && Who ? Who->Pos : T.Waypoint;
		Scroll.AddSlot().Padding(0, 1)[Row(T.Task, T.Text, Sub, Detail, T.bComplete ? CoHNav::Done : CoHNav::Text, &Way, T.bComplete && Who ? Who->Name : T.Text)];
	}
}

void SCoHNavPanel::BuildClues(SScrollBox& Scroll, bool bSouvenirs)
{
	const UCoHStoryComponent* C = Owner.Get();
	const UCoHStory* S = UCoHStory::Get(C);
	const FCoHStoryProgress& Pr = C->Progress()->Hero.Story;
	const TArray<FString>& Have = bSouvenirs ? Pr.Souvenirs : Pr.Clues;
	if (Have.Num() == 0) { Scroll.AddSlot()[CoHNav::Label(bSouvenirs ? TEXT("You have no souvenirs yet. Story arcs leave you one when you finish them.") : TEXT("You have no clues."), CoHNav::Dim, 10, false, true)]; return; }
	for (int32 i = Have.Num() - 1; i >= 0; --i)    // newest first
	{
		const FCoHClueDef* D = S ? (bSouvenirs ? S->Souvenirs : S->Clues).Find(Have[i].ToLower()) : nullptr;
		if (!D && S) D = (bSouvenirs ? S->Souvenirs : S->Clues).Find(Have[i]);
		const FString Name = D ? C->Fill(D->Name) : Have[i];
		Scroll.AddSlot().Padding(0, 1)[Row(Have[i], Name, FString(), D ? C->Fill(D->Text) : FString(), CoHNav::Gold, nullptr, FString())];
	}
}

void SCoHNavPanel::BuildBadges(SScrollBox& Scroll)
{
	const UCoHStoryComponent* C = Owner.Get();
	const UCoHBadges* B = UCoHBadges::Get(C);
	const FCoHBadgeState& Mine = C->Progress()->Hero.Badges;
	if (!B || B->Badges.Num() == 0) { Scroll.AddSlot()[CoHNav::Label(TEXT("No badge data (tools/badges/badges_game.py)."), CoHNav::Dim)]; return; }
	Scroll.AddSlot().Padding(0, 0, 0, 6)
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center)
		[CoHNav::Label(FString::Printf(TEXT("%d of %d badges"), Mine.Owned.Num(), B->Badges.Num()), CoHNav::Text, 10)]
		+ SHorizontalBox::Slot().AutoWidth()
		[
			SNew(SButton).ContentPadding(FMargin(6, 1)).OnClicked_Lambda([this]() { bEarnedOnly = !bEarnedOnly; Rebuild(); return FReply::Handled(); })
			[CoHNav::Label(bEarnedOnly ? TEXT("Show all") : TEXT("Earned only"), FLinearColor::White, 9, true)]
		]
	];
	// by category, as the original's badge tabs (Exploration, History, Accomplishment, Achievement, Defeat...)
	TArray<FString> Cats;
	for (const FCoHBadgeDef& D : B->Badges) Cats.AddUnique(D.Category);
	Cats.Sort();
	for (const FString& Cat : Cats)
	{
		bool bHeader = false;
		for (const FCoHBadgeDef& D : B->Badges)
		{
			if (D.Category != Cat) continue;
			const bool bOwned = Mine.Owned.Contains(D.Id);
			if (bEarnedOnly && !bOwned) continue;
			if (!bHeader)
			{
				bHeader = true;
				Scroll.AddSlot().Padding(0, 6, 0, 2)[CoHNav::Label(CoHNav::Category(Cat), CoHNav::Frame, 12, true)];
			}
			Scroll.AddSlot().Padding(0, 1)[Row(D.Id, D.Title, bOwned ? FString() : TEXT("not earned"), D.Text, bOwned ? CoHNav::Gold : CoHNav::Dim, nullptr, FString())];
		}
	}
	if (bEarnedOnly && Mine.Owned.Num() == 0) Scroll.AddSlot()[CoHNav::Label(TEXT("No badges yet. Explore the city and defeat villains to earn them."), CoHNav::Dim, 10, false, true)];
}

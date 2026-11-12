// The HQ lobby screen (Slate). Data and actions live in UCoHFrontend; this
// is only the look: an animated "mission control" over the city backdrop.
// Layout units are 1080p pixels (the game viewport's DPI scale handles the rest).
#pragma once

#include "CoreMinimal.h"
#include "Styling/SlateBrush.h"
#include "Widgets/SCompoundWidget.h"

class UCoHFrontend;
class SVerticalBox;
class SBox;
class SEditableTextBox;
class SUniformGridPanel;
struct FSlateDynamicImageBrush;

class COHREBORN_API SCoHLobby : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHLobby) {}
		SLATE_ARGUMENT(UCoHFrontend*, Frontend)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& Geometry, const FSlateRect& Culling,
		FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle& Style, bool bParentEnabled) const override;
	virtual void Tick(const FGeometry& Geometry, const double CurrentTime, const float DeltaTime) override;
	virtual FReply OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Key) override;
	virtual bool SupportsKeyboardFocus() const override { return true; }

	/** The in-game Esc panel: Return to HQ / Quit / Keep playing. */
	static TSharedRef<SWidget> MakeLeaveMenu(bool bHost, FSimpleDelegate OnHQ, FSimpleDelegate OnQuit, FSimpleDelegate OnStay);

private:
	enum class ETab : uint8 { Join, Host, Roster, Settings };

	// pages
	TSharedRef<SWidget> MakeTopBar();
	TSharedRef<SWidget> MakeJoinPage();
	TSharedRef<SWidget> MakeHostPage();
	TSharedRef<SWidget> MakeRosterPage();
	TSharedRef<SWidget> MakeSettingsPage();
	TSharedRef<SWidget> MakeRightColumn();
	TSharedRef<SWidget> MakeConnecting();

	// rows rebuilt when the frontend's revision changes
	void Rebuild();
	TSharedRef<SWidget> MakeServerRow(int32 Index);
	TSharedRef<SWidget> MakeLanRow(int32 Index);
	TSharedRef<SWidget> MakeHeroCard(int32 Index);

	// dialogs
	void OpenModal(TSharedRef<SWidget> Content);
	void CloseModal();
	void OpenPassword(int32 Index, bool bLan);
	void OpenServerEditor(int32 Index);   // -1 = add
	void OpenDirectConnect();
	void OpenNewHero();

	const struct FCoHServerEntry* Server(int32 Index) const;
	FText HeroChipText() const;

	TWeakObjectPtr<UCoHFrontend> F;
	ETab Tab = ETab::Join;
	int32 BuiltRevision = -1;

	TSharedPtr<SVerticalBox> ServerRows;
	TSharedPtr<SVerticalBox> LanRows;
	TSharedPtr<SVerticalBox> FeedRows;
	TSharedPtr<SUniformGridPanel> HeroGrid;
	TSharedPtr<SBox> ModalHost;
	bool bModal = false;

	// host form
	TSharedPtr<SEditableTextBox> HostName;
	TSharedPtr<SEditableTextBox> HostPassword;
	bool bShowHostPassword = false;

	// art
	TSharedPtr<FSlateDynamicImageBrush> Backdrop;
	FVector2D BackdropSize = FVector2D(1024, 660);
	FSlateBrush GlowBrush;
	FSlateBrush BeamBrush;
};

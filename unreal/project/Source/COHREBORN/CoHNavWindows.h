// The original's navigation windows (uiCompass.c, uiContact.c, uiMission.c,
// uiClue.c, uiBadge.c): the compass at the top of the screen with the
// waypoint, and the Contacts, Missions, Clues/Souvenirs and Badges windows
// its tabs open. Built on the player's PC from the replicated hero record
// (story and badges) and the story and badge data every PC loads.
// See docs/nav-windows.md.
#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

class UCoHStoryComponent;
class SBox;
class SVerticalBox;
class STextBlock;

class COHREBORN_API SCoHNavPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHNavPanel) {}
		SLATE_ARGUMENT(TWeakObjectPtr<UCoHStoryComponent>, Owner)
	SLATE_END_ARGS()

	void Construct(const FArguments& Args);
	virtual void Tick(const FGeometry& G, const double Now, const float Dt) override;

	/** "contacts", "missions", "clues", "souvenirs", "badges"; the open tab again closes it. */
	void Toggle(const FString& Tab);
	void ToggleCompass();
	bool IsOpen() const;

	/** The waypoint the compass shows: the player's pick, else the first mission's. */
	bool Waypoint(FVector& Out, FString& Name) const;

private:
	TWeakObjectPtr<UCoHStoryComponent> Owner;
	TSharedPtr<SBox> Window, Compass;
	TSharedPtr<STextBlock> Title;
	TSharedPtr<SVerticalBox> Body;
	FString Tab = TEXT("missions");
	FString Selected;
	FString LastSig;
	bool bEarnedOnly = true;

	FString Signature() const;
	void Rebuild();
	void BuildContacts(class SScrollBox& Scroll);
	void BuildMissions(class SScrollBox& Scroll);
	void BuildClues(class SScrollBox& Scroll, bool bSouvenirs);
	void BuildBadges(class SScrollBox& Scroll);
	TSharedRef<SWidget> TabButton(const FString& Id, const FString& Label);
	TSharedRef<SWidget> Row(const FString& Key, const FString& Head, const FString& Sub, const FString& Detail, FLinearColor Colour, const FVector* Way, const FString& WayName);
};

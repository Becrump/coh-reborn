// The Hero Corps terminal (docs/lobby.md): the HQ's first screen. The
// player picks which hero to "call", sees it on the pedestal (ACoHHeroStage),
// reads its profile and Nemesis file, restyles its powers and plays them on
// the hero, then Calls it, which opens Deploy (SCoHLobby's join/host pages).
// Everything here is local to this PC: hero files live in Saved/Heroes.
#pragma once

#include "CoreMinimal.h"
#include "Styling/SlateBrush.h"
#include "Widgets/SCompoundWidget.h"

class UCoHFrontend;
class SVerticalBox;
class ACoHHeroCharacter;

class COHREBORN_API SCoHTerminal : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHTerminal) {}
		SLATE_ARGUMENT(UCoHFrontend*, Frontend)
		/** CALL <hero>: go on to Deploy (join or host). */
		SLATE_EVENT(FSimpleDelegate, OnCall)
		/** RECRUIT NEW HERO: the lobby's new hero dialog. */
		SLATE_EVENT(FSimpleDelegate, OnNewHero)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	virtual void Tick(const FGeometry& Geometry, const double CurrentTime, const float DeltaTime) override;

private:
	enum class EPage : uint8 { Profile, Powers, Nemesis, Database };

	TSharedRef<SWidget> MakeTopBar();
	TSharedRef<SWidget> MakeRoster();
	TSharedRef<SWidget> MakeCenter();
	TSharedRef<SWidget> MakeFile();
	TSharedRef<SWidget> MakeProfile();
	TSharedRef<SWidget> MakePowers();

	/** Lists that depend on the hero: rebuilt when the hero or roster changes. */
	void Rebuild();
	void RebuildPowers();
	void RebuildNemesis();
	void RebuildDatabase();

	ACoHHeroCharacter* Hero() const;
	FString HeroName() const;
	const FSlateBrush* PowerIcon(FName Power);
	/** Restyle the selected power on the pedestal hero, then play it. */
	void SetEmitter(int32 Emitter);
	void SetTint(const FLinearColor& Tint);

	TWeakObjectPtr<UCoHFrontend> F;
	FSimpleDelegate OnCall, OnNewHero;
	EPage Page = EPage::Profile;
	int32 BuiltRevision = -1;
	TWeakObjectPtr<ACoHHeroCharacter> BuiltHero;
	FName SelectedPower;
	bool bLooksChanged = false;

	TSharedPtr<SVerticalBox> RosterRows;
	TSharedPtr<SVerticalBox> PowerRows;
	TSharedPtr<SVerticalBox> NemesisBox;
	TSharedPtr<SVerticalBox> DatabaseBox;
	TMap<FName, TSharedPtr<FSlateBrush>> IconBrushes;
};

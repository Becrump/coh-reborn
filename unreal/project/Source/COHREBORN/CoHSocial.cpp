#include "CoHSocial.h"
#include "CoHStory.h"
#include "CoHPowers.h"
#include "CoHBadges.h"
#include "CoHHeroProgress.h"
#include "CoHCombat.h"
#include "CoHItems.h"
#include "CoHZoneEvents.h"
#include "CoHCivilians.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "Net/UnrealNetwork.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/SWeakWidget.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Text/STextBlock.h"

static FLinearColor CoHChatColour(ECoHChat C)
{
	switch (C)
	{
	case ECoHChat::Local: return FLinearColor(1.f, 1.f, 1.f);
	case ECoHChat::Broadcast: return FLinearColor(1.f, 0.9f, 0.45f);
	case ECoHChat::Team: return FLinearColor(0.45f, 0.85f, 1.f);
	case ECoHChat::Tell: return FLinearColor(0.4f, 1.f, 0.5f);
	default: return FLinearColor(1.f, 0.65f, 0.35f);
	}
}

static const TCHAR* CoHChatPrefix(ECoHChat C)
{
	switch (C)
	{
	case ECoHChat::Local: return TEXT("[Local] ");
	case ECoHChat::Broadcast: return TEXT("[Broadcast] ");
	case ECoHChat::Team: return TEXT("[Team] ");
	case ECoHChat::Tell: return TEXT("[Tell] ");
	default: return TEXT("");
	}
}

// ------------------------------------------------------------------ the window
class SCoHChatPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHChatPanel) {}
		SLATE_ARGUMENT(TWeakObjectPtr<UCoHSocial>, Owner)
	SLATE_END_ARGS()

	void Construct(const FArguments& Args)
	{
		Owner = Args._Owner;
		// the panel fills the whole viewport: only its windows take clicks, the rest goes through
		SetVisibility(EVisibility::SelfHitTestInvisible);
		ChildSlot
		.HAlign(HAlign_Left).VAlign(VAlign_Bottom).Padding(FMargin(12, 0, 0, 150))
		[
			SAssignNew(Root, SBox).WidthOverride(460)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 4)[SAssignNew(TeamBox, SVerticalBox)]
				+ SVerticalBox::Slot().AutoHeight()
				[
					SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.f, 0.02f, 0.08f, 0.55f)).Padding(6)
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot().AutoHeight()[SNew(SBox).HeightOverride(170)[SAssignNew(Scroll, SScrollBox)]]
						+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)
						[
							SAssignNew(Input, SEditableTextBox)
							.HintText(FText::FromString(TEXT("Enter to chat: /l /b /t /tell name, /invite name /leave")))
							.ClearKeyboardFocusOnCommit(true)
							.OnTextCommitted(this, &SCoHChatPanel::Committed)
						]
					]
				]
			]
		];
	}

	void Focus()
	{
		Root->SetVisibility(EVisibility::Visible);
		FSlateApplication::Get().SetKeyboardFocus(Input, EFocusCause::SetDirectly);
	}
	void Toggle() { Root->SetVisibility(Root->GetVisibility() == EVisibility::Visible ? EVisibility::Collapsed : EVisibility::Visible); }

	virtual void Tick(const FGeometry& G, const double Now, const float Dt) override
	{
		SCompoundWidget::Tick(G, Now, Dt);
		const UCoHSocial* S = Owner.Get();
		if (!S) return;
		if (S->LinesVersion != Shown)
		{
			Shown = S->LinesVersion;
			Scroll->ClearChildren();
			for (const FCoHChatLine& L : S->Lines)
			{
				const FString T = FString(CoHChatPrefix(L.Channel)) + (L.From.IsEmpty() ? L.Text : L.From + TEXT(": ") + L.Text);
				Scroll->AddSlot()[SNew(STextBlock).Text(FText::FromString(T)).AutoWrapText(true).ColorAndOpacity(CoHChatColour(L.Channel))
					.Font(FCoreStyle::GetDefaultFontStyle("Regular", 10)).ShadowOffset(FVector2D(1, 1))];
			}
			Scroll->ScrollToEnd();
		}
		if ((NextTeam -= Dt) <= 0.f) { NextTeam = 0.5f; RebuildTeam(); }
	}

private:
	TWeakObjectPtr<UCoHSocial> Owner;
	TSharedPtr<SBox> Root;
	TSharedPtr<SVerticalBox> TeamBox;
	TSharedPtr<SScrollBox> Scroll;
	TSharedPtr<SEditableTextBox> Input;
	int32 Shown = -1;
	float NextTeam = 0.f;

	void Committed(const FText& Text, ETextCommit::Type How)
	{
		if (How == ETextCommit::OnEnter)
		{
			const FString Line = Text.ToString().TrimStartAndEnd();
			if (UCoHSocial* S = Owner.Get()) if (!Line.IsEmpty()) S->Submit(Line);
		}
		Input->SetText(FText::GetEmpty());
		FSlateApplication::Get().SetAllUserFocusToGameViewport();
	}

	/** The team window: each teammate with health, as the original's team list. */
	void RebuildTeam()
	{
		TeamBox->ClearChildren();
		const UCoHSocial* S = Owner.Get();
		UWorld* W = S ? S->GetWorld() : nullptr;
		if (!W || S->TeamId == 0) return;
		for (TActorIterator<APawn> It(W); It; ++It)
		{
			const UCoHSocial* O = UCoHSocial::Of(*It);
			if (!O || O->TeamId != S->TeamId) continue;
			const UCoHPowerComponent* P = UCoHPowerComponent::Of(*It);
			const float Hp = P && P->MaxHealth > 0.f ? P->Health / P->MaxHealth : 1.f;
			const FString T = FString::Printf(TEXT("%s%s  %d%%"), O->bLeader ? TEXT("* ") : TEXT(""), *O->Name(), FMath::RoundToInt(Hp * 100.f));
			TeamBox->AddSlot().AutoHeight()
			[
				SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).Padding(FMargin(6, 1))
				.BorderBackgroundColor(FLinearColor(0.05f + 0.5f * (1.f - Hp), 0.25f * Hp, 0.45f * Hp, 0.6f))
				[SNew(STextBlock).Text(FText::FromString(T)).ColorAndOpacity(FLinearColor::White).Font(FCoreStyle::GetDefaultFontStyle("Bold", 10))]
			];
		}
	}
};

// ------------------------------------------------------------------ UCoHSocial
UCoHSocial::UCoHSocial()
{
	SetIsReplicatedByDefault(true);
}

void UCoHSocial::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(UCoHSocial, TeamId);
	DOREPLIFETIME(UCoHSocial, bLeader);
}

UCoHSocial* UCoHSocial::Of(const AActor* A) { return A ? A->FindComponentByClass<UCoHSocial>() : nullptr; }

bool UCoHSocial::SameTeam(const AActor* A, const AActor* B)
{
	if (A == B) return A != nullptr;
	const UCoHSocial* X = Of(A); const UCoHSocial* Y = Of(B);
	return X && Y && X->TeamId != 0 && X->TeamId == Y->TeamId;
}

FString UCoHSocial::Name() const
{
	if (const UCoHPowerComponent* P = UCoHPowerComponent::Of(GetOwner())) if (!P->DisplayName.IsEmpty()) return P->DisplayName;
	if (const APawn* Pawn = Cast<APawn>(GetOwner())) if (const APlayerState* PS = Pawn->GetPlayerState()) return PS->GetPlayerName();
	return GetNameSafe(GetOwner());
}

void UCoHSocial::BeginPlay()
{
	Super::BeginPlay();
	const APawn* Pawn = Cast<APawn>(GetOwner());
	if (Pawn && Pawn->IsLocallyControlled() && GEngine && GEngine->GameViewport)
	{
		Panel = SNew(SCoHChatPanel).Owner(this);
		PanelHost = SNew(SWeakWidget).Visibility(EVisibility::SelfHitTestInvisible).PossiblyNullContent(Panel);
		GEngine->GameViewport->AddViewportWidgetContent(PanelHost.ToSharedRef(), 8);
		Lines.Add({ ECoHChat::System, FString(), TEXT("Welcome to Paragon City. Enter to chat, /invite name to team up.") });
		++LinesVersion;
	}
}

void UCoHSocial::EndPlay(const EEndPlayReason::Type Reason)
{
	if (GetOwnerRole() == ROLE_Authority && TeamId != 0) Leave();
	if (PanelHost.IsValid() && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(PanelHost.ToSharedRef());
	PanelHost.Reset(); Panel.Reset();
	Super::EndPlay(Reason);
}

void UCoHSocial::FocusChat() { if (Panel.IsValid()) Panel->Focus(); }
void UCoHSocial::ToggleChat() { if (Panel.IsValid()) Panel->Toggle(); }

void UCoHSocial::Submit(const FString& Line)
{
	if (!Line.StartsWith(TEXT("/"))) { ServerSay(DefaultChannel, FString(), Line); return; }
	FString Cmd = Line.Mid(1), Rest;
	if (!Cmd.Split(TEXT(" "), &Cmd, &Rest)) Rest.Empty();
	Cmd = Cmd.ToLower(); Rest.TrimStartAndEndInline();
	if (Cmd == TEXT("l") || Cmd == TEXT("local")) { DefaultChannel = ECoHChat::Local; if (!Rest.IsEmpty()) ServerSay(ECoHChat::Local, FString(), Rest); }
	else if (Cmd == TEXT("b") || Cmd == TEXT("broadcast") || Cmd == TEXT("y") || Cmd == TEXT("yell")) { DefaultChannel = ECoHChat::Broadcast; if (!Rest.IsEmpty()) ServerSay(ECoHChat::Broadcast, FString(), Rest); }
	else if (Cmd == TEXT("t") || Cmd == TEXT("tm") || Cmd == TEXT("g") || Cmd == TEXT("group")) { DefaultChannel = ECoHChat::Team; if (!Rest.IsEmpty()) ServerSay(ECoHChat::Team, FString(), Rest); }
	else if (Cmd == TEXT("tell") || Cmd == TEXT("p") || Cmd == TEXT("private"))
	{
		FString Who, Text;
		if (Rest.Split(TEXT(","), &Who, &Text)) ServerSay(ECoHChat::Tell, Who.TrimStartAndEnd(), Text.TrimStartAndEnd());
		else { Lines.Add({ ECoHChat::System, FString(), TEXT("Use /tell name, message") }); ++LinesVersion; }
	}
	else if (Cmd == TEXT("contacts") || Cmd == TEXT("missions") || Cmd == TEXT("clues") || Cmd == TEXT("souvenirs") || Cmd == TEXT("badges") || Cmd == TEXT("nav") || Cmd == TEXT("map"))
	{
		// the nav windows (CoHNavWindows.h); /nav shows or hides the compass
		if (UCoHStoryComponent* St = UCoHStoryComponent::Of(GetOwner())) { if (Cmd == TEXT("nav")) St->ToggleCompass(); else St->ToggleNavWindow(Cmd); }
	}
	else if (Cmd == TEXT("civilians"))
	{
		// the original civilians and traffic run on each PC: on, off or a status line
		ACoHCivilians* C = ACoHCivilians::Get(GetWorld());
		Lines.Add({ ECoHChat::System, FString(), C ? C->Command(Rest.TrimStartAndEnd()) : FString(TEXT("No original civilians on this map.")) });
		++LinesVersion;
	}
	else if (Cmd == TEXT("badgelist") || Cmd == TEXT("cluelist") || Cmd == TEXT("souvenirlist"))
		ServerCommand(Cmd.LeftChop(4) + TEXT("s"), Rest);   // the old chat lists
	else if (Cmd == TEXT("invite") || Cmd == TEXT("i") || Cmd == TEXT("accept") || Cmd == TEXT("decline") || Cmd == TEXT("leave")
		|| Cmd == TEXT("kick") || Cmd == TEXT("team") || Cmd == TEXT("who") || Cmd == TEXT("respec") || Cmd == TEXT("releasepets") || Cmd == TEXT("release")
		|| Cmd == TEXT("zoneevent"))
		ServerCommand(Cmd == TEXT("i") ? FString(TEXT("invite")) : Cmd, Rest);
	else if (Cmd == TEXT("inventions") || Cmd == TEXT("invent") || Cmd == TEXT("salvage") || Cmd == TEXT("recipes"))
	{
		if (UCoHEnhancements* E = UCoHEnhancements::Of(GetOwner())) E->ToggleInventions();
	}
	else { Lines.Add({ ECoHChat::System, FString(), TEXT("Unknown command /") + Cmd }); ++LinesVersion; }
}

void UCoHSocial::Tell(ECoHChat Channel, const FString& From, const FString& Text) { ClientChat(Channel, From, Text); }

void UCoHSocial::ClientChat_Implementation(ECoHChat Channel, const FString& From, const FString& Text)
{
	Lines.Add({ Channel, From, Text });
	if (Lines.Num() > 80) Lines.RemoveAt(0, Lines.Num() - 80);
	++LinesVersion;
}

TArray<UCoHSocial*> UCoHSocial::AllHeroes() const
{
	TArray<UCoHSocial*> Out;
	if (UWorld* W = GetWorld())
		for (FConstPlayerControllerIterator It = W->GetPlayerControllerIterator(); It; ++It)
			if (const APlayerController* PC = It->Get())
				if (UCoHSocial* S = Of(PC->GetPawn())) Out.Add(S);
	return Out;
}

UCoHSocial* UCoHSocial::FindByName(const FString& Who) const
{
	UCoHSocial* Partial = nullptr;
	for (UCoHSocial* S : AllHeroes())
	{
		if (S->Name().Equals(Who, ESearchCase::IgnoreCase)) return S;
		if (!Partial && S->Name().StartsWith(Who, ESearchCase::IgnoreCase)) Partial = S;
	}
	return Partial;
}

int32 UCoHSocial::CombatLevelFor(const AActor* Hero, int32 OwnLevel)
{
	const UCoHSocial* Me = Of(Hero);
	if (!Me || Me->TeamId == 0 || Me->bLeader) return 0;
	for (APawn* P : Me->TeamMembers())
	{
		const UCoHSocial* S = Of(P);
		const UCoHHeroProgress* L = S && S->bLeader ? UCoHHeroProgress::Of(P) : nullptr;
		if (!L || !L->bHasRecord) continue;
		const int32 Lead = L->Hero.Level;
		if (OwnLevel < Lead - 1) return Lead - 1;      // sidekick
		if (OwnLevel > Lead) return Lead;              // exemplar
		return 0;
	}
	return 0;
}

void UCoHSocial::RefreshTeamLevels()
{
	TArray<APawn*> Who = TeamMembers();
	if (APawn* Self = Cast<APawn>(GetOwner())) Who.AddUnique(Self);
	for (APawn* P : Who) if (UCoHHeroProgress* H = UCoHHeroProgress::Of(P)) if (H->bHasRecord) H->Apply(false);
}

TArray<APawn*> UCoHSocial::TeamMembers() const
{
	TArray<APawn*> Out;
	if (TeamId == 0) { if (APawn* P = Cast<APawn>(GetOwner())) Out.Add(P); return Out; }
	for (UCoHSocial* S : AllHeroes()) if (S->TeamId == TeamId) if (APawn* P = Cast<APawn>(S->GetOwner())) Out.Add(P);
	return Out;
}

void UCoHSocial::SayTeam(const FString& Text)
{
	for (APawn* P : TeamMembers()) if (UCoHSocial* S = Of(P)) S->Tell(ECoHChat::System, FString(), Text);
}

void UCoHSocial::ServerSay_Implementation(ECoHChat Channel, const FString& To, const FString& Text)
{
	const FString Msg = Text.Left(255);
	if (Msg.IsEmpty()) return;
	const FString From = Name();
	switch (Channel)
	{
	case ECoHChat::Broadcast:
		for (UCoHSocial* S : AllHeroes()) S->Tell(Channel, From, Msg);
		break;
	case ECoHChat::Team:
		if (TeamId == 0) { Tell(ECoHChat::System, FString(), TEXT("You are not on a team.")); break; }
		for (APawn* P : TeamMembers()) if (UCoHSocial* S = Of(P)) S->Tell(Channel, From, Msg);
		break;
	case ECoHChat::Tell:
		if (UCoHSocial* S = FindByName(To))
		{
			S->Tell(Channel, From, Msg);
			if (S != this) Tell(Channel, TEXT("To ") + S->Name(), Msg);
		}
		else Tell(ECoHChat::System, FString(), FString::Printf(TEXT("%s is not online."), *To));
		break;
	default:
	{
		const FVector Here = GetOwner()->GetActorLocation();
		for (UCoHSocial* S : AllHeroes())
			if (FVector::Dist(S->GetOwner()->GetActorLocation(), Here) <= LocalRangeCm) S->Tell(ECoHChat::Local, From, Msg);
	}
	}
}

void UCoHSocial::ServerCommand_Implementation(const FString& Command, const FString& Arg)
{
	if (Command == TEXT("invite")) Invite(Arg);
	else if (Command == TEXT("accept")) Accept();
	else if (Command == TEXT("decline"))
	{
		if (UCoHSocial* I = InvitedBy.Get()) I->Tell(ECoHChat::System, FString(), Name() + TEXT(" declined your invitation."));
		InvitedBy.Reset();
	}
	else if (Command == TEXT("leave")) Leave();
	else if (Command == TEXT("kick")) Kick(Arg);
	else if (Command == TEXT("team"))
	{
		if (TeamId == 0) { Tell(ECoHChat::System, FString(), TEXT("You are not on a team.")); return; }
		TArray<FString> Names;
		for (APawn* P : TeamMembers()) if (const UCoHSocial* S = Of(P)) Names.Add(S->bLeader ? S->Name() + TEXT(" (leader)") : S->Name());
		Tell(ECoHChat::System, FString(), TEXT("Team: ") + FString::Join(Names, TEXT(", ")));
	}
	else if (Command == TEXT("badges"))
	{
		if (const UCoHBadges* B = UCoHBadges::Get(this)) Tell(ECoHChat::System, FString(), B->Describe(GetOwner()));
	}
	else if (Command == TEXT("respec"))
	{
		if (UCoHHeroProgress* H = UCoHHeroProgress::Of(GetOwner())) H->ServerRespec_Implementation();
	}
	else if (Command == TEXT("zoneevent"))
	{
		// host only: start one now, stop them, or list them
		const APawn* Me = Cast<APawn>(GetOwner());
		ACoHZoneEvents* Z = ACoHZoneEvents::Get(GetWorld());
		if (!Me || !Me->IsLocallyControlled()) Tell(ECoHChat::System, FString(), TEXT("Only the host can start zone events."));
		else if (!Z) Tell(ECoHChat::System, FString(), TEXT("No zone events on this map."));
		else Tell(ECoHChat::System, FString(), Z->Command(Arg.TrimStartAndEnd(), const_cast<APawn*>(Me)));
	}
	else if (Command == TEXT("releasepets") || Command == TEXT("release"))
	{
		ACoHCombatEnemy::DismissPets(GetOwner(), NAME_None);
		Tell(ECoHChat::System, FString(), TEXT("Your pets are dismissed."));
	}
	else if (Command == TEXT("clues") || Command == TEXT("souvenirs"))
	{
		if (const UCoHStoryComponent* St = UCoHStoryComponent::Of(GetOwner())) Tell(ECoHChat::System, FString(), St->DescribeClues(Command == TEXT("souvenirs")));
	}
	else if (Command == TEXT("who"))
	{
		TArray<FString> Names;
		for (UCoHSocial* S : AllHeroes()) Names.Add(S->Name());
		Tell(ECoHChat::System, FString(), FString::Printf(TEXT("%d online: %s"), Names.Num(), *FString::Join(Names, TEXT(", "))));
	}
}

void UCoHSocial::Invite(const FString& Who)
{
	UCoHSocial* S = FindByName(Who);
	if (!S || S == this) { Tell(ECoHChat::System, FString(), FString::Printf(TEXT("No one called %s is online."), *Who)); return; }
	if (TeamId != 0 && !bLeader) { Tell(ECoHChat::System, FString(), TEXT("Only the team leader can invite.")); return; }
	if (S->TeamId != 0) { Tell(ECoHChat::System, FString(), S->Name() + TEXT(" is already on a team.")); return; }
	if (const ACoHStoryDirector* D = ACoHStoryDirector::Get(GetWorld()))
		if (D->TaskForceOf(GetOwner())) { Tell(ECoHChat::System, FString(), TEXT("Your team is on a task force: no one can join until it is over.")); return; }
	if (TeamMembers().Num() >= MaxTeam) { Tell(ECoHChat::System, FString(), TEXT("Your team is full.")); return; }
	S->InvitedBy = this;
	S->Tell(ECoHChat::System, FString(), Name() + TEXT(" invites you to join a team. Type /accept or /decline."));
	Tell(ECoHChat::System, FString(), TEXT("You invited ") + S->Name() + TEXT("."));
}

int32 UCoHSocial::NewTeamId()
{
	static int32 NextTeam = 1;
	return NextTeam++;
}

void UCoHSocial::Accept()
{
	UCoHSocial* L = InvitedBy.Get();
	InvitedBy.Reset();
	if (!L) { Tell(ECoHChat::System, FString(), TEXT("No invitation to accept.")); return; }
	if (TeamId != 0) Leave();
	if (L->TeamId == 0)
	{
		L->TeamId = NewTeamId();
		L->bLeader = true;
	}
	if (L->TeamMembers().Num() >= MaxTeam) { Tell(ECoHChat::System, FString(), TEXT("That team is full.")); return; }
	TeamId = L->TeamId;
	bLeader = false;
	SayTeam(Name() + TEXT(" has joined the team."));
	RefreshTeamLevels();
}

void UCoHSocial::Leave()
{
	if (TeamId == 0) { Tell(ECoHChat::System, FString(), TEXT("You are not on a team.")); return; }
	const int32 Old = TeamId;
	const bool bWasLeader = bLeader;
	SayTeam(Name() + TEXT(" has left the team."));
	TeamId = 0; bLeader = false;
	TArray<UCoHSocial*> Rest;
	for (UCoHSocial* S : AllHeroes()) if (S->TeamId == Old) Rest.Add(S);
	ACoHStoryDirector* D = ACoHStoryDirector::Get(GetWorld());
	const bool bTaskForce = D && Rest.Num() && D->TaskForceOf(Rest[0]->GetOwner());
	if (Rest.Num() == 1 && bTaskForce)
	{
		// a task force goes on with whoever is left, even one hero
		if (!Rest[0]->bLeader) { Rest[0]->bLeader = true; Rest[0]->Tell(ECoHChat::System, FString(), TEXT("You are now the team leader.")); }
	}
	else if (Rest.Num() == 1) { Rest[0]->TeamId = 0; Rest[0]->bLeader = false; Rest[0]->Tell(ECoHChat::System, FString(), TEXT("Your team has disbanded.")); }
	else if (bWasLeader && Rest.Num() > 1)
	{
		Rest[0]->bLeader = true;
		for (UCoHSocial* S : Rest) S->Tell(ECoHChat::System, FString(), Rest[0]->Name() + TEXT(" is now the team leader."));
	}
	RefreshTeamLevels();      // back to this hero's own level
	if (Rest.Num()) Rest[0]->RefreshTeamLevels();
	if (D) D->LeftTeam(Cast<APawn>(GetOwner()), Old);
}

void UCoHSocial::Kick(const FString& Who)
{
	UCoHSocial* S = FindByName(Who);
	if (!bLeader || TeamId == 0) { Tell(ECoHChat::System, FString(), TEXT("Only the team leader can kick.")); return; }
	if (!S || S == this || S->TeamId != TeamId) { Tell(ECoHChat::System, FString(), FString::Printf(TEXT("%s is not on your team."), *Who)); return; }
	S->Tell(ECoHChat::System, FString(), TEXT("You were removed from the team."));
	S->Leave();
}

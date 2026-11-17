// Chat and teams from the original game (docs/social.md).
//
//   Chat     Enter opens the chat line; channels as the original: local (people
//            near you), broadcast (the whole city), team, tells. Slash commands:
//            /l /b /t(eam) /tell name, text /invite name /accept /decline /leave
//            /kick name /team (who is on it) /who
//   Teams    up to 8 heroes. Teammates share defeat XP and influence (each in
//            range gets the team's share), can use each other's mission doors,
//            and show in the team window above the chat.
//
// The host owns teams and routes chat; each hero carries a UCoHSocial.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "CoHSocial.generated.h"

class SCoHChatPanel;
class APawn;

UENUM()
enum class ECoHChat : uint8 { Local, Broadcast, Team, Tell, System };

struct FCoHChatLine { ECoHChat Channel = ECoHChat::System; FString From, Text; };

UCLASS(ClassGroup = CoH, meta = (BlueprintSpawnableComponent))
class COHREBORN_API UCoHSocial : public UActorComponent
{
	GENERATED_BODY()
public:
	UCoHSocial();
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	static UCoHSocial* Of(const AActor* A);

	/** Local chat reaches heroes this near (the original: 100 feet). */
	UPROPERTY(EditAnywhere, Category = "CoH|Social") float LocalRangeCm = 3048.f;
	UPROPERTY(EditAnywhere, Category = "CoH|Social") int32 MaxTeam = 8;

	/** 0: not on a team. */
	UPROPERTY(Replicated) int32 TeamId = 0;
	UPROPERTY(Replicated) bool bLeader = false;

	/** Are these two heroes on the same team (or the same hero)? */
	static bool SameTeam(const AActor* A, const AActor* B);
	/** Host: every hero on this one's team (itself included; just itself when not teamed). */
	TArray<APawn*> TeamMembers() const;
	/** The hero's name as others see it. */
	FString Name() const;

	/** The player's own PC: a line typed in the chat box (text or a /command). */
	void Submit(const FString& Line);
	/** The player's own PC: focus the chat line (Enter). */
	void FocusChat();
	void ToggleChat();
	/** Host: a line for this hero's chat window. */
	void Tell(ECoHChat Channel, const FString& From, const FString& Text);

	UFUNCTION(Server, Reliable) void ServerSay(ECoHChat Channel, const FString& To, const FString& Text);
	UFUNCTION(Server, Reliable) void ServerCommand(const FString& Command, const FString& Arg);
	UFUNCTION(Client, Reliable) void ClientChat(ECoHChat Channel, const FString& From, const FString& Text);

	// for the window
	TArray<FCoHChatLine> Lines;
	int32 LinesVersion = 0;
	ECoHChat DefaultChannel = ECoHChat::Local;
private:
	/** host: who invited this hero (pending) */
	TWeakObjectPtr<UCoHSocial> InvitedBy;
	void Invite(const FString& Who);
	void Accept();
	void Leave();
	void Kick(const FString& Who);
	UCoHSocial* FindByName(const FString& Who) const;
	TArray<UCoHSocial*> AllHeroes() const;
	void SayTeam(const FString& Text);
	TSharedPtr<SCoHChatPanel> Panel;
	TSharedPtr<class SWidget> PanelHost;
};

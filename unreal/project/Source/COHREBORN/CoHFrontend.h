// The HQ lobby: the game's front end (docs/lobby.md).
//
// The game starts on the frontend map (GameDefaultMap, an empty level run by
// ACoHFrontendGameMode) and UCoHFrontend shows the HQ screen over it:
//   - Host: open a zone as a listen server, optional password, max heroes.
//   - Join: friends' saved servers with live status from the UDP beacon
//     (CoHLobbyNet.h), servers found on the home network, direct connect.
//   - Hero roster: the hero files in Saved/Heroes, pick one or start a new
//     one from an archetype starter.
// Wrong password, server full, or a dropped connection lands back here with
// a message. In game, Esc offers "Return to HQ".
//
// Lobby data (saved servers, chosen hero, last host settings) lives in
// Saved/CoHLobby.json on each PC.
#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "Engine/EngineBaseTypes.h"
#include "GameFramework/GameModeBase.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "CoHLobbyNet.h"
#include "CoHFrontend.generated.h"

class SCoHLobby;
class UTexture2D;

/** A zone the host can start in. */
USTRUCT()
struct FCoHZoneChoice
{
	GENERATED_BODY()
	UPROPERTY(Config) FString Name;
	/** Long package name, e.g. /Game/AtlasPark4/AtlasPark_DressingStudy_Nanite */
	UPROPERTY(Config) FString Map;
	/** false: shown greyed out ("after zone import"). */
	UPROPERTY(Config) bool bReady = true;
};

/** A friend's server saved in the lobby, plus what the beacon last said. */
struct FCoHServerEntry
{
	// saved
	FString Name;
	FString Host;            // IP or name (Tailscale MagicDNS names work)
	int32 Port = CoHLobby::DefaultGamePort;
	FString Password;        // kept only when bRemember
	bool bRemember = false;
	FDateTime LastSeen;      // last time it answered, MinValue = never

	// live
	enum class EState : uint8 { Checking, Online, Offline, BadAddress };
	EState State = EState::Checking;
	FCoHServerInfo Info;
	float PingMs = 0.f;
	TSharedPtr<FInternetAddr> Beacon;   // resolved host, port + 1
	FString ResolvedIp;
	bool bResolving = false;
	uint32 LastNonce = 0;
	double FirstQuery = -1.0;
	double LastReply = -1.0;

	FString Key() const { return Host.ToLower() + TEXT(":") + FString::FromInt(Port); }
	bool CanJoin() const { return State == EState::Online && Info.Version == CoHLobby::NetVersion; }
};

/** A server that answered the LAN broadcast and isn't saved. */
struct FCoHLanServer
{
	FString Ip;
	FCoHServerInfo Info;
	float PingMs = 0.f;
	double LastReply = 0.0;
};

/** One hero file in Saved/Heroes. */
struct FCoHHeroCard
{
	FString File;            // base name, as -Hero= takes it
	FString Name;
	FString Class;           // Class_Blaster
	FString Origin;
	FString Primary;         // Blaster_Ranged.Fire_Blast
	FString Secondary;
	int32 Level = 1;
	FString ArchetypeName() const;   // "Blaster"
	FString SetsLine() const;        // "Fire Blast · Fire Manipulation"
};

/** Last host settings, remembered. */
struct FCoHHostSettings
{
	FString ServerName = TEXT("My Base");
	FString Password;
	int32 MaxPlayers = 7;
	int32 Zone = 0;
	bool bShowOnLan = true;
	bool bRemember = true;
};

/** One address of this PC, for "tell your friends". */
struct FCoHLocalAddress
{
	FString Ip;
	FString Kind;            // "Tailscale", "Home network", "Other"
};

UCLASS(Config = Game)
class COHREBORN_API UCoHFrontend : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	static UCoHFrontend* Get(const UObject* WorldContext);

	// ---- config (DefaultGame.ini [/Script/COHREBORN.CoHFrontend])
	/** The map the game returns to for the HQ (also GameDefaultMap). */
	UPROPERTY(Config) FString FrontendMap = TEXT("/Engine/Maps/Entry");
	/** Backdrop art, relative to Content (PNG, read at runtime). */
	UPROPERTY(Config) FString BackdropImage = TEXT("Frontend/HQ_Backdrop.png");
	UPROPERTY(Config) TArray<FCoHZoneChoice> Zones;
	/** Lines for the news ticker at the bottom of the HQ. */
	UPROPERTY(Config) TArray<FString> NewsLines;
	/** Seconds between status checks. */
	UPROPERTY(Config) float StatusInterval = 4.f;

	// ---- servers
	const TArray<FCoHServerEntry>& Servers() const { return ServerList; }
	const TArray<FCoHLanServer>& LanServers() const { return LanList; }
	void AddServer(const FString& Name, const FString& HostAndPort, const FString& Password, bool bRemember);
	void EditServer(int32 Index, const FString& Name, const FString& HostAndPort, const FString& Password, bool bRemember);
	void RemoveServer(int32 Index);
	void RefreshNow();
	/** Bumped whenever the list changes shape (the widget rebuilds rows). */
	int32 ServersRevision() const { return Revision; }

	// ---- play
	/** Join a saved server. An empty Password uses the remembered one. */
	void Join(int32 Index, const FString& Password, bool bRememberPassword);
	void JoinLan(int32 LanIndex, const FString& Password);
	/** "host[:port]" typed by hand. */
	void JoinAddress(const FString& HostAndPort, const FString& Password);
	void CancelJoin();
	void Host(const FCoHHostSettings& Settings);
	FCoHHostSettings& HostSettings() { return LastHost; }
	TArray<FCoHLocalAddress> LocalAddresses() const;
	bool IsConnecting() const { return bConnecting; }
	/** The running server's name and password, so they survive monorail travel. */
	FString HostedName() const { return ActiveName; }
	FString HostedPassword() const { return ActivePassword; }
	void RememberHosted(const FString& Name, const FString& Password) { ActiveName = Name; ActivePassword = Password; }
	bool IsFrontendMap(const UWorld* World) const { return IsFrontendWorld(World); }
	FString ConnectingTo() const { return ConnectingName; }

	/** Leave the game (host: closes the server) and go back to the HQ. */
	void ReturnToHQ();
	void QuitGame();
	/** Esc in game: Return to HQ / Quit / Keep playing. */
	void ToggleLeaveMenu(class APlayerController* PC);
	/** The F10 graphics & city life panel, from the HQ's Settings tab. */
	void OpenGraphics();

	// ---- heroes
	const TArray<FCoHHeroCard>& Heroes() const { return HeroList; }
	void RescanHeroes();
	/** The hero file the player picked, empty = the default (-Hero= or starter). */
	FString ChosenHero() const { return SelectedHero; }
	const FCoHHeroCard* ChosenHeroCard() const;
	void ChooseHero(const FString& File);
	/** Archetype starters (Class_*.json in the rules HeroesDir). */
	TArray<FString> StarterClasses() const;
	/** Copies a starter into Saved/Heroes/<Name>.json and picks it. */
	bool CreateHero(const FString& Name, const FString& StarterClass, FString& OutError);

	// ---- messages
	FString LastError() const { return ErrorText; }
	void ClearError() { ErrorText.Reset(); }
	FString ZoneDisplayName(const FString& MapPath) const;

	/** Procedural glow textures the HQ screen paints with. */
	UTexture2D* GlowTexture() const { return Glow; }
	UTexture2D* BeamTexture() const { return Beam; }

private:
	bool Tick(float DeltaTime);
	void TickFrontend(UWorld* World, double Now);
	void TickHost(UWorld* World);
	bool IsFrontendWorld(const UWorld* World) const;
	void ShowLobby(UWorld* World);
	void HideLobby();
	void ResolveServer(int32 Index);
	void Load();
	void Save() const;
	void OpenAddress(const FString& Address, int32 Port, const FString& Password, const FString& DisplayName);
	void HandleNetworkFailure(UWorld* World, class UNetDriver* Driver, ENetworkFailure::Type Type, const FString& Message);
	void HandleTravelFailure(UWorld* World, ETravelFailure::Type Type, const FString& Message);
	void MakeTextures();
	FCoHServerInfo MakeHostInfo(UWorld* World) const;

	UPROPERTY() TObjectPtr<UTexture2D> Glow;
	UPROPERTY() TObjectPtr<UTexture2D> Beam;
	UPROPERTY() TObjectPtr<class UCoHGraphicsMenu> Graphics;

	TArray<FCoHServerEntry> ServerList;
	TArray<FCoHLanServer> LanList;
	TArray<FCoHHeroCard> HeroList;
	FString SelectedHero;
	FCoHHostSettings LastHost;
	FString ErrorText;
	int32 Revision = 0;

	FCoHBeaconClient Client;
	FCoHBeaconHost HostBeacon;
	bool bHostBeaconFailed = false;
	uint32 LanNonce = 0;
	double NextQuery = 0.0;

	FString ActiveName, ActivePassword;
	bool bConnecting = false;
	bool bLeaving = false;
	FString ConnectingName;

	TSharedPtr<SCoHLobby> Lobby;
	TSharedPtr<class SWidget> LeaveMenu;
	TWeakObjectPtr<UWorld> LobbyWorld;
	FTSTicker::FDelegateHandle TickHandle;
	FDelegateHandle NetFailHandle, TravelFailHandle;
};

/** Runs the frontend map: no hero, no villains, just the HQ screen. */
UCLASS()
class COHREBORN_API ACoHFrontendGameMode : public AGameModeBase
{
	GENERATED_BODY()
public:
	ACoHFrontendGameMode();
};

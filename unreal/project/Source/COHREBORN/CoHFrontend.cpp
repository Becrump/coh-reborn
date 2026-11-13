#include "CoHFrontend.h"

#include "Async/Async.h"
#include "CoHGameRules.h"
#include "CoHGraphicsMenu.h"
#include "CoHHeroCharacter.h"
#include "CoHHeroProgress.h"
#include "CoHHeroStage.h"
#include "CoHPortMapper.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GameFramework/GameSession.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "HAL/FileManager.h"
#include "IPAddress.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "SCoHLobby.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "SocketSubsystem.h"

// ------------------------------------------------------------------ hero card
static FString HeroCardPretty(const FString& Id)
{
	FString S = Id;
	int32 Dot;
	if (S.FindLastChar('.', Dot)) S = S.Mid(Dot + 1);
	S.RemoveFromStart(TEXT("Class_"));
	return S.Replace(TEXT("_"), TEXT(" "));
}

FString FCoHHeroCard::ArchetypeName() const { return HeroCardPretty(Class); }

FString FCoHHeroCard::SetsLine() const
{
	if (Primary.IsEmpty()) return Secondary.IsEmpty() ? FString() : HeroCardPretty(Secondary);
	return Secondary.IsEmpty() ? HeroCardPretty(Primary) : HeroCardPretty(Primary) + TEXT("  /  ") + HeroCardPretty(Secondary);
}

// ------------------------------------------------------------------ game mode
ACoHFrontendGameMode::ACoHFrontendGameMode()
{
	// the HQ is a screen, not a place (yet): nobody to spawn
	DefaultPawnClass = nullptr;
	bStartPlayersAsSpectators = false;
}

// ------------------------------------------------------------------ lifetime
UCoHFrontend* UCoHFrontend::Get(const UObject* WorldContext)
{
	const UWorld* W = WorldContext ? WorldContext->GetWorld() : nullptr;
	return W && W->GetGameInstance() ? W->GetGameInstance()->GetSubsystem<UCoHFrontend>() : nullptr;
}

void UCoHFrontend::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	if (Zones.Num() == 0)
	{
		FCoHZoneChoice Atlas;
		Atlas.Name = TEXT("Atlas Park");
		Atlas.Map = TEXT("/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite");
		Zones.Add(Atlas);
	}
	Load();
	RescanHeroes();
	if (!IsRunningDedicatedServer()) MakeTextures();
	TickHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UCoHFrontend::Tick), 0.f);
	if (GEngine)
	{
		NetFailHandle = GEngine->OnNetworkFailure().AddUObject(this, &UCoHFrontend::HandleNetworkFailure);
		TravelFailHandle = GEngine->OnTravelFailure().AddUObject(this, &UCoHFrontend::HandleTravelFailure);
	}
}

void UCoHFrontend::Deinitialize()
{
	FTSTicker::GetCoreTicker().RemoveTicker(TickHandle);
	if (GEngine)
	{
		GEngine->OnNetworkFailure().Remove(NetFailHandle);
		GEngine->OnTravelFailure().Remove(TravelFailHandle);
	}
	HideLobby();
	HostBeacon.Stop();
	if (bPortsOpen)
		CoHPortMapper::ClosePorts({CoHLobby::DefaultGamePort, CoHLobby::DefaultGamePort + CoHLobby::BeaconOffset});
	Client.Stop();
	Super::Deinitialize();
}

bool UCoHFrontend::IsFrontendWorld(const UWorld* World) const
{
	if (!World || !World->IsGameWorld()) return false;
	if (World->GetAuthGameMode() && World->GetAuthGameMode()->IsA<ACoHFrontendGameMode>()) return true;
	const FString Pkg = UWorld::RemovePIEPrefix(World->GetOutermost()->GetName());
	return Pkg == FPackageName::ObjectPathToPackageName(FrontendMap);
}

// ------------------------------------------------------------------ tick
bool UCoHFrontend::Tick(float)
{
	UGameInstance* GI = GetGameInstance();
	UWorld* World = GI ? GI->GetWorld() : nullptr;
	if (!World) return true;
	const double Now = FPlatformTime::Seconds();

	if (!IsRunningDedicatedServer() && IsFrontendWorld(World))
	{
		if (!Lobby.IsValid() || LobbyWorld.Get() != World) ShowLobby(World);
		TickFrontend(World, Now);
	}
	else if (Lobby.IsValid())
	{
		HideLobby();
	}
	TickHost(World);
	return true;
}

void UCoHFrontend::TickHost(UWorld* World)
{
	const ENetMode Mode = World->GetNetMode();
	const bool bHosting = Mode == NM_ListenServer || Mode == NM_DedicatedServer;
	if (!bHosting)
	{
		if (HostBeacon.IsRunning()) HostBeacon.Stop();
		bHostBeaconFailed = false;
		return;
	}
	if (!HostBeacon.IsRunning() && !bHostBeaconFailed)
		bHostBeaconFailed = !HostBeacon.Start(World->URL.Port + CoHLobby::BeaconOffset);
	HostBeacon.Poll([this, World] { return MakeHostInfo(World); }, LastHost.bShowOnLan);
}

FCoHServerInfo UCoHFrontend::MakeHostInfo(UWorld* World) const
{
	FCoHServerInfo I;
	I.Version = CoHLobby::NetVersion;
	I.GamePort = World->URL.Port;
	I.Zone = ZoneDisplayName(World->GetOutermost()->GetName());
	if (const ACoHGameMode* GM = World->GetAuthGameMode<ACoHGameMode>())
	{
		I.Name = GM->ServerName;
		I.bLocked = !GM->ServerPassword.IsEmpty();
	}
	if (const AGameModeBase* GMB = World->GetAuthGameMode())
		if (GMB->GameSession) I.MaxPlayers = GMB->GameSession->MaxPlayers;
	if (const AGameStateBase* GS = World->GetGameState())
		for (const APlayerState* PS : GS->PlayerArray)
			if (PS && !PS->IsInactive()) I.Heroes.Add(PS->GetPlayerName());
	I.Players = I.Heroes.Num();
	if (I.Name.IsEmpty()) I.Name = TEXT("City of Heroes Reborn");
	return I;
}

void UCoHFrontend::TickFrontend(UWorld* World, double Now)
{
	// the Hero Corps terminal's pedestal, with the chosen hero on it (after
	// BeginPlay, so the hero's own start-up doesn't overwrite the loaded file)
	if (!HeroStage.IsValid() && World->HasBegunPlay())
	{
		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		if (ACoHHeroStage* NewStage = World->SpawnActor<ACoHHeroStage>(ACoHHeroStage::StaticClass(), FTransform::Identity, SP))
		{
			HeroStage = NewStage;
			NewStage->ShowHero(SelectedHero);
			++Revision;
		}
	}
	// the player controller arrives a frame or two after the map
	if (APlayerController* PC = GetGameInstance()->GetFirstLocalPlayerController(World))
	{
		// look through the stage's camera
		if (ACoHHeroStage* S = HeroStage.Get(); S && PC->GetViewTarget() != S) PC->SetViewTarget(S);
		if (!PC->ShouldShowMouseCursor() && Lobby.IsValid())
		{
			PC->SetShowMouseCursor(true);
			FInputModeUIOnly Mode;
			Mode.SetWidgetToFocus(Lobby);
			Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
			PC->SetInputMode(Mode);
		}
	}
	if (!Client.IsRunning() && !Client.Start()) return;

	// replies
	TArray<FCoHBeaconClient::FReply> Replies;
	Client.Poll(Replies);
	// the same server seen twice (a saved entry, e.g. 127.0.0.1, and the LAN scan's
	// 192.168.x.x): one server, so the LAN row is dropped
	auto SavedOnline = [this](const FString& InIp, const FString& InName, int32 InPort)
	{
		return ServerList.ContainsByPredicate([&](const FCoHServerEntry& E)
		{
			return E.ResolvedIp == InIp || (E.State == FCoHServerEntry::EState::Online && !InName.IsEmpty()
				&& E.Info.Name == InName && E.Info.GamePort == InPort);
		});
	};
	for (FCoHBeaconClient::FReply& R : Replies)
	{
		bool bSaved = false;
		for (FCoHServerEntry& E : ServerList)
		{
			const bool bSameHost = !E.ResolvedIp.IsEmpty() && E.ResolvedIp == R.Ip && R.BeaconPort == E.Port + CoHLobby::BeaconOffset;
			if (!bSameHost && R.Nonce != E.LastNonce) continue;
			if (E.State != FCoHServerEntry::EState::Online) ++Revision;
			E.State = FCoHServerEntry::EState::Online;
			E.Info = R.Info;
			if (R.Nonce == E.LastNonce) E.PingMs = R.PingMs;
			E.LastReply = Now;
			E.LastSeen = FDateTime::UtcNow();
			bSaved = true;
		}
		if (bSaved || R.Nonce != LanNonce || SavedOnline(R.Ip, R.Info.Name, R.Info.GamePort)) continue;
		FCoHLanServer* L = LanList.FindByPredicate([&](const FCoHLanServer& X) { return X.Ip == R.Ip; });
		if (!L) { L = &LanList.AddDefaulted_GetRef(); L->Ip = R.Ip; ++Revision; }
		L->Info = R.Info;
		L->PingMs = R.PingMs;
		L->LastReply = Now;
	}

	// queries
	if (Now >= NextQuery)
	{
		NextQuery = Now + FMath::Max(1.f, StatusInterval);
		for (int32 i = 0; i < ServerList.Num(); ++i)
		{
			FCoHServerEntry& E = ServerList[i];
			if (E.Beacon.IsValid())
			{
				E.LastNonce = Client.Query(*E.Beacon);
				if (E.FirstQuery < 0) E.FirstQuery = Now;
			}
			else if (!E.bResolving && E.State != FCoHServerEntry::EState::BadAddress)
			{
				ResolveServer(i);
			}
		}
		LanNonce = Client.Broadcast(CoHLobby::DefaultGamePort + CoHLobby::BeaconOffset);
	}

	// states
	const double Fresh = FMath::Max(1.f, StatusInterval) * 2.5;
	for (FCoHServerEntry& E : ServerList)
	{
		if (E.State == FCoHServerEntry::EState::BadAddress) continue;
		const FCoHServerEntry::EState Was = E.State;
		if (E.LastReply > 0 && Now - E.LastReply < Fresh) E.State = FCoHServerEntry::EState::Online;
		else if (E.FirstQuery > 0 && Now - E.FirstQuery > 2.5) E.State = FCoHServerEntry::EState::Offline;
		else E.State = FCoHServerEntry::EState::Checking;
		if (Was != E.State) ++Revision;
	}
	const int32 Before = LanList.Num();
	LanList.RemoveAll([&](const FCoHLanServer& L)
	{
		return Now - L.LastReply > Fresh || SavedOnline(L.Ip, L.Info.Name, L.Info.GamePort);
	});
	if (LanList.Num() != Before) ++Revision;
}

void UCoHFrontend::ResolveServer(int32 Index)
{
	FCoHServerEntry& E = ServerList[Index];
	ISocketSubsystem* SS = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	if (!SS) return;
	bool bValid = false;
	TSharedRef<FInternetAddr> A = SS->CreateInternetAddr();
	A->SetIp(*E.Host, bValid);
	if (bValid)
	{
		A->SetPort(E.Port + CoHLobby::BeaconOffset);
		E.Beacon = A;
		E.ResolvedIp = A->ToString(false);
		return;
	}
	// a name (robert-pc, a Tailscale MagicDNS name): look it up off the game thread
	E.bResolving = true;
	const FString Host = E.Host, Key = E.Key();
	const int32 Port = E.Port;
	TWeakObjectPtr<UCoHFrontend> Weak(this);
	Async(EAsyncExecution::ThreadPool, [Weak, Host, Key, Port]()
	{
		TSharedPtr<FInternetAddr> Found;
		if (ISocketSubsystem* Sub = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM))
		{
			const FAddressInfoResult Res = Sub->GetAddressInfo(*Host, nullptr, EAddressInfoFlags::Default, NAME_None, SOCKTYPE_Datagram);
			if (Res.ReturnCode == SE_NO_ERROR)
				for (const FAddressInfoResultData& D : Res.Results)
					if (D.Address->GetProtocolType() == FNetworkProtocolTypes::IPv4) { Found = D.Address->Clone(); break; }
		}
		AsyncTask(ENamedThreads::GameThread, [Weak, Key, Port, Found]()
		{
			UCoHFrontend* F = Weak.Get();
			if (!F) return;
			for (FCoHServerEntry& E : F->ServerList)
			{
				if (E.Key() != Key) continue;
				E.bResolving = false;
				if (Found.IsValid())
				{
					Found->SetPort(Port + CoHLobby::BeaconOffset);
					E.Beacon = Found;
					E.ResolvedIp = Found->ToString(false);
				}
				else
				{
					E.State = FCoHServerEntry::EState::BadAddress;
					++F->Revision;
				}
			}
		});
	});
}

// ------------------------------------------------------------------ lobby widget
void UCoHFrontend::ShowLobby(UWorld* World)
{
	HideLobby();
	UGameViewportClient* VC = GetGameInstance()->GetGameViewportClient();
	if (!VC) return;
	bLeaving = false;
	bConnecting = false;
	RescanHeroes();
	for (FCoHServerEntry& E : ServerList)
	{
		// fresh look at every server each time the HQ opens
		E.State = FCoHServerEntry::EState::Checking;
		E.FirstQuery = E.LastReply = -1.0;
		E.Beacon.Reset();
		E.ResolvedIp.Reset();
	}
	NextQuery = 0.0;
	Lobby = SNew(SCoHLobby).Frontend(this);
	VC->AddViewportWidgetContent(Lobby.ToSharedRef(), 50);
	LobbyWorld = World;
	++Revision;
}

void UCoHFrontend::HideLobby()
{
	if (Lobby.IsValid())
	{
		if (UGameViewportClient* VC = GetGameInstance() ? GetGameInstance()->GetGameViewportClient() : nullptr)
			VC->RemoveViewportWidgetContent(Lobby.ToSharedRef());
		Lobby.Reset();
	}
	LobbyWorld.Reset();
	if (ACoHHeroStage* S = HeroStage.Get()) S->Destroy();
	HeroStage.Reset();
	Client.Stop();
	LanList.Reset();
	bConnecting = false;
}

// ------------------------------------------------------------------ servers
static void SplitHostPort(const FString& Text, FString& Host, int32& Port)
{
	Host = Text.TrimStartAndEnd();
	Port = CoHLobby::DefaultGamePort;
	FString H, P;
	// "host:port" (an IPv6 address has several colons: leave it alone)
	if (Host.Split(TEXT(":"), &H, &P, ESearchCase::IgnoreCase, ESearchDir::FromEnd) && !H.Contains(TEXT(":")) && P.IsNumeric())
	{
		Host = H;
		Port = FMath::Clamp(FCString::Atoi(*P), 1, 65534);
	}
}

void UCoHFrontend::AddServer(const FString& Name, const FString& HostAndPort, const FString& Password, bool bRemember)
{
	FCoHServerEntry E;
	SplitHostPort(HostAndPort, E.Host, E.Port);
	if (E.Host.IsEmpty()) return;
	E.Name = Name.TrimStartAndEnd().IsEmpty() ? E.Host : Name.TrimStartAndEnd();
	E.bRemember = bRemember;
	E.Password = bRemember ? Password : FString();
	E.LastSeen = FDateTime::MinValue();
	// the same address twice: update the old one
	for (FCoHServerEntry& Old : ServerList)
		if (Old.Key() == E.Key())
		{
			Old.Name = E.Name;
			if (bRemember) { Old.Password = Password; Old.bRemember = true; }
			Save();
			++Revision;
			return;
		}
	ServerList.Add(E);
	NextQuery = 0.0;
	Save();
	++Revision;
}

void UCoHFrontend::EditServer(int32 Index, const FString& Name, const FString& HostAndPort, const FString& Password, bool bRemember)
{
	if (!ServerList.IsValidIndex(Index)) return;
	FCoHServerEntry& E = ServerList[Index];
	FString Host; int32 Port;
	SplitHostPort(HostAndPort, Host, Port);
	if (Host.IsEmpty()) return;
	if (Host != E.Host || Port != E.Port)
	{
		E.Host = Host;
		E.Port = Port;
		E.Beacon.Reset();
		E.ResolvedIp.Reset();
		E.State = FCoHServerEntry::EState::Checking;
		E.FirstQuery = E.LastReply = -1.0;
		NextQuery = 0.0;
	}
	E.Name = Name.TrimStartAndEnd().IsEmpty() ? Host : Name.TrimStartAndEnd();
	E.bRemember = bRemember;
	E.Password = bRemember ? Password : FString();
	Save();
	++Revision;
}

void UCoHFrontend::RemoveServer(int32 Index)
{
	if (!ServerList.IsValidIndex(Index)) return;
	ServerList.RemoveAt(Index);
	Save();
	++Revision;
}

void UCoHFrontend::RefreshNow()
{
	NextQuery = 0.0;
	for (FCoHServerEntry& E : ServerList)
		if (E.State == FCoHServerEntry::EState::BadAddress) { E.State = FCoHServerEntry::EState::Checking; E.FirstQuery = -1.0; }
	++Revision;
}

// ------------------------------------------------------------------ play
void UCoHFrontend::OpenAddress(const FString& Address, int32 Port, const FString& Password, const FString& DisplayName)
{
	UWorld* World = GetGameInstance()->GetWorld();
	if (!World) return;
	FString Options;
	if (!Password.IsEmpty()) Options = TEXT("Password=") + CoHLobby::EncodeOption(Password);
	ErrorText.Reset();
	bConnecting = true;
	ConnectingName = DisplayName;
	const FString Url = FString::Printf(TEXT("%s:%d"), *Address, Port);
	UE_LOG(LogTemp, Log, TEXT("CoH lobby: joining %s (%s)%s"), *DisplayName, *Url, Password.IsEmpty() ? TEXT("") : TEXT(" with a password"));
	UGameplayStatics::OpenLevel(World, FName(*Url), true, Options);
}

void UCoHFrontend::Join(int32 Index, const FString& Password, bool bRememberPassword)
{
	if (!ServerList.IsValidIndex(Index)) return;
	FCoHServerEntry& E = ServerList[Index];
	const FString Pw = Password.IsEmpty() ? E.Password : Password;
	if (bRememberPassword && !Pw.IsEmpty())
	{
		E.Password = Pw;
		E.bRemember = true;
		Save();
	}
	// the beacon's numbers are the freshest: its address, the port the game really uses
	const FString Address = E.ResolvedIp.IsEmpty() ? E.Host : E.ResolvedIp;
	const int32 Port = E.State == FCoHServerEntry::EState::Online && E.Info.GamePort > 0 ? E.Info.GamePort : E.Port;
	OpenAddress(Address, Port, Pw, E.Name);
}

void UCoHFrontend::JoinLan(int32 LanIndex, const FString& Password)
{
	if (!LanList.IsValidIndex(LanIndex)) return;
	const FCoHLanServer& L = LanList[LanIndex];
	OpenAddress(L.Ip, L.Info.GamePort > 0 ? L.Info.GamePort : CoHLobby::DefaultGamePort, Password, L.Info.Name);
}

void UCoHFrontend::JoinAddress(const FString& HostAndPort, const FString& Password)
{
	// a direct connect is saved too, so it shows up next time with its status
	AddServer(FString(), HostAndPort, Password, !Password.IsEmpty());
	FString Host; int32 Port;
	SplitHostPort(HostAndPort, Host, Port);
	const int32 Index = ServerList.IndexOfByPredicate([&](const FCoHServerEntry& E) { return E.Host.Equals(Host, ESearchCase::IgnoreCase) && E.Port == Port; });
	if (Index != INDEX_NONE) Join(Index, Password, false);
}

void UCoHFrontend::CancelJoin()
{
	if (UWorld* World = GetGameInstance()->GetWorld())
		GEngine->Exec(World, TEXT("CANCEL"));
	bConnecting = false;
}

void UCoHFrontend::Host(const FCoHHostSettings& Settings)
{
	UWorld* World = GetGameInstance()->GetWorld();
	if (!World || Zones.Num() == 0) return;
	LastHost = Settings;
	LastHost.MaxPlayers = FMath::Clamp(Settings.MaxPlayers, 1, 16);
	LastHost.Zone = FMath::Clamp(Settings.Zone, 0, Zones.Num() - 1);
	Save();
	const FCoHZoneChoice& Z = Zones[LastHost.Zone];
	FString Options = FString::Printf(TEXT("listen?MaxPlayers=%d?ServerName=%s"), LastHost.MaxPlayers, *CoHLobby::EncodeOption(LastHost.ServerName));
	if (!LastHost.Password.IsEmpty()) Options += TEXT("?Password=") + CoHLobby::EncodeOption(LastHost.Password);
	ErrorText.Reset();
	bConnecting = true;
	ConnectingName = Z.Name;
	ActiveName = LastHost.ServerName;
	ActivePassword = LastHost.Password;
	UE_LOG(LogTemp, Log, TEXT("CoH lobby: hosting \"%s\" in %s, %d heroes max%s"), *LastHost.ServerName, *Z.Name, LastHost.MaxPlayers,
		LastHost.Password.IsEmpty() ? TEXT("") : TEXT(", password set"));
	UGameplayStatics::OpenLevel(World, FName(*Z.Map), true, Options);
}

TArray<FCoHLocalAddress> UCoHFrontend::LocalAddresses() const
{
	TArray<FCoHLocalAddress> Out;
	ISocketSubsystem* SS = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	TArray<TSharedPtr<FInternetAddr>> Addrs;
	if (!SS || !SS->GetLocalAdapterAddresses(Addrs)) return Out;
	for (const TSharedPtr<FInternetAddr>& A : Addrs)
	{
		if (!A.IsValid() || A->GetProtocolType() != FNetworkProtocolTypes::IPv4) continue;
		const FString Ip = A->ToString(false);
		TArray<FString> Parts;
		if (Ip.ParseIntoArray(Parts, TEXT(".")) != 4) continue;
		const int32 B0 = FCString::Atoi(*Parts[0]), B1 = FCString::Atoi(*Parts[1]);
		if (B0 == 127 || (B0 == 169 && B1 == 254) || B0 == 0) continue;
		FCoHLocalAddress L;
		L.Ip = Ip;
		if (B0 == 100 && B1 >= 64 && B1 <= 127) L.Kind = TEXT("Tailscale");
		else if (B0 == 10 || (B0 == 192 && B1 == 168) || (B0 == 172 && B1 >= 16 && B1 <= 31)) L.Kind = TEXT("Home network");
		else L.Kind = TEXT("Internet");
		if (!Out.ContainsByPredicate([&](const FCoHLocalAddress& X) { return X.Ip == Ip; })) Out.Add(L);
	}
	Out.Sort([](const FCoHLocalAddress& A, const FCoHLocalAddress& B)
	{
		auto Rank = [](const FString& K) { return K == TEXT("Tailscale") ? 0 : K == TEXT("Home network") ? 1 : 2; };
		return Rank(A.Kind) < Rank(B.Kind);
	});
	return Out;
}

void UCoHFrontend::PrepareHosting()
{
	if (bPrepared) return;
	bPrepared = true;
	TWeakObjectPtr<UCoHFrontend> Weak(this);

	// what friends type: the public IP (a tiny plain-text lookup, nothing sent but the request)
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
	Req->SetURL(TEXT("https://api.ipify.org"));
	Req->SetVerb(TEXT("GET"));
	Req->OnProcessRequestComplete().BindLambda([Weak](FHttpRequestPtr, FHttpResponsePtr Resp, bool bOk)
	{
		UCoHFrontend* F = Weak.Get();
		if (!F) return;
		if (bOk && Resp.IsValid() && Resp->GetResponseCode() == 200)
			F->PublicAddress = Resp->GetContentAsString().TrimStartAndEnd();
		F->CheckSharedIp();
		++F->Revision;
	});
	Req->ProcessRequest();

	// open the ports on the router, pointing at this PC's home network address
	for (const FCoHLocalAddress& A : LocalAddresses())
		if (A.Kind == TEXT("Home network")) { PortsLanIp = A.Ip; break; }
	if (PortsLanIp.IsEmpty())
	{
		PortMessage = TEXT("No home network address found");
		return;
	}
	bPortsBusy = true;
	CoHPortMapper::OpenPorts({CoHLobby::DefaultGamePort, CoHLobby::DefaultGamePort + CoHLobby::BeaconOffset}, PortsLanIp,
		[Weak](const CoHPortMapper::FResult& R)
		{
			UCoHFrontend* F = Weak.Get();
			if (!F) return;
			F->bPortsBusy = false;
			F->bPortsOpen = R.bOpened;
			F->RouterAddress = R.RouterIp;
			F->PortMessage = R.Message;
			F->CheckSharedIp();
			++F->Revision;
		});
}

void UCoHFrontend::CheckSharedIp()
{
	// a router whose internet address is private (100.64/10, 10/8, 192.168/16, 172.16/12) sits
	// behind the provider's own NAT: no port forward can reach it
	bSharedIp = false;
	if (RouterAddress.IsEmpty() || PublicAddress.IsEmpty() || RouterAddress == PublicAddress) return;
	TArray<FString> P;
	if (RouterAddress.ParseIntoArray(P, TEXT(".")) != 4) return;
	const int32 A = FCString::Atoi(*P[0]), B = FCString::Atoi(*P[1]);
	bSharedIp = A == 10 || (A == 100 && B >= 64 && B <= 127) || (A == 192 && B == 168) || (A == 172 && B >= 16 && B <= 31);
}

FString UCoHFrontend::InternetStatus() const
{
	if (bPortsBusy) return TEXT("Asking the router to open the ports...");
	if (bSharedIp)
		return TEXT("Your internet provider shares one address between homes (CGNAT), so friends can't reach you directly. Ask the provider for a public IP, or use Tailscale.");
	if (bPortsOpen) return TEXT("Ports opened on the router automatically. Friends add this address.");
	if (PortMessage.IsEmpty()) return TEXT("Checking the router...");
	return PortMessage + FString::Printf(TEXT(". In the router, forward UDP %d-%d to %s once."),
		CoHLobby::DefaultGamePort, CoHLobby::DefaultGamePort + CoHLobby::BeaconOffset, PortsLanIp.IsEmpty() ? TEXT("this PC") : *PortsLanIp);
}

void UCoHFrontend::ReturnToHQ()
{
	UWorld* World = GetGameInstance()->GetWorld();
	if (!World) return;
	bLeaving = true;
	ActiveName.Reset();
	ActivePassword.Reset();
	if (LeaveMenu.IsValid())
	{
		if (UGameViewportClient* VC = GetGameInstance()->GetGameViewportClient()) VC->RemoveViewportWidgetContent(LeaveMenu.ToSharedRef());
		LeaveMenu.Reset();
	}
	UGameplayStatics::OpenLevel(World, FName(*FrontendMap), true);
}

void UCoHFrontend::QuitGame()
{
	UWorld* World = GetGameInstance()->GetWorld();
	UKismetSystemLibrary::QuitGame(World, World ? GetGameInstance()->GetFirstLocalPlayerController(World) : nullptr, EQuitPreference::Quit, false);
}

void UCoHFrontend::ToggleLeaveMenu(APlayerController* PC)
{
	UGameViewportClient* VC = GetGameInstance()->GetGameViewportClient();
	if (!VC || !PC) return;
	if (LeaveMenu.IsValid())
	{
		VC->RemoveViewportWidgetContent(LeaveMenu.ToSharedRef());
		LeaveMenu.Reset();
		ACoHHeroCharacter::RestoreGameInput(PC);
		return;
	}
	const bool bHost = PC->GetWorld() && PC->GetWorld()->GetNetMode() == NM_ListenServer;
	TWeakObjectPtr<UCoHFrontend> Weak(this);
	TWeakObjectPtr<APlayerController> WeakPC(PC);
	LeaveMenu = SCoHLobby::MakeLeaveMenu(bHost,
		FSimpleDelegate::CreateLambda([Weak] { if (Weak.IsValid()) Weak->ReturnToHQ(); }),
		FSimpleDelegate::CreateLambda([Weak] { if (Weak.IsValid()) Weak->QuitGame(); }),
		FSimpleDelegate::CreateLambda([Weak, WeakPC] { if (Weak.IsValid() && WeakPC.IsValid()) Weak->ToggleLeaveMenu(WeakPC.Get()); }));
	VC->AddViewportWidgetContent(LeaveMenu.ToSharedRef(), 120);
	PC->SetShowMouseCursor(true);
	FInputModeGameAndUI Mode;
	Mode.SetWidgetToFocus(LeaveMenu);
	Mode.SetHideCursorDuringCapture(false);
	PC->SetInputMode(Mode);
}

void UCoHFrontend::OpenGraphics()
{
	UWorld* World = GetGameInstance()->GetWorld();
	APlayerController* PC = World ? GetGameInstance()->GetFirstLocalPlayerController(World) : nullptr;
	if (!PC) return;
	if (!Graphics) Graphics = NewObject<UCoHGraphicsMenu>(this);
	Graphics->Toggle(PC);
}

// ------------------------------------------------------------------ failures
void UCoHFrontend::HandleNetworkFailure(UWorld* World, UNetDriver*, ENetworkFailure::Type Type, const FString& Message)
{
	if (bLeaving) return;
	// a host doesn't care when one of its players drops
	if (World && World->GetNetMode() == NM_ListenServer) return;
	bConnecting = false;
	if (Message.Contains(TEXT("WRONG_PASSWORD")))
		ErrorText = TEXT("Wrong password. Ask the host for the current one.");
	else if (Message.Contains(TEXT("full"), ESearchCase::IgnoreCase))
		ErrorText = TEXT("That server is full.");
	else if (Type == ENetworkFailure::NetGuidMismatch || Type == ENetworkFailure::NetChecksumMismatch || Type == ENetworkFailure::OutdatedClient || Type == ENetworkFailure::OutdatedServer)
		ErrorText = TEXT("Your game version doesn't match the host's. Both need the same build.");
	else if (Type == ENetworkFailure::PendingConnectionFailure || Type == ENetworkFailure::ConnectionTimeout)
		ErrorText = TEXT("Couldn't reach the server. Check that it's running, the address is right, and the host's router ports are open.");
	else
		ErrorText = TEXT("Lost the connection to the host. The server may have closed.");
	UE_LOG(LogTemp, Warning, TEXT("CoH lobby: network failure %s: %s"), ENetworkFailure::ToString(Type), *Message);
}

void UCoHFrontend::HandleTravelFailure(UWorld*, ETravelFailure::Type Type, const FString& Message)
{
	if (bLeaving) return;
	bConnecting = false;
	ErrorText = Type == ETravelFailure::PackageMissing || Type == ETravelFailure::NoLevel
		? TEXT("This PC is missing the zone the server is running. Update the game files.")
		: TEXT("Couldn't load the zone. ") + Message;
	UE_LOG(LogTemp, Warning, TEXT("CoH lobby: travel failure %s: %s"), ETravelFailure::ToString(Type), *Message);
}

FString UCoHFrontend::ZoneDisplayName(const FString& MapPath) const
{
	const FString Pkg = FPackageName::ObjectPathToPackageName(UWorld::RemovePIEPrefix(MapPath));
	for (const FCoHZoneChoice& Z : Zones)
		if (FPackageName::ObjectPathToPackageName(Z.Map) == Pkg) return Z.Name;
	return FPackageName::GetShortName(Pkg).Replace(TEXT("_"), TEXT(" "));
}

// ------------------------------------------------------------------ heroes
void UCoHFrontend::RescanHeroes()
{
	HeroList.Reset();
	const FString Dir = UCoHHeroProgress::LocalHeroDir();
	TArray<FString> Files;
	IFileManager::Get().FindFiles(Files, *(Dir / TEXT("*.json")), true, false);
	for (const FString& File : Files)
	{
		if (File.EndsWith(TEXT(".rivals.json"))) continue;   // a hero's rivals, not a hero
		FString Json;
		TSharedPtr<FJsonObject> O;
		if (!FFileHelper::LoadFileToString(Json, *(Dir / File))) continue;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), O) || !O.IsValid()) continue;
		FCoHHeroCard C;
		C.File = FPaths::GetBaseFilename(File);
		C.Name = O->HasField(TEXT("name")) ? O->GetStringField(TEXT("name")) : C.File;
		O->TryGetStringField(TEXT("class"), C.Class);
		O->TryGetStringField(TEXT("origin"), C.Origin);
		O->TryGetStringField(TEXT("primary"), C.Primary);
		O->TryGetStringField(TEXT("secondary"), C.Secondary);
		double Level = 1;
		O->TryGetNumberField(TEXT("level"), Level);
		C.Level = FMath::Max(1, (int32)Level);
		HeroList.Add(C);
	}
	HeroList.Sort([](const FCoHHeroCard& A, const FCoHHeroCard& B) { return A.Name < B.Name; });
	++Revision;
}

const FCoHHeroCard* UCoHFrontend::ChosenHeroCard() const
{
	return SelectedHero.IsEmpty() ? nullptr : HeroList.FindByPredicate([&](const FCoHHeroCard& C) { return C.File == SelectedHero; });
}

void UCoHFrontend::ChooseHero(const FString& File)
{
	SelectedHero = File;
	Save();
	if (ACoHHeroStage* S = HeroStage.Get()) S->ShowHero(File);
	++Revision;
}

ACoHHeroCharacter* UCoHFrontend::StageHero() const
{
	const ACoHHeroStage* S = HeroStage.Get();
	return S ? S->Hero() : nullptr;
}

void UCoHFrontend::SaveStageLooks()
{
	ACoHHeroCharacter* H = StageHero();
	if (H && H->Progress) H->Progress->SaveLooks();
	RescanHeroes();
}

FString FCoHRivalCard::StageName(int32 Stage)
{
	static const TCHAR* Names[] = {TEXT("Marked"), TEXT("Rising"), TEXT("Crew Boss"), TEXT("Gang Legend"), TEXT("Breakout"), TEXT("Supervillain")};
	return Names[FMath::Clamp(Stage, 0, 5)];
}

TArray<FCoHRivalCard> UCoHFrontend::Rivals(const FString& HeroFile) const
{
	// Saved/Heroes/<hero>.rivals.json: an array of rival records, or {"rivals": [...]}
	TArray<FCoHRivalCard> Out;
	FString Name = HeroFile;
	if (Name.IsEmpty()) return Out;
	FString Json;
	if (!FFileHelper::LoadFileToString(Json, *(UCoHHeroProgress::LocalHeroDir() / Name + TEXT(".rivals.json")))) return Out;
	TArray<TSharedPtr<FJsonValue>> List;
	TSharedPtr<FJsonObject> Top;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), List))
	{
		const TArray<TSharedPtr<FJsonValue>>* Inner = nullptr;
		if (FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Top) && Top.IsValid() && Top->TryGetArrayField(TEXT("rivals"), Inner)) List = *Inner;
	}
	for (const TSharedPtr<FJsonValue>& V : List)
	{
		const TSharedPtr<FJsonObject>* O = nullptr;
		if (!V.IsValid() || !V->TryGetObject(O)) continue;
		const FJsonObject& R = **O;
		FCoHRivalCard C;
		R.TryGetStringField(TEXT("name"), C.Name);
		R.TryGetStringField(TEXT("faction"), C.Faction);
		R.TryGetStringField(TEXT("rank"), C.Rank);
		R.TryGetStringField(TEXT("status"), C.Status);
		R.TryGetBoolField(TEXT("isNemesis"), C.bNemesis);
		R.TryGetNumberField(TEXT("level"), C.Level);
		R.TryGetNumberField(TEXT("stage"), C.Stage);
		R.TryGetNumberField(TEXT("grudge"), C.Grudge);
		R.TryGetNumberField(TEXT("arrests"), C.Arrests);
		const TArray<TSharedPtr<FJsonValue>>* Hist = nullptr;
		if (R.TryGetArrayField(TEXT("history"), Hist))
			for (int32 i = Hist->Num() - 1; i >= 0; --i)
			{
				const TSharedPtr<FJsonObject>* H = nullptr;
				if (!(*Hist)[i].IsValid() || !(*Hist)[i]->TryGetObject(H)) continue;
				FString When, Event, Who, Power;
				(*H)->TryGetStringField(TEXT("t"), When);
				(*H)->TryGetStringField(TEXT("event"), Event);
				(*H)->TryGetStringField(TEXT("hero"), Who);
				(*H)->TryGetStringField(TEXT("power"), Power);
				FString Line = When + TEXT("  ") + Event.ToUpper();
				if (!Who.IsEmpty()) Line += TEXT("  ") + Who;
				if (!Power.IsEmpty()) Line += TEXT(" (") + Power + TEXT(")");
				C.History.Add(Line);
			}
		if (!C.Name.IsEmpty()) Out.Add(C);
	}
	Out.StableSort([](const FCoHRivalCard& A, const FCoHRivalCard& B) { return A.bNemesis && !B.bNemesis; });
	return Out;
}

TArray<FString> UCoHFrontend::StarterClasses() const
{
	TArray<FString> Out;
	const UCoHGameRules* R = GetGameInstance()->GetSubsystem<UCoHGameRules>();
	if (!R || R->HeroesDir.IsEmpty()) return Out;
	TArray<FString> Files;
	IFileManager::Get().FindFiles(Files, *(R->HeroesDir / TEXT("Class_*.json")), true, false);
	for (const FString& F : Files) Out.Add(FPaths::GetBaseFilename(F));
	Out.Sort();
	return Out;
}

bool UCoHFrontend::CreateHero(const FString& Name, const FString& StarterClass, FString& OutError)
{
	const FString Clean = Name.TrimStartAndEnd();
	if (Clean.Len() < 2) { OutError = TEXT("Give your hero a name."); return false; }
	const FString File = FPaths::MakeValidFileName(Clean, '_');
	const FString Path = UCoHHeroProgress::LocalHeroDir() / File + TEXT(".json");
	if (FPaths::FileExists(Path)) { OutError = TEXT("You already have a hero with that name."); return false; }
	const UCoHGameRules* R = GetGameInstance()->GetSubsystem<UCoHGameRules>();
	FString Json;
	if (!R || !FFileHelper::LoadFileToString(Json, *(R->HeroesDir / StarterClass + TEXT(".json"))))
	{
		OutError = TEXT("The archetype starters weren't found (rules folder missing?).");
		return false;
	}
	TSharedPtr<FJsonObject> O;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), O) || !O.IsValid()) { OutError = TEXT("That starter file is broken."); return false; }
	O->SetStringField(TEXT("name"), Clean);
	FString Out;
	TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
	FJsonSerializer::Serialize(O.ToSharedRef(), W);
	if (!FFileHelper::SaveStringToFile(Out, *Path)) { OutError = TEXT("Couldn't write ") + Path; return false; }
	RescanHeroes();
	ChooseHero(File);
	return true;
}

// ------------------------------------------------------------------ persistence
static FString LobbyFile() { return FPaths::ProjectSavedDir() / TEXT("CoHLobby.json"); }

void UCoHFrontend::Load()
{
	FString Json;
	TSharedPtr<FJsonObject> O;
	if (!FFileHelper::LoadFileToString(Json, *LobbyFile())) return;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), O) || !O.IsValid()) return;
	O->TryGetStringField(TEXT("hero"), SelectedHero);
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	if (O->TryGetArrayField(TEXT("servers"), List))
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> S = V->AsObject();
			if (!S.IsValid()) continue;
			FCoHServerEntry E;
			S->TryGetStringField(TEXT("name"), E.Name);
			S->TryGetStringField(TEXT("host"), E.Host);
			double Port = CoHLobby::DefaultGamePort;
			S->TryGetNumberField(TEXT("port"), Port);
			E.Port = (int32)Port;
			S->TryGetBoolField(TEXT("remember"), E.bRemember);
			if (E.bRemember) S->TryGetStringField(TEXT("password"), E.Password);
			FString Seen;
			if (!S->TryGetStringField(TEXT("last_seen"), Seen) || !FDateTime::ParseIso8601(*Seen, E.LastSeen)) E.LastSeen = FDateTime::MinValue();
			if (!E.Host.IsEmpty()) ServerList.Add(E);
		}
	const TSharedPtr<FJsonObject>* H = nullptr;
	if (O->TryGetObjectField(TEXT("host"), H))
	{
		(*H)->TryGetStringField(TEXT("name"), LastHost.ServerName);
		(*H)->TryGetStringField(TEXT("password"), LastHost.Password);
		double Max = 7, Zone = 0;
		(*H)->TryGetNumberField(TEXT("max"), Max);
		(*H)->TryGetNumberField(TEXT("zone"), Zone);
		LastHost.MaxPlayers = (int32)Max;
		LastHost.Zone = (int32)Zone;
		(*H)->TryGetBoolField(TEXT("lan"), LastHost.bShowOnLan);
	}
}

void UCoHFrontend::Save() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	O->SetStringField(TEXT("hero"), SelectedHero);
	TArray<TSharedPtr<FJsonValue>> List;
	for (const FCoHServerEntry& E : ServerList)
	{
		TSharedRef<FJsonObject> S = MakeShared<FJsonObject>();
		S->SetStringField(TEXT("name"), E.Name);
		S->SetStringField(TEXT("host"), E.Host);
		S->SetNumberField(TEXT("port"), E.Port);
		S->SetBoolField(TEXT("remember"), E.bRemember);
		if (E.bRemember) S->SetStringField(TEXT("password"), E.Password);
		if (E.LastSeen > FDateTime::MinValue()) S->SetStringField(TEXT("last_seen"), E.LastSeen.ToIso8601());
		List.Add(MakeShared<FJsonValueObject>(S));
	}
	O->SetArrayField(TEXT("servers"), List);
	if (LastHost.bRemember)
	{
		TSharedRef<FJsonObject> H = MakeShared<FJsonObject>();
		H->SetStringField(TEXT("name"), LastHost.ServerName);
		H->SetStringField(TEXT("password"), LastHost.Password);
		H->SetNumberField(TEXT("max"), LastHost.MaxPlayers);
		H->SetNumberField(TEXT("zone"), LastHost.Zone);
		H->SetBoolField(TEXT("lan"), LastHost.bShowOnLan);
		O->SetObjectField(TEXT("host"), H);
	}
	FString Out;
	TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
	FJsonSerializer::Serialize(O, W);
	FFileHelper::SaveStringToFile(Out, *LobbyFile());
}

// ------------------------------------------------------------------ glow textures
static UTexture2D* MakeAlphaTexture(int32 W, int32 H, TFunctionRef<float(float, float)> Alpha)
{
	UTexture2D* T = UTexture2D::CreateTransient(W, H, PF_B8G8R8A8);
	if (!T) return nullptr;
	T->Filter = TF_Bilinear;
	T->SRGB = false;
	T->AddressX = T->AddressY = TA_Clamp;
	FTexture2DMipMap& Mip = T->GetPlatformData()->Mips[0];
	FColor* Px = static_cast<FColor*>(Mip.BulkData.Lock(LOCK_READ_WRITE));
	for (int32 y = 0; y < H; ++y)
		for (int32 x = 0; x < W; ++x)
		{
			const float U = (x + .5f) / W, V = (y + .5f) / H;
			Px[y * W + x] = FColor(255, 255, 255, (uint8)FMath::Clamp(FMath::RoundToInt(Alpha(U, V) * 255.f), 0, 255));
		}
	Mip.BulkData.Unlock();
	T->UpdateResource();
	return T;
}

void UCoHFrontend::MakeTextures()
{
	// soft round glow (holo table, status lights)
	Glow = MakeAlphaTexture(128, 128, [](float U, float V)
	{
		const float D = FVector2f(U - .5f, V - .5f).Size() * 2.f;
		return FMath::Pow(FMath::Clamp(1.f - D, 0.f, 1.f), 2.f);
	});
	// searchlight beam: bright at the bottom, soft sides, fading upward
	Beam = MakeAlphaTexture(32, 256, [](float U, float V)
	{
		const float Side = FMath::Pow(FMath::Clamp(1.f - FMath::Abs(U - .5f) * 2.f, 0.f, 1.f), 1.6f);
		return Side * FMath::Pow(V, 1.4f);
	});
}

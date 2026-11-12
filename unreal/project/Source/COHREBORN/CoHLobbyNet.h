// Server status beacon for the HQ lobby (docs/lobby.md).
//
// A hosted game answers a tiny UDP status query on game port + 1 (7778 for
// the default 7777), so the lobby can show whether a friend's server is
// running, who is on it, if it needs a password and the ping, before
// joining. Plain text + JSON, no online subsystem needed; works on a home
// network and over Tailscale. The same port answers LAN broadcasts, which
// fills "Found on your network".
//
//   query: "COHR? <nonce> <direct|lan>"
//   reply: "COHR! <nonce> <json FCoHServerInfo>"
#pragma once

#include "CoreMinimal.h"

class FSocket;
class FInternetAddr;

namespace CoHLobby
{
	/** Bump when hosts and clients stop being able to play together. */
	constexpr int32 NetVersion = 1;
	constexpr int32 DefaultGamePort = 7777;
	/** The beacon listens on the game port + this. */
	constexpr int32 BeaconOffset = 1;

	/** URL option values may not hold ? = or spaces: %XX everything else. */
	COHREBORN_API FString EncodeOption(const FString& Value);
	COHREBORN_API FString DecodeOption(const FString& Value);
}

/** What a running server says about itself. */
struct COHREBORN_API FCoHServerInfo
{
	FString Name;
	FString Zone;
	int32 Players = 0;
	int32 MaxPlayers = 0;
	int32 GamePort = CoHLobby::DefaultGamePort;
	int32 Version = 0;
	bool bLocked = false;
	TArray<FString> Heroes;

	FString ToJson() const;
	bool FromJson(const FString& Json);
};

/** Host side: answers status queries. */
class COHREBORN_API FCoHBeaconHost
{
public:
	~FCoHBeaconHost() { Stop(); }
	bool Start(int32 BeaconPort);
	void Stop();
	bool IsRunning() const { return Socket != nullptr; }
	/** Answer every waiting query. MakeInfo runs only when one came in.
	 *  bAnswerLan false: broadcast queries are ignored (hidden from LAN). */
	void Poll(TFunctionRef<FCoHServerInfo()> MakeInfo, bool bAnswerLan);

private:
	FSocket* Socket = nullptr;
};

/** Client side: asks servers for their status. */
class COHREBORN_API FCoHBeaconClient
{
public:
	struct FReply
	{
		uint32 Nonce = 0;
		FString Ip;          // sender, no port
		int32 BeaconPort = 0;
		float PingMs = 0.f;
		FCoHServerInfo Info;
	};

	~FCoHBeaconClient() { Stop(); }
	bool Start();
	void Stop();
	bool IsRunning() const { return Socket != nullptr; }
	/** Returns the nonce used, 0 if nothing was sent. */
	uint32 Query(const FInternetAddr& BeaconAddr);
	uint32 Broadcast(int32 BeaconPort);
	void Poll(TArray<FReply>& Out);

private:
	uint32 Send(const FInternetAddr& To, const TCHAR* Kind);
	FSocket* Socket = nullptr;
	uint32 NextNonce = 1;
	TMap<uint32, double> SentAt;
};

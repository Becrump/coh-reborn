#include "CoHLobbyNet.h"

#include "Common/UdpSocketBuilder.h"
#include "Dom/JsonObject.h"
#include "HAL/PlatformTime.h"
#include "IPAddress.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Sockets.h"
#include "SocketSubsystem.h"

static const TCHAR* QueryTag = TEXT("COHR?");
static const TCHAR* ReplyTag = TEXT("COHR!");

// ------------------------------------------------------------------ helpers
FString CoHLobby::EncodeOption(const FString& Value)
{
	FString Out;
	FTCHARToUTF8 Utf8(*Value);
	for (int32 i = 0; i < Utf8.Length(); ++i)
	{
		const uint8 C = (uint8)Utf8.Get()[i];
		if ((C >= 'a' && C <= 'z') || (C >= 'A' && C <= 'Z') || (C >= '0' && C <= '9') || C == '-' || C == '_' || C == '.')
			Out.AppendChar((TCHAR)C);
		else
			Out += FString::Printf(TEXT("%%%02X"), C);
	}
	return Out;
}

FString CoHLobby::DecodeOption(const FString& Value)
{
	TArray<uint8> Bytes;
	for (int32 i = 0; i < Value.Len(); ++i)
	{
		if (Value[i] == '%' && i + 2 < Value.Len() && FChar::IsHexDigit(Value[i + 1]) && FChar::IsHexDigit(Value[i + 2]))
		{
			Bytes.Add((uint8)FParse::HexNumber(*Value.Mid(i + 1, 2)));
			i += 2;
		}
		else
		{
			const TCHAR One1[2] = {Value[i], 0};
			FTCHARToUTF8 One(One1);
			Bytes.Append((const uint8*)One.Get(), One.Length());
		}
	}
	Bytes.Add(0);
	return UTF8_TO_TCHAR((const ANSICHAR*)Bytes.GetData());
}

static ISocketSubsystem* LobbySockets() { return ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM); }

static void SendText(FSocket* Socket, const FString& Text, const FInternetAddr& To)
{
	FTCHARToUTF8 Utf8(*Text);
	int32 Sent = 0;
	Socket->SendTo((const uint8*)Utf8.Get(), Utf8.Length(), Sent, To);
}

/** Next datagram as text; false when none is waiting. */
static bool ReceiveText(FSocket* Socket, FString& Out, FInternetAddr& From)
{
	uint32 Pending = 0;
	if (!Socket->HasPendingData(Pending)) return false;
	uint8 Buffer[4096];
	int32 Read = 0;
	if (!Socket->RecvFrom(Buffer, sizeof(Buffer) - 1, Read, From) || Read <= 0) return false;
	Buffer[Read] = 0;
	Out = UTF8_TO_TCHAR((const ANSICHAR*)Buffer);
	return true;
}

// ------------------------------------------------------------------ info
FString FCoHServerInfo::ToJson() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	O->SetStringField(TEXT("name"), Name);
	O->SetStringField(TEXT("zone"), Zone);
	O->SetNumberField(TEXT("players"), Players);
	O->SetNumberField(TEXT("max"), MaxPlayers);
	O->SetNumberField(TEXT("port"), GamePort);
	O->SetNumberField(TEXT("v"), Version);
	O->SetBoolField(TEXT("locked"), bLocked);
	TArray<TSharedPtr<FJsonValue>> H;
	for (const FString& N : Heroes) H.Add(MakeShared<FJsonValueString>(N));
	O->SetArrayField(TEXT("heroes"), H);
	FString Out;
	TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
	FJsonSerializer::Serialize(O, W);
	return Out;
}

bool FCoHServerInfo::FromJson(const FString& Json)
{
	TSharedPtr<FJsonObject> O;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), O) || !O.IsValid()) return false;
	Name = O->GetStringField(TEXT("name"));
	Zone = O->GetStringField(TEXT("zone"));
	Players = (int32)O->GetNumberField(TEXT("players"));
	MaxPlayers = (int32)O->GetNumberField(TEXT("max"));
	GamePort = (int32)O->GetNumberField(TEXT("port"));
	Version = (int32)O->GetNumberField(TEXT("v"));
	bLocked = O->GetBoolField(TEXT("locked"));
	Heroes.Reset();
	const TArray<TSharedPtr<FJsonValue>>* H = nullptr;
	if (O->TryGetArrayField(TEXT("heroes"), H))
		for (const TSharedPtr<FJsonValue>& V : *H) Heroes.Add(V->AsString());
	return true;
}

// ------------------------------------------------------------------ host
bool FCoHBeaconHost::Start(int32 BeaconPort)
{
	Stop();
	Socket = FUdpSocketBuilder(TEXT("CoHBeaconHost"))
		.AsNonBlocking()
		.AsReusable()
		.WithBroadcast()
		.BoundToPort((uint16)BeaconPort)
		.Build();
	UE_LOG(LogTemp, Log, TEXT("CoH lobby: status beacon %s on UDP %d"), Socket ? TEXT("listening") : TEXT("could NOT open"), BeaconPort);
	return Socket != nullptr;
}

void FCoHBeaconHost::Stop()
{
	if (Socket)
	{
		Socket->Close();
		LobbySockets()->DestroySocket(Socket);
		Socket = nullptr;
	}
}

void FCoHBeaconHost::Poll(TFunctionRef<FCoHServerInfo()> MakeInfo, bool bAnswerLan)
{
	if (!Socket) return;
	TSharedRef<FInternetAddr> From = LobbySockets()->CreateInternetAddr();
	FString Msg, Cached;
	for (int32 Guard = 0; Guard < 64 && ReceiveText(Socket, Msg, *From); ++Guard)
	{
		TArray<FString> Parts;
		Msg.ParseIntoArrayWS(Parts);
		if (Parts.Num() < 2 || Parts[0] != QueryTag) continue;
		if (!bAnswerLan && Parts.Num() > 2 && Parts[2] == TEXT("lan")) continue;
		if (Cached.IsEmpty()) Cached = MakeInfo().ToJson();
		SendText(Socket, FString::Printf(TEXT("%s %s %s"), ReplyTag, *Parts[1], *Cached), *From);
	}
}

// ------------------------------------------------------------------ client
bool FCoHBeaconClient::Start()
{
	if (Socket) return true;
	Socket = FUdpSocketBuilder(TEXT("CoHBeaconClient"))
		.AsNonBlocking()
		.WithBroadcast()
		.BoundToPort(0)
		.Build();
	return Socket != nullptr;
}

void FCoHBeaconClient::Stop()
{
	if (Socket)
	{
		Socket->Close();
		LobbySockets()->DestroySocket(Socket);
		Socket = nullptr;
	}
	SentAt.Reset();
}

uint32 FCoHBeaconClient::Send(const FInternetAddr& To, const TCHAR* Kind)
{
	if (!Socket) return 0;
	const uint32 Nonce = NextNonce++;
	if (NextNonce == 0) NextNonce = 1;
	SentAt.Add(Nonce, FPlatformTime::Seconds());
	SendText(Socket, FString::Printf(TEXT("%s %u %s"), QueryTag, Nonce, Kind), To);
	return Nonce;
}

uint32 FCoHBeaconClient::Query(const FInternetAddr& BeaconAddr) { return Send(BeaconAddr, TEXT("direct")); }

uint32 FCoHBeaconClient::Broadcast(int32 BeaconPort)
{
	TSharedRef<FInternetAddr> All = LobbySockets()->CreateInternetAddr();
	All->SetBroadcastAddress();
	All->SetPort(BeaconPort);
	return Send(*All, TEXT("lan"));
}

void FCoHBeaconClient::Poll(TArray<FReply>& Out)
{
	if (!Socket) return;
	const double Now = FPlatformTime::Seconds();
	TSharedRef<FInternetAddr> From = LobbySockets()->CreateInternetAddr();
	FString Msg;
	for (int32 Guard = 0; Guard < 64 && ReceiveText(Socket, Msg, *From); ++Guard)
	{
		// "COHR! <nonce> <json>": the json may hold spaces, so split twice
		FString Tag, Rest, NonceText, Json;
		if (!Msg.Split(TEXT(" "), &Tag, &Rest) || Tag != ReplyTag) continue;
		if (!Rest.Split(TEXT(" "), &NonceText, &Json)) continue;
		FReply R;
		R.Nonce = (uint32)FCString::Strtoui64(*NonceText, nullptr, 10);
		if (!R.Info.FromJson(Json)) continue;
		const double* T = SentAt.Find(R.Nonce);
		R.PingMs = T ? float((Now - *T) * 1000.0) : 0.f;
		R.Ip = From->ToString(false);
		R.BeaconPort = From->GetPort();
		Out.Add(MoveTemp(R));
	}
	// forget queries nobody answered (broadcast nonces get many replies, keep them a while)
	for (auto It = SentAt.CreateIterator(); It; ++It)
		if (Now - It.Value() > 10.0) It.RemoveCurrent();
}

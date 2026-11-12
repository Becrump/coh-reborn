// Opens the game's UDP ports on the home router (UPnP) so friends can join
// over the internet without Tailscale or a manual port forward
// (docs/lobby.md). Windows only (the router talk goes through the Windows
// UPnP NAT service); other platforms report "not supported".
#pragma once

#include "CoreMinimal.h"

namespace CoHPortMapper
{
	struct FResult
	{
		bool bOpened = false;
		/** The router's internet-side address, when it told us. */
		FString RouterIp;
		FString Message;
	};

	/** Maps each UDP port to LocalIp on a worker thread (a few seconds);
	 *  Done runs on the game thread. */
	COHREBORN_API void OpenPorts(const TArray<int32>& Ports, const FString& LocalIp, TFunction<void(const FResult&)> Done);

	/** Removes the mappings again (blocking; call at shutdown). */
	COHREBORN_API void ClosePorts(const TArray<int32>& Ports);
}

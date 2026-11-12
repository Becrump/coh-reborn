#include "CoHPortMapper.h"

#include "Async/Async.h"

#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include <objbase.h>
#include <oleauto.h>
#include <natupnp.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

namespace
{
#if PLATFORM_WINDOWS
	/** The router's static port mapping list, or null when it has no UPnP. */
	IStaticPortMappingCollection* Mappings(IUPnPNAT*& OutNat)
	{
		OutNat = nullptr;
		IStaticPortMappingCollection* Coll = nullptr;
		if (FAILED(CoCreateInstance(__uuidof(UPnPNAT), nullptr, CLSCTX_ALL, __uuidof(IUPnPNAT), (void**)&OutNat)) || !OutNat) return nullptr;
		if (FAILED(OutNat->get_StaticPortMappingCollection(&Coll))) Coll = nullptr;
		return Coll;
	}
#endif
}

void CoHPortMapper::OpenPorts(const TArray<int32>& Ports, const FString& LocalIp, TFunction<void(const FResult&)> Done)
{
	Async(EAsyncExecution::Thread, [Ports, LocalIp, Done]()
	{
		FResult R;
#if PLATFORM_WINDOWS
		const HRESULT Init = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
		IUPnPNAT* Nat = nullptr;
		if (IStaticPortMappingCollection* Coll = Mappings(Nat))
		{
			BSTR Udp = SysAllocString(L"UDP");
			BSTR Client = SysAllocString(TCHAR_TO_WCHAR(*LocalIp));
			BSTR Desc = SysAllocString(L"City of Heroes Reborn");
			int32 Ok = 0;
			for (const int32 Port : Ports)
			{
				// replace an older mapping of ours (the PC's address may have changed)
				Coll->Remove(Port, Udp);
				IStaticPortMapping* Map = nullptr;
				if (SUCCEEDED(Coll->Add(Port, Udp, Port, Client, VARIANT_TRUE, Desc, &Map)) && Map)
				{
					++Ok;
					BSTR Ext = nullptr;
					if (R.RouterIp.IsEmpty() && SUCCEEDED(Map->get_ExternalIPAddress(&Ext)) && Ext)
					{
						R.RouterIp = WCHAR_TO_TCHAR(Ext);
						SysFreeString(Ext);
					}
					Map->Release();
				}
			}
			SysFreeString(Udp);
			SysFreeString(Client);
			SysFreeString(Desc);
			Coll->Release();
			R.bOpened = Ok == Ports.Num();
			R.Message = R.bOpened ? TEXT("Router ports opened automatically")
				: TEXT("The router refused to open the ports");
		}
		else
		{
			R.Message = TEXT("The router doesn't allow automatic port opening (UPnP off)");
		}
		if (Nat) Nat->Release();
		if (SUCCEEDED(Init)) CoUninitialize();
#else
		R.Message = TEXT("Automatic port opening only works on Windows");
#endif
		UE_LOG(LogTemp, Log, TEXT("CoH lobby: UPnP %s (router %s)"), *R.Message, R.RouterIp.IsEmpty() ? TEXT("?") : *R.RouterIp);
		AsyncTask(ENamedThreads::GameThread, [Done, R]() { if (Done) Done(R); });
	});
}

void CoHPortMapper::ClosePorts(const TArray<int32>& Ports)
{
#if PLATFORM_WINDOWS
	const HRESULT Init = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
	IUPnPNAT* Nat = nullptr;
	if (IStaticPortMappingCollection* Coll = Mappings(Nat))
	{
		BSTR Udp = SysAllocString(L"UDP");
		for (const int32 Port : Ports) Coll->Remove(Port, Udp);
		SysFreeString(Udp);
		Coll->Release();
	}
	if (Nat) Nat->Release();
	if (SUCCEEDED(Init)) CoUninitialize();
#endif
}

// Zone events: the original's scripted events in the city zones (Hellions
// setting fires in King's Row, the Troll rave in Skyway City, the Croatoa
// giants) and the city-wide invasions (Rikti, zombies). The data comes from
// <out>/zone_encounters/zone_events.json (tools/zones/zone_events.py); the
// original scripts were C code in the server, so these are our versions of
// them, run by the host. See docs/zone-events.md.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CoHZoneEvents.generated.h"

class ACoHCombatEnemy;

struct FCoHZoneEventDef
{
	FString Zone, Script, Def, Marker;
	float EveryHours = 1.f, RangeMinutes = 0.f;
	FVector World = FVector::ZeroVector;
	bool bHasWorld = false;
	TMap<FString, FString> Vars, Text;
	TMap<FString, TArray<FString>> Villains;
	FString Var(const TCHAR* K, const TCHAR* Default = TEXT("")) const { const FString* V = Vars.Find(K); return V ? *V : FString(Default); }
	int32 Int(const TCHAR* K, int32 Default) const { const FString* V = Vars.Find(K); return V && V->IsNumeric() ? FCString::Atoi(**V) : Default; }
};

UCLASS(Config = Game)
class COHREBORN_API ACoHZoneEvents : public AActor
{
	GENERATED_BODY()
public:
	ACoHZoneEvents();
	static ACoHZoneEvents* Get(const UWorld* World);
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Host: start an event now by its script or marker name ("HellionsFire", "RiktiInvasion",
	 *  "HellionFire_3"), near Who; "stop" ends the running ones; "list" says what there is. */
	FString Command(const FString& What, APawn* Who);

	/** Server setting: zone events happen at all, and how often (1 = the original's timing). */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Zone events") bool bZoneEvents = true;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Zone events") float TimeScale = 1.f;
	/** City-wide invasions: hours between them (random in this range); 0 turns them off. */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Zone events") FVector2D InvasionHours = FVector2D(4.f, 8.f);

private:
	struct FRunning
	{
		const FCoHZoneEventDef* Def = nullptr;
		FVector Center = FVector::ZeroVector;
		double Started = 0, NextSpawn = 0, NextFx = 0, LastHeroNear = 0, NextMessage = 0;
		int32 Level = 1, Spawned = 0, Total = 0, MaxAlive = 10, Stage = 0;
		bool bBoss = false;
		TArray<TWeakObjectPtr<ACoHCombatEnemy>> Foes;
	};
	TArray<FCoHZoneEventDef> Events, City;
	TMap<FString, FString> ZoneNames;
	TMap<FString, TMap<FString, FVector>> Targets;
	TMap<int32, double> NextRun;      // index in Events (city events: -1 - index)
	TArray<FRunning> Running;
	double NextCheck = 0;
	void Load();
	bool Start(const FCoHZoneEventDef& D, const FVector& Center, APawn* Near);
	void TickEvent(FRunning& R, double Now);
	void Finish(FRunning& R, bool bWon);
	ACoHCombatEnemy* SpawnFoe(FRunning& R, const FString& Villain, const FVector& At, APawn* Target);
	TArray<APawn*> Heroes() const;
	FString ZoneAt(const FVector& Pos) const;
	FString ZoneName(const FString& Zone) const { const FString* N = ZoneNames.Find(Zone); return N ? *N : Zone; }
	void Announce(const FString& Text, const FVector* Near, float RadiusCm) const;
	double Schedule(const FCoHZoneEventDef& D) const;
	UFUNCTION(NetMulticast, Unreliable) void MulticastFire(FVector_NetQuantize Where, float Radius, FLinearColor Colour);
};

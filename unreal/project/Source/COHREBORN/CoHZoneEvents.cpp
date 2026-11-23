#include "CoHZoneEvents.h"
#include "CoHCombat.h"
#include "CoHGameRules.h"
#include "CoHHeroProgress.h"
#include "CoHPowerFX.h"
#include "CoHPowers.h"
#include "CoHSocial.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

static constexpr float ZoneEventFeet = 30.48f;

ACoHZoneEvents::ACoHZoneEvents()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 1.f;
	bReplicates = true;
	bAlwaysRelevant = true;
}

ACoHZoneEvents* ACoHZoneEvents::Get(const UWorld* World)
{
	if (!World) return nullptr;
	for (TActorIterator<ACoHZoneEvents> It(const_cast<UWorld*>(World)); It; ++It) return *It;
	return nullptr;
}

void ACoHZoneEvents::BeginPlay()
{
	Super::BeginPlay();
	if (!HasAuthority()) return;
	Load();
	// first runs: somewhere in each event's own interval, so they don't all go at once
	const double Now = GetWorld()->GetTimeSeconds();
	for (int32 i = 0; i < Events.Num(); ++i) NextRun.Add(i, Now + FMath::FRandRange(0.2, 1.0) * Schedule(Events[i]));
	for (int32 i = 0; i < City.Num(); ++i)
		NextRun.Add(-1 - i, InvasionHours.Y > 0.f ? Now + FMath::FRandRange(InvasionHours.X, InvasionHours.Y) * 3600.0 * TimeScale : 1e12);
}

void ACoHZoneEvents::Load()
{
	FString Rules;
	GConfig->GetString(TEXT("/Script/COHREBORN.CoHPowerDatabase"), TEXT("RulesDir"), Rules, GGameIni);
	if (Rules.IsEmpty()) Rules = FPaths::ProjectContentDir() / TEXT("CoH/Data/Rules");
	const FString File = FPaths::GetPath(Rules) / TEXT("zone_encounters/zone_events.json");
	FString Text;
	TSharedPtr<FJsonObject> Root;
	if (!FFileHelper::LoadFileToString(Text, *File) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH zone events: no %s (tools/zones/zone_events.py)"), *File);
		return;
	}
	auto Vec = [](const TArray<TSharedPtr<FJsonValue>>* A, FVector& Out)
	{
		if (!A || A->Num() < 3) return false;
		Out = FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber());
		return true;
	};
	auto Read = [&](const TSharedPtr<FJsonObject>& O, const FString& Zone)
	{
		FCoHZoneEventDef D;
		D.Zone = Zone;
		O->TryGetStringField(TEXT("script"), D.Script); O->TryGetStringField(TEXT("def"), D.Def); O->TryGetStringField(TEXT("marker"), D.Marker);
		double H = 1, M = 0; O->TryGetNumberField(TEXT("every_h"), H); O->TryGetNumberField(TEXT("range_min"), M);
		D.EveryHours = (float)H; D.RangeMinutes = (float)M;
		const TArray<TSharedPtr<FJsonValue>>* W = nullptr;
		if (O->TryGetArrayField(TEXT("world_cm"), W)) D.bHasWorld = Vec(W, D.World);
		const TSharedPtr<FJsonObject>* Sub;
		if (O->TryGetObjectField(TEXT("vars"), Sub)) for (const auto& KV : (*Sub)->Values) D.Vars.Add(FString(KV.Key), KV.Value->AsString());
		if (O->TryGetObjectField(TEXT("text"), Sub))
			for (const auto& KV : (*Sub)->Values)
			{
				FString S;
				if (!KV.Value->TryGetString(S)) { const TArray<TSharedPtr<FJsonValue>>* L; if (KV.Value->TryGetArray(L) && L->Num()) S = (*L)[FMath::RandRange(0, L->Num() - 1)]->AsString(); }
				D.Text.Add(FString(KV.Key), S);
			}
		if (O->TryGetObjectField(TEXT("villains"), Sub))
			for (const auto& KV : (*Sub)->Values)
			{
				TArray<FString>& L = D.Villains.Add(FString(KV.Key));
				for (const auto& V : KV.Value->AsArray()) L.Add(V->AsString());
			}
		return D;
	};
	const TSharedPtr<FJsonObject>* Obj;
	if (Root->TryGetObjectField(TEXT("names"), Obj)) for (const auto& KV : (*Obj)->Values) ZoneNames.Add(FString(KV.Key), KV.Value->AsString());
	// the zone events sit at one-world positions: only the ParagonCity map has them (invasions go anywhere)
	const bool bOneWorld = GetWorld()->GetMapName().Contains(TEXT("ParagonCity"));
	if (bOneWorld && Root->TryGetObjectField(TEXT("zone"), Obj))
		for (const auto& KV : (*Obj)->Values)
			for (const auto& V : KV.Value->AsArray())
			{
				FCoHZoneEventDef D = Read(V->AsObject(), FString(KV.Key));
				// ours: the fires, the rave and the Croatoa giants (KeepPopulated is the zone's own spawns)
				if (D.bHasWorld && (D.Script == TEXT("HellionsFire") || D.Script == TEXT("TrollsRave") || D.Script == TEXT("CroatoaBattle"))) Events.Add(MoveTemp(D));
			}
	if (Root->TryGetObjectField(TEXT("targets"), Obj))
		for (const auto& Z : (*Obj)->Values)
			for (const auto& KV : Z.Value->AsObject()->Values)
			{
				FVector P; const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
				if (KV.Value->TryGetArray(A) && Vec(A, P)) Targets.FindOrAdd(FString(Z.Key)).Add(FString(KV.Key), P);
			}
	const TArray<TSharedPtr<FJsonValue>>* CityA;
	if (Root->TryGetArrayField(TEXT("city"), CityA)) for (const auto& V : *CityA) City.Add(Read(V->AsObject(), FString()));
	UE_LOG(LogTemp, Log, TEXT("CoH zone events: %d zone events, %d city-wide"), Events.Num(), City.Num());
}

double ACoHZoneEvents::Schedule(const FCoHZoneEventDef& D) const
{
	// RunEvery hours, give or take RunEveryRange minutes
	return FMath::Max(60.0, (D.EveryHours * 3600.0 + FMath::FRandRange(-1.f, 1.f) * D.RangeMinutes * 60.0) * TimeScale);
}

TArray<APawn*> ACoHZoneEvents::Heroes() const
{
	TArray<APawn*> Out;
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
		if (APawn* P = It->Get() ? It->Get()->GetPawn() : nullptr)
		{
			const UCoHPowerComponent* C = UCoHPowerComponent::Of(P);
			if (C && !C->IsDefeated()) Out.Add(P);
		}
	return Out;
}

FString ACoHZoneEvents::ZoneAt(const FVector& Pos) const
{
	if (const UCoHGameRules* GR = UCoHGameRules::Get(this))
		for (const auto& R : GR->ZoneRects) if (R.Value.IsInside(FVector2D(Pos.X, Pos.Y))) return R.Key;
	return FString();
}

void ACoHZoneEvents::Announce(const FString& Text, const FVector* Near, float RadiusCm) const
{
	if (Text.IsEmpty()) return;
	// the original's zone-wide alert: every hero in the zone (or near), in chat and over their heads
	for (APawn* P : Heroes())
	{
		if (Near && FVector::Dist2D(P->GetActorLocation(), *Near) > RadiusCm) continue;
		if (UCoHSocial* S = UCoHSocial::Of(P)) S->Tell(ECoHChat::System, FString(), Text);
		if (UCoHPowerComponent* C = UCoHPowerComponent::Of(P)) C->MulticastText(Text, FLinearColor(1.f, 0.55f, 0.3f));
	}
}

void ACoHZoneEvents::MulticastFire_Implementation(FVector_NetQuantize Where, float Radius, FLinearColor Colour)
{
	ACoHPowerFX::Burst(this, Where, Radius, Colour, 1.6f, 0.f);
}

static FString CoHZoneEventText(const FCoHZoneEventDef& D, const TCHAR* Key, const FString& Zone)
{
	const FString* T = D.Text.Find(Key);
	if (!T || T->IsEmpty()) return FString();
	FString S = T->Replace(TEXT("{zonename}"), *Zone).Replace(TEXT("{ZoneName}"), *Zone);
	// the invasion messages end on the zone ("heading for")
	if (!T->Contains(TEXT("{zonename}")) && (S.EndsWith(TEXT("for")) || S.EndsWith(TEXT("in")) || S.EndsWith(TEXT("from")))) S += TEXT(" ") + Zone + TEXT("!");
	// emotes (<em dance>) are for the speaker's body
	int32 A;
	while (S.FindChar(TEXT('<'), A)) { const int32 B = S.Find(TEXT(">"), ESearchCase::CaseSensitive, ESearchDir::FromStart, A); if (B == INDEX_NONE) break; S.RemoveAt(A, B - A + 1); }
	return S.TrimStartAndEnd();
}

ACoHCombatEnemy* ACoHZoneEvents::SpawnFoe(FRunning& R, const FString& Villain, const FVector& At, APawn* Target)
{
	ACoHEnemySpawner* Sp = nullptr;
	for (TActorIterator<ACoHEnemySpawner> It(GetWorld()); It; ++It) { Sp = *It; break; }
	if (!Sp || Villain.IsEmpty()) return nullptr;
	// on the ground (the original markers sit on roofs and in streets)
	FVector Spot = At; FHitResult Hit; FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHZoneEventSpot), true);
	if (GetWorld()->LineTraceSingleByObjectType(Hit, At + FVector(0, 0, 4000.f), At - FVector(0, 0, 20000.f), FCollisionObjectQueryParams(ECC_WorldStatic), Q)) Spot = Hit.ImpactPoint;
	ACoHCombatEnemy* E = Sp->SpawnKitVillain(Villain, R.Level, Spot, FRotator(0, FMath::FRandRange(0.f, 360.f), 0));
	if (!E) return nullptr;
	E->SetHome(R.Center);
	if (Target) E->Alert(Target);
	R.Foes.Add(E);
	++R.Spawned;
	return E;
}

bool ACoHZoneEvents::Start(const FCoHZoneEventDef& D, const FVector& Center, APawn* Near)
{
	for (const FRunning& X : Running) if (X.Def == &D) return false;
	FRunning R;
	R.Def = &D; R.Center = Center;
	const double Now = GetWorld()->GetTimeSeconds();
	R.Started = R.NextSpawn = R.LastHeroNear = Now;
	const FString Zone = ZoneName(D.Zone.IsEmpty() ? ZoneAt(Center) : D.Zone);
	const UCoHHeroProgress* HP = UCoHHeroProgress::Of(Near);
	const int32 HeroLevel = HP && HP->bHasRecord ? HP->EffectiveLevel() : 10;
	// heroes near enough to take part: a small server gets a smaller event
	int32 Near300 = 0;
	for (APawn* P : Heroes()) if (FVector::Dist2D(P->GetActorLocation(), Center) < 30000.f) ++Near300;
	const int32 Share = FMath::Max(1, Near300);
	if (D.Script == TEXT("HellionsFire") || D.Script == TEXT("TrollsRave"))
	{
		R.Level = D.Int(TEXT("SpawnLevel"), 10);
		R.MaxAlive = FMath::Min(D.Int(D.Script == TEXT("HellionsFire") ? TEXT("MaxHellions") : TEXT("MaxTrolls"), 20), 6 + 4 * Share);
		R.Total = FMath::Min(D.Int(D.Script == TEXT("HellionsFire") ? TEXT("TotalHellions") : TEXT("TotalTrolls"), 100), 20 * Share);
		Announce(CoHZoneEventText(D, TEXT("AlertMessage"), Zone), nullptr, 0.f);
		Announce(CoHZoneEventText(D, TEXT("PoliceSpeech"), Zone), &Center, 15000.f);
	}
	else if (D.Script == TEXT("CroatoaBattle"))
	{
		// the giants come out (ChanceOfGiants % when it runs on its own; always when asked)
		R.Level = FMath::Clamp(HeroLevel, 20, 30);
		R.Total = 0; R.MaxAlive = 0;
		Announce(CoHZoneEventText(D, TEXT("AlertMessage"), Zone), nullptr, 0.f);
	}
	else
	{
		// invasions: around every hero, at the hero's level
		R.Level = HeroLevel;
		R.Total = FMath::Clamp(25 * Heroes().Num(), 25, D.Int(TEXT("MaxInvasion"), 200));
		R.MaxAlive = 8 + 4 * Heroes().Num();
		R.NextSpawn = Now + 45.0;          // the warning first, then the ships
		Announce(CoHZoneEventText(D, TEXT("AlertMessage"), Zone.IsEmpty() ? FString(TEXT("Paragon City")) : Zone), nullptr, 0.f);
	}
	UE_LOG(LogTemp, Log, TEXT("CoH zone event %s (%s) starts in %s, level %d, %d foes"), *D.Script, *D.Marker, *Zone, R.Level, R.Total);
	Running.Add(MoveTemp(R));
	return true;
}

void ACoHZoneEvents::Tick(float Dt)
{
	Super::Tick(Dt);
	if (!HasAuthority() || !bZoneEvents) return;
	const double Now = GetWorld()->GetTimeSeconds();
	for (int32 i = Running.Num() - 1; i >= 0; --i)
	{
		TickEvent(Running[i], Now);
		if (Running[i].Stage < 0) Running.RemoveAt(i);
	}
	if (Now < NextCheck) return;
	NextCheck = Now + 10.0;
	const TArray<APawn*> Hs = Heroes();
	if (Hs.Num() == 0) return;
	// a zone event starts when its time comes and a hero is in its zone
	for (int32 i = 0; i < Events.Num(); ++i)
	{
		double& Next = NextRun.FindOrAdd(i);
		if (Now < Next) continue;
		Next = Now + Schedule(Events[i]);
		const FCoHZoneEventDef& D = Events[i];
		APawn* In = nullptr;
		for (APawn* P : Hs) if (ZoneAt(P->GetActorLocation()) == D.Zone) { In = P; break; }
		if (!In) continue;
		bool bBusy = false;      // one event of a kind per zone at a time
		for (const FRunning& X : Running) if (X.Def->Script == D.Script && X.Def->Zone == D.Zone) bBusy = true;
		if (bBusy) continue;
		if (D.Script == TEXT("CroatoaBattle") && FMath::FRand() * 100.f >= D.Int(TEXT("ChanceOfGiants"), 25)) continue;
		Start(D, D.World, In);
	}
	for (int32 i = 0; i < City.Num(); ++i)
	{
		double& Next = NextRun.FindOrAdd(-1 - i);
		if (Now < Next || InvasionHours.Y <= 0.f) continue;
		Next = Now + FMath::FRandRange(InvasionHours.X, InvasionHours.Y) * 3600.0 * TimeScale;
		const bool bInvading = Running.ContainsByPredicate([](const FRunning& X) { return X.Def->Zone.IsEmpty(); });
		if (!bInvading) Start(City[i], Hs[0]->GetActorLocation(), Hs[0]);
	}
}

void ACoHZoneEvents::TickEvent(FRunning& R, double Now)
{
	const FCoHZoneEventDef& D = *R.Def;
	R.Foes.RemoveAll([](const TWeakObjectPtr<ACoHCombatEnemy>& E) { return !E.IsValid() || E->IsDead(); });
	const TArray<APawn*> Hs = Heroes();
	const bool bCity = D.Zone.IsEmpty();
	// heroes taking part (near the event; anyone for an invasion)
	TArray<APawn*> Near;
	for (APawn* P : Hs) if (bCity || FVector::Dist2D(P->GetActorLocation(), R.Center) < 30000.f) Near.Add(P);
	if (Near.Num()) R.LastHeroNear = Now;
	// nobody came, or it went on too long: the event ends (a lost fire burns the building down)
	const double Limit = bCity ? 20.0 * 60.0 : 15.0 * 60.0;
	if (Now - R.LastHeroNear > 180.0 || Now - R.Started > Limit) { Finish(R, false); return; }
	if (D.Script == TEXT("HellionsFire") && Now >= R.NextFx)
	{
		// the building burns: fire bursts around the marker while the event runs
		R.NextFx = Now + 1.5;
		const FVector P = R.Center + FVector(FMath::FRandRange(-1500.f, 1500.f), FMath::FRandRange(-1500.f, 1500.f), FMath::FRandRange(200.f, 2500.f));
		MulticastFire(P, FMath::FRandRange(250.f, 600.f), FLinearColor(1.f, 0.35f, 0.05f));
	}
	if (D.Script == TEXT("CroatoaBattle"))
	{
		if (R.Stage == 0)
		{
			R.Stage = 1;
			for (const TCHAR* K : { TEXT("RedcapGiantSpawnDef"), TEXT("FirbolgGiantSpawnDef") })
				if (const TArray<FString>* L = D.Villains.Find(K))
					if (L->Num()) SpawnFoe(R, (*L)[0], R.Center + FVector(FMath::FRandRange(-3000.f, 3000.f), FMath::FRandRange(-3000.f, 3000.f), 0), nullptr);
			if (R.Foes.Num() == 0) { Finish(R, false); return; }
		}
		else if (R.Foes.Num() == 0) Finish(R, true);
		return;
	}
	if (Now < R.NextSpawn) return;
	R.NextSpawn = Now + (bCity ? 6.0 : 2.0);
	if (R.Spawned < R.Total)
	{
		if (R.Foes.Num() >= R.MaxAlive || Near.Num() == 0) return;
		// the next few: around the marker (fires, rave) or around each hero (invasions)
		APawn* Hero = Near[FMath::RandRange(0, Near.Num() - 1)];
		const FVector Around = bCity ? Hero->GetActorLocation() : R.Center;
		const float Dist = bCity ? FMath::Max(D.Int(TEXT("InvaderSpawnDistance"), 500) * ZoneEventFeet * 0.25f, 2500.f) : 1500.f;
		const int32 N = FMath::Min(FMath::RandRange(2, 4), FMath::Min(R.Total - R.Spawned, R.MaxAlive - R.Foes.Num()));
		const FVector GroupAt = Around + FRotator(0, FMath::FRandRange(0.f, 360.f), 0).RotateVector(FVector(Dist, 0, 0));
		for (int32 k = 0; k < N; ++k)
		{
			const TArray<FString>* L = nullptr;
			if (D.Script == TEXT("HellionsFire")) L = D.Villains.Find(TEXT("Hellions"));
			else if (D.Script == TEXT("TrollsRave")) L = D.Villains.Find(FMath::RandBool() ? TEXT("TrollsSpawnFar") : TEXT("TrollsSpawnDoor"));
			else L = D.Villains.Find(FMath::FRand() < 0.01f ? TEXT("InvaderListEB") : FMath::FRand() < 0.1f ? TEXT("InvaderListBoss") : TEXT("InvaderList"));
			if (!L || L->Num() == 0) L = D.Villains.Find(TEXT("InvaderList"));
			if (!L || L->Num() == 0) continue;
			ACoHCombatEnemy* E = SpawnFoe(R, (*L)[FMath::RandRange(0, L->Num() - 1)], GroupAt + FVector(FMath::FRandRange(-300.f, 300.f), FMath::FRandRange(-300.f, 300.f), 0), bCity ? Hero : nullptr);
			// ravers head for the party spots
			if (E && D.Script == TEXT("TrollsRave"))
				if (const TMap<FString, FVector>* T = Targets.Find(D.Zone))
				{
					TArray<FVector> Spots; T->GenerateValueArray(Spots);
					if (Spots.Num()) E->SetHome(Spots[FMath::RandRange(0, Spots.Num() - 1)]);
				}
		}
		if (bCity && R.Stage == 0 && R.Spawned > 0)
		{
			R.Stage = 1;
			const FString Zone = ZoneName(ZoneAt(Hero->GetActorLocation()));
			Announce(CoHZoneEventText(D, TEXT("InvasionMessage"), Zone.IsEmpty() ? FString(TEXT("Paragon City")) : Zone) + TEXT(" ") + CoHZoneEventText(D, TEXT("InvasionMessagePost"), Zone), nullptr, 0.f);
		}
		return;
	}
	// all came: then the bosses (the Arson boss, the Supa Troll)
	if (!R.bBoss && !bCity)
	{
		R.bBoss = true;
		const FString Boss = D.Var(TEXT("BossName"));
		const int32 N = FMath::Clamp(D.Int(TEXT("BossNumber"), 1), 1, 3);
		for (int32 k = 0; k < N; ++k) SpawnFoe(R, Boss, R.Center + FVector(FMath::FRandRange(-800.f, 800.f), FMath::FRandRange(-800.f, 800.f), 0), Near.Num() ? Near[0] : nullptr);
		return;
	}
	if (R.Foes.Num() == 0) Finish(R, true);
}

void ACoHZoneEvents::Finish(FRunning& R, bool bWon)
{
	const FCoHZoneEventDef& D = *R.Def;
	const bool bCity = D.Zone.IsEmpty();
	const FString Zone = ZoneName(bCity ? ZoneAt(R.Center) : D.Zone);
	if (bCity) Announce(CoHZoneEventText(D, TEXT("DoneMessage"), Zone.IsEmpty() ? FString(TEXT("Paragon City")) : Zone), nullptr, 0.f);
	else if (D.Script == TEXT("CroatoaBattle")) { if (bWon) Announce(CoHZoneEventText(D, TEXT("ClearMessage"), Zone), nullptr, 0.f); }
	else
	{
		Announce(CoHZoneEventText(D, TEXT("CompleteMessage"), Zone), nullptr, 0.f);
		Announce(CoHZoneEventText(D, bWon ? TEXT("PoliceCheer") : TEXT("PoliceBoo"), Zone), &R.Center, 15000.f);
		Announce(CoHZoneEventText(D, bWon ? TEXT("CrowdCheer") : TEXT("CrowdBoo"), Zone), &R.Center, 15000.f);
	}
	// a win pays the heroes who were there (RewardRadius feet), as the event's reward table did
	if (bWon && !bCity)
	{
		const float Radius = FMath::Max(D.Int(TEXT("RewardRadius"), 300), 300) * ZoneEventFeet;
		for (APawn* P : Heroes())
			if (FVector::Dist2D(P->GetActorLocation(), R.Center) <= Radius)
				if (UCoHHeroProgress* H = UCoHHeroProgress::Of(P)) H->Award(R.Level * 60, R.Level * 40);
	}
	// what's left of the event's villains leaves
	for (const TWeakObjectPtr<ACoHCombatEnemy>& E : R.Foes) if (E.IsValid() && !E->IsBusy()) E->SetLifeSpan(5.f);
	UE_LOG(LogTemp, Log, TEXT("CoH zone event %s (%s) %s"), *D.Script, *D.Marker, bWon ? TEXT("won") : TEXT("ended"));
	R.Stage = -1;
}

FString ACoHZoneEvents::Command(const FString& What, APawn* Who)
{
	if (!HasAuthority()) return TEXT("Only the host can start zone events.");
	if (What.IsEmpty() || What == TEXT("list"))
	{
		TArray<FString> Names;
		for (const FCoHZoneEventDef& D : Events) Names.AddUnique(D.Script + TEXT(" (") + ZoneName(D.Zone) + TEXT(")"));
		for (const FCoHZoneEventDef& D : City) Names.AddUnique(D.Script);
		FString Out = TEXT("Zone events: ") + FString::Join(Names, TEXT(", "));
		if (Running.Num()) { Out += TEXT(". Running:"); for (const FRunning& R : Running) Out += TEXT(" ") + R.Def->Script; }
		return Out;
	}
	if (What == TEXT("stop"))
	{
		for (FRunning& R : Running) Finish(R, false);
		Running.Reset();
		return TEXT("Zone events stopped.");
	}
	// the nearest marker of that script (or the marker named), else a city-wide one
	const FCoHZoneEventDef* Best = nullptr; float BestD = TNumericLimits<float>::Max();
	for (const FCoHZoneEventDef& D : Events)
	{
		if (!D.Script.Equals(What, ESearchCase::IgnoreCase) && !D.Marker.Equals(What, ESearchCase::IgnoreCase)) continue;
		const float Dd = Who ? FVector::Dist(Who->GetActorLocation(), D.World) : 0.f;
		if (Dd < BestD) { BestD = Dd; Best = &D; }
	}
	if (Best) return Start(*Best, Best->World, Who) ? FString::Printf(TEXT("%s started in %s (%s)"), *Best->Script, *ZoneName(Best->Zone), *Best->Marker) : TEXT("That event is already running.");
	for (const FCoHZoneEventDef& D : City)
		if (D.Script.Equals(What, ESearchCase::IgnoreCase) || D.Def.Equals(What, ESearchCase::IgnoreCase))
			return Start(D, Who ? Who->GetActorLocation() : FVector::ZeroVector, Who) ? D.Script + TEXT(" started") : TEXT("That event is already running.");
	return TEXT("No zone event called ") + What + TEXT(" (/zoneevent list)");
}

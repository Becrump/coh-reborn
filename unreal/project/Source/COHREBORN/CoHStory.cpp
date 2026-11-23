#include "CoHStory.h"
#include "CoHCombat.h"
#include "CoHHeroProgress.h"
#include "CoHItems.h"
#include "CoHSocial.h"
#include "CoHPowers.h"
#include "Animation/AnimSequenceBase.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LevelStreamingDynamic.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "NavigationSystem.h"
#include "Net/UnrealNetwork.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/ConstructorHelpers.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/SWeakWidget.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Styling/CoreStyle.h"

// ------------------------------------------------------------------ json helpers (file-local names: unity build)
// (unique names: the unity build joins this file with CoHEffects.cpp, which has its own Str/Num)
	static FString StoryStr(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
	{
		FString V; if (O.IsValid()) O->TryGetStringField(K, V); return V;
	}
	static double StoryNum(const TSharedPtr<FJsonObject>& O, const TCHAR* K, double D = 0)
	{
		double V = D; if (O.IsValid()) O->TryGetNumberField(K, V); return V;
	}
	static int32 StoryInt(const TSharedPtr<FJsonObject>& O, const TCHAR* K, int32 D = 0)
	{
		double V = D; if (O.IsValid()) O->TryGetNumberField(K, V); return (int32)V;
	}
	static bool StoryFlag(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
	{
		bool V = false; if (O.IsValid()) O->TryGetBoolField(K, V); return V;
	}
	static TArray<FString> StoryList(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
	{
		TArray<FString> Out;
		const TArray<TSharedPtr<FJsonValue>>* A;
		if (O.IsValid() && O->TryGetArrayField(K, A)) for (const auto& V : *A) { FString S; if (V->TryGetString(S)) Out.Add(S); }
		return Out;
	}
	static FVector StoryVec(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
	{
		const TArray<TSharedPtr<FJsonValue>>* A;
		if (O.IsValid() && O->TryGetArrayField(K, A) && A->Num() >= 3) return FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber());
		return FVector::ZeroVector;
	}
	static FCoHStoryClues StoryClues(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
	{
		FCoHStoryClues C;
		const TSharedPtr<FJsonObject>* Sub;
		if (!O.IsValid() || !O->TryGetObjectField(K, Sub)) return C;
		C.Add = StoryList(*Sub, TEXT("add")); C.Remove = StoryList(*Sub, TEXT("remove")); C.Souvenirs = StoryList(*Sub, TEXT("souvenirs"));
		return C;
	}
	static TSharedPtr<FJsonObject> StoryObj(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
	{
		const TSharedPtr<FJsonObject>* P; return O.IsValid() && O->TryGetObjectField(K, P) ? *P : nullptr;
	}

// ------------------------------------------------------------------ UCoHStory
void UCoHStory::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	const double T0 = FPlatformTime::Seconds();
	FString File = StoryFile;
	if (File.IsEmpty())
	{
		FString Rules;
		GConfig->GetString(TEXT("/Script/COHREBORN.CoHPowerDatabase"), TEXT("RulesDir"), Rules, GGameIni);
		if (Rules.IsEmpty()) Rules = FPaths::ProjectContentDir() / TEXT("CoH/Data/Rules");
		File = FPaths::GetPath(Rules) / TEXT("story/story_game.json");      // <out>/rules -> <out>/story
	}
	FString Text;
	TSharedPtr<FJsonObject> Root;
	if (!FFileHelper::LoadFileToString(Text, *File) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH story: no %s (run tools/imports/finish_imports.cmd convert): no contacts or missions"), *File);
		return;
	}
	if (const auto Cs = StoryObj(Root, TEXT("contacts")))
		for (const auto& KV : Cs->Values)
		{
			const auto O = KV.Value->AsObject();
			FCoHStoryContact C;
			C.Id = FString(KV.Key); C.Name = StoryStr(O, TEXT("name")); C.Profession = StoryStr(O, TEXT("profession"));
			C.Description = StoryStr(O, TEXT("description")); C.Location = StoryStr(O, TEXT("location"));
			C.Zone = StoryStr(O, TEXT("zone")); C.Model = StoryStr(O, TEXT("model"));
			C.Pos = StoryVec(O, TEXT("pos")); C.Yaw = (float)StoryNum(O, TEXT("yaw"));
			C.MinLevel = StoryInt(O, TEXT("min_level"), 1); C.MaxLevel = StoryInt(O, TEXT("max_level"), 54);
			C.FriendCP = StoryInt(O, TEXT("friend_cp"), 10); C.ConfidantCP = StoryInt(O, TEXT("confidant_cp"), 20); C.CompleteCP = StoryInt(O, TEXT("complete_cp"), 30);
			C.bTaskForce = StoryFlag(O, TEXT("task_force"));
			C.Hello = StoryList(O, TEXT("hello"));
			C.FirstVisit = StoryStr(O, TEXT("first_visit")); C.DontKnow = StoryStr(O, TEXT("dont_know")); C.NoTasks = StoryStr(O, TEXT("no_tasks"));
			C.Busy = StoryStr(O, TEXT("busy")); C.ComeBack = StoryStr(O, TEXT("come_back"));
			C.ToFriend = StoryStr(O, TEXT("to_friend")); C.ToConfidant = StoryStr(O, TEXT("to_confidant"));
			C.Tasks = StoryList(O, TEXT("tasks")); C.Arcs = StoryList(O, TEXT("arcs"));
			C.Stores = StoryList(O, TEXT("stores")); C.Requires = StoryList(O, TEXT("requires"));
			Contacts.Add(C.Id, MoveTemp(C));
		}
	if (const auto Ps = StoryObj(Root, TEXT("people")))
		for (const auto& KV : Ps->Values)
		{
			const auto O = KV.Value->AsObject();
			FCoHStoryPerson P;
			P.Id = FString(KV.Key); P.Name = StoryStr(O, TEXT("name")); P.Zone = StoryStr(O, TEXT("zone")); P.Model = StoryStr(O, TEXT("model"));
			P.Line = StoryStr(O, TEXT("line")); P.Store = StoryStr(O, TEXT("store")); P.Pos = StoryVec(O, TEXT("pos")); P.Yaw = (float)StoryNum(O, TEXT("yaw"));
			People.Add(P.Id, MoveTemp(P));
		}
	if (const auto Ts = StoryObj(Root, TEXT("tasks")))
		for (const auto& KV : Ts->Values)
		{
			const auto O = KV.Value->AsObject();
			FCoHStoryTask T;
			T.Id = FString(KV.Key); T.Type = StoryStr(O, TEXT("type"));
			T.Intro = StoryStr(O, TEXT("intro")); T.Accept = StoryStr(O, TEXT("accept")); T.SendOff = StoryStr(O, TEXT("sendoff"));
			T.Active = StoryStr(O, TEXT("active")); T.Busy = StoryStr(O, TEXT("busy")); T.Title = StoryStr(O, TEXT("title"));
			T.Begin = StoryStr(O, TEXT("begin")); T.Complete = StoryStr(O, TEXT("complete")); T.Return = StoryStr(O, TEXT("return"));
			T.Reward = StoryStr(O, TEXT("reward")); T.CompleteReward = StoryStr(O, TEXT("complete_reward"));
			T.Next = StoryStr(O, TEXT("next")); T.Arc = StoryStr(O, TEXT("arc")); T.bAutoNext = StoryFlag(O, TEXT("auto_next"));
			T.bLong = StoryFlag(O, TEXT("long")); T.bRequired = StoryFlag(O, TEXT("required")); T.bNoReturn = StoryFlag(O, TEXT("no_return"));
			T.MinLevel = StoryInt(O, TEXT("min_level"), 1); T.MaxLevel = StoryInt(O, TEXT("max_level"), 54);
			T.ContactPoints = StoryInt(O, TEXT("contact_points"));
			if (const auto K = StoryObj(O, TEXT("killx")))
			{
				T.KillGroup = StoryStr(K, TEXT("group")); T.KillCount = StoryInt(K, TEXT("count"), 5);
				T.KillZone = StoryStr(K, TEXT("zone")); T.KillWhat = StoryStr(K, TEXT("what"));
			}
			if (const auto D = StoryObj(O, TEXT("deliver"))) { T.DeliverNpc = StoryStr(D, TEXT("npc")); T.DeliverContact = StoryStr(D, TEXT("contact")); }
			if (const auto V = StoryObj(O, TEXT("visit"))) T.VisitLocation = StoryStr(V, TEXT("location"));
			if (const auto M = StoryObj(O, TEXT("mission")))
			{
				T.MapSet = StoryStr(M, TEXT("mapset")); T.MissionGroup = StoryStr(M, TEXT("group")); T.MissionZone = StoryStr(M, TEXT("zone"));
				T.Door = StoryStr(M, TEXT("door")); T.Entry = StoryStr(M, TEXT("entry")); T.MapLength = StoryInt(M, TEXT("length"), 15);
				T.CompleteWith = StoryList(M, TEXT("complete_with")); T.FailWith = StoryList(M, TEXT("fail_with"));
				const TArray<TSharedPtr<FJsonValue>>* A;
				if (M->TryGetArrayField(TEXT("objectives"), A))
					for (const auto& V : *A)
					{
						const auto OO = V->AsObject();
						FCoHStoryObjective Ob;
						Ob.Name = StoryStr(OO, TEXT("name")); Ob.Display = StoryStr(OO, TEXT("display")); Ob.Begin = StoryStr(OO, TEXT("begin"));
						Ob.Done = StoryStr(OO, TEXT("done")); Ob.Reward = StoryStr(OO, TEXT("reward")); Ob.Number = FMath::Clamp(StoryInt(OO, TEXT("number"), 1), 1, 8);
						Ob.Location = StoryStr(OO, TEXT("location")); Ob.Placement = StoryStr(OO, TEXT("placement")); Ob.Desc = StoryStr(OO, TEXT("desc"));
						Ob.Delay = FMath::Clamp(StoryInt(OO, TEXT("delay")), 0, 30); Ob.ActivateOn = StoryList(OO, TEXT("activate_on"));
						Ob.Clues = StoryClues(OO, TEXT("clues"));
						T.Objectives.Add(Ob);
					}
				if (M->TryGetArrayField(TEXT("spawns"), A))
					for (const auto& V : *A)
					{
						const auto SO = V->AsObject();
						FCoHStorySpawn Sp;
						Sp.Logical = StoryStr(SO, TEXT("logical")); Sp.Placement = StoryStr(SO, TEXT("placement"));
						Sp.Group = StoryStr(SO, TEXT("group")); Sp.Villain = StoryStr(SO, TEXT("villain")); Sp.Display = StoryStr(SO, TEXT("display"));
						Sp.Count = FMath::Clamp(StoryInt(SO, TEXT("count"), 1), 1, 6); Sp.Lines = StoryList(SO, TEXT("lines"));
						Sp.Kind = StoryStr(SO, TEXT("kind")); if (Sp.Kind.IsEmpty()) Sp.Kind = TEXT("fight");
						Sp.Objective = StoryStr(SO, TEXT("objective")); Sp.ObjectiveText = StoryStr(SO, TEXT("objective_text"));
						Sp.RewardText = StoryStr(SO, TEXT("reward")); Sp.Clues = StoryClues(SO, TEXT("clues"));
						Sp.CreateOn = StoryList(SO, TEXT("create_on")); Sp.ActivateOn = StoryList(SO, TEXT("activate_on"));
						if (const auto H = StoryObj(SO, TEXT("hostage"))) { Sp.HostageVillain = StoryStr(H, TEXT("villain")); Sp.HostageName = StoryStr(H, TEXT("name")); }
						const TArray<TSharedPtr<FJsonValue>>* Ac;
						if (SO->TryGetArrayField(TEXT("actors"), Ac))
							for (const auto& AV : *Ac)
							{
								const auto AO = AV->AsObject();
								if (!AO.IsValid()) continue;
								FCoHStoryActor Act;
								Act.Role = StoryStr(AO, TEXT("role")); Act.Villain = StoryStr(AO, TEXT("villain")); Act.Group = StoryStr(AO, TEXT("group"));
								Act.Rank = StoryStr(AO, TEXT("rank")); Act.Name = StoryStr(AO, TEXT("name"));
								Act.Number = FMath::Clamp(StoryInt(AO, TEXT("number"), 1), 1, 8);
								const TArray<FString> Say = StoryList(AO, TEXT("say"));
								if (Say.Num() > 0) Act.SayIdle = Say[0];
								if (Say.Num() > 1) Act.SayAlert = Say[1];
								const TArray<TSharedPtr<FJsonValue>>* H;
								if (AO->TryGetArrayField(TEXT("heroes"), H) && H->Num() == 2) { Act.MinHeroes = (int32)(*H)[0]->AsNumber(); Act.MaxHeroes = (int32)(*H)[1]->AsNumber(); }
								Sp.Actors.Add(Act);
							}
						T.Spawns.Add(Sp);
					}
			}
			if (const auto Cl = StoryObj(O, TEXT("clues")))
			{
				T.BeginClues = StoryClues(Cl, TEXT("begin")); T.CompleteClues = StoryClues(Cl, TEXT("complete")); T.ReturnClues = StoryClues(Cl, TEXT("return"));
			}
			Tasks.Add(T.Id, MoveTemp(T));
		}
	for (const TCHAR* Which : { TEXT("clues"), TEXT("souvenirs") })
		if (const auto Cs = StoryObj(Root, Which))
			for (const auto& KV : Cs->Values)
			{
				const auto O = KV.Value->AsObject();
				if (!O.IsValid()) continue;
				(FCString::Strcmp(Which, TEXT("clues")) == 0 ? Clues : Souvenirs).Add(FString(KV.Key).ToLower(), { StoryStr(O, TEXT("name")), StoryStr(O, TEXT("text")) });
			}
	for (const auto& KV : Tasks)
		if (!KV.Value.Next.IsEmpty() && !KV.Value.bAutoNext) Prev.Add(KV.Value.Next, KV.Key);
	if (const auto As = StoryObj(Root, TEXT("arcs")))
		for (const auto& KV : As->Values)
		{
			const auto O = KV.Value->AsObject();
			FCoHStoryArc A;
			A.Name = StoryStr(O, TEXT("name")); A.MinLevel = StoryInt(O, TEXT("min_level"), 1); A.MaxLevel = StoryInt(O, TEXT("max_level"), 54);
			A.Episodes = StoryList(O, TEXT("episodes"));
			Arcs.Add(FString(KV.Key), MoveTemp(A));
		}
	if (const auto Ds = StoryObj(Root, TEXT("doors")))
		for (const auto& KV : Ds->Values)
		{
			TArray<FCoHStoryDoor>& List = Doors.FindOrAdd(FString(KV.Key));
			for (const auto& V : KV.Value->AsArray())
			{
				const auto O = V->AsObject();
				FCoHStoryDoor D; D.Lair = StoryList(O, TEXT("lair")); D.Pos = StoryVec(O, TEXT("pos")); D.Yaw = (float)StoryNum(O, TEXT("yaw"));
				List.Add(D);
			}
		}
	if (const auto Vs = StoryObj(Root, TEXT("visits")))
		for (const auto& KV : Vs->Values)
		{
			auto& List = Visits.FindOrAdd(FString(KV.Key));
			for (const auto& V : KV.Value->AsArray()) { const auto O = V->AsObject(); List.Add({ StoryStr(O, TEXT("name")), StoryVec(O, TEXT("pos")) }); }
		}
	if (const auto Sp = StoryObj(Root, TEXT("spawns")))
		for (const auto& KV : Sp->Values)
		{
			const FString Zone = FString(KV.Key);
			if (NoHospitalZones.Contains(Zone)) continue;
			for (const auto& V : KV.Value->AsArray())
			{
				const auto O = V->AsObject();
				if (O.IsValid() && StoryStr(O, TEXT("name")).Equals(TEXT("gurney"), ESearchCase::IgnoreCase)) Gurneys.FindOrAdd(Zone).Add(StoryVec(O, TEXT("pos")));
			}
		}
	if (const auto Rs = StoryObj(Root, TEXT("rewards")))
		for (const auto& KV : Rs->Values)
		{
			auto& Levels = Rewards.FindOrAdd(FString(KV.Key).ToLower());
			for (const auto& L : KV.Value->AsObject()->Values)
			{
				const auto O = L.Value->AsObject();
				FCoHStoryReward R; R.XP = StoryInt(O, TEXT("xp")); R.Influence = StoryInt(O, TEXT("inf"));
				const TArray<TSharedPtr<FJsonValue>>* Drops;
				if (O->TryGetArrayField(TEXT("drops"), Drops))
					for (const auto& D : *Drops)
					{
						const auto& DA = D->AsArray();
						if (DA.Num() < 2) continue;
						TArray<FString> Sets; for (const auto& SV : DA[1]->AsArray()) Sets.Add(SV->AsString());
						R.Drops.Add({ (float)DA[0]->AsNumber(), Sets });
					}
				Levels.Add(FCString::Atoi(*FString(L.Key)), R);
			}
		}
	UE_LOG(LogTemp, Log, TEXT("CoH story: %d contacts, %d people, %d tasks, %d arcs, %d reward tables, %d clues, %d souvenirs (%.1f s)"),
		Contacts.Num(), People.Num(), Tasks.Num(), Arcs.Num(), Rewards.Num(), Clues.Num(), Souvenirs.Num(), FPlatformTime::Seconds() - T0);
	LoadMaps(MissionsFile.IsEmpty() ? FPaths::GetPath(FPaths::GetPath(File)) / TEXT("missions/missions.json") : MissionsFile);
}

void UCoHStory::LoadMaps(const FString& File)
{
	FString Text;
	TSharedPtr<FJsonObject> Root;
	if (!FFileHelper::LoadFileToString(Text, *File) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH story: no %s (tools/missions/mission_maps.py): door missions play at the door"), *File);
		return;
	}
	auto Spot = [](const TSharedPtr<FJsonObject>& O)
	{
		FCoHMapSpot S; S.Pos = StoryVec(O, TEXT("pos")); S.Yaw = (float)StoryNum(O, TEXT("yaw"));
		S.Rank = StoryStr(O, TEXT("rank")); S.Kind = StoryStr(O, TEXT("kind"));
		const TArray<TSharedPtr<FJsonValue>>* A;
		if (O->TryGetArrayField(TEXT("spots"), A))
			for (const auto& V : *A)
			{
				const auto& P = V->AsArray();
				if (P.Num() >= 3) S.Spots.Add(FVector(P[0]->AsNumber(), P[1]->AsNumber(), P[2]->AsNumber()));
			}
		return S;
	};
	if (const auto Ms = StoryObj(Root, TEXT("maps")))
		for (const auto& KV : Ms->Values)
		{
			const auto O = KV.Value->AsObject();
			if (!O.IsValid()) continue;
			FCoHMissionMap M;
			M.Id = FString(KV.Key); M.Set = StoryStr(O, TEXT("set")); M.Length = StoryInt(O, TEXT("length"), 30);
			const auto St = StoryObj(O, TEXT("start"));
			M.Start = StoryVec(St, TEXT("pos")); M.StartYaw = (float)StoryNum(St, TEXT("yaw"));
			M.Exit = StoryVec(StoryObj(O, TEXT("exit")), TEXT("pos"));
			const TArray<TSharedPtr<FJsonValue>>* A;
			if (O->TryGetArrayField(TEXT("bounds"), A) && A->Num() == 2)
			{
				const auto& Lo = (*A)[0]->AsArray(); const auto& Hi = (*A)[1]->AsArray();
				if (Lo.Num() >= 3 && Hi.Num() >= 3)
				{
					M.BoundsMin = FVector(Lo[0]->AsNumber(), Lo[1]->AsNumber(), Lo[2]->AsNumber());
					M.BoundsMax = FVector(Hi[0]->AsNumber(), Hi[1]->AsNumber(), Hi[2]->AsNumber());
				}
			}
			if (O->TryGetArrayField(TEXT("encounters"), A))
				for (const auto& V : *A) if (V->AsObject().IsValid()) M.Encounters.Add(Spot(V->AsObject()));
			if (const auto Ob = StoryObj(O, TEXT("objectives")))
				for (const auto& OK : Ob->Values)
				{
					TArray<FCoHMapSpot>& L = M.Objectives.FindOrAdd(FString(OK.Key));
					for (const auto& V : OK.Value->AsArray()) if (V->AsObject().IsValid()) L.Add(Spot(V->AsObject()));
				}
			Maps.Add(M.Id, MoveTemp(M));
		}
	if (const auto Ss = StoryObj(Root, TEXT("sets")))
		for (const auto& KV : Ss->Values)
		{
			TMap<int32, TArray<FString>>& Lens = MapSets.FindOrAdd(FString(KV.Key).ToLower());
			const auto O = KV.Value->AsObject();
			if (!O.IsValid()) continue;
			for (const auto& L : O->Values)
			{
				TArray<FString>& Ids = Lens.FindOrAdd(FCString::Atoi(*FString(L.Key)));
				for (const auto& V : L.Value->AsArray()) { FString Id; if (V->TryGetString(Id) && Maps.Contains(Id)) Ids.AddUnique(Id); }
			}
		}
	const TArray<TSharedPtr<FJsonValue>>* Sel;
	if (Root->TryGetArrayField(TEXT("select"), Sel))
		for (const auto& V : *Sel)
		{
			const auto O = V->AsObject();
			if (!O.IsValid()) continue;
			FCoHMapSelection S; S.Groups = StoryList(O, TEXT("groups")); S.MinLevel = StoryInt(O, TEXT("min"), 1);
			S.MaxLevel = StoryInt(O, TEXT("max"), 50); S.Set = StoryStr(O, TEXT("set"));
			MapSelect.Add(S);
		}
	UE_LOG(LogTemp, Log, TEXT("CoH story: %d indoor mission maps in %d map sets"), Maps.Num(), MapSets.Num());
}

const FCoHMissionMap* UCoHStory::PickMap(const FCoHStoryTask& T, int32 Level) const
{
	TArray<FString> Sets;
	if (!T.MapSet.IsEmpty()) Sets.Add(T.MapSet.ToLower());
	else
	{
		const FString G = T.MissionGroup.ToLower();
		for (const FCoHMapSelection& S : MapSelect)
			if (S.Groups.Contains(G) && Level >= S.MinLevel && Level <= S.MaxLevel) Sets.AddUnique(S.Set.ToLower());
		if (Sets.Num() == 0) { Sets.Add(TEXT("warehouse")); Sets.Add(TEXT("office")); }
	}
	// layouts of those sets, nearest length first, whose level is imported
	TArray<FString> Best; int32 BestGap = TNumericLimits<int32>::Max();
	for (const FString& Set : Sets)
	{
		const TMap<int32, TArray<FString>>* Lens = MapSets.Find(Set);
		if (!Lens) continue;
		for (const auto& L : *Lens)
		{
			TArray<FString> Have;
			for (const FString& Id : L.Value)
				if (const FCoHMissionMap* M = Maps.Find(Id))
					if (FPackageName::DoesPackageExist(M->Level())) Have.Add(Id);
			if (Have.Num() == 0) continue;
			const int32 Gap = FMath::Abs(L.Key - T.MapLength);
			if (Gap < BestGap) { BestGap = Gap; Best = Have; }
			else if (Gap == BestGap) Best.Append(Have);
		}
	}
	return Best.Num() ? Maps.Find(Best[FMath::RandRange(0, Best.Num() - 1)]) : nullptr;
}

FString UCoHStory::ClueKey(const FString& TaskId, const FString& Clue) const
{
	FString File = TaskId, Rest;
	TaskId.Split(TEXT("#"), &File, &Rest);
	return (File + TEXT("#") + Clue).ToLower();
}

UCoHStory* UCoHStory::Get(const UObject* WorldContext)
{
	const UWorld* W = WorldContext ? WorldContext->GetWorld() : nullptr;
	return W && W->GetGameInstance() ? W->GetGameInstance()->GetSubsystem<UCoHStory>() : nullptr;
}

FCoHStoryReward UCoHStory::Reward(const FString& Table, int32 Level) const
{
	const TMap<int32, FCoHStoryReward>* T = Rewards.Find(Table.ToLower());
	if (!T || T->Num() == 0) return FCoHStoryReward();
	if (const FCoHStoryReward* R = T->Find(Level)) return *R;
	// past the table's last level: its last row
	int32 Best = 0; for (const auto& KV : *T) if (KV.Key <= Level) Best = FMath::Max(Best, KV.Key);
	const FCoHStoryReward* R = T->Find(Best);
	return R ? *R : FCoHStoryReward();
}

FString UCoHStory::ZoneAt(const UObject* WorldContext, const FVector& Pos) const
{
	if (const UCoHGameRules* R = UCoHGameRules::Get(WorldContext))
		for (const auto& Z : R->ZoneRects)
			if (Z.Value.IsInside(FVector2D(Pos.X, Pos.Y))) return Z.Key;
	return FString();
}

bool UCoHStory::PickDoor(const FCoHStoryTask& T, const FString& FallbackZone, const FVector& Near, FCoHStoryDoor& Out) const
{
	FString Zone = T.MissionZone;
	if (Zone.IsEmpty() || Zone.StartsWith(TEXT("whereissued")) || !Doors.Contains(Zone)) Zone = FallbackZone;
	const TArray<FCoHStoryDoor>* List = Doors.Find(Zone);
	if (!List || List->Num() == 0) return false;
	// doors whose lair types name the task's door type (or map set), else any door
	TArray<const FCoHStoryDoor*> Match, Any;
	const FString Want = T.Door.ToLower(), Set = T.MapSet.ToLower();
	for (const FCoHStoryDoor& D : *List)
	{
		Any.Add(&D);
		for (const FString& L : D.Lair)
			if ((!Want.IsEmpty() && (L == Want || L.Contains(Want))) || (!Set.IsEmpty() && L == Set)) { Match.Add(&D); break; }
	}
	TArray<const FCoHStoryDoor*>& Pool = Match.Num() ? Match : Any;
	// one of the nearer half, so missions do not all send heroes across the zone
	Pool.Sort([&](const FCoHStoryDoor& A, const FCoHStoryDoor& B) { return FVector::DistSquared2D(A.Pos, Near) < FVector::DistSquared2D(B.Pos, Near); });
	const int32 N = FMath::Max(1, Pool.Num() / 2);
	Out = *Pool[FMath::RandRange(0, N - 1)];
	return true;
}

bool UCoHStory::VisitPoint(const FString& Name, FVector& Out) const
{
	const FString Want = Name.ToLower();
	for (const auto& Z : Visits)
		for (const auto& P : Z.Value)
			if (P.Key == Want) { Out = P.Value; return true; }
	return false;
}

// ------------------------------------------------------------------ the contact window (player's PC)
class SCoHStoryPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SCoHStoryPanel) {}
		SLATE_ARGUMENT(TWeakObjectPtr<UCoHStoryComponent>, Owner)
	SLATE_END_ARGS()

	void Construct(const FArguments& Args)
	{
		Owner = Args._Owner;
		ChildSlot
		[
			SNew(SOverlay)
			+ SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Top).Padding(0, 220, 18, 0)
			[
				SNew(SBox).WidthOverride(340)
				[
					SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.02f, 0.04f, 0.1f, 0.55f)).Padding(8)
					.Visibility_Lambda([this]() { return TrackerText().IsEmpty() ? EVisibility::Collapsed : EVisibility::HitTestInvisible; })
					[
						SNew(STextBlock).AutoWrapText(true).ColorAndOpacity(FLinearColor(1.f, 0.92f, 0.6f))
						.Font(FCoreStyle::GetDefaultFontStyle("Regular", 11))
						.Text_Lambda([this]() { return FText::FromString(TrackerText()); })
					]
				]
			]
			+ SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Center).Padding(60, 0, 0, 0)
			[
				SAssignNew(Window, SBox).WidthOverride(520).MaxDesiredHeight(560).Visibility(EVisibility::Collapsed)
				[
					SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.03f, 0.06f, 0.16f, 0.92f)).Padding(14)
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)
						[
							SAssignNew(Title, STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Bold", 15)).ColorAndOpacity(FLinearColor(0.55f, 0.85f, 1.f))
						]
						+ SVerticalBox::Slot().FillHeight(1.f)
						[
							SNew(SScrollBox)
							+ SScrollBox::Slot()
							[
								SAssignNew(Body, STextBlock).AutoWrapText(true).Font(FCoreStyle::GetDefaultFontStyle("Regular", 12)).ColorAndOpacity(FLinearColor::White)
							]
						]
						+ SVerticalBox::Slot().AutoHeight().Padding(0, 10, 0, 0)
						[
							SAssignNew(Buttons, SVerticalBox)
						]
					]
				]
			]
		];
	}

	void ShowPage(const FCoHDialogPage& Page)
	{
		Title->SetText(FText::FromString(Page.Title));
		Body->SetText(FText::FromString(Page.Body));
		Buttons->ClearChildren();
		for (int32 i = 0; i < Page.Labels.Num() && i < Page.Actions.Num(); ++i)
		{
			const FString Action = Page.Actions[i];
			Buttons->AddSlot().AutoHeight().Padding(0, 2)
			[
				SNew(SButton).OnClicked_Lambda([this, Action]()
				{
					if (UCoHStoryComponent* C = Owner.Get())
					{
						if (Action == TEXT("close")) C->ClosePage();
						else C->ServerChoose(Action);
					}
					return FReply::Handled();
				})
				[
					SNew(STextBlock).AutoWrapText(true).Font(FCoreStyle::GetDefaultFontStyle("Regular", 12)).Text(FText::FromString(Page.Labels[i]))
				]
			];
		}
		Window->SetVisibility(EVisibility::Visible);
	}
	void Hide() { if (Window.IsValid()) Window->SetVisibility(EVisibility::Collapsed); }
	bool IsOpen() const { return Window.IsValid() && Window->GetVisibility() == EVisibility::Visible; }

private:
	FString TrackerText() const
	{
		const UCoHStoryComponent* C = Owner.Get();
		const UCoHHeroProgress* P = C ? C->Progress() : nullptr;
		if (!P || !P->bHasRecord || P->Hero.Story.Tasks.Num() == 0) return FString();
		const AActor* Me = C->GetOwner();
		FString Out = TEXT("MISSIONS");
		for (const FCoHTaskState& S : P->Hero.Story.Tasks)
		{
			Out += TEXT("\n- ") + S.Text;
			if (!S.Waypoint.IsZero() && Me)
			{
				const FVector D = S.Waypoint - Me->GetActorLocation();
				static const TCHAR* Dirs[] = { TEXT("E"), TEXT("NE"), TEXT("N"), TEXT("NW"), TEXT("W"), TEXT("SW"), TEXT("S"), TEXT("SE") };
				// zones: map east = game -x = Unreal -X; map north = game -z = Unreal +Y
				const float Deg = FMath::RadiansToDegrees(FMath::Atan2(D.Y, -D.X));
				const int32 Oct = (FMath::RoundToInt(Deg / 45.f) % 8 + 8) % 8;
				Out += FString::Printf(TEXT("  (%d m %s)"), FMath::RoundToInt(D.Size2D() / 100.f), Dirs[Oct]);
			}
		}
		return Out;
	}
	TWeakObjectPtr<UCoHStoryComponent> Owner;
	TSharedPtr<SBox> Window;
	TSharedPtr<STextBlock> Title, Body;
	TSharedPtr<SVerticalBox> Buttons;
};

// ------------------------------------------------------------------ ACoHStoryNPC
ACoHStoryNPC::ACoHStoryNPC()
{
	bReplicates = true;
	SetReplicatingMovement(false);
	SetNetCullDistanceSquared(FMath::Square(20000.f));
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.1f;
	UCapsuleComponent* Cap = CreateDefaultSubobject<UCapsuleComponent>(TEXT("Capsule"));
	Cap->InitCapsuleSize(40.f, 90.f);
	Cap->SetCollisionProfileName(TEXT("Pawn"));
	RootComponent = Cap;
	Mesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Cap);
	Mesh->SetRelativeLocation(FVector(0, 0, -90.f));
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Stand = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Stand"));
	Stand->SetupAttachment(Cap);
	Stand->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cyl(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (Cyl.Succeeded()) Stand->SetStaticMesh(Cyl.Object);
	Stand->SetRelativeScale3D(FVector(0.6f, 0.6f, 1.8f));
	Label = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Label"));
	Label->SetupAttachment(Cap);
	Label->SetRelativeLocation(FVector(0, 0, 125.f));
	Label->SetHorizontalAlignment(EHTA_Center);
	Label->SetWorldSize(22.f);
	Label->SetTextRenderColor(FColor(255, 215, 90));
}

void ACoHStoryNPC::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ACoHStoryNPC, Key);
	DOREPLIFETIME(ACoHStoryNPC, DisplayName);
	DOREPLIFETIME(ACoHStoryNPC, Model);
	DOREPLIFETIME(ACoHStoryNPC, bContact);
}

void ACoHStoryNPC::OnRep_Look() { ApplyLook(); }

void ACoHStoryNPC::ApplyLook()
{
	Label->SetText(FText::FromString(bContact ? DisplayName : DisplayName));
	Label->SetTextRenderColor(bContact ? FColor(255, 215, 90) : FColor(200, 230, 255));
	if (bLookApplied || Model.IsEmpty() || GetNetMode() == NM_DedicatedServer) return;
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!R) return;
	bLookApplied = true;
	// a contact on a player body (/Game/CoH/Player/Presets/<body>/<model>) or on its own rig (/Game/CoH/NPCs/<model>)
	FString Body, Folder;
	USkeletalMesh* SM = R->PresetMesh(Model, Body);
	if (SM) Folder = R->PresetRoot / Body / Model;
	else
	{
		Folder = TEXT("/Game/CoH/NPCs") / Model;
		IAssetRegistry& AR = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry").Get();
		TArray<FAssetData> Found;
		AR.GetAssetsByPath(FName(*Folder), Found, true);
		for (const FAssetData& D : Found) if (D.IsInstanceOf(USkeletalMesh::StaticClass())) { SM = Cast<USkeletalMesh>(D.GetAsset()); break; }
		if (!SM)
		{
			// a hostage on a villain model (/Game/CoH/Enemies/<model>)
			Folder = R->EnemyRoot / Model;
			Found.Reset();
			AR.GetAssetsByPath(FName(*Folder), Found, true);
			for (const FAssetData& D : Found) if (D.IsInstanceOf(USkeletalMesh::StaticClass())) { SM = Cast<USkeletalMesh>(D.GetAsset()); break; }
		}
	}
	if (!SM)
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH story: no model %s for %s (not imported): a marker stands in"), *Model, *DisplayName);
		return;
	}
	Mesh->SetSkeletalMeshAsset(SM);
	Mesh->SetRelativeRotation(FRotator(0.f, MeshYaw, 0.f));
	Stand->SetVisibility(false);
	if (UAnimSequenceBase* Idle = R->ClipIn(Folder, TEXT("idle"))) Mesh->PlayAnimation(Idle, true);
}

void ACoHStoryNPC::FollowHero(APawn* Hero)
{
	Follow = Hero;
	if (Hero) SetReplicatingMovement(true);
}

void ACoHStoryNPC::Tick(float Delta)
{
	Super::Tick(Delta);
	if (HasAuthority() && Follow.IsValid())
	{
		// a freed hostage walks a little behind its hero, on the floor under it (indoor maps have floors above)
		const APawn* H = Follow.Get();
		const FVector Want = H->GetActorLocation() - H->GetActorForwardVector() * 160.f;
		FVector To = Want - GetActorLocation();
		if (To.Size() > 4000.f) Follow = nullptr;                // the hero left it behind (teleported out): it waits here
		else if (To.Size2D() > 120.f)
		{
			To.Z = 0.f;
			const FVector Step = To.GetSafeNormal() * FMath::Min(To.Size(), 520.f * Delta);
			FVector Next = GetActorLocation() + Step;
			FHitResult Hit;
			FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHHostageFloor), false, this);
			Q.AddIgnoredActor(H);
			if (GetWorld()->LineTraceSingleByChannel(Hit, Next + FVector(0, 0, 60.f), Next - FVector(0, 0, 400.f), ECC_WorldStatic, Q))
				Next.Z = Hit.ImpactPoint.Z + 92.f;
			else Next.Z = FMath::FInterpTo(GetActorLocation().Z, H->GetActorLocation().Z, Delta, 4.f);
			SetActorLocationAndRotation(Next, FRotator(0.f, To.Rotation().Yaw, 0.f));
		}
	}
	if (GetNetMode() == NM_DedicatedServer) return;
	// the name turns to face the local camera
	const APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (PC && PC->PlayerCameraManager)
	{
		const FVector To = PC->PlayerCameraManager->GetCameraLocation() - Label->GetComponentLocation();
		Label->SetWorldRotation(FRotator(0.f, To.Rotation().Yaw, 0.f));
		Label->SetVisibility(To.SizeSquared() < FMath::Square(4000.f));
	}
}

// ------------------------------------------------------------------ ACoHMissionMarker
ACoHMissionMarker::ACoHMissionMarker()
{
	bReplicates = true;
	SetReplicatingMovement(false);
	SetNetCullDistanceSquared(FMath::Square(60000.f));
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.1f;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Beam = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Beam"));
	Beam->SetupAttachment(RootComponent);
	Beam->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Beam->CastShadow = false;
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cyl(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (Cyl.Succeeded()) Beam->SetStaticMesh(Cyl.Object);
	Label = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Label"));
	Label->SetupAttachment(RootComponent);
	Label->SetHorizontalAlignment(EHTA_Center);
	Label->SetWorldSize(30.f);
}

void ACoHMissionMarker::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ACoHMissionMarker, Kind);
	DOREPLIFETIME(ACoHMissionMarker, Text);
	DOREPLIFETIME(ACoHMissionMarker, ForHero);
}

void ACoHMissionMarker::OnRep_Marker()
{
	const bool bDoor = Kind == ECoHMarkerKind::Door, bExit = Kind == ECoHMarkerKind::Exit;
	const bool bObj = Kind == ECoHMarkerKind::Objective || bExit;      // short posts (indoors)
	// door: a tall gold beam; objective: a short green post; visit: a blue beam
	Beam->SetRelativeScale3D(bObj ? FVector(0.5f, 0.5f, 1.2f) : FVector(0.6f, 0.6f, 40.f));
	Beam->SetRelativeLocation(FVector(0, 0, bObj ? 60.f : 2000.f));
	Label->SetRelativeLocation(FVector(0, 0, bObj ? 160.f : 260.f));
	const FLinearColor Col = bDoor ? FLinearColor(1.f, 0.75f, 0.1f) : bExit ? FLinearColor(0.85f, 0.95f, 1.f)
		: bObj ? FLinearColor(0.2f, 1.f, 0.35f) : FLinearColor(0.3f, 0.6f, 1.f);
	if (UMaterialInterface* Base = Beam->GetMaterial(0))
	{
		UMaterialInstanceDynamic* MID = Beam->CreateDynamicMaterialInstance(0, Base);
		if (MID) MID->SetVectorParameterValue(TEXT("Color"), Col);
	}
	Label->SetText(FText::FromString(Text));
	Label->SetTextRenderColor(Col.ToFColor(true));
}

void ACoHMissionMarker::Tick(float Delta)
{
	Super::Tick(Delta);
	if (GetNetMode() == NM_DedicatedServer) return;
	const APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (!PC) return;
	// only the hero it is for sees it (teams: later)
	const bool bMine = !ForHero || ForHero.Get() == PC->GetPawn();
	SetActorHiddenInGame(!bMine);
	if (bMine && PC->PlayerCameraManager)
	{
		const FVector To = PC->PlayerCameraManager->GetCameraLocation() - Label->GetComponentLocation();
		Label->SetWorldRotation(FRotator(0.f, To.Rotation().Yaw, 0.f));
	}
}

// ------------------------------------------------------------------ ACoHMissionMap
ACoHMissionMap::ACoHMissionMap()
{
	bReplicates = true;
	bAlwaysRelevant = true;
	SetReplicatingMovement(false);
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void ACoHMissionMap::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ACoHMissionMap, LevelPath);
	DOREPLIFETIME(ACoHMissionMap, InstanceName);
}

void ACoHMissionMap::OnRep_Map()
{
	if (Streaming || LevelPath.IsEmpty() || InstanceName.IsEmpty()) return;
	bool bOk = false;
	// the same instance name on host and clients, so the level's actors match up
	Streaming = ULevelStreamingDynamic::LoadLevelInstance(this, LevelPath, GetActorLocation(), FRotator::ZeroRotator, bOk, InstanceName);
	UE_LOG(LogTemp, Log, TEXT("CoH mission map: %s as %s at %s: %s"), *LevelPath, *InstanceName, *GetActorLocation().ToCompactString(), bOk ? TEXT("loading") : TEXT("FAILED"));
}

bool ACoHMissionMap::IsReady() const
{
	return Streaming && Streaming->IsLevelLoaded() && Streaming->IsLevelVisible();
}

void ACoHMissionMap::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Streaming)
	{
		Streaming->SetShouldBeLoaded(false);
		Streaming->SetShouldBeVisible(false);
		Streaming->SetIsRequestingUnloadAndRemoval(true);
		Streaming = nullptr;
	}
	Super::EndPlay(Reason);
}

// ------------------------------------------------------------------ ACoHStoryDirector
ACoHStoryDirector::ACoHStoryDirector()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.5f;
	bReplicates = false;
}

void ACoHStoryDirector::BeginPlay()
{
	Super::BeginPlay();
	const UCoHStory* S = UCoHStory::Get(this);
	UE_LOG(LogTemp, Log, TEXT("CoH story director: %d contacts and %d people to stand near players"),
		S ? S->Contacts.Num() : 0, S ? S->People.Num() : 0);
}

ACoHStoryDirector* ACoHStoryDirector::Get(const UWorld* World)
{
	if (!World) return nullptr;
	for (TActorIterator<ACoHStoryDirector> It(const_cast<UWorld*>(World)); It; ++It) return *It;
	return nullptr;
}

bool ACoHStoryDirector::Ground(const FVector& Near, FVector& Out) const
{
	UWorld* W = GetWorld();
	FHitResult Hit;
	FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHStoryGround), true);
	const FVector Top = Near + FVector(0, 0, 3000.f), Bottom = Near - FVector(0, 0, 20000.f);
	if (!W->LineTraceSingleByObjectType(Hit, Top, Bottom, FCollisionObjectQueryParams(ECC_WorldStatic), Q)) return false;
	Out = Hit.ImpactPoint;
	if (UNavigationSystemV1* Nav = FNavigationSystem::GetCurrent<UNavigationSystemV1>(W))
	{
		FNavLocation NL;
		if (Nav->ProjectPointToNavigation(Out, NL, FVector(600.f, 600.f, 300.f))) Out = NL.Location;
	}
	return true;
}

bool ACoHStoryDirector::StandingSpot(const FVector& Pos, FVector& Out) const
{
	// the lowest surface at or above the data position: the street, not a roof over it, and not the
	// ground far below when the position itself is under the rebuilt city (it came from the old map)
	UWorld* W = GetWorld();
	TArray<FHitResult> Hits;
	FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHStoryStand), true);
	W->LineTraceMultiByObjectType(Hits, Pos + FVector(0, 0, 60000.f), Pos - FVector(0, 0, 3000.f), FCollisionObjectQueryParams(ECC_WorldStatic), Q);
	const FHitResult* Best = nullptr;
	for (const FHitResult& H : Hits)
		if (H.ImpactPoint.Z >= Pos.Z - 300.f && (!Best || H.ImpactPoint.Z < Best->ImpactPoint.Z)) Best = &H;
	if (!Best) return Ground(Pos, Out);
	Out = Best->ImpactPoint;
	// on top of something (a roof: the old interior position is now inside a solid rebuilt building)?
	// then the lowest open ground nearby, the nearest of it
	auto Lowest = [&](const FVector& At, FVector& Hit) -> bool
	{
		FHitResult H;
		if (!W->LineTraceSingleByObjectType(H, At + FVector(0, 0, 60000.f), At - FVector(0, 0, 30000.f), FCollisionObjectQueryParams(ECC_WorldStatic), Q)) return false;
		Hit = H.ImpactPoint;
		return true;
	};
	if (Out.Z < Pos.Z + 1500.f) return true;                     // about where the data puts it: keep it
	FVector BestNear = Out; float BestD = TNumericLimits<float>::Max();
	for (float R : { 600.f, 1200.f, 2000.f, 3000.f, 4500.f })
		for (int32 a = 0; a < 16; ++a)
		{
			const FVector At = Pos + FVector(FMath::Cos(a * PI / 8.f), FMath::Sin(a * PI / 8.f), 0.f) * R;
			FVector H;
			if (!Lowest(At, H) || H.Z > Out.Z - 500.f) continue;    // not clearly lower than where we are
			// prefer the lowest ground, then the nearest
			const float Score = H.Z * 4.f + R;
			if (Score < BestD) { BestD = Score; BestNear = H; }
		}
	Out = BestNear;
	return true;
}

bool ACoHStoryDirector::RandomSpot(const FVector& Center, float Radius, FVector& Out) const
{
	if (UNavigationSystemV1* Nav = FNavigationSystem::GetCurrent<UNavigationSystemV1>(GetWorld()))
	{
		FNavLocation NL;
		if (Nav->GetRandomReachablePointInRadius(Center, Radius, NL)) { Out = NL.Location; return true; }
	}
	const FVector2D R = FMath::RandPointInCircle(Radius);
	return Ground(Center + FVector(R.X, R.Y, 0.f), Out);
}

bool ACoHStoryDirector::WhereIs(const FString& Key, FVector& Out) const
{
	if (const ACoHStoryNPC* N = NPCFor(Key)) { Out = N->GetActorLocation(); return true; }
	const UCoHStory* S = UCoHStory::Get(this);
	if (!S) return false;
	if (const FCoHStoryContact* C = S->Contact(Key)) { Out = C->Pos; return true; }
	if (const FCoHStoryPerson* P = S->Person(Key)) { Out = P->Pos; return true; }
	return false;
}

void ACoHStoryDirector::Stream()
{
	const UCoHStory* S = UCoHStory::Get(this);
	if (!S) return;
	TArray<FVector> Heroes;
	for (TActorIterator<APawn> It(GetWorld()); It; ++It) if (It->IsPlayerControlled()) Heroes.Add(It->GetActorLocation());
	auto Nearest = [&](const FVector& P) { float D = TNumericLimits<float>::Max(); for (const FVector& H : Heroes) D = FMath::Min(D, (float)FVector::Dist2D(H, P)); return D; };
	auto Keep = [&](const FString& Key, const FString& Name, const FString& Model, const FVector& Pos, float Yaw, bool bContact)
	{
		const float D = Nearest(Pos);
		TWeakObjectPtr<ACoHStoryNPC>* Have = NPCs.Find(Key);
		if (Have && Have->IsValid())
		{
			if (D > LeaveDistance) { (*Have)->Destroy(); NPCs.Remove(Key); }
			return;
		}
		if (D > StandDistance) return;
		FVector At;
		if (!StandingSpot(Pos, At)) return;     // the ground there is not streamed in yet: next time
		FActorSpawnParameters P; P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
		// game yaw -> Unreal: the converter's yaw is already Unreal's
		ACoHStoryNPC* N = GetWorld()->SpawnActor<ACoHStoryNPC>(At + FVector(0, 0, 92.f), FRotator(0.f, Yaw, 0.f), P);
		if (!N) return;
		N->Key = Key; N->DisplayName = Name; N->Model = Model; N->bContact = bContact;
		N->ApplyLook();
		NPCs.Add(Key, N);
	};
	for (const auto& KV : S->Contacts) Keep(KV.Key, KV.Value.Name, KV.Value.Model, KV.Value.Pos, KV.Value.Yaw, true);
	for (const auto& KV : S->People) Keep(KV.Key, KV.Value.Name, KV.Value.Model, KV.Value.Pos, KV.Value.Yaw, false);
}

void ACoHStoryDirector::Tick(float Delta)
{
	Super::Tick(Delta);
	if (!HasAuthority()) return;
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now >= NextStream) { NextStream = Now + 1.0; Stream(); }
	for (int32 i = Missions.Num() - 1; i >= 0; --i)
	{
		FMission& M = Missions[i];
		if (!M.Hero.IsValid())
		{
			for (auto& F : M.Foes) if (F.IsValid()) F->Destroy();
			FreeMission(M);
			Missions.RemoveAt(i);
			continue;
		}
		if (M.bLoading)
		{
			if (!M.Map.IsValid()) { M.bLoading = false; SpawnOutdoor(M); continue; }
			if (!M.Map->IsReady())
			{
				if (Now > M.LoadStarted + 60.0) { UE_LOG(LogTemp, Warning, TEXT("CoH story: map %s did not load in 60 s: mission at the door"), *M.MapId); M.Map->Destroy(); }
				continue;
			}
			if (M.ReadyAt <= 0) { M.ReadyAt = Now + 1.5; continue; }   // a moment for clients to stream it in too
			if (Now < M.ReadyAt) continue;
			M.bLoading = false;
			PopulateIndoor(M);
			TeleportHero(M, true);
			continue;
		}
		if (M.bEntered && !M.bFinished) CheckMission(M);
	}
}

ACoHMissionMarker* ACoHStoryDirector::SpawnMarker(ECoHMarkerKind Kind, const FVector& At, APawn* For, const FString& Text, const FString& Task)
{
	FActorSpawnParameters P; P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ACoHMissionMarker* Mk = GetWorld()->SpawnActor<ACoHMissionMarker>(At, FRotator::ZeroRotator, P);
	if (!Mk) return nullptr;
	Mk->Kind = Kind; Mk->Text = Text; Mk->ForHero = For; Mk->Task = Task;
	Mk->OnRep_Marker();
	return Mk;
}

bool UCoHStory::NearestHospital(const UObject* WorldContext, const FVector& From, FVector& Out) const
{
	// only the zone the hero is in: other zones' beds may not be streamed in (or the zone is far away)
	const FString Zone = ZoneAt(WorldContext, From);
	if (Zone.IsEmpty()) return false;
	const TArray<FVector>* Beds = Gurneys.Find(Zone);
	if (!Beds) return false;
	float Best = TNumericLimits<float>::Max();
	for (const FVector& G : *Beds)
	{
		const float D = FVector::DistSquared(G, From);
		if (D < Best) { Best = D; Out = G; }
	}
	return Best < TNumericLimits<float>::Max();
}

bool ACoHStoryDirector::LeaveForHospital(APawn* Who, FVector& Door)
{
	if (!Who || !IsMissionSpace(Who->GetActorLocation())) return false;
	for (FMission& M : Missions)
	{
		const UCoHStoryComponent* For = M.Hero.Get();
		const bool bOwner = For && For->GetOwner() == Who;
		if (!bOwner && !M.Guests.Contains(Who)) continue;
		Door = M.Door;
		if (bOwner) M.bInside = false; else M.Guests.Remove(Who);
		return true;
	}
	return false;
}

ACoHStoryDirector::FMission* ACoHStoryDirector::Find(UCoHStoryComponent* For, const FString& TaskId)
{
	for (FMission& M : Missions) if (M.Hero.Get() == For && M.Task == TaskId) return &M;
	return nullptr;
}

FVector ACoHStoryDirector::OpenMission(UCoHStoryComponent* For, const FString& TaskId)
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(TaskId) : nullptr;
	APawn* Hero = For ? Cast<APawn>(For->GetOwner()) : nullptr;
	if (!T || !Hero) return FVector::ZeroVector;
	if (FMission* Old = Find(For, TaskId)) return Old->Door;
	const FString HereZone = S->ZoneAt(this, Hero->GetActorLocation());
	FCoHStoryDoor Door;
	FVector At = Hero->GetActorLocation() + Hero->GetActorForwardVector() * 3000.f;
	if (S->PickDoor(*T, HereZone, Hero->GetActorLocation(), Door)) At = Door.Pos;
	FMission M;
	M.Task = TaskId; M.Hero = For; M.Door = At;
	M.DoorMarker = SpawnMarker(ECoHMarkerKind::Door, At, Hero, T->MapSet.IsEmpty() ? TEXT("Mission") : FString::Printf(TEXT("Mission: %s"), *T->MapSet), TaskId);
	Missions.Add(M);
	UE_LOG(LogTemp, Log, TEXT("CoH story: mission door for %s at %s (%s, door %s)"), *TaskId, *At.ToCompactString(), *T->MissionZone, *T->Door);
	return At;
}

// villains of a group and rank that the original encounters roll at a level
static TArray<FString> CoHStoryRoll(const UCoHGameRules* R, const FString& Group, const FString& Rank, int32 Level)
{
	TArray<FString> Out;
	auto Scan = [&](const TArray<FCoHEncounter>& List)
	{
		for (const FCoHEncounter& E : List)
			for (const FCoHEncounterActor& A : E.Actors)
			{
				if (!A.Group.Equals(Group, ESearchCase::IgnoreCase) || !A.Rank.Contains(Rank)) continue;
				int32 Best = -1;
				for (const auto& KV : A.Rolls) if (KV.Value.Num() && FMath::Abs(KV.Key - Level) < FMath::Abs(Best - Level)) Best = KV.Key;
				if (Best >= 0 && FMath::Abs(Best - Level) <= 3)
					for (const FString& V : A.Rolls[Best]) if (R->Kit(V)) Out.AddUnique(V);
			}
	};
	for (const auto& KV : R->ZoneEncounters) Scan(KV.Value);
	Scan(R->Encounters);
	if (Out.Num() == 0)       // no encounter rolls it: any kit villain of the group and rank
		for (const auto& KV : R->Villains)
			if (KV.Value.Group.Equals(Group, ESearchCase::IgnoreCase) && KV.Value.Rank.Contains(Rank) && KV.Value.Models.Num()) Out.Add(KV.Key);
	return Out;
}

ACoHCombatEnemy* ACoHStoryDirector::SpawnFoe(FMission& M, const FString& Villain, const FVector& At, const FString& Display, int32 Level, int32 GroupId)
{
	TActorIterator<ACoHEnemySpawner> Spawner(GetWorld());
	if (!Spawner) return nullptr;
	const FRotator Rot(0.f, FMath::FRandRange(-180.f, 180.f), 0.f);
	ACoHCombatEnemy* E = Spawner->SpawnKitVillain(Villain, Level, At, Rot);
	if (!E) return nullptr;
	E->GroupId = GroupId;
	if (!Display.IsEmpty() && E->Powers && M.Hero.IsValid()) E->Powers->DisplayName = M.Hero->Fill(Display);
	M.Foes.Add(E);
	return E;
}

void ACoHStoryDirector::SpawnGroupAt(FMission& M, const FString& Group, const TArray<FVector>& Spots, const FVector& Center, int32 Minions, bool bLt, int32 Level)
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!R) return;
	const int32 GroupId = NextGroupId++;
	const TArray<FString> Min = CoHStoryRoll(R, Group, TEXT("Minion"), Level);
	const TArray<FString> Lt = CoHStoryRoll(R, Group, TEXT("Lieutenant"), Level);
	int32 Used = 0;
	auto Where = [&](float Radius)
	{
		if (Spots.IsValidIndex(Used)) return Spots[Used++];
		FVector P; return RandomSpot(Center, Radius, P) ? P : Center;
	};
	for (int32 i = 0; i < Minions && Min.Num(); ++i) SpawnFoe(M, Min[FMath::RandRange(0, Min.Num() - 1)], Where(350.f), FString(), Level, GroupId);
	if (bLt && Lt.Num()) SpawnFoe(M, Lt[FMath::RandRange(0, Lt.Num() - 1)], Where(250.f), FString(), Level, GroupId);
}

int32 ACoHStoryDirector::FreeSlot() const
{
	for (int32 Slot = 0;; ++Slot)
		if (!Missions.ContainsByPredicate([&](const FMission& M) { return M.Slot == Slot; })) return Slot;
}

void ACoHStoryDirector::EnterMission(UCoHStoryComponent* For, const FString& TaskId)
{
	FMission* M = Find(For, TaskId);
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(TaskId) : nullptr;
	APawn* Hero = For ? Cast<APawn>(For->GetOwner()) : nullptr;
	if (!M || !T || !Hero) return;
	if (M->bEntered)
	{
		// back in through the door of a mission still running inside
		if (M->Map.IsValid() && !M->bLoading && !M->bFinished) TeleportHero(*M, true);
		return;
	}
	M->bEntered = true;
	const FCoHMissionMap* Map = S->PickMap(*T, FMath::Clamp(For->HeroLevel(), 1, 50));
	if (!Map) { if (M->DoorMarker.IsValid()) M->DoorMarker->Destroy(); SpawnOutdoor(*M); return; }
	M->Slot = FreeSlot();
	M->MapId = Map->Id;
	M->Origin = FVector(M->Slot * MissionSlotSpacing, 0.f, MissionHeight) - Map->Start;     // the map's start ends up at the slot point
	FActorSpawnParameters P; P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ACoHMissionMap* MA = GetWorld()->SpawnActor<ACoHMissionMap>(M->Origin, FRotator::ZeroRotator, P);
	if (!MA) { SpawnOutdoor(*M); return; }
	MA->LevelPath = Map->Level();
	MA->InstanceName = FString::Printf(TEXT("CoHMission_%d_%s"), M->Slot, *Map->Id);
	MA->OnRep_Map();
	M->Map = MA;
	M->bLoading = true;
	M->ReadyAt = 0;
	M->LoadStarted = GetWorld()->GetTimeSeconds();
	UE_LOG(LogTemp, Log, TEXT("CoH story: mission %s loads indoor map %s (%s, %d min) in slot %d"), *TaskId, *Map->Id, *Map->Set, Map->Length, M->Slot);
}

void ACoHStoryDirector::SpawnOutdoor(FMission& M)
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
	UCoHStoryComponent* For = M.Hero.Get();
	APawn* Hero = For ? Cast<APawn>(For->GetOwner()) : nullptr;
	if (!T || !Hero) return;
	if (!TActorIterator<ACoHEnemySpawner>(GetWorld())) { UE_LOG(LogTemp, Warning, TEXT("CoH story: no enemy spawner: mission %s has no villains"), *M.Task); return; }
	if (M.DoorMarker.IsValid()) M.DoorMarker->Destroy();
	const int32 Level = FMath::Clamp(For->HeroLevel(), 1, 50);
	const FString Group = T->MissionGroup.IsEmpty() ? TEXT("Hellions") : T->MissionGroup;
	const TArray<FVector> None;
	// the mission's own spawns (bosses, hostages, patrols; some wait for a trigger), then filler groups by map length
	M.Heroes = TeamSize(M);
	int32 Groups = FMath::Clamp(T->MapLength / 10, 2, 5) + (T->bLong ? 1 : 0);
	for (int32 i = 0; i < T->Spawns.Num(); ++i)
	{
		for (int32 c = 0; c < FMath::Clamp(T->Spawns[i].Count, 1, 4); ++c)
		{
			FVector C; if (!RandomSpot(M.Door, 2500.f, C)) C = M.Door;
			AddRun(M, i, C, None, false);
		}
		--Groups;
	}
	for (int32 i = 0; i < Groups; ++i) { FVector C; if (!RandomSpot(M.Door, 3000.f, C)) C = M.Door; SpawnGroupAt(M, Group, None, C, 3, i % 2 == 0, Level); }
	// objectives to click (crates, computers, bombs...)
	for (int32 o = 0; o < T->Objectives.Num(); ++o)
		for (int32 n = 0; n < T->Objectives[o].Number; ++n)
		{
			FVector P; if (!RandomSpot(M.Door, 2500.f, P)) continue;
			PlaceClickable(M, o, P);
		}
	TickRuns(M);
	UE_LOG(LogTemp, Log, TEXT("CoH story: mission %s started at the door: %d villains (%s, level %d), %d objectives, %d spawns (%d waiting)"),
		*M.Task, M.Foes.Num(), *Group, Level, M.ObjectivesLeft, M.Runs.Num(), M.Runs.FilterByPredicate([](const FMission::FRun& R) { return !R.bCreated; }).Num());
}

void ACoHStoryDirector::PopulateIndoor(FMission& M)
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
	const FCoHMissionMap* Map = S ? S->Map(M.MapId) : nullptr;
	UCoHStoryComponent* For = M.Hero.Get();
	APawn* Hero = For ? Cast<APawn>(For->GetOwner()) : nullptr;
	if (!T || !Map || !Hero) return;
	const int32 Level = FMath::Clamp(For->HeroLevel(), 1, 50);
	const FString Group = T->MissionGroup.IsEmpty() ? TEXT("Hellions") : T->MissionGroup;
	// encounter places by rank; each used once
	TArray<int32> Free;
	for (int32 i = 0; i < Map->Encounters.Num(); ++i) Free.Add(i);
	auto Take = [&](const FString& Rank) -> const FCoHMapSpot*
	{
		TArray<int32> Match;
		for (int32 i : Free)
		{
			const FString& R = Map->Encounters[i].Rank;
			if (Rank.IsEmpty() || Rank == TEXT("Any") || R == Rank) Match.Add(i);
		}
		if (Match.Num() == 0) for (int32 i : Free) if (Map->Encounters[i].Rank != TEXT("Lobby")) Match.Add(i);
		if (Match.Num() == 0) Match = Free;
		if (Match.Num() == 0) return nullptr;
		const int32 Pick = Match[FMath::RandRange(0, Match.Num() - 1)];
		Free.Remove(Pick);
		return &Map->Encounters[Pick];
	};
	auto ToWorld = [&](const FVector& Local) { return M.Origin + Local; };
	auto Spots = [&](const FCoHMapSpot& E) { TArray<FVector> Out; for (const FVector& V : E.Spots) Out.Add(ToWorld(V)); return Out; };
	// the task's own spawns at encounters of their placement: placed now, or later when their trigger objective is done
	M.Heroes = TeamSize(M);
	for (int32 i = 0; i < T->Spawns.Num(); ++i)
	{
		const FCoHStorySpawn& Sp = T->Spawns[i];
		if (Sp.Placement == TEXT("Lobby") && Sp.Villain.Contains(TEXT("Marker"))) continue;   // invisible script helpers
		for (int32 c = 0; c < FMath::Clamp(Sp.Count, 1, 4); ++c)
		{
			const FCoHMapSpot* E = Take(Sp.Placement);
			if (!E) break;
			AddRun(M, i, ToWorld(E->Pos), Spots(*E), E->Rank == TEXT("Back"));
		}
	}
	// the rest of the map's mission encounters (as the original fills them), up to MaxFillerGroups
	TArray<int32> Fill;
	for (int32 i : Free) if (Map->Encounters[i].Rank != TEXT("Lobby") && (Map->Encounters[i].Kind.IsEmpty() || Map->Encounters[i].Kind == TEXT("Mission"))) Fill.Add(i);
	for (int32 n = 0; n < FMath::Min(MaxFillerGroups, Fill.Num()); ++n)
	{
		const int32 k = FMath::RandRange(n, Fill.Num() - 1);
		Fill.Swap(n, k);
		const FCoHMapSpot& E = Map->Encounters[Fill[n]];
		SpawnGroupAt(M, Group, Spots(E), ToWorld(E.Pos), 2 + (n % 3), n % 2 == 0, Level);
	}
	// objectives at the map's item / person spots, Back and Middle rooms first
	TSet<const FCoHMapSpot*> UsedSpots;
	for (int32 o = 0; o < T->Objectives.Num(); ++o)
	{
		const FCoHStoryObjective& Ob = T->Objectives[o];
		for (int32 n = 0; n < Ob.Number; ++n)
		{
			const FCoHMapSpot* Best = nullptr; int32 BestScore = -1;
			for (const FString& Kind : { Ob.Location, FString(TEXT("ItemFloor")), FString(TEXT("ItemAgainstWall")), FString(TEXT("Person")) })
			{
				const TArray<FCoHMapSpot>* L = Map->Objectives.Find(Kind.IsEmpty() ? TEXT("ItemFloor") : Kind);
				if (!L) continue;
				for (const FCoHMapSpot& Sp : *L)
				{
					if (UsedSpots.Contains(&Sp)) continue;
					int32 Score = (Sp.Rank == TEXT("Back") ? 3 : Sp.Rank == TEXT("Middle") ? 2 : Sp.Rank == TEXT("Front") ? 1 : 0) * 10 + FMath::RandRange(0, 9);
					if (!Ob.Placement.IsEmpty() && Ob.Placement != TEXT("Any") && Sp.Rank == Ob.Placement) Score += 100;   // the room the original asks for
					if (Score > BestScore) { BestScore = Score; Best = &Sp; }
				}
				if (Best) break;
			}
			FVector P;
			if (Best) { UsedSpots.Add(Best); P = ToWorld(Best->Pos); }
			else if (const FCoHMapSpot* E = Take(TEXT("Back"))) P = ToWorld(E->Pos);
			else continue;
			PlaceClickable(M, o, P);
		}
	}
	TickRuns(M);
	M.ExitMarker = SpawnMarker(ECoHMarkerKind::Exit, ToWorld(Map->Exit), Hero, TEXT("Exit"), M.Task);
	UE_LOG(LogTemp, Log, TEXT("CoH story: mission %s inside %s: %d villains (%s, level %d), %d objectives, %d spawns (%d waiting), team of %d"),
		*M.Task, *M.MapId, M.Foes.Num(), *Group, Level, M.ObjectivesLeft, M.Runs.Num(),
		M.Runs.FilterByPredicate([](const FMission::FRun& R) { return !R.bCreated; }).Num(), M.Heroes);
}

void ACoHStoryDirector::TeleportHero(FMission& M, bool bIn)
{
	UCoHStoryComponent* For = M.Hero.Get();
	APawn* Hero = For ? Cast<APawn>(For->GetOwner()) : nullptr;
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHMissionMap* Map = S ? S->Map(M.MapId) : nullptr;
	if (!Hero) return;
	if (bIn && Map)
	{
		Hero->TeleportTo(M.Origin + Map->Start + FVector(0, 0, 100.f), FRotator(0.f, Map->StartYaw, 0.f));
		M.bInside = true;
	}
	else
	{
		PutAtDoor(M, Hero);
		M.bInside = false;
	}
}

void ACoHStoryDirector::PutAtDoor(const FMission& M, APawn* Who) const
{
	if (!Who) return;
	FVector At = M.Door + FVector(0, 0, 100.f);
	FVector G; if (Ground(M.Door, G)) At = G + FVector(0, 0, 100.f);
	Who->TeleportTo(At, Who->GetActorRotation());
}

static void CoHGuestSay(APawn* Who, const FString& Text)
{
	if (UCoHPowerComponent* P = UCoHPowerComponent::Of(Who)) P->MulticastText(Text, FLinearColor(1.f, 0.85f, 0.4f));
}

void ACoHStoryDirector::GuestEnter(UCoHStoryComponent* OwnerStory, const FString& TaskId, APawn* Guest)
{
	FMission* M = Find(OwnerStory, TaskId);
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHMissionMap* Map = S && M ? S->Map(M->MapId) : nullptr;
	if (!M || !Guest) return;
	if (!M->bEntered) { CoHGuestSay(Guest, TEXT("Your teammate has to go in first")); return; }
	if (!M->Map.IsValid()) { CoHGuestSay(Guest, TEXT("This mission is out here")); return; }
	if (M->bLoading || !Map) { CoHGuestSay(Guest, TEXT("The mission is still loading")); return; }
	if (M->bFinished) { CoHGuestSay(Guest, TEXT("This mission is complete")); return; }
	Guest->TeleportTo(M->Origin + Map->Start + FVector(FMath::FRandRange(-150.f, 150.f), FMath::FRandRange(-150.f, 150.f), 100.f), FRotator(0.f, Map->StartYaw, 0.f));
	M->Guests.AddUnique(Guest);
}

void ACoHStoryDirector::GuestExit(UCoHStoryComponent* OwnerStory, const FString& TaskId, APawn* Guest)
{
	FMission* M = Find(OwnerStory, TaskId);
	if (!M || !Guest) return;
	PutAtDoor(*M, Guest);
	M->Guests.Remove(Guest);
}
// ---------------------------------------------------------------- mission variety
// The original's mission spawns (docs/missions.md): each copy of a task spawn is a run. A run
// is placed when the mission fills, or once an objective it waits for is done
// (CreateOnObjectiveComplete; an ambush also on ActivateOnObjectiveComplete). A run that
// carries an objective completes it when its villains are down, its hostage is freed
// (rescue) or brought to the exit (escort), or its object is smashed (destroy). The mission
// completes by its CanCompleteWith lines: any one line whose objectives are all done.

int32 ACoHStoryDirector::TeamSize(const FMission& M) const
{
	const UCoHStoryComponent* For = M.Hero.Get();
	const UCoHSocial* So = For ? UCoHSocial::Of(For->GetOwner()) : nullptr;
	return FMath::Clamp(So ? So->TeamMembers().Num() : 1, 1, 8);
}

void ACoHStoryDirector::AddRun(FMission& M, int32 Spawn, const FVector& Center, const TArray<FVector>& Spots, bool bEndRoom)
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
	if (!T || !T->Spawns.IsValidIndex(Spawn)) return;
	FMission::FRun R;
	R.Spawn = Spawn; R.Center = Center; R.Spots = Spots; R.bEndRoom = bEndRoom;
	M.Runs.Add(R);
	const FString Ob = T->Spawns[Spawn].Objective.ToLower();
	if (!Ob.IsEmpty()) { M.Left.FindOrAdd(Ob) += 1; M.Known.Add(Ob); }
}

void ACoHStoryDirector::PlaceClickable(FMission& M, int32 Objective, const FVector& At, bool bCount)
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
	UCoHStoryComponent* For = M.Hero.Get();
	APawn* Hero = For ? Cast<APawn>(For->GetOwner()) : nullptr;
	if (!T || !Hero || !T->Objectives.IsValidIndex(Objective)) return;
	const FCoHStoryObjective& Ob = T->Objectives[Objective];
	if (bCount)
	{
		const FString Name = Ob.Name.ToLower();
		M.Left.FindOrAdd(Name) += 1;
		M.Known.Add(Name);
		++M.ObjectivesLeft;
	}
	// it waits for another objective of this mission (ActivateOnObjectiveComplete)
	if (Ob.ActivateOn.Num() && !Triggered(M, Ob.ActivateOn))
	{
		bool bAny = false;
		for (const FString& N : Ob.ActivateOn) bAny |= T->Objectives.ContainsByPredicate([&](const FCoHStoryObjective& X) { return X.Name.Equals(N, ESearchCase::IgnoreCase); })
			|| T->Spawns.ContainsByPredicate([&](const FCoHStorySpawn& X) { return X.Objective.Equals(N, ESearchCase::IgnoreCase); });
		if (bAny) { M.Waiting.Add(TPair<int32, FVector>(Objective, At)); return; }
	}
	ACoHMissionMarker* Mk = SpawnMarker(ECoHMarkerKind::Objective, At, Hero, Ob.Display.IsEmpty() ? Ob.Name : Ob.Display, M.Task);
	if (Mk) { Mk->Objective = Objective; M.Objectives.Add(Mk); }
}

bool ACoHStoryDirector::Triggered(const FMission& M, const TArray<FString>& On) const
{
	for (const FString& N : On) if (M.Done.Contains(N.ToLower())) return true;
	return false;
}

void ACoHStoryDirector::CreateRun(FMission& M, int32 RunIdx)
{
	FMission::FRun& R = M.Runs[RunIdx];
	if (R.bCreated) return;
	R.bCreated = true;
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
	UCoHStoryComponent* For = M.Hero.Get();
	APawn* Hero = For ? Cast<APawn>(For->GetOwner()) : nullptr;
	const UCoHGameRules* GR = UCoHGameRules::Get(this);
	if (!T || !Hero || !GR || !T->Spawns.IsValidIndex(R.Spawn)) { RunDone(M, RunIdx); return; }
	const FCoHStorySpawn& Sp = T->Spawns[R.Spawn];
	const int32 Level = FMath::Clamp(For->HeroLevel(), 1, 50);
	const FString G = Sp.Group.IsEmpty() ? (T->MissionGroup.IsEmpty() ? FString(TEXT("Hellions")) : T->MissionGroup) : Sp.Group;
	const int32 GroupId = NextGroupId++;
	const int32 Before = M.Foes.Num();
	int32 Used = 0;
	auto Where = [&]() { if (R.Spots.IsValidIndex(Used)) return R.Spots[Used++]; FVector P; return RandomSpot(R.Center, 350.f, P) ? P : R.Center; };
	bool bAny = false;
	// the encounter's actors, as many as the original puts out for a team this size
	for (const FCoHStoryActor& A : Sp.Actors)
	{
		if (M.Heroes < A.MinHeroes || M.Heroes > A.MaxHeroes) continue;
		for (int32 n = 0; n < A.Number; ++n)
		{
			const FVector At = Where();
			if (A.Role == TEXT("hostage"))
			{
				if (R.Hostage.IsValid()) continue;
				FActorSpawnParameters P; P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
				ACoHStoryNPC* N = GetWorld()->SpawnActor<ACoHStoryNPC>(At + FVector(0, 0, 92.f), FRotator(0.f, FMath::FRandRange(-180.f, 180.f), 0.f), P);
				if (!N) continue;
				const FString Name = !A.Name.IsEmpty() ? A.Name : !Sp.HostageName.IsEmpty() ? Sp.HostageName : FString(TEXT("Hostage"));
				const FCoHKitVillain* K = GR->Kit(A.Villain.IsEmpty() ? Sp.HostageVillain : A.Villain);
				N->Key = TEXT("hostage"); N->bContact = false; N->bHostage = true;
				N->DisplayName = For->Fill(Name);
				N->Model = K && K->Models.Num() ? K->Models[0] : FString();
				N->ApplyLook();
				R.Hostage = N;
				continue;
			}
			FString Villain = A.Villain;
			if (Villain.IsEmpty())
			{
				const FString AG = A.Group.IsEmpty() ? G : A.Group;
				for (const FString& Rank : { A.Rank.IsEmpty() ? FString(TEXT("Minion")) : A.Rank, FString(TEXT("Lieutenant")), FString(TEXT("Minion")) })
				{
					const TArray<FString> Roll = CoHStoryRoll(GR, AG, Rank, Level);
					if (Roll.Num()) { Villain = Roll[FMath::RandRange(0, Roll.Num() - 1)]; break; }
				}
			}
			ACoHCombatEnemy* E = Villain.IsEmpty() ? nullptr : SpawnFoe(M, Villain, At, A.Name, Level, GroupId);
			if (A.Role == TEXT("object") && !E && !R.Object.IsValid())
			{
				// no model for the object: a marker to smash
				R.Object = SpawnMarker(ECoHMarkerKind::Objective, At, Hero, For->Fill(A.Name.IsEmpty() ? FString(TEXT("Destroy")) : A.Name), M.Task);
				if (R.Object.IsValid()) { R.Object->Run = RunIdx; M.Objectives.Add(R.Object); }
				continue;
			}
			if (!E) continue;
			bAny = true;
			// what the original has it say (boss taunts, captors' threats): "=" marks a line given as is
			if (!A.SayIdle.IsEmpty()) E->ChatIdle = TEXT("=") + For->Fill(A.SayIdle);
			if (!A.SayAlert.IsEmpty()) E->ChatAlert = TEXT("=") + For->Fill(A.SayAlert);
			if (A.Rank == TEXT("Boss") && !A.Villain.IsEmpty()) M.Boss = E;
		}
	}
	if (!bAny && !R.Hostage.IsValid() && !R.Object.IsValid())
	{
		// no encounter of its own (or none of it could spawn): the spawn's boss with two, else three and a lieutenant
		TArray<FVector> At = R.Spots;
		if (!Sp.Villain.IsEmpty())
		{
			const FVector BossAt = At.Num() ? At[0] : R.Center;
			if (At.Num()) At.RemoveAt(0);
			if (ACoHCombatEnemy* B = SpawnFoe(M, Sp.Villain, BossAt, Sp.Display, Level, GroupId)) M.Boss = B;
			SpawnGroupAt(M, G, At, R.Center, 2, false, Level);
		}
		else SpawnGroupAt(M, G, At, R.Center, 3, true, Level);
	}
	for (int32 i = Before; i < M.Foes.Num(); ++i) R.Foes.AddUnique(M.Foes[i]);
	if (Sp.Kind == TEXT("ambush"))
	{
		// the wave runs at the heroes
		for (auto& F : R.Foes) if (ACoHCombatEnemy* E = F.Get()) { E->SetHome(Hero->GetActorLocation()); E->Alert(Hero); }
		if (UCoHPowerComponent* P = UCoHPowerComponent::Of(Hero)) P->MulticastText(TEXT("Ambush!"), FLinearColor(1.f, 0.35f, 0.25f));
	}
	if (R.Foes.Num() == 0 && !R.Hostage.IsValid() && !R.Object.IsValid()) RunDone(M, RunIdx);
	UE_LOG(LogTemp, Log, TEXT("CoH story: %s spawn %s (%s) placed: %d villains%s"), *M.Task, *Sp.Logical, *Sp.Kind, R.Foes.Num(), R.Hostage.IsValid() ? TEXT(", a hostage") : TEXT(""));
}

void ACoHStoryDirector::RunDone(FMission& M, int32 RunIdx)
{
	FMission::FRun& R = M.Runs[RunIdx];
	if (R.bDone) return;
	R.bDone = true;
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
	if (!T || !T->Spawns.IsValidIndex(R.Spawn)) return;
	const FCoHStorySpawn& Sp = T->Spawns[R.Spawn];
	const FString Ob = Sp.Objective.ToLower();
	if (Ob.IsEmpty()) return;
	UCoHStoryComponent* For = M.Hero.Get();
	if (For && !Sp.RewardText.IsEmpty()) if (UCoHPowerComponent* P = UCoHPowerComponent::Of(For->GetOwner())) P->MulticastText(For->Fill(Sp.RewardText), FLinearColor(0.4f, 1.f, 0.5f));
	if (For) For->GiveClues(M.Task, Sp.Clues);
	int32& L = M.Left.FindOrAdd(Ob);
	L = FMath::Max(0, L - 1);
	if (L == 0) ObjectiveDone(M, Ob);
}

void ACoHStoryDirector::ObjectiveDone(FMission& M, const FString& Name)
{
	if (M.Done.Contains(Name)) return;
	M.Done.Add(Name);
	UE_LOG(LogTemp, Log, TEXT("CoH story: %s objective %s done"), *M.Task, *Name);
	// objectives to click that were waiting for it
	for (int32 i = M.Waiting.Num() - 1; i >= 0; --i)
	{
		const TPair<int32, FVector> W = M.Waiting[i];
		const UCoHStory* S = UCoHStory::Get(this);
		const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
		if (!T || !T->Objectives.IsValidIndex(W.Key) || !Triggered(M, T->Objectives[W.Key].ActivateOn)) continue;
		M.Waiting.RemoveAt(i);
		PlaceClickable(M, W.Key, W.Value, false);
	}
	TickRuns(M);
}

void ACoHStoryDirector::TickRuns(FMission& M)
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
	if (!T) return;
	auto KnownAny = [&](const TArray<FString>& On) { for (const FString& N : On) if (M.Known.Contains(N.ToLower())) return true; return false; };
	// the objectives a waiting run is not itself part of: when they are all done and it still waits, it comes anyway
	bool bOthersDone = true;
	for (const auto& KV : M.Left)
		if (KV.Value > 0 && !M.Runs.ContainsByPredicate([&](const FMission::FRun& R) { return !R.bCreated && T->Spawns[R.Spawn].Objective.ToLower() == KV.Key; }))
			bOthersDone = false;
	// half the mission's villains down (and the hero inside): an ambush on a script trigger comes then
	int32 FoesDown = 0;
	for (const auto& F : M.Foes) if (!F.IsValid() || F->IsDead()) ++FoesDown;
	const bool bHalfDown = M.bEntered && M.Foes.Num() > 0 && FoesDown * 2 >= M.Foes.Num();
	for (int32 i = 0; i < M.Runs.Num(); ++i)
	{
		FMission::FRun& R = M.Runs[i];
		const FCoHStorySpawn& Sp = T->Spawns[R.Spawn];
		if (!R.bCreated)
		{
			TArray<FString> On = Sp.CreateOn;
			if (Sp.Kind == TEXT("ambush")) On.Append(Sp.ActivateOn);
			bool bGo;
			if (On.Num() == 0) bGo = Sp.Kind != TEXT("ambush") || M.Done.Num() > 0 || bHalfDown;          // an ambush with no trigger: after the first objective
			else if (KnownAny(On)) bGo = Triggered(M, On);
			else bGo = Sp.Kind != TEXT("ambush") || M.Done.Num() > 0 || bHalfDown;                     // its trigger is a script of the original: at once (ambush: after the first objective, or half the villains down)
			if (!bGo && bOthersDone && M.bEntered && M.Done.Num() > 0) bGo = true;                        // never leave a mission stuck on a trigger
			if (!bGo) continue;
			CreateRun(M, i);
			if (R.bDone) continue;
		}
		if (R.bDone) continue;
		if (Sp.Kind == TEXT("rescue") || Sp.Kind == TEXT("escort"))
		{
			if (!R.Hostage.IsValid()) { RunDone(M, i); continue; }
			if (Sp.Kind == TEXT("escort") && R.bRescued)
			{
				// brought to the exit (indoors) or back to the door
				const FCoHMissionMap* Map = S->Map(M.MapId);
				const FVector Goal = M.Map.IsValid() && Map ? M.Origin + Map->Exit : M.Door;
				if (FVector::Dist(R.Hostage->GetActorLocation(), Goal) < 800.f)
				{
					R.Hostage->FollowHero(nullptr);
					R.Hostage->SetLifeSpan(3.f);
					RunDone(M, i);
				}
			}
			continue;
		}
		if (R.Object.IsValid()) continue;                       // the object marker is still standing
		bool bLeft = false;
		for (const auto& F : R.Foes) if (F.IsValid() && !F->IsDead()) { bLeft = true; break; }
		if (!bLeft) RunDone(M, i);
	}
	// objectives to click still waiting when every spawn and other objective is through: their trigger will not come, so they show now
	if (M.Waiting.Num() && M.bEntered && M.Objectives.Num() == 0 && !M.Runs.ContainsByPredicate([](const FMission::FRun& R) { return !R.bDone; }))
	{
		const TArray<TPair<int32, FVector>> Now = MoveTemp(M.Waiting);
		M.Waiting.Reset();
		for (const auto& W : Now)
		{
			const FCoHStoryObjective& Ob = T->Objectives[W.Key];
			if (ACoHMissionMarker* Mk = SpawnMarker(ECoHMarkerKind::Objective, W.Value, Cast<APawn>(M.Hero->GetOwner()), Ob.Display.IsEmpty() ? Ob.Name : Ob.Display, M.Task))
			{ Mk->Objective = W.Key; M.Objectives.Add(Mk); }
		}
	}
}

void ACoHStoryDirector::UseHostage(APawn* By, ACoHStoryNPC* Hostage)
{
	if (!By || !Hostage) return;
	for (FMission& M : Missions)
		for (int32 i = 0; i < M.Runs.Num(); ++i)
		{
			FMission::FRun& R = M.Runs[i];
			if (R.Hostage.Get() != Hostage) continue;
			UCoHStoryComponent* For = M.Hero.Get();
			APawn* OwnerPawn = For ? Cast<APawn>(For->GetOwner()) : nullptr;
			UCoHPowerComponent* P = UCoHPowerComponent::Of(By);
			if (By != OwnerPawn && !UCoHSocial::SameTeam(By, OwnerPawn)) return;
			if (R.bRescued)
			{
				// another hero takes the lead
				Hostage->FollowHero(By);
				if (P) P->MulticastText(FString::Printf(TEXT("%s follows you"), *Hostage->DisplayName), FLinearColor(0.6f, 0.9f, 1.f));
				return;
			}
			for (const auto& F : R.Foes)
				if (F.IsValid() && !F->IsDead() && FVector::Dist(F->GetActorLocation(), Hostage->GetActorLocation()) < 2500.f)
				{
					if (P) P->MulticastText(TEXT("Defeat the captors first!"), FLinearColor(1.f, 0.6f, 0.4f));
					return;
				}
			R.bRescued = true;
			Hostage->FollowHero(By);
			const UCoHStory* S = UCoHStory::Get(this);
			const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
			const bool bEscort = T && T->Spawns.IsValidIndex(R.Spawn) && T->Spawns[R.Spawn].Kind == TEXT("escort");
			if (P) P->MulticastText(bEscort ? FString::Printf(TEXT("%s: Get me out of here!"), *Hostage->DisplayName)
				: FString::Printf(TEXT("%s: Thank you!"), *Hostage->DisplayName), FLinearColor(0.6f, 0.9f, 1.f));
			if (!bEscort) RunDone(M, i);
			return;
		}
}

void ACoHStoryDirector::UseObjective(UCoHStoryComponent* For, ACoHMissionMarker* Marker, APawn* ByPawn)
{
	FMission* M = Marker ? Find(For, Marker->Task) : nullptr;
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S && M ? S->Task(M->Task) : nullptr;
	if (!T || Marker->bBusy) return;
	if (Marker->Run != INDEX_NONE)
	{
		// an object to destroy with no model of its own: smashed at once
		if (M->Runs.IsValidIndex(Marker->Run)) { M->Runs[Marker->Run].Object = nullptr; RunDone(*M, Marker->Run); }
		M->Objectives.Remove(Marker);
		Marker->Destroy();
		return;
	}
	const FCoHStoryObjective* O = T->Objectives.IsValidIndex(Marker->Objective) ? &T->Objectives[Marker->Objective] : nullptr;
	if (O && O->Delay > 0)
	{
		// it takes a moment (the original's InteractDelay): stay near it
		APawn* By = ByPawn ? ByPawn : For ? Cast<APawn>(For->GetOwner()) : nullptr;
		if (!O->Begin.IsEmpty()) if (UCoHPowerComponent* P = UCoHPowerComponent::Of(By)) P->MulticastText(For->Fill(O->Begin), FLinearColor(0.9f, 0.9f, 0.9f));
		Marker->bBusy = true;
		FMission::FClick C; C.Marker = Marker; C.By = By; C.At = GetWorld()->GetTimeSeconds() + O->Delay;
		M->Clicks.Add(C);
		return;
	}
	FinishClick(*M, Marker);
}

void ACoHStoryDirector::FinishClick(FMission& M, ACoHMissionMarker* Marker)
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
	UCoHStoryComponent* For = M.Hero.Get();
	if (!T || !Marker) return;
	const FCoHStoryObjective* O = T->Objectives.IsValidIndex(Marker->Objective) ? &T->Objectives[Marker->Objective] : nullptr;
	if (O && For)
	{
		const FString Msg = !O->Reward.IsEmpty() ? O->Reward : !O->Done.IsEmpty() ? O->Done : FString::Printf(TEXT("%s: done"), *O->Display);
		if (UCoHPowerComponent* P = UCoHPowerComponent::Of(For->GetOwner())) P->MulticastText(For->Fill(Msg), FLinearColor(0.4f, 1.f, 0.5f));
		For->GiveClues(M.Task, O->Clues);
	}
	M.Objectives.Remove(Marker);
	M.ObjectivesLeft = FMath::Max(0, M.ObjectivesLeft - 1);
	Marker->Destroy();
	if (O)
	{
		const FString Name = O->Name.ToLower();
		int32& L = M.Left.FindOrAdd(Name);
		L = FMath::Max(0, L - 1);
		if (L == 0) ObjectiveDone(M, Name);
	}
}

void ACoHStoryDirector::CheckMission(FMission& M)
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(M.Task) : nullptr;
	if (!T) return;
	// clicks that take time
	const double Now = GetWorld()->GetTimeSeconds();
	for (int32 i = M.Clicks.Num() - 1; i >= 0; --i)
	{
		const FMission::FClick C = M.Clicks[i];
		ACoHMissionMarker* Mk = C.Marker.Get();
		if (!Mk) { M.Clicks.RemoveAt(i); continue; }
		if (!C.By.IsValid() || FVector::Dist2D(C.By->GetActorLocation(), Mk->GetActorLocation()) > 700.f)
		{
			if (UCoHPowerComponent* P = UCoHPowerComponent::Of(C.By.Get())) P->MulticastText(TEXT("Interrupted"), FLinearColor(1.f, 0.6f, 0.4f));
			Mk->bBusy = false;
			M.Clicks.RemoveAt(i);
			continue;
		}
		if (Now < C.At) continue;
		M.Clicks.RemoveAt(i);
		Mk->bBusy = false;
		FinishClick(M, Mk);
	}
	TickRuns(M);
	int32 Alive = 0, AliveEnd = 0;
	for (const auto& F : M.Foes) if (F.IsValid() && !F->IsDead()) ++Alive;
	for (const FMission::FRun& R : M.Runs) if (R.bEndRoom) for (const auto& F : R.Foes) if (F.IsValid() && !F->IsDead()) ++AliveEnd;
	// CanCompleteWith: any one line whose names are all done (DefeatAllVillains[InEndRoom], objectives
	// and spawns by name); names of the original's scripts we can't run are left out, and a line of
	// only those, or no line at all, is defeat all with every objective done
	const bool bAllDone = Alive == 0 && M.ObjectivesLeft == 0 && !M.Runs.ContainsByPredicate([](const FMission::FRun& R) { return !R.bDone; });
	bool bDone = T->CompleteWith.Num() == 0 && bAllDone;
	for (const FString& Line : T->CompleteWith)
	{
		TArray<FString> Names;
		Line.ParseIntoArrayWS(Names);
		bool bOk = true, bAny = false;
		for (const FString& N : Names)
		{
			const FString L = N.ToLower();
			if (L == TEXT("defeatallvillains")) { bAny = true; bOk &= Alive == 0; }
			else if (L == TEXT("defeatallvillainsinendroom")) { bAny = true; bOk &= M.MapId.IsEmpty() ? Alive == 0 : AliveEnd == 0; }
			else if (M.Known.Contains(L)) { bAny = true; bOk &= M.Done.Contains(L); }
		}
		if (!bAny) bOk = bAllDone;
		if (bOk) { bDone = true; break; }
	}
	if (!bDone) return;
	UCoHStoryComponent* Hero = M.Hero.Get();
	const FString Task = M.Task;
	if (M.Map.IsValid() && M.bInside)
	{
		// done inside: the task completes now, the hero walks out through the exit
		M.bFinished = true;
		for (auto& O : M.Objectives) if (O.IsValid()) O->Destroy();
		M.Objectives.Reset();
		if (Hero) Hero->CompleteTask(Task, T->Complete);
		return;
	}
	CloseMission(Hero, Task);
	if (Hero) Hero->CompleteTask(Task, T->Complete);
}

void ACoHStoryDirector::ExitMission(UCoHStoryComponent* For, const FString& TaskId)
{
	FMission* M = Find(For, TaskId);
	if (!M) return;
	TeleportHero(*M, false);
	if (M->bFinished) CloseMission(For, TaskId);
}

void ACoHStoryDirector::FreeMission(FMission& M)
{
	// teammates still inside come out at the door before the map goes
	for (const TWeakObjectPtr<APawn>& G : M.Guests)
		if (APawn* P = G.Get()) if (IsMissionSpace(P->GetActorLocation())) PutAtDoor(M, P);
	M.Guests.Reset();
	for (auto& O : M.Objectives) if (O.IsValid()) O->Destroy();
	for (FMission::FRun& R : M.Runs) if (R.Hostage.IsValid()) R.Hostage->Destroy();
	if (M.DoorMarker.IsValid()) M.DoorMarker->Destroy();
	if (M.ExitMarker.IsValid()) M.ExitMarker->Destroy();
	if (M.Map.IsValid()) M.Map->Destroy();     // unloads the level here and on clients
}

void ACoHStoryDirector::CloseMission(UCoHStoryComponent* For, const FString& TaskId)
{
	for (int32 i = Missions.Num() - 1; i >= 0; --i)
	{
		FMission& M = Missions[i];
		if (M.Hero.Get() != For || M.Task != TaskId) continue;
		if (M.bInside) TeleportHero(M, false);      // abandoned inside: out to the door first
		const bool bIndoor = M.Map.IsValid();
		FreeMission(M);
		// the mission's villains clear away: at once with their map, else half a minute later
		for (auto& F : M.Foes) if (F.IsValid()) { if (bIndoor) F->Destroy(); else F->SetLifeSpan(30.f); }
		Missions.RemoveAt(i);
	}
}

// ------------------------------------------------------------------ UCoHStoryComponent
UCoHStoryComponent::UCoHStoryComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickInterval = 0.5f;
	SetIsReplicatedByDefault(true);
}

UCoHStoryComponent* UCoHStoryComponent::Of(const AActor* A) { return A ? A->FindComponentByClass<UCoHStoryComponent>() : nullptr; }
UCoHHeroProgress* UCoHStoryComponent::Progress() const { return UCoHHeroProgress::Of(GetOwner()); }
FCoHStoryProgress* UCoHStoryComponent::Story() const { UCoHHeroProgress* P = Progress(); return P && P->bHasRecord ? &P->Hero.Story : nullptr; }
FString UCoHStoryComponent::HeroName() const { const UCoHHeroProgress* P = Progress(); return P ? P->Hero.Name : TEXT("Hero"); }
int32 UCoHStoryComponent::HeroLevel() const
{
	const UCoHHeroProgress* P = Progress();
	if (P && P->bHasRecord) return P->Hero.Level;
	const UCoHPowerComponent* Pw = UCoHPowerComponent::Of(GetOwner());
	return Pw ? Pw->Level : 1;
}

void UCoHStoryComponent::BeginPlay()
{
	Super::BeginPlay();
	const APawn* Pawn = Cast<APawn>(GetOwner());
	if (Pawn && Pawn->IsLocallyControlled() && GEngine && GEngine->GameViewport)
	{
		Panel = SNew(SCoHStoryPanel).Owner(this);
		PanelHost = SNew(SWeakWidget).PossiblyNullContent(Panel);
		GEngine->GameViewport->AddViewportWidgetContent(PanelHost.ToSharedRef(), 8);
	}
	// the host stands the contacts in the world (one director per map)
	if (GetOwnerRole() == ROLE_Authority && GetWorld() && !ACoHStoryDirector::Get(GetWorld()))
		GetWorld()->SpawnActor<ACoHStoryDirector>(ACoHStoryDirector::StaticClass(), FTransform::Identity);
}

void UCoHStoryComponent::EndPlay(const EEndPlayReason::Type Reason)
{
	if (PanelHost.IsValid() && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(PanelHost.ToSharedRef());
	PanelHost.Reset(); Panel.Reset();
	Super::EndPlay(Reason);
}

FString UCoHStoryComponent::Fill(const FString& Text, const FCoHStoryContact* C) const
{
	FString Out = Text.Replace(TEXT("{HeroName}"), *HeroName(), ESearchCase::IgnoreCase);
	Out = Out.Replace(TEXT("{Level}"), *FString::FromInt(C ? C->MinLevel : HeroLevel()), ESearchCase::IgnoreCase);
	if (C) Out = Out.Replace(TEXT("{ContactName}"), *C->Name, ESearchCase::IgnoreCase);
	// variables the export could not fill (random picks): show the name without braces
	FString Clean; Clean.Reserve(Out.Len());
	for (int32 i = 0; i < Out.Len(); ++i)
	{
		if (Out[i] == TEXT('{'))
		{
			const int32 End = Out.Find(TEXT("}"), ESearchCase::CaseSensitive, ESearchDir::FromStart, i);
			if (End > i)
			{
				FString Var = Out.Mid(i + 1, End - i - 1).Replace(TEXT("_"), TEXT(" ")).ToLower();
				if (Var.Len()) Var[0] = FChar::ToUpper(Var[0]);
				Clean += Var; i = End; continue;
			}
		}
		Clean.AppendChar(Out[i]);
	}
	return Clean;
}

void UCoHStoryComponent::Say(const FString& Text, FLinearColor Colour) const
{
	if (UCoHPowerComponent* P = UCoHPowerComponent::Of(GetOwner())) P->MulticastText(Text, Colour);
}

void UCoHStoryComponent::Save()
{
	if (UCoHHeroProgress* P = Progress()) P->Save();
}

void UCoHStoryComponent::Show(const FCoHDialogPage& Page) { ClientShowPage(Page); }

void UCoHStoryComponent::ClientShowPage_Implementation(const FCoHDialogPage& Page)
{
	if (Panel.IsValid()) Panel->ShowPage(Page);
}

void UCoHStoryComponent::ClosePage() { if (Panel.IsValid()) Panel->Hide(); }

FCoHContactState& UCoHStoryComponent::ContactState(const FString& Id)
{
	FCoHStoryProgress* S = Story();
	check(S);
	for (FCoHContactState& C : S->Contacts) if (C.Contact == Id) return C;
	FCoHContactState N; N.Contact = Id;
	return S->Contacts[S->Contacts.Add(N)];
}

void UCoHStoryComponent::Interact()
{
	ServerInteract();
}

void UCoHStoryComponent::ServerInteract_Implementation()
{
	const AActor* Me = GetOwner();
	if (!Me || !Story()) return;
	if (const UCoHPowerComponent* Pw = UCoHPowerComponent::Of(Me)) if (Pw->IsDefeated()) return;   // down: no talking, clicking or freeing
	AActor* Best = nullptr; float BestD = TNumericLimits<float>::Max();
	for (TActorIterator<ACoHStoryNPC> It(GetWorld()); It; ++It)
	{
		const float D = FVector::Dist(It->GetActorLocation(), Me->GetActorLocation());
		if (D < 500.f && D < BestD) { BestD = D; Best = *It; }
	}
	for (TActorIterator<ACoHMissionMarker> It(GetWorld()); It; ++It)
	{
		if (It->ForHero.Get() != Me && !UCoHSocial::SameTeam(It->ForHero.Get(), Me)) continue;
		const float D = FVector::Dist2D(It->GetActorLocation(), Me->GetActorLocation());
		if (D < 600.f && D < BestD) { BestD = D; Best = *It; }
	}
	if (ACoHStoryNPC* N = Cast<ACoHStoryNPC>(Best))
	{
		if (N->bHostage) { if (ACoHStoryDirector* D = ACoHStoryDirector::Get(GetWorld())) D->UseHostage(Cast<APawn>(GetOwner()), N); }
		else if (N->bContact) TalkTo(N->Key); else TalkToPerson(N->Key);
	}
	else if (ACoHMissionMarker* Mk = Cast<ACoHMissionMarker>(Best))
	{
		ACoHStoryDirector* D = ACoHStoryDirector::Get(GetWorld());
		const UCoHStory* St = UCoHStory::Get(this);
		const FCoHStoryTask* T = St ? St->Task(Mk->Task) : nullptr;
		if (!D || !T) return;
		// a teammate's mission
		UCoHStoryComponent* OwnerStory = Mk->ForHero ? Mk->ForHero->FindComponentByClass<UCoHStoryComponent>() : nullptr;
		if (OwnerStory && OwnerStory != this)
		{
			APawn* MePawn = Cast<APawn>(GetOwner());
			if (Mk->Kind == ECoHMarkerKind::Door) D->GuestEnter(OwnerStory, Mk->Task, MePawn);
			else if (Mk->Kind == ECoHMarkerKind::Objective) D->UseObjective(OwnerStory, Mk, MePawn);
			else if (Mk->Kind == ECoHMarkerKind::Exit) D->GuestExit(OwnerStory, Mk->Task, MePawn);
			return;
		}
		if (Mk->Kind == ECoHMarkerKind::Door)
		{
			FCoHDialogPage P;
			P.Title = T->MapSet.IsEmpty() ? TEXT("Mission") : T->MapSet;
			P.Body = Fill(T->Entry.IsEmpty() ? T->Active : T->Entry);
			if (D->IsInside(this, Mk->Task)) P.Body = TEXT("Go back inside?");
			P.Labels = { TEXT("Enter"), TEXT("Not now") };
			P.Actions = { TEXT("enter|") + Mk->Task, TEXT("close") };
			Show(P);
		}
		else if (Mk->Kind == ECoHMarkerKind::Objective) D->UseObjective(this, Mk);
		else if (Mk->Kind == ECoHMarkerKind::Exit) D->ExitMission(this, Mk->Task);
	}
}

void UCoHStoryComponent::ServerChoose_Implementation(const FString& Action)
{
	TArray<FString> Parts;
	Action.ParseIntoArray(Parts, TEXT("|"), false);
	if (Parts.Num() == 0 || !Story()) return;
	const FString& Verb = Parts[0];
	const FString A1 = Parts.IsValidIndex(1) ? Parts[1] : FString(), A2 = Parts.IsValidIndex(2) ? Parts[2] : FString();
	if (Verb == TEXT("talk")) TalkTo(A1);
	else if (Verb == TEXT("show")) ShowTask(A1, A2);
	else if (Verb == TEXT("accept")) Accept(A1, A2);
	else if (Verb == TEXT("turnin")) TurnIn(A1);
	else if (Verb == TEXT("abandon")) Abandon(A1);
	else if (Verb == TEXT("store")) OpenContactStore(A1);
	else if (Verb == TEXT("pstore"))
	{
		const FCoHStoryPerson* Who = Story() ? UCoHStory::Get(this)->Person(A1) : nullptr;
		UCoHEnhancements* E = UCoHEnhancements::Of(GetOwner());
		if (Who && E && !Who->Store.IsEmpty()) E->OpenStore({ Who->Store }, Who->Name);
	}
	else if (Verb == TEXT("enter"))
	{
		if (ACoHStoryDirector* D = ACoHStoryDirector::Get(GetWorld())) D->EnterMission(this, A1);
		FCoHDialogPage P; P.Title = TEXT("Mission"); P.Body = TEXT("Defeat the villains and complete the objectives. The exit post inside takes you back to the door.");
		P.Labels = { TEXT("Go") }; P.Actions = { TEXT("close") };
		Show(P);
	}
}

bool UCoHStoryComponent::Available(const FCoHStoryTask& T) const
{
	const UCoHStory* S = UCoHStory::Get(this);
	const int32 Lv = HeroLevel();
	if (Lv < T.MinLevel || Lv > T.MaxLevel) return false;
	if (T.Type == TEXT("deliver") && !S->Contact(T.DeliverContact) && !S->Person(T.DeliverNpc)) return false;
	if (T.Type == TEXT("visit")) { FVector P; if (!S->VisitPoint(T.VisitLocation, P)) return false; }
	return T.Type == TEXT("mission") || T.Type == TEXT("killx") || T.Type == TEXT("deliver") || T.Type == TEXT("visit");
}

// ContactRequires, the original's postfix test of the hero: "class_peacebringer arch char> eq",
// "level char> 20 >=", "alignment char> hero eq ... ||". Tokens and products we don't keep are false.
static bool CoHContactAllows(const TArray<FString>& Req, const FCoHHeroRecord& H)
{
	if (Req.Num() == 0) return true;
	TArray<FString> St;
	auto Pop = [&]() { return St.Num() ? St.Pop() : FString(); };
	auto Truth = [](const FString& V) { return !V.IsEmpty() && V != TEXT("0"); };
	for (const FString& Tok : Req)
	{
		const FString T = Tok.ToLower();
		if (T == TEXT("char>"))
		{
			const FString What = Pop().ToLower();
			if (What == TEXT("arch") || What == TEXT("archetype") || What == TEXT("class")) St.Push(H.Class.ToLower());
			else if (What == TEXT("level")) St.Push(FString::FromInt(H.Level));
			else if (What == TEXT("origin")) St.Push(H.Origin.ToLower());
			else if (What == TEXT("alignment") || What == TEXT("allyid") || What == TEXT("type")) St.Push(TEXT("hero"));
			else St.Push(FString());
		}
		else if (T == TEXT("eq")) { const FString B = Pop(), A = Pop(); St.Push(A.Equals(B, ESearchCase::IgnoreCase) ? TEXT("1") : TEXT("0")); }
		else if (T == TEXT(">=") || T == TEXT("<=") || T == TEXT(">") || T == TEXT("<"))
		{
			const float B = FCString::Atof(*Pop()), A = FCString::Atof(*Pop());
			const bool R = T == TEXT(">=") ? A >= B : T == TEXT("<=") ? A <= B : T == TEXT(">") ? A > B : A < B;
			St.Push(R ? TEXT("1") : TEXT("0"));
		}
		else if (T == TEXT("&&") || T == TEXT("||")) { const bool B = Truth(Pop()), A = Truth(Pop()); St.Push((T == TEXT("&&") ? A && B : A || B) ? TEXT("1") : TEXT("0")); }
		else if (T == TEXT("!")) St.Push(Truth(Pop()) ? TEXT("0") : TEXT("1"));
		else if (T == TEXT("productowned?") || T == TEXT("owned?")) { Pop(); St.Push(TEXT("1")); }   // store products: every hero owns them
		else if (T.EndsWith(TEXT("?")) || T == TEXT("tokenval>")) { Pop(); St.Push(TEXT("0")); }   // story tokens: not kept yet
		else St.Push(Tok);
	}
	return St.Num() && Truth(St.Last());
}

TArray<FString> UCoHStoryComponent::Offers(const FCoHStoryContact& C) const
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryProgress* P = Story();
	TArray<FString> Out;
	if (!S || !P) return Out;
	if (const UCoHHeroProgress* HP = Progress()) if (!CoHContactAllows(C.Requires, HP->Hero)) return Out;   // e.g. Kheldian-only contacts
	auto Active = [&](const FString& First)
	{
		// any part of the chain that starts here is in hand
		for (FString Id = First; !Id.IsEmpty();)
		{
			if (P->Tasks.ContainsByPredicate([&](const FCoHTaskState& T) { return T.Task == Id; })) return true;
			const FCoHStoryTask* T = S->Task(Id);
			Id = T && T->bAutoNext ? T->Next : FString();
		}
		return false;
	};
	auto Consider = [&](const FString& Id)
	{
		const FCoHStoryTask* T = S->Task(Id);
		if (!T || P->Done.Contains(Id) || Active(Id) || !Available(*T)) return false;
		const FString Before = S->Previous(Id);
		if (!Before.IsEmpty() && !P->Done.Contains(Before)) return false;
		Out.Add(Id);
		return true;
	};
	const int32 Lv = HeroLevel();
	for (const FString& A : C.Arcs)
	{
		const FCoHStoryArc* Arc = S->Arc(A);
		if (!Arc || Lv < Arc->MinLevel || Lv > Arc->MaxLevel) continue;
		for (const FString& E : Arc->Episodes)
		{
			if (P->Done.Contains(E)) continue;
			if (Active(E)) break;
			Consider(E);
			break;           // only the arc's next episode
		}
	}
	for (const FString& Id : C.Tasks) { if (Out.Num() >= 3) break; Consider(Id); }
	return Out;
}

void UCoHStoryComponent::TalkTo(const FString& ContactId)
{
	const UCoHStory* S = UCoHStory::Get(this);
	FCoHStoryProgress* P = Story();
	const FCoHStoryContact* C = S ? S->Contact(ContactId) : nullptr;
	if (!C || !P) return;
	LastContact = ContactId;
	FCoHDialogPage Page;
	Page.Title = C->Profession.IsEmpty() ? C->Name : FString::Printf(TEXT("%s, %s"), *C->Name, *C->Profession);
	// a delivery for this contact
	for (FCoHTaskState& T : P->Tasks)
	{
		const FCoHStoryTask* D = S->Task(T.Task);
		if (D && !T.bComplete && D->Type == TEXT("deliver") && D->DeliverContact == ContactId && T.Contact != ContactId)
		{
			const FString Id = T.Task;      // CompleteTask changes the list
			CompleteTask(Id, FString());
			Page.Body = Fill(D->Complete.IsEmpty() ? TEXT("Thank you, {HeroName}.") : D->Complete, C);
			Page.Labels = { TEXT("Continue") }; Page.Actions = { TEXT("talk|") + ContactId };
			ShowContact(Page, *C);
			return;
		}
	}
	// a finished task of this contact: turn it in
	for (const FCoHTaskState& T : P->Tasks)
		if (T.Contact == ContactId && T.bComplete)
		{
			const FCoHStoryTask* D = S->Task(T.Task);
			Page.Body = Fill(D && !D->Return.IsEmpty() ? D->Return : TEXT("Well done, {HeroName}."), C);
			Page.Labels = { TEXT("Finish") }; Page.Actions = { TEXT("turnin|") + T.Task };
			ShowContact(Page, *C);
			return;
		}
	if (const UCoHHeroProgress* HP = Progress())
		if (!CoHContactAllows(C->Requires, HP->Hero))
		{
			// not for this hero (ContactRequires: Kheldian-only, level 20+ ...)
			Page.Body = Fill(C->DontKnow.IsEmpty() ? TEXT("I don't think I can help you, {HeroName}.") : C->DontKnow, C);
			Page.Labels = { TEXT("Leave") }; Page.Actions = { TEXT("close") };
			ShowContact(Page, *C);
			return;
		}
	const bool bFirst = !P->Contacts.ContainsByPredicate([&](const FCoHContactState& X) { return X.Contact == ContactId; });
	ContactState(ContactId);
	const int32 Lv = HeroLevel();
	if (Lv < C->MinLevel)
	{
		Page.Body = Fill(C->ComeBack.IsEmpty() ? C->DontKnow : C->ComeBack, C);
		Page.Labels = { TEXT("Leave") }; Page.Actions = { TEXT("close") };
		ShowContact(Page, *C);
		return;
	}
	FString Hello = bFirst && !C->FirstVisit.IsEmpty() ? C->FirstVisit : C->Hello.Num() ? C->Hello[FMath::RandRange(0, C->Hello.Num() - 1)] : FString();
	// tasks in hand from this contact
	for (const FCoHTaskState& T : P->Tasks)
		if (T.Contact == ContactId)
		{
			const FCoHStoryTask* D = S->Task(T.Task);
			Page.Body = Fill(D && !D->Busy.IsEmpty() ? D->Busy : Hello, C);
			Page.Labels = { TEXT("I'm on it"), TEXT("Abandon this task") };
			Page.Actions = { TEXT("close"), TEXT("abandon|") + T.Task };
			ShowContact(Page, *C);
			return;
		}
	if (P->Tasks.Num() >= 3)
	{
		Page.Body = Fill(C->Busy.IsEmpty() ? TEXT("You have enough on your plate, {HeroName}.") : C->Busy, C);
		Page.Labels = { TEXT("Leave") }; Page.Actions = { TEXT("close") };
		ShowContact(Page, *C);
		return;
	}
	const TArray<FString> Offer = Offers(*C);
	if (Offer.Num() == 0)
	{
		Page.Body = Fill(C->NoTasks.IsEmpty() ? TEXT("I have nothing for you right now.") : C->NoTasks, C);
		Page.Labels = { TEXT("Leave") }; Page.Actions = { TEXT("close") };
		ShowContact(Page, *C);
		return;
	}
	Page.Body = Fill(Hello, C);
	for (const FString& Id : Offer)
	{
		const FCoHStoryTask* D = S->Task(Id);
		Page.Labels.Add(Fill(D->Accept.IsEmpty() ? D->Active : D->Accept, C));
		Page.Actions.Add(FString::Printf(TEXT("show|%s|%s"), *Id, *ContactId));
	}
	Page.Labels.Add(TEXT("Leave")); Page.Actions.Add(TEXT("close"));
	ShowContact(Page, *C);
}

void UCoHStoryComponent::ShowTask(const FString& TaskId, const FString& ContactId)
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryContact* C = S ? S->Contact(ContactId) : nullptr;
	const FCoHStoryTask* T = S ? S->Task(TaskId) : nullptr;
	if (!C || !T) return;
	FCoHDialogPage Page;
	Page.Title = C->Name;
	Page.Body = Fill(T->Intro.IsEmpty() ? T->Active : T->Intro, C);
	if (!T->Arc.IsEmpty()) if (const FCoHStoryArc* A = S->Arc(T->Arc)) Page.Title += FString::Printf(TEXT("  (story arc: %s)"), *A->Name);
	Page.Labels = { Fill(T->Accept.IsEmpty() ? TEXT("Accept") : T->Accept, C), TEXT("Back") };
	Page.Actions = { FString::Printf(TEXT("accept|%s|%s"), *TaskId, *ContactId), TEXT("talk|") + ContactId };
	Show(Page);
}

void UCoHStoryComponent::Refresh(FCoHTaskState& St) const
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryTask* T = S ? S->Task(St.Task) : nullptr;
	if (!T) return;
	const FCoHStoryContact* C = S->Contact(St.Contact);
	if (St.bComplete)
	{
		St.Text = FString::Printf(TEXT("Return to %s"), C ? *C->Name : TEXT("your contact"));
		if (C) St.Waypoint = C->Pos;
		if (const ACoHStoryDirector* D = ACoHStoryDirector::Get(GetWorld())) { FVector W; if (D->WhereIs(St.Contact, W)) St.Waypoint = W; }
		return;
	}
	St.Text = Fill(T->Active.IsEmpty() ? T->Accept : T->Active, C);
	if (St.Needed > 0) St.Text += FString::Printf(TEXT(" (%d/%d)"), St.Progress, St.Needed);
}

void UCoHStoryComponent::Accept(const FString& TaskId, const FString& ContactId)
{
	const UCoHStory* S = UCoHStory::Get(this);
	FCoHStoryProgress* P = Story();
	const FCoHStoryContact* C = S ? S->Contact(ContactId) : nullptr;
	const FCoHStoryTask* T = S ? S->Task(TaskId) : nullptr;
	if (!P || !T) return;
	// accepted from a contact window: it has to be on offer (compound parts come from CompleteTask)
	if (C && LastContact == ContactId && !Offers(*C).Contains(TaskId) && !P->Tasks.ContainsByPredicate([&](const FCoHTaskState& X) { return X.Task == TaskId; }))
	{
		UE_LOG(LogTemp, Warning, TEXT("CoH story: %s is not on offer from %s"), *TaskId, *ContactId);
		return;
	}
	FCoHTaskState St;
	St.Task = TaskId; St.Contact = ContactId;
	ACoHStoryDirector* D = ACoHStoryDirector::Get(GetWorld());
	if (T->Type == TEXT("killx")) St.Needed = FMath::Max(1, T->KillCount);
	else if (T->Type == TEXT("mission") && D) St.Waypoint = D->OpenMission(this, TaskId);
	else if (T->Type == TEXT("deliver") && D) { FVector W; if (D->WhereIs(T->DeliverContact.IsEmpty() ? T->DeliverNpc : T->DeliverContact, W) || D->WhereIs(T->DeliverNpc, W)) St.Waypoint = W; }
	else if (T->Type == TEXT("visit")) S->VisitPoint(T->VisitLocation, St.Waypoint);
	Refresh(St);
	P->Tasks.Add(St);
	GiveClues(TaskId, T->BeginClues);
	UE_LOG(LogTemp, Log, TEXT("CoH story: %s took %s (%s) from %s"), *HeroName(), *TaskId, *T->Type, *ContactId);
	Save();
	if (C)
	{
		FCoHDialogPage Page;
		Page.Title = C->Name;
		Page.Body = Fill(T->SendOff.IsEmpty() ? TEXT("Good luck, {HeroName}.") : T->SendOff, C);
		if (!T->Begin.IsEmpty()) Page.Body += TEXT("\n\n") + Fill(T->Begin, C);
		Page.Labels = { TEXT("Leave") }; Page.Actions = { TEXT("close") };
		Show(Page);
	}
}

void UCoHStoryComponent::CompleteTask(const FString& TaskId, const FString& Message)
{
	const UCoHStory* S = UCoHStory::Get(this);
	FCoHStoryProgress* P = Story();
	const FCoHStoryTask* T = S ? S->Task(TaskId) : nullptr;
	if (!P || !T) return;
	const int32 Idx = P->Tasks.IndexOfByPredicate([&](const FCoHTaskState& X) { return X.Task == TaskId; });
	if (Idx == INDEX_NONE || P->Tasks[Idx].bComplete) return;
	if (!Message.IsEmpty()) Say(Fill(Message), FLinearColor(0.4f, 1.f, 0.5f));
	Say(TEXT("Mission complete!"), FLinearColor(1.f, 0.85f, 0.2f));
	GiveReward(T->CompleteReward);
	GiveClues(TaskId, T->CompleteClues);
	if (T->bAutoNext && !T->Next.IsEmpty())
	{
		// the next part of the same task, at once
		const FString Contact = P->Tasks[Idx].Contact;
		P->Done.AddUnique(TaskId);
		P->Tasks.RemoveAt(Idx);
		Accept(T->Next, Contact);
		return;
	}
	FCoHTaskState& St = P->Tasks[Idx];
	St.bComplete = true;
	if (T->bNoReturn) { TurnIn(TaskId); return; }
	Refresh(St);
	Save();
}

void UCoHStoryComponent::GiveReward(const FString& Table)
{
	const UCoHStory* S = UCoHStory::Get(this);
	UCoHHeroProgress* P = Progress();
	if (!S || !P || Table.IsEmpty()) return;
	const FCoHStoryReward R = S->Reward(Table, HeroLevel());
	if (R.XP > 0 || R.Influence > 0) P->Award(R.XP, R.Influence);
	for (const auto& D : R.Drops)
		if (FMath::FRand() * 100.f < D.Key)
		{
			// the original's power-up lists (PL.Single5Magic, PL.Dual5NatMag, PL.GenericPowerFive...):
			// an enhancement of the hero's origin around the hero's level
			bool bEnh = false;
			for (const FString& Set : D.Value)
				bEnh |= Set.Contains(TEXT("Single")) || Set.Contains(TEXT("Dual")) || Set.Contains(TEXT("PowerFive"));
			const UCoHItems* I = UCoHItems::Get(this);
			UCoHEnhancements* E = UCoHEnhancements::Of(GetOwner());
			if (bEnh && I && E) E->Give(I->RandomDrop(P->Hero.Origin, HeroLevel()));
			else UE_LOG(LogTemp, Log, TEXT("CoH story: reward %s would drop %s (not in the game yet)"), *Table, *FString::Join(D.Value, TEXT(", ")));
		}
}

void UCoHStoryComponent::GiveClues(const FString& TaskId, const FCoHStoryClues& C)
{
	const UCoHStory* S = UCoHStory::Get(this);
	FCoHStoryProgress* P = Story();
	if (!S || !P || C.IsEmpty()) return;
	for (const FString& Name : C.Remove) P->Clues.Remove(S->ClueKey(TaskId, Name));
	for (const FString& Name : C.Add)
	{
		const FString Key = S->ClueKey(TaskId, Name);
		const FCoHClueDef* D = S->Clues.Find(Key);
		if (P->Clues.Contains(Key)) continue;
		P->Clues.Add(Key);
		Say(TEXT("New clue: ") + (D && !D->Name.IsEmpty() ? Fill(D->Name) : Name), FLinearColor(0.7f, 0.85f, 1.f));
	}
	for (const FString& Name : C.Souvenirs)
	{
		const FString Key = Name.ToLower();
		if (P->Souvenirs.Contains(Key)) continue;
		P->Souvenirs.Add(Key);
		const FCoHClueDef* D = S->Souvenirs.Find(Key);
		Say(TEXT("Souvenir: ") + (D && !D->Name.IsEmpty() ? Fill(D->Name) : Name), FLinearColor(1.f, 0.8f, 0.3f));
	}
	Save();
}

FString UCoHStoryComponent::DescribeClues(bool bSouvenirs) const
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryProgress* P = Story();
	if (!S || !P) return FString();
	const TArray<FString>& Have = bSouvenirs ? P->Souvenirs : P->Clues;
	if (Have.Num() == 0) return bSouvenirs ? TEXT("You have no souvenirs yet.") : TEXT("You have no clues.");
	FString Out = FString::Printf(TEXT("%d %s:"), Have.Num(), bSouvenirs ? TEXT("souvenirs") : TEXT("clues"));
	for (const FString& Key : Have)
	{
		const FCoHClueDef* D = (bSouvenirs ? S->Souvenirs : S->Clues).Find(Key);
		Out += TEXT("\n- ") + (D ? Fill(D->Name) + (D->Text.IsEmpty() ? FString() : TEXT(": ") + Fill(D->Text).Left(300)) : Key);
	}
	return Out;
}

void UCoHStoryComponent::TurnIn(const FString& TaskId)
{
	const UCoHStory* S = UCoHStory::Get(this);
	FCoHStoryProgress* P = Story();
	const FCoHStoryTask* T = S ? S->Task(TaskId) : nullptr;
	if (!P || !T) return;
	const int32 Idx = P->Tasks.IndexOfByPredicate([&](const FCoHTaskState& X) { return X.Task == TaskId && X.bComplete; });
	if (Idx == INDEX_NONE) return;
	const FString ContactId = P->Tasks[Idx].Contact;
	P->Tasks.RemoveAt(Idx);
	P->Done.AddUnique(TaskId);
	GiveReward(T->Reward);
	GiveClues(TaskId, T->ReturnClues);
	const FCoHStoryContact* C = S->Contact(ContactId);
	FString Extra;
	if (C)
	{
		FCoHContactState& CS = ContactState(ContactId);
		const int32 Before = CS.Points;
		CS.Points += FMath::Max(T->ContactPoints, 1);
		if (Before < C->FriendCP && CS.Points >= C->FriendCP && !C->ToFriend.IsEmpty()) Extra = Fill(C->ToFriend, C);
		else if (Before < C->ConfidantCP && CS.Points >= C->ConfidantCP && !C->ToConfidant.IsEmpty()) Extra = Fill(C->ToConfidant, C);
	}
	UE_LOG(LogTemp, Log, TEXT("CoH story: %s turned in %s"), *HeroName(), *TaskId);
	Save();
	if (C && LastContact == ContactId)
	{
		FCoHDialogPage Page;
		Page.Title = C->Name;
		Page.Body = Extra.IsEmpty() ? TEXT("Anything else?") : Extra;
		Page.Labels = { TEXT("Ask for another task"), TEXT("Leave") };
		Page.Actions = { TEXT("talk|") + ContactId, TEXT("close") };
		Show(Page);
	}
}

void UCoHStoryComponent::Abandon(const FString& TaskId)
{
	FCoHStoryProgress* P = Story();
	if (!P) return;
	P->Tasks.RemoveAll([&](const FCoHTaskState& X) { return X.Task == TaskId; });
	if (ACoHStoryDirector* D = ACoHStoryDirector::Get(GetWorld())) D->CloseMission(this, TaskId);
	Say(TEXT("Task abandoned"), FLinearColor(1.f, 0.6f, 0.4f));
	Save();
	if (!LastContact.IsEmpty()) TalkTo(LastContact);
}

void UCoHStoryComponent::ShowContact(FCoHDialogPage& Page, const FCoHStoryContact& C)
{
	if (C.Stores.Num() && UCoHEnhancements::Of(GetOwner()))
	{
		const int32 At = FMath::Max(0, Page.Actions.IndexOfByKey(TEXT("close")));
		Page.Labels.Insert(TEXT("Store"), At); Page.Actions.Insert(TEXT("store|") + C.Id, At);
	}
	Show(Page);
}

void UCoHStoryComponent::OpenContactStore(const FString& ContactId)
{
	const UCoHStory* S = UCoHStory::Get(this);
	const FCoHStoryContact* C = S ? S->Contact(ContactId) : nullptr;
	UCoHEnhancements* E = UCoHEnhancements::Of(GetOwner());
	if (!C || !E || !C->Stores.Num()) return;
	// the original: a contact's store improves as the hero becomes a friend, then a confidant
	int32 Points = 0;
	if (const FCoHStoryProgress* P = Story())
		if (const FCoHContactState* CS = P->Contacts.FindByPredicate([&](const FCoHContactState& X) { return X.Contact == ContactId; })) Points = CS->Points;
	const FString Tier = Points >= C->ConfidantCP ? TEXT("_CL3") : Points >= C->FriendCP ? TEXT("_CL2") : TEXT("_CL1");
	TArray<FString> Use;
	for (const FString& Sid : C->Stores) if (Sid.EndsWith(Tier)) Use.Add(Sid);
	if (!Use.Num()) for (const FString& Sid : C->Stores) if (!Sid.Contains(TEXT("_CL"))) Use.Add(Sid);
	if (!Use.Num()) Use = C->Stores;
	E->OpenStore(Use, C->Name);
}

void UCoHStoryComponent::TalkToPerson(const FString& PersonId)
{
	const UCoHStory* S = UCoHStory::Get(this);
	FCoHStoryProgress* P = Story();
	const FCoHStoryPerson* Who = S ? S->Person(PersonId) : nullptr;
	if (!Who || !P) return;
	FCoHDialogPage Page;
	Page.Title = Who->Name;
	Page.Body = Fill(Who->Line.IsEmpty() ? TEXT("Hello there.") : Who->Line);
	for (const FCoHTaskState& T : P->Tasks)
	{
		const FCoHStoryTask* D = S->Task(T.Task);
		if (D && !T.bComplete && D->Type == TEXT("deliver") && D->DeliverNpc == PersonId)
		{
			Page.Body = Fill(D->Complete.IsEmpty() ? TEXT("Thanks, {HeroName}.") : D->Complete);
			const FString Id = T.Task;      // CompleteTask changes the list
			CompleteTask(Id, FString());
			break;
		}
	}
	Page.Labels = { TEXT("Leave") }; Page.Actions = { TEXT("close") };
	if (!Who->Store.IsEmpty() && UCoHEnhancements::Of(GetOwner()))
	{
		Page.Labels.Insert(TEXT("Store"), 0); Page.Actions.Insert(TEXT("pstore|") + PersonId, 0);
	}
	Show(Page);
}

void UCoHStoryComponent::OnVillainDefeated(AActor* Hero, AActor* Villain)
{
	UCoHStoryComponent* Me = Of(Hero);
	const ACoHCombatEnemy* E = Cast<ACoHCombatEnemy>(Villain);
	FCoHStoryProgress* P = Me ? Me->Story() : nullptr;
	const UCoHStory* S = UCoHStory::Get(Hero);
	if (!P || !E || !S) return;
	bool bChanged = false;
	TArray<FString> Finished;
	for (FCoHTaskState& St : P->Tasks)
	{
		const FCoHStoryTask* T = S->Task(St.Task);
		if (!T || St.bComplete || T->Type != TEXT("killx")) continue;
		// the group (VillainType) and, if the task names one, the zone
		if (!T->KillGroup.IsEmpty() && !E->Faction.Equals(T->KillGroup, ESearchCase::IgnoreCase) && !E->Faction.Contains(T->KillGroup)) continue;
		if (!T->KillZone.IsEmpty() && T->KillZone != S->ZoneAt(Hero, E->GetActorLocation())) continue;
		St.Progress = FMath::Min(St.Progress + 1, St.Needed);
		Me->Refresh(St);
		bChanged = true;
		if (St.Progress >= St.Needed) Finished.Add(St.Task);
	}
	for (const FString& Id : Finished) { const FCoHStoryTask* T = S->Task(Id); Me->CompleteTask(Id, T ? T->Complete : FString()); }
	(void)bChanged;     // the record replicates by itself (property diff); saves come with completion
}

void UCoHStoryComponent::TickComponent(float Delta, ELevelTick TickType, FActorComponentTickFunction* ThisTick)
{
	Super::TickComponent(Delta, TickType, ThisTick);
	if (GetOwnerRole() != ROLE_Authority) return;
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now < NextVisitCheck) return;
	NextVisitCheck = Now + 1.0;
	FCoHStoryProgress* P = Story();
	const UCoHStory* S = UCoHStory::Get(this);
	if (!P || !S) return;
	// door missions carried over from the hero file (or a host restart): put their doors back
	if (ACoHStoryDirector* D = ACoHStoryDirector::Get(GetWorld()))
		for (FCoHTaskState& St : P->Tasks)
		{
			const FCoHStoryTask* T = S->Task(St.Task);
			if (T && !St.bComplete && T->Type == TEXT("mission") && !D->HasMission(this, St.Task)) St.Waypoint = D->OpenMission(this, St.Task);
		}
	// visit tasks: being there completes them
	TArray<FString> Reached;
	for (const FCoHTaskState& St : P->Tasks)
	{
		const FCoHStoryTask* T = S->Task(St.Task);
		if (T && !St.bComplete && T->Type == TEXT("visit") && !St.Waypoint.IsZero()
			&& FVector::Dist2D(St.Waypoint, GetOwner()->GetActorLocation()) < 1500.f) Reached.Add(St.Task);
	}
	for (const FString& Id : Reached) { const FCoHStoryTask* T = S->Task(Id); CompleteTask(Id, T ? T->Complete : FString()); }
}

// ------------------------------------------------------------------ test commands (host)
static FAutoConsoleCommandWithWorldAndArgs GCoHStoryTalkCommand(
	TEXT("coh.Story.Talk"),
	TEXT("Host only: talk to a contact from anywhere (part of its name, e.g. azuria). No name: lists contacts within 300 m."),
	FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
	{
		if (!World || World->GetNetMode() == NM_Client) return;
		APlayerController* PC = World->GetFirstPlayerController();
		UCoHStoryComponent* C = PC ? UCoHStoryComponent::Of(PC->GetPawn()) : nullptr;
		const UCoHStory* S = UCoHStory::Get(World);
		if (!C || !S) { UE_LOG(LogTemp, Warning, TEXT("coh.Story.Talk: no hero or no story data")); return; }
		const FVector Me = PC->GetPawn()->GetActorLocation();
		for (const auto& KV : S->Contacts)
		{
			if (Args.Num() == 0)
			{
				const float D = FVector::Dist2D(KV.Value.Pos, Me);
				if (D < 30000.f) UE_LOG(LogTemp, Log, TEXT("coh.Story: %s (%s) %d m, %d tasks"), *KV.Value.Name, *KV.Key, FMath::RoundToInt(D / 100.f), KV.Value.Tasks.Num());
				continue;
			}
			if (KV.Key.Contains(Args[0]) || KV.Value.Name.Contains(Args[0])) { C->TalkTo(KV.Key); return; }
		}
	}));

// Contacts, tasks and missions from the original game (docs/story.md).
//
//   UCoHStory           story_game.json (tools/story/story_game.py): every
//                       contact placed in the city's zones, its dialogue and
//                       the tasks it gives, story arcs, reward tables, mission
//                       doors and visit points
//   ACoHStoryDirector   host: stands contacts and other story NPCs in the
//                       world near players, and runs door missions
//   ACoHStoryNPC        a contact (or delivery target) standing in the world
//   ACoHMissionMarker   a mission door, a mission objective or a visit spot
//   UCoHStoryComponent  on each hero: talk (E), accept, turn in, task
//                       progress; the contact window and mission list on
//                       the player's own PC
//
// The host owns all story state; it lives in the hero record
// (FCoHHeroRecord::Story), so it replicates and saves with the hero.
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "GameFramework/Actor.h"
#include "Components/ActorComponent.h"
#include "CoHGameRules.h"
#include "CoHStory.generated.h"

class ACoHCombatEnemy;
class UCoHHeroProgress;
class SCoHStoryPanel;

struct FCoHStoryObjective { FString Name, Display, Begin, Done, Reward; int32 Number = 1; };
struct FCoHStorySpawn { FString Logical, Placement, Group, Villain, Display; int32 Count = 1; TArray<FString> Lines; };

struct FCoHStoryTask
{
	FString Id, Type, Intro, Accept, SendOff, Active, Busy, Title, Begin, Complete, Return;
	FString Reward, CompleteReward, Next, Arc;
	bool bAutoNext = false, bLong = false, bRequired = false, bNoReturn = false;
	int32 MinLevel = 1, MaxLevel = 54, ContactPoints = 0;
	// killx
	FString KillGroup, KillZone, KillWhat; int32 KillCount = 0;
	// deliver / visit
	FString DeliverNpc, DeliverContact, VisitLocation;
	// mission
	FString MapSet, MissionGroup, MissionZone, Door, Entry;
	int32 MapLength = 15;
	TArray<FString> CompleteWith;
	TArray<FCoHStoryObjective> Objectives;
	TArray<FCoHStorySpawn> Spawns;
};

struct FCoHStoryContact
{
	FString Id, Name, Profession, Description, Location, Zone, Model;
	FVector Pos = FVector::ZeroVector; float Yaw = 0.f;
	int32 MinLevel = 1, MaxLevel = 54, FriendCP = 10, ConfidantCP = 20, CompleteCP = 30;
	bool bTaskForce = false;
	TArray<FString> Hello;
	FString FirstVisit, DontKnow, NoTasks, Busy, ComeBack, ToFriend, ToConfidant;
	TArray<FString> Tasks, Arcs;
};

/** A story NPC who is not a contact (delivery targets and the like). */
struct FCoHStoryPerson { FString Id, Name, Zone, Model, Line; FVector Pos = FVector::ZeroVector; float Yaw = 0.f; };
struct FCoHStoryDoor { TArray<FString> Lair; FVector Pos = FVector::ZeroVector; float Yaw = 0.f; };
struct FCoHStoryArc { FString Name; int32 MinLevel = 1, MaxLevel = 54; TArray<FString> Episodes; };
struct FCoHStoryReward { int32 XP = 0, Influence = 0; TArray<TPair<float, TArray<FString>>> Drops; };

UCLASS(Config = Game)
class COHREBORN_API UCoHStory : public UGameInstanceSubsystem
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	static UCoHStory* Get(const UObject* WorldContext);

	/** <out>/story/story_game.json; default: next to the rules folder. */
	UPROPERTY(Config) FString StoryFile;

	bool IsLoaded() const { return Contacts.Num() > 0; }
	const FCoHStoryContact* Contact(const FString& Id) const { return Contacts.Find(Id); }
	const FCoHStoryTask* Task(const FString& Id) const { return Tasks.Find(Id); }
	const FCoHStoryPerson* Person(const FString& Id) const { return People.Find(Id); }
	const FCoHStoryArc* Arc(const FString& Id) const { return Arcs.Find(Id); }
	/** The task before this one in an arc (empty: first). */
	FString Previous(const FString& TaskId) const { const FString* P = Prev.Find(TaskId); return P ? *P : FString(); }
	/** Reward table at a level (1-based): XP and influence always given. */
	FCoHStoryReward Reward(const FString& Table, int32 Level) const;
	/** Zone id at a world position (one-world map), or empty. */
	FString ZoneAt(const UObject* WorldContext, const FVector& Pos) const;
	/** A mission door for a task: in its zone (or the contact's), matching its door type. */
	bool PickDoor(const FCoHStoryTask& T, const FString& FallbackZone, const FVector& Near, FCoHStoryDoor& Out) const;
	/** A visit-location marker by name, in any zone. */
	bool VisitPoint(const FString& Name, FVector& Out) const;

	TMap<FString, FCoHStoryContact> Contacts;
	TMap<FString, FCoHStoryPerson> People;
	TMap<FString, FCoHStoryTask> Tasks;
	TMap<FString, FCoHStoryArc> Arcs;
	TMap<FString, TArray<FCoHStoryDoor>> Doors;
	TMap<FString, TArray<TPair<FString, FVector>>> Visits;
	TMap<FString, TMap<int32, FCoHStoryReward>> Rewards;
private:
	TMap<FString, FString> Prev;
};

/** A dialogue page the host sends to one player's contact window. */
USTRUCT(BlueprintType)
struct FCoHDialogPage
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly) FString Title;
	UPROPERTY(BlueprintReadOnly) FString Body;
	/** Buttons: label and the action sent back (accept|<task>|<contact> ...). */
	UPROPERTY(BlueprintReadOnly) TArray<FString> Labels;
	UPROPERTY(BlueprintReadOnly) TArray<FString> Actions;
};

/** A contact or story NPC standing in the world. */
UCLASS()
class COHREBORN_API ACoHStoryNPC : public AActor
{
	GENERATED_BODY()
public:
	ACoHStoryNPC();
	/** Contact id (bContact) or person id. */
	UPROPERTY(ReplicatedUsing = OnRep_Look, BlueprintReadOnly, Category = "CoH|Story") FString Key;
	UPROPERTY(ReplicatedUsing = OnRep_Look, BlueprintReadOnly, Category = "CoH|Story") FString DisplayName;
	UPROPERTY(ReplicatedUsing = OnRep_Look, BlueprintReadOnly, Category = "CoH|Story") FString Model;
	UPROPERTY(Replicated, BlueprintReadOnly, Category = "CoH|Story") bool bContact = true;
	UPROPERTY(VisibleAnywhere, Category = "CoH|Story") TObjectPtr<class USkeletalMeshComponent> Mesh;
	UPROPERTY(VisibleAnywhere, Category = "CoH|Story") TObjectPtr<class UStaticMeshComponent> Stand;
	UPROPERTY(VisibleAnywhere, Category = "CoH|Story") TObjectPtr<class UTextRenderComponent> Label;
	/** Mesh turn for the CoH bodies (as the hero's). */
	UPROPERTY(EditAnywhere, Category = "CoH|Story") float MeshYaw = -90.f;
	void ApplyLook();
	virtual void Tick(float Delta) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const override;
private:
	UFUNCTION() void OnRep_Look();
	bool bLookApplied = false;
};

UENUM()
enum class ECoHMarkerKind : uint8 { Door, Objective, Visit };

/** A glowing marker only its hero sees: a mission door, an objective to click, a place to visit. */
UCLASS()
class COHREBORN_API ACoHMissionMarker : public AActor
{
	GENERATED_BODY()
public:
	ACoHMissionMarker();
	UPROPERTY(ReplicatedUsing = OnRep_Marker) ECoHMarkerKind Kind = ECoHMarkerKind::Door;
	UPROPERTY(ReplicatedUsing = OnRep_Marker) FString Text;
	UPROPERTY(ReplicatedUsing = OnRep_Marker) TObjectPtr<APawn> ForHero;
	/** Host: the task it belongs to and, for objectives, which. */
	FString Task;
	int32 Objective = INDEX_NONE;
	UPROPERTY(VisibleAnywhere) TObjectPtr<class UStaticMeshComponent> Beam;
	UPROPERTY(VisibleAnywhere) TObjectPtr<class UTextRenderComponent> Label;
	virtual void Tick(float Delta) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const override;
	UFUNCTION() void OnRep_Marker();
};

/** Host only: keeps story NPCs standing near players and runs door missions. */
UCLASS(Config = Game)
class COHREBORN_API ACoHStoryDirector : public AActor
{
	GENERATED_BODY()
public:
	ACoHStoryDirector();
	virtual void BeginPlay() override;
	virtual void Tick(float Delta) override;
	static ACoHStoryDirector* Get(const UWorld* World);

	/** NPCs stand when a player is this close (cm) and go past LeaveDistance. */
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Story") float StandDistance = 12000.f;
	UPROPERTY(EditAnywhere, Config, Category = "CoH|Story") float LeaveDistance = 20000.f;

	/** Places a task's mission door for a hero; returns where (zero: none). */
	FVector OpenMission(class UCoHStoryComponent* For, const FString& TaskId);
	/** The hero went in at the door. Until the mission maps are in, the
	 *  mission plays out at the door: its villains, boss and objectives. */
	void EnterMission(class UCoHStoryComponent* For, const FString& TaskId);
	/** The hero clicked an objective. */
	void UseObjective(class UCoHStoryComponent* For, ACoHMissionMarker* Marker);
	/** Removes a hero's mission (abandoned, finished, or the hero left). */
	void CloseMission(class UCoHStoryComponent* For, const FString& TaskId);
	bool HasMission(const class UCoHStoryComponent* For, const FString& TaskId) const
	{
		return Missions.ContainsByPredicate([&](const FMission& M) { return M.Hero.Get() == For && M.Task == TaskId; });
	}
	ACoHStoryNPC* NPCFor(const FString& Key) const { const TWeakObjectPtr<ACoHStoryNPC>* N = NPCs.Find(Key); return N ? N->Get() : nullptr; }
	/** Where a story NPC stands (spawned, else its data position). */
	bool WhereIs(const FString& Key, FVector& Out) const;
private:
	struct FMission
	{
		FString Task;
		TWeakObjectPtr<class UCoHStoryComponent> Hero;
		FVector Door = FVector::ZeroVector;
		TWeakObjectPtr<ACoHMissionMarker> DoorMarker;
		TArray<TWeakObjectPtr<ACoHCombatEnemy>> Foes;
		TWeakObjectPtr<ACoHCombatEnemy> Boss;
		TArray<TWeakObjectPtr<ACoHMissionMarker>> Objectives;
		int32 ObjectivesLeft = 0;
		bool bEntered = false;
	};
	TArray<FMission> Missions;
	TMap<FString, TWeakObjectPtr<ACoHStoryNPC>> NPCs;
	double NextStream = 0;
	int32 NextGroupId = 900000;
	void Stream();
	bool Ground(const FVector& Near, FVector& Out) const;
	bool RandomSpot(const FVector& Center, float Radius, FVector& Out) const;
	ACoHMissionMarker* SpawnMarker(ECoHMarkerKind Kind, const FVector& At, APawn* For, const FString& Text, const FString& Task);
	FMission* Find(class UCoHStoryComponent* For, const FString& TaskId);
	void CheckMission(FMission& M);
};

/** On each hero: talks to contacts, carries tasks; the contact window on the player's PC. */
UCLASS(ClassGroup = CoH, meta = (BlueprintSpawnableComponent))
class COHREBORN_API UCoHStoryComponent : public UActorComponent
{
	GENERATED_BODY()
public:
	UCoHStoryComponent();
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void TickComponent(float Delta, ELevelTick TickType, FActorComponentTickFunction* ThisTick) override;
	static UCoHStoryComponent* Of(const AActor* A);

	/** E: talk to the contact, use the door or objective in front of the hero. */
	UFUNCTION(BlueprintCallable, Category = "CoH|Story") void Interact();
	UFUNCTION(Server, Reliable) void ServerInteract();
	/** A button of the contact window. */
	UFUNCTION(Server, Reliable) void ServerChoose(const FString& Action);
	UFUNCTION(Client, Reliable) void ClientShowPage(const FCoHDialogPage& Page);
	/** The contact window closed on the player's PC. */
	void ClosePage();

	/** Host: a villain the hero helped defeat (defeat-X tasks). */
	static void OnVillainDefeated(AActor* Hero, AActor* Villain);
	/** Host: a task part is done (mission cleared, item delivered, place visited). */
	void CompleteTask(const FString& TaskId, const FString& Message);
	/** Host: tasks of the hero (the record's story). */
	FCoHStoryProgress* Story() const;
	UCoHHeroProgress* Progress() const;
	FString HeroName() const;
	int32 HeroLevel() const;
	/** {HeroName}, {Level}... filled in; leftover {VARS} lose their braces. */
	FString Fill(const FString& Text, const FCoHStoryContact* C = nullptr) const;
	/** Console: coh.Story.Give <task id> (tests), coh.Story.Contact <id> (talk from anywhere). */
	void TalkTo(const FString& ContactId);
	void Accept(const FString& TaskId, const FString& ContactId);

private:
	void Show(const FCoHDialogPage& Page);
	void TalkToPerson(const FString& PersonId);
	void ShowTask(const FString& TaskId, const FString& ContactId);
	void TurnIn(const FString& TaskId);
	void Abandon(const FString& TaskId);
	void Save();
	void Refresh(FCoHTaskState& S) const;
	FCoHContactState& ContactState(const FString& Id);
	TArray<FString> Offers(const FCoHStoryContact& C) const;
	bool Available(const FCoHStoryTask& T) const;
	void GiveReward(const FString& Table);
	void Say(const FString& Text, FLinearColor Colour = FLinearColor(1.f, 0.9f, 0.5f)) const;
	FString LastContact;
	double NextVisitCheck = 0;
	// the player's own PC
	TSharedPtr<SCoHStoryPanel> Panel;
	TSharedPtr<class SWidget> PanelHost;
};

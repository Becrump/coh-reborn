// Badges from the original game (docs/badges.md).
//
// badges_game.json (tools/badges/badges_game.py): exploration and history badges
// (markers in the zones), defeat, accomplishment and achievement badges, each
// with the original's postfix requirement ("kills.Hellions 100 >=",
// "visits.AtlasPark1", "level char> 20 >=", "X owned? Y owned? &&"...).
// The host counts each hero's stats (kills by group, rank and villain, visits,
// level) in the hero record (FCoHHeroRecord::Badges), checks the requirements
// when a stat changes, and awards the badge.
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "CoHBadges.generated.h"

struct FCoHBadgeDef
{
	FString Id, Category, Title, Text, Icon;
	TArray<FString> Requires;
};

struct FCoHBadgeSpot { FString Name; FVector Pos = FVector::ZeroVector; };

UCLASS(Config = Game)
class COHREBORN_API UCoHBadges : public UGameInstanceSubsystem, public FTickableGameObject
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	static UCoHBadges* Get(const UObject* WorldContext);
	/** <out>/badges/badges_game.json; default: next to the rules folder. */
	UPROPERTY(Config) FString BadgesFile;
	/** How near a hero must come to an exploration marker or plaque (cm). */
	UPROPERTY(Config) float VisitRadius = 1500.f;

	/** Host: add to one of the hero's stats (lower-cased) and award any badge it completes. */
	static void AddStat(AActor* Hero, const FString& Key, int32 Amount = 1);
	/** Host: a villain the hero helped defeat (kills.<group>, kills.<group>.<rank>, kills.<villain>). */
	static void OnDefeat(AActor* Hero, const FString& Group, const FString& Rank, const FString& Villain);
	/** Host: a reward token the story gives ("SynapseTF" when Synapse's task force is done): the
	 *  badge of that name when there is one, else kept as the stat token.<id>. */
	static void Grant(AActor* Hero, const FString& Id);
	/** Host: check every badge the hero lacks (after a level-up and the like). */
	void Check(AActor* Hero) const;
	/** "12 badges: Title, Title..." for /badges. */
	FString Describe(const AActor* Hero) const;

	TArray<FCoHBadgeDef> Badges;
	TArray<FCoHBadgeSpot> Spots;

	// FTickableGameObject: the host watches heroes walk past markers
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UCoHBadges, STATGROUP_Tickables); }
	virtual bool IsTickable() const override { return Spots.Num() > 0 && !IsTemplate(); }
	virtual ETickableTickType GetTickableTickType() const override { return ETickableTickType::Conditional; }
private:
	float NextVisitCheck = 0.f;
	bool Eval(const FCoHBadgeDef& B, const struct FCoHHeroRecord& Hero) const;
};

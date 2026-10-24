// A hero built and levelled by the original rules (docs/hero-build.md,
// docs/leveling.md): the hero file (format 2) names the archetype, sets,
// picks and the player-body preset; XP, influence and defeat debt follow the
// original reward rules; level-ups wait for training (L, as at a trainer)
// and open the level's power pick (P lists only what the pick may take).
// The server owns the record; clients get it by replication.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "CoHGameRules.h"
#include "CoHHeroProgress.generated.h"

class UCoHPowerComponent;

UCLASS(ClassGroup = CoH, meta = (BlueprintSpawnableComponent))
class COHREBORN_API UCoHHeroProgress : public UActorComponent
{
	GENERATED_BODY()
public:
	UCoHHeroProgress();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Replicated, Category = "CoH|Hero") FCoHHeroRecord Hero;
	/** Where the record is saved (in the rules' HeroesDir); empty: never saved. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CoH|Hero") FString SaveFile;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Replicated, Category = "CoH|Hero") bool bHasRecord = false;

	/** Server: load a hero file and grant its powers. */
	UFUNCTION(BlueprintCallable, Category = "CoH|Hero") bool LoadHeroFile(const FString& File);
	/** Server: make the record current on the power component (class, level, powers, tray). */
	void Apply(bool bRefillTray);

	/** XP level reached (the hero may train up to it). */
	UFUNCTION(BlueprintPure, Category = "CoH|Hero") int32 XPLevel() const;
	UFUNCTION(BlueprintPure, Category = "CoH|Hero") bool CanTrain() const { return bHasRecord && XPLevel() > Hero.Level; }
	/** Power picks open now (picks allowed at this level minus picks made). */
	UFUNCTION(BlueprintPure, Category = "CoH|Hero") int32 PicksOpen() const;
	/** XP into this level and needed for the next, for the bar. */
	void XPBar(int32& Into, int32& Span) const;
	/** What the open pick may take (computed on the client too). */
	TArray<FName> Options() const;

	/** Server: an award from a defeat (debt takes its half first). */
	void Award(int32 XP, int32 Influence);
	/** Server: defeated by villains: add debt. */
	void OnDefeatedByVillains();
	/** Server: a drop: an inspiration goes to the tray if there is room. */
	void AddInspiration(FName Inspiration);

	UFUNCTION(BlueprintCallable, Category = "CoH|Hero") void Train();
	UFUNCTION(BlueprintCallable, Category = "CoH|Hero") void Pick(FName Power);
	UFUNCTION(BlueprintCallable, Category = "CoH|Hero") void UseInspiration(int32 Index);
	UFUNCTION(Server, Reliable) void ServerTrain();
	UFUNCTION(Server, Reliable) void ServerPick(FName Power);
	UFUNCTION(Server, Reliable) void ServerUseInspiration(int32 Index);

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const override;
	static UCoHHeroProgress* Of(const AActor* A);
	/** Server: a villain was defeated: XP and influence to the heroes who
	 *  fought it, by their share of the damage (each hero is its own team
	 *  until teams exist), and a drop roll for the top damage dealer. */
	static void RewardDefeat(UCoHPowerComponent* Victim, const FString& Rank, const FString& Group);

private:
	UCoHPowerComponent* Powers() const;
	void Say(const FString& Text, FLinearColor Colour) const;
	void Save() const;
};

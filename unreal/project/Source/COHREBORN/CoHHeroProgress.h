// A hero built and levelled by the original rules (docs/hero-build.md,
// docs/leveling.md): the hero file (format 2) names the archetype, sets,
// picks and the player-body preset; XP, influence and defeat debt follow the
// original reward rules; level-ups wait for training (L, as at a trainer)
// and open the level's power pick (P lists only what the pick may take).
// The server owns the record; clients get it by replication.
// Saves live on each player's own PC (Saved/Heroes/<name>.json): the player
// sends the hero to the host on joining, and the host sends every save back
// (and keeps a backup in its own Saved/HeroBackups).
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

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, ReplicatedUsing = OnRep_Hero, Category = "CoH|Hero") FCoHHeroRecord Hero;
	/** The owning player's PC: the hero file in Saved/Heroes the host's saves go to; empty: never saved. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CoH|Hero") FString SaveFile;
	/** Host: the player's hero file name (sent on joining); names the host's backup folder. */
	UPROPERTY(Transient) FString BackupName;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Replicated, Category = "CoH|Hero") bool bHasRecord = false;

	/** Server: load a hero file and grant its powers. */
	UFUNCTION(BlueprintCallable, Category = "CoH|Hero") bool LoadHeroFile(const FString& File);
	/** Server: take this record as the hero and grant its powers. */
	void LoadHeroRecord(const FCoHHeroRecord& Record);
	/** Where a player's own heroes are kept on their PC. */
	static FString LocalHeroDir();
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
	/** Writes the hero file now (the customize panel calls it when it closes, so powers keep their look). */
	UFUNCTION(BlueprintCallable, Category = "CoH|Hero") void SaveLooks();
	UFUNCTION(BlueprintCallable, Category = "CoH|Hero") void UseInspiration(int32 Index);
	UFUNCTION(Server, Reliable) void ServerTrain();
	UFUNCTION(Server, Reliable) void ServerPick(FName Power);
	UFUNCTION(Server, Reliable) void ServerUseInspiration(int32 Index);
	/** The customize panel closed on a player's PC: the host takes the looks, saves, and everyone sees them. */
	UFUNCTION(Server, Reliable) void ServerSetLooks(const TArray<FCoHPowerLook>& Looks);
	/** The host saved: write the hero file on the owning player's PC. */
	UFUNCTION(Client, Reliable) void ClientSaveHero(const FString& Json);

	/** Host: writes the hero to the owning player's PC (ClientSaveHero) and the host's backup. */
	void Save();
	/** A player's own PC: writes its copy of the hero (replicated from the host) to Saved/Heroes. */
	void SaveLocal();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const override;
	static UCoHHeroProgress* Of(const AActor* A);
	/** Server: a villain was defeated: XP and influence to the heroes who
	 *  fought it, by their share of the damage (each hero is its own team
	 *  until teams exist), and a drop roll for the top damage dealer. */
	static void RewardDefeat(UCoHPowerComponent* Victim, const FString& Rank, const FString& Group);

private:
	UCoHPowerComponent* Powers() const;
	void Say(const FString& Text, FLinearColor Colour) const;
	UFUNCTION() void OnRep_Hero();
	/** The power component's styles as saved looks, and back. */
	TArray<FCoHPowerLook> LooksFromStyles() const;
	void ApplyLooks(const TArray<FCoHPowerLook>& Looks);
};

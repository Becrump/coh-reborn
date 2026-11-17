// Enhancements, slots and stores from the original game (docs/enhancements.md).
//
//   UCoHItems          items_game.json (tools/items/items_game.py): the Training,
//                      Dual and Single Origin enhancements, what each store sells,
//                      the levels new slots come at
//   UCoHEnhancements   on each hero: slots, slotting, the enhancement tray, buying
//                      and selling at stores, drops; the Enhancements window (N)
//                      and the store window on the player's own PC
//
// The host owns the state; it lives in the hero record (FCoHHeroRecord::Boosts),
// so it replicates and saves with the hero. Slotted enhancements change the
// hero's powers through UCoHPowerComponent::SetBoosts (accuracy, damage,
// recharge, endurance, range, durations...), with the original's diminishing
// returns past +70% (schedule A) / +40% (schedule B).
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Components/ActorComponent.h"
#include "CoHGameRules.h"
#include "CoHItems.generated.h"

class SCoHEnhPanel;
class UCoHHeroProgress;
class UCoHPowerComponent;
struct FCoHPowerDef;

struct FCoHBoostDef
{
	FString Id, Name, Grade, Type, Icon, Help;   // Grade TO / DO / SO; Type kDamage_Boost...
	TArray<FString> Origins, Attribs;
	float Scale = 0.f;
	bool bScheduleB = false;
	/** "Dmg", "Acc"... for the slot buttons */
	FString Short() const;
};
struct FCoHStoreItem { FString Boost; int32 Level = 1, Price = 0; };

UCLASS(Config = Game)
class COHREBORN_API UCoHItems : public UGameInstanceSubsystem
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	static UCoHItems* Get(const UObject* WorldContext);
	/** <out>/items/items_game.json; default: next to the rules folder. */
	UPROPERTY(Config) FString ItemsFile;

	const FCoHBoostDef* Boost(const FString& Id) const { return Boosts.Find(Id); }
	/** Slots a hero of this level may have added in all (beyond each power's first). */
	int32 SlotsAt(int32 Level) const;
	/** "Generic_Damage@15" -> id, level. */
	static bool Split(const FString& Item, FString& Id, int32& Level);
	/** The boost's strength at its level for a hero of this level (before diminishing returns). */
	float Strength(const FCoHBoostDef& B, int32 EnhLevel, int32 HeroLevel) const;
	/** The original's enhancement diversification: full to 70% (B: 40%), then less and less. */
	static float Diminish(float Total, bool bScheduleB);
	/** Can this power take this enhancement (type, and origin for DO/SO)? */
	bool Fits(const FCoHBoostDef& B, const FCoHPowerDef& P, const FString& Origin) const;
	/** A dropped enhancement for a hero: grade by level, of the hero's origin, at about the hero's level. */
	FString RandomDrop(const FString& Origin, int32 Level) const;
	/** Influence a store pays for one. */
	int32 SellPrice(const FString& Item) const;
	/** A label for an item ("Single Origin: Damage 25"). */
	FString Label(const FString& Item) const;

	TMap<FString, FCoHBoostDef> Boosts;
	TMap<FString, TArray<FCoHStoreItem>> Stores;
	TArray<int32> SlotLevels;
	TArray<float> Above, Below;
};

UCLASS(ClassGroup = CoH, meta = (BlueprintSpawnableComponent))
class COHREBORN_API UCoHEnhancements : public UActorComponent
{
	GENERATED_BODY()
public:
	UCoHEnhancements();
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	static UCoHEnhancements* Of(const AActor* A);

	/** Enhancement tray size. */
	UPROPERTY(EditAnywhere, Category = "CoH|Enhancements") int32 TraySize = 10;

	/** Host: an enhancement for the hero (drop, reward); false when the tray is full. */
	bool Give(const FString& Item, bool bSay = true);
	/** Host: open a store window on the hero's PC (stores of a store NPC or contact). */
	void OpenStore(const TArray<FString>& StoreIds, const FString& Title);
	/** Host: a defeated villain may drop an enhancement (as the original). */
	static void OnVillainDefeated(AActor* Hero, int32 VillainLevel);

	UFUNCTION(Server, Reliable) void ServerAddSlot(FName Power);
	UFUNCTION(Server, Reliable) void ServerSlot(int32 TrayIndex, FName Power, int32 SlotIndex);
	UFUNCTION(Server, Reliable) void ServerTrash(int32 TrayIndex);
	UFUNCTION(Server, Reliable) void ServerBuy(int32 Row);
	UFUNCTION(Server, Reliable) void ServerSell(int32 TrayIndex);
	UFUNCTION(Client, Reliable) void ClientShowStore(const FString& Title, const TArray<FString>& Rows);

	/** The player's own PC: the Enhancements window. */
	void TogglePanel();
	// for the window
	const FCoHBoostState* State() const;
	UCoHHeroProgress* Progress() const;
	UCoHPowerComponent* Powers() const;
	int32 SlotsLeft() const;
	FString StoreTitle;
	TArray<FString> StoreRows;   // "<boost>@<level>@<price>"
private:
	FCoHBoostState* MutableState() const;
	void Changed();
	/** host: store rows open for this hero (validated on buy) */
	TArray<FString> OpenRows;
	TSharedPtr<SCoHEnhPanel> Panel;
	TSharedPtr<class SWidget> PanelHost;
};

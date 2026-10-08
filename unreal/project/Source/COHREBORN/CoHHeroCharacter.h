#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "CoHHeroCharacter.generated.h"

class UCameraComponent;
class USpringArmComponent;
class UInputAction;
class UInputMappingContext;
struct FInputActionValue;

/**
 * Playable hero for testing the zone: third-person camera, run, sprint and
 * jump. Input is built in code (Enhanced Input objects created at startup),
 * so it needs no input assets. Mesh and animation blueprint come from
 * DefaultGame.ini ([/Script/COHREBORN.CoHHeroCharacter]) or the details
 * panel, e.g. the retargeted Iron Vanguard and ABP_Unarmed.
 */
UCLASS(Config = Game)
class COHREBORN_API ACoHHeroCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	ACoHHeroCharacter();

	UPROPERTY(Config, EditAnywhere, Category = "CoH|Hero")
	FSoftObjectPath HeroMesh;

	UPROPERTY(Config, EditAnywhere, Category = "CoH|Hero")
	FSoftClassPath HeroAnimClass;

	/** Turn of the mesh so it faces the capsule's forward (+X): -90 for the
	 *  UE mannequin, 90 for Meshy exports. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Hero")
	float MeshYaw = -90.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Hero")
	float RunSpeed = 600.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Hero")
	float SprintSpeed = 1100.f;

	/** Super Jump (F toggles): jump launch speed, run speed, air control. */
	UPROPERTY(EditAnywhere, Category = "CoH|Travel")
	float SuperJumpVelocity = 2400.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Travel")
	float SuperJumpRunSpeed = 900.f;

	UPROPERTY(EditAnywhere, Category = "CoH|Travel")
	float ClimbSpeed = 350.f;

	/** Brawl combo (left mouse): animations played in order. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Brawl")
	TArray<FSoftObjectPath> PunchAnims;

	/** Climbing clips (up, down, left, right), played while on a wall. */
	UPROPERTY(Config, EditAnywhere, Category = "CoH|Travel")
	TArray<FSoftObjectPath> ClimbAnims;

	virtual void Tick(float DeltaSeconds) override;
	virtual void Jump() override;

protected:
	virtual void BeginPlay() override;
	virtual void SetupPlayerInputComponent(UInputComponent* Input) override;

private:
	void Move(const FInputActionValue& Value);
	void Look(const FInputActionValue& Value);
	void SprintOn(const FInputActionValue& Value);
	void SprintOff(const FInputActionValue& Value);
	void ToggleSuperJump(const FInputActionValue& Value);
	void LetGo(const FInputActionValue& Value);
	void Punch(const FInputActionValue& Value);
	void Zoom(const FInputActionValue& Value);
	void UpdateCamera(float DeltaSeconds);
	void EndPunch();
	void RestoreLocomotion();
	void UpdateClimbAnim();
	void ApplyMovementMode();
	bool TraceWall(FHitResult& Hit, float Height, float Reach) const;
	void StartClimb(const FVector& Normal);
	void StopClimb();

	bool bSuperJump = false;
	bool bSprint = false;
	bool bClimbing = false;
	FVector WallNormal = FVector::ZeroVector;
	FVector2D MoveInput = FVector2D::ZeroVector;
	float ClimbCooldown = 0.f;
	int32 ComboStep = 0;
	float PunchTimeLeft = 0.f;      // > 0 while a punch plays
	float ComboWindow = 0.f;        // time left to chain the next punch
	bool bQueuedPunch = false;
	int32 ClimbClip = -1;
	float ZoomTarget = 450.f;       // camera distance; 0 = first person
	bool bFirstPerson = false;
	UPROPERTY(Transient)
	TObjectPtr<UClass> LocomotionAnimClass;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<USpringArmComponent> Boom;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(Transient)
	TObjectPtr<UInputMappingContext> Mapping;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> MoveAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LookAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> JumpAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SprintAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SuperJumpAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LetGoAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> PunchAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ZoomAction;
};

/** Game mode that plays as the CoH hero. */
UCLASS()
class COHREBORN_API ACoHGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ACoHGameMode();
};

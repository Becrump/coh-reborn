#include "CoHHeroCharacter.h"
#include "CoHCombat.h"
#include "CoHGraphicsMenu.h"
#include "RebornMonorail.h"
#include "GameFramework/PlayerStart.h"
#include "Kismet/GameplayStatics.h"
#include "EngineUtils.h"
#include "NavigationInvokerComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Engine/Engine.h"

#include "Animation/AnimSequenceBase.h"
#include "CoHLifeManager.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "Engine/LocalPlayer.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"

ACoHHeroCharacter::ACoHHeroCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	GetCapsuleComponent()->InitCapsuleSize(42.f, 96.f);
	bUseControllerRotationYaw = false;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;

	UCharacterMovementComponent* MoveComp = GetCharacterMovement();
	MoveComp->bOrientRotationToMovement = true;
	MoveComp->RotationRate = FRotator(0.f, 540.f, 0.f);
	MoveComp->MaxWalkSpeed = RunSpeed;
	MoveComp->JumpZVelocity = 900.f;       // heroic hop; Super Jump comes later
	MoveComp->AirControl = 0.4f;

	// the mesh's feet sit at the capsule bottom, facing +X
	GetMesh()->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -96.f), FRotator(0.f, -90.f, 0.f));

	Boom = CreateDefaultSubobject<USpringArmComponent>(TEXT("Boom"));
	Boom->SetupAttachment(RootComponent);
	Boom->TargetArmLength = 450.f;
	Boom->SocketOffset = FVector(0.f, 60.f, 80.f);
	Boom->bUsePawnControlRotation = true;
	Boom->bEnableCameraLag = true;
	Boom->CameraLagSpeed = 12.f;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(Boom, USpringArmComponent::SocketName);
	Camera->bUsePawnControlRotation = false;
}

void ACoHHeroCharacter::BeginPlay()
{
	if (USkeletalMesh* HeroAsset = Cast<USkeletalMesh>(HeroMesh.TryLoad()))
	{
		GetMesh()->SetSkeletalMeshAsset(HeroAsset);
		GetMesh()->SetRelativeRotation(FRotator(0.f, MeshYaw, 0.f));
		if (UClass* Anim = HeroAnimClass.TryLoadClass<UAnimInstance>())
		{
			GetMesh()->SetAnimInstanceClass(Anim);
			LocomotionAnimClass = Anim;
		}
	}
	Super::BeginPlay();
 Health = MaxHealth;
 RespawnLocation = GetActorLocation();
 auto* Invoker = NewObject<UNavigationInvokerComponent>(this);
 Invoker->SetGenerationRadii(3500.f, 5000.f);
 Invoker->RegisterComponent();
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (UEnhancedInputLocalPlayerSubsystem* Sub =
				ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
		{
			if (Mapping)
			{
				Sub->AddMappingContext(Mapping, 0);
			}
		}
	}
}

void ACoHHeroCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
	Super::SetupPlayerInputComponent(Input);
	Input->BindKey(EKeys::F10, IE_Pressed, this, &ACoHHeroCharacter::ToggleGraphicsMenu);

	// input assets built here so the project needs none
	Mapping = NewObject<UInputMappingContext>(this);
	MoveAction = NewObject<UInputAction>(this);
	MoveAction->ValueType = EInputActionValueType::Axis2D;
	LookAction = NewObject<UInputAction>(this);
	LookAction->ValueType = EInputActionValueType::Axis2D;
	JumpAction = NewObject<UInputAction>(this);
	SprintAction = NewObject<UInputAction>(this);
	SuperJumpAction = NewObject<UInputAction>(this);
 FlightAction = NewObject<UInputAction>(this);
 SuperSpeedAction = NewObject<UInputAction>(this);
 FlyDownAction = NewObject<UInputAction>(this);
	LetGoAction = NewObject<UInputAction>(this);
	PunchAction = NewObject<UInputAction>(this);
 UppercutAction = NewObject<UInputAction>(this);
	ZoomAction = NewObject<UInputAction>(this);
	ZoomAction->ValueType = EInputActionValueType::Axis1D;

	// WASD -> (x = right, y = forward)
	auto MapKey = [this](const FKey& Key, bool bSwizzle, bool bNegate)
	{
		FEnhancedActionKeyMapping& M = Mapping->MapKey(MoveAction, Key);
		if (bSwizzle)
		{
			M.Modifiers.Add(NewObject<UInputModifierSwizzleAxis>(Mapping));
		}
		if (bNegate)
		{
			M.Modifiers.Add(NewObject<UInputModifierNegate>(Mapping));
		}
	};
	MapKey(EKeys::W, true, false);
	MapKey(EKeys::S, true, true);
	MapKey(EKeys::D, false, false);
	MapKey(EKeys::A, false, true);
	FEnhancedActionKeyMapping& Mouse = Mapping->MapKey(LookAction, EKeys::Mouse2D);
	UInputModifierNegate* InvertY = NewObject<UInputModifierNegate>(Mapping);
	InvertY->bX = false;
	InvertY->bZ = false;
	Mouse.Modifiers.Add(InvertY);
	Mapping->MapKey(JumpAction, EKeys::SpaceBar);
	Mapping->MapKey(SprintAction, EKeys::LeftShift);
	Mapping->MapKey(SuperJumpAction, EKeys::F);
 Mapping->MapKey(FlightAction, EKeys::G);
 Mapping->MapKey(SuperSpeedAction, EKeys::R);
 Mapping->MapKey(FlyDownAction, EKeys::LeftControl);
	Mapping->MapKey(LetGoAction, EKeys::C);
	Mapping->MapKey(PunchAction, EKeys::LeftMouseButton);
 Mapping->MapKey(UppercutAction, EKeys::Q);
	Mapping->MapKey(ZoomAction, EKeys::MouseWheelAxis);

	if (UEnhancedInputComponent* EI = Cast<UEnhancedInputComponent>(Input))
	{
		EI->BindAction(MoveAction, ETriggerEvent::Triggered, this, &ACoHHeroCharacter::Move);
		EI->BindAction(LookAction, ETriggerEvent::Triggered, this, &ACoHHeroCharacter::Look);
		EI->BindAction(JumpAction, ETriggerEvent::Started, this, &ACoHHeroCharacter::Jump);
 EI->BindAction(JumpAction, ETriggerEvent::Triggered, this, &ACoHHeroCharacter::FlyUp);
 EI->BindAction(FlyDownAction, ETriggerEvent::Triggered, this, &ACoHHeroCharacter::FlyDown);
 EI->BindAction(FlightAction, ETriggerEvent::Started, this, &ACoHHeroCharacter::ToggleFlight);
 EI->BindAction(SuperSpeedAction, ETriggerEvent::Started, this, &ACoHHeroCharacter::ToggleSuperSpeed);
		EI->BindAction(JumpAction, ETriggerEvent::Completed, this, &ACharacter::StopJumping);
		EI->BindAction(SprintAction, ETriggerEvent::Started, this, &ACoHHeroCharacter::SprintOn);
		EI->BindAction(SprintAction, ETriggerEvent::Completed, this, &ACoHHeroCharacter::SprintOff);
		EI->BindAction(SuperJumpAction, ETriggerEvent::Started, this, &ACoHHeroCharacter::ToggleSuperJump);
		EI->BindAction(LetGoAction, ETriggerEvent::Started, this, &ACoHHeroCharacter::LetGo);
		EI->BindAction(PunchAction, ETriggerEvent::Started, this, &ACoHHeroCharacter::Punch);
 EI->BindAction(UppercutAction, ETriggerEvent::Started, this, &ACoHHeroCharacter::UppercutInput);
		EI->BindAction(ZoomAction, ETriggerEvent::Triggered, this, &ACoHHeroCharacter::Zoom);
		EI->BindAction(MoveAction, ETriggerEvent::Completed, this, &ACoHHeroCharacter::Move);
	}
}

void ACoHHeroCharacter::ToggleGraphicsMenu()
{
    if (!GraphicsMenu) GraphicsMenu = NewObject<UCoHGraphicsMenu>(this);
    GraphicsMenu->Toggle(Cast<APlayerController>(GetController()));
}

void ACoHHeroCharacter::EndPlay(const EEndPlayReason::Type Reason)
{
    if (GraphicsMenu) GraphicsMenu->Close();
    Super::EndPlay(Reason);
}

void ACoHHeroCharacter::Move(const FInputActionValue& Value)
{
	const FVector2D V = Value.Get<FVector2D>();
	MoveInput = V;
	if (!Controller)
	{
		return;
	}
	if (bClimbing)
	{
		// on a wall: forward/back = up/down, left/right = along the wall
		const FVector Right = FVector::CrossProduct(FVector::UpVector, WallNormal).GetSafeNormal();
		AddMovementInput(FVector::UpVector, V.Y);
		AddMovementInput(-Right, V.X);
		return;
	}
	const FRotator Yaw(0.f, Controller->GetControlRotation().Yaw, 0.f);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), V.Y);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), V.X);
}

void ACoHHeroCharacter::Look(const FInputActionValue& Value)
{
	const FVector2D V = Value.Get<FVector2D>();
	AddControllerYawInput(V.X);
	AddControllerPitchInput(V.Y);
}

void ACoHHeroCharacter::SprintOn(const FInputActionValue&)
{
	bSprint = true;
	ApplyMovementMode();
}

void ACoHHeroCharacter::SprintOff(const FInputActionValue&)
{
	bSprint = false;
	ApplyMovementMode();
}

void ACoHHeroCharacter::ToggleSuperJump(const FInputActionValue&)
{
	bSuperJump = !bSuperJump;
	ApplyMovementMode();
	UE_LOG(LogTemp, Log, TEXT("Super Jump %s"), bSuperJump ? TEXT("on") : TEXT("off"));
}

void ACoHHeroCharacter::ApplyMovementMode()
{
	UCharacterMovementComponent* M = GetCharacterMovement();
	const float Run = bSuperSpeed ? SuperSpeedRunSpeed : (bSuperJump ? SuperJumpRunSpeed : RunSpeed);
	M->MaxWalkSpeed = bSprint ? FMath::Max(Run, SprintSpeed) : Run;
	M->JumpZVelocity = bSuperJump ? SuperJumpVelocity : 900.f;
	M->AirControl = bSuperJump ? 0.9f : 0.4f;
	M->GravityScale = bSuperJump ? 1.5f : 1.f;
	M->MaxFlySpeed = bClimbing ? ClimbSpeed : (bSuperSpeed ? SuperSpeedRunSpeed : FlightSpeed);
 M->MaxAcceleration = bSuperSpeed ? 6000.f : 2048.f;
 M->BrakingDecelerationFlying = bClimbing ? 4000.f : 1800.f;
}

void ACoHHeroCharacter::Jump()
{
 if (bFlight) return;
	if (bClimbing)
	{
		// kick off the wall
		const FVector Off = WallNormal * 600.f + FVector::UpVector * (bSuperJump ? 1200.f : 650.f);
		StopClimb();
		LaunchCharacter(Off, true, true);
		return;
	}
	Super::Jump();
}

void ACoHHeroCharacter::Punch(const FInputActionValue&)
{
	if (bClimbing || PunchAnims.Num() == 0)
	{
		return;
	}
	if (PunchTimeLeft > 0.f)
	{
		bQueuedPunch = true;     // chain into the next punch when this one lands
		return;
	}
	if (ComboWindow <= 0.f)
	{
		ComboStep = 0;
	}
	UAnimSequenceBase* Anim = Cast<UAnimSequenceBase>(PunchAnims[ComboStep % PunchAnims.Num()].TryLoad());
	if (!Anim)
	{
		return;
	}
	// play the punch straight on the mesh (the locomotion blueprint has no
	// attack slot), then hand back to locomotion in EndPunch
	GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
	GetMesh()->PlayAnimation(Anim, false);
	PunchTimeLeft = Anim->GetPlayLength() * 0.8f;
 PunchHitTimeLeft = Anim->GetPlayLength() * 0.35f;
 bPunchLanded = false;
 if (Controller) SetActorRotation(FRotator(0.f, Controller->GetControlRotation().Yaw, 0.f));
	ComboStep = (ComboStep + 1) % PunchAnims.Num();
	GetCharacterMovement()->StopMovementImmediately();
	GetCharacterMovement()->DisableMovement();
	// a fight breaks out: civilians nearby run, traffic stops
	ACoHLifeManager::ReportDanger(this, GetActorLocation(), 1500.f, 4.f);
}

void ACoHHeroCharacter::EndPunch()
{
	PunchTimeLeft = 0.f;
 bUppercutPunch=false;
	ComboWindow = 0.6f;
	GetCharacterMovement()->SetMovementMode(bFlight ? MOVE_Flying : MOVE_Falling);
	if (bQueuedPunch)
	{
		bQueuedPunch = false;
		Punch(FInputActionValue());
		if (PunchTimeLeft > 0.f)
		{
			return;
		}
	}
	RestoreLocomotion();
}

void ACoHHeroCharacter::RestoreLocomotion()
{
	if (LocomotionAnimClass)
	{
		GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		GetMesh()->SetAnimInstanceClass(LocomotionAnimClass);
	}
}

void ACoHHeroCharacter::UpdateClimbAnim()
{
	// 0 up, 1 down, 2 left, 3 right; hold the last clip still when idle
	int32 Want = ClimbClip < 0 ? 0 : ClimbClip;
	const bool bMoving = MoveInput.SizeSquared() > 0.09f;
	if (bMoving)
	{
		if (FMath::Abs(MoveInput.Y) >= FMath::Abs(MoveInput.X))
		{
			Want = MoveInput.Y > 0.f ? 0 : 1;
		}
		else
		{
			Want = MoveInput.X > 0.f ? 3 : 2;
		}
	}
	if (Want != ClimbClip && ClimbAnims.IsValidIndex(Want))
	{
		if (UAnimSequenceBase* Anim = Cast<UAnimSequenceBase>(ClimbAnims[Want].TryLoad()))
		{
			GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
			GetMesh()->PlayAnimation(Anim, true);
			ClimbClip = Want;
		}
	}
	GetMesh()->SetPlayRate(bMoving ? 1.f : 0.f);
}

void ACoHHeroCharacter::Zoom(const FInputActionValue& Value)
{
	// wheel up = closer; steps scale with distance so close range is fine
	const float Wheel = Value.Get<float>();
	const float Step = FMath::Max(40.f, ZoomTarget * 0.18f);
	ZoomTarget = FMath::Clamp(ZoomTarget - Wheel * Step, 0.f, 1400.f);
	if (ZoomTarget < 60.f)
	{
		ZoomTarget = 0.f;       // snap into first person
	}
}

void ACoHHeroCharacter::UpdateCamera(float DeltaSeconds)
{
	Boom->TargetArmLength = FMath::FInterpTo(Boom->TargetArmLength, ZoomTarget, DeltaSeconds, 10.f);
	const bool bFP = Boom->TargetArmLength < 40.f && ZoomTarget == 0.f;
	// third person: over-the-shoulder offset; first person: at the eyes
	const FVector Offset = bFP ? FVector(0.f, 0.f, 70.f)
		: FVector(0.f, 60.f, 80.f) * FMath::Clamp(Boom->TargetArmLength / 450.f, 0.f, 1.f);
	Boom->SocketOffset = FMath::VInterpTo(Boom->SocketOffset, Offset, DeltaSeconds, 10.f);
	if (bFP != bFirstPerson)
	{
		bFirstPerson = bFP;
		GetMesh()->SetOwnerNoSee(bFP);          // don't render the body from inside
		bUseControllerRotationYaw = bFP;        // face where you look
		GetCharacterMovement()->bOrientRotationToMovement = !bFP && !bClimbing;
		Boom->bDoCollisionTest = !bFP;
	}
}

void ACoHHeroCharacter::LetGo(const FInputActionValue&)
{
	if (bClimbing)
	{
		// step clear of the wall first (no sweep, so it works even when the
		// capsule has ended up inside the geometry), then hop outwards
		const FVector Away = WallNormal.IsNearlyZero() ? -GetActorForwardVector() : WallNormal;
		StopClimb();
		SetActorLocation(GetActorLocation() + Away * 50.f, false, nullptr, ETeleportType::TeleportPhysics);
		LaunchCharacter(Away * 300.f + FVector::UpVector * 150.f, true, true);
	}
}

bool ACoHHeroCharacter::TraceWall(FHitResult& Hit, float Height, float Reach) const
{
	const FVector Fwd = bClimbing ? -WallNormal : GetActorForwardVector();
	const FVector Start = GetActorLocation() + FVector(0.f, 0.f, Height);
	FCollisionQueryParams Params(SCENE_QUERY_STAT(CoHClimb), false, this);
	return GetWorld()->LineTraceSingleByChannel(Hit, Start, Start + Fwd * Reach, ECC_Visibility, Params)
		&& FMath::Abs(Hit.ImpactNormal.Z) < 0.35f;      // steep enough to be a wall
}

void ACoHHeroCharacter::StartClimb(const FVector& Normal)
{
	bClimbing = true;
	WallNormal = FVector(Normal.X, Normal.Y, 0.f).GetSafeNormal();
	UCharacterMovementComponent* M = GetCharacterMovement();
	M->SetMovementMode(MOVE_Flying);
	M->bOrientRotationToMovement = false;
	M->BrakingDecelerationFlying = 4000.f;
	M->Velocity = FVector::ZeroVector;
	SetActorRotation(FRotator(0.f, (-WallNormal).Rotation().Yaw, 0.f));
	ClimbClip = -1;
 ApplyMovementMode();
	UpdateClimbAnim();
}

void ACoHHeroCharacter::StopClimb()
{
	bClimbing = false;
	ClimbCooldown = 0.4f;
	UCharacterMovementComponent* M = GetCharacterMovement();
	M->bOrientRotationToMovement = !bFirstPerson;
	M->SetMovementMode(MOVE_Falling);
	ClimbClip = -1;
	GetMesh()->SetPlayRate(1.f);
	RestoreLocomotion();
}

void ACoHHeroCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	ClimbCooldown = FMath::Max(0.f, ClimbCooldown - DeltaSeconds);
	ComboWindow = FMath::Max(0.f, ComboWindow - DeltaSeconds);
	UpdateCamera(DeltaSeconds);
	if (PunchTimeLeft > 0.f)
	{
		PunchHitTimeLeft -= DeltaSeconds;
  if (!bPunchLanded && PunchHitTimeLeft <= 0.f) { bPunchLanded = true; LandPunch(); }
  PunchTimeLeft -= DeltaSeconds;
		if (PunchTimeLeft <= 0.f)
		{
			EndPunch();
		}
		return;
	}
	UCharacterMovementComponent* M = GetCharacterMovement();
	FHitResult Hit;
	if (!bClimbing)
	{
		// grab a wall when jumping or falling into it while pushing towards it
		if (!bFlight && ClimbCooldown <= 0.f && M->IsFalling() && MoveInput.Y > 0.5f && TraceWall(Hit, 40.f, 80.f))
		{
			StartClimb(Hit.ImpactNormal);
		}
		return;
	}
	if (TraceWall(Hit, 40.f, 90.f))
	{
		// follow the wall's surface and stay pressed against it
		WallNormal = FVector(Hit.ImpactNormal.X, Hit.ImpactNormal.Y, 0.f).GetSafeNormal();
		SetActorRotation(FRotator(0.f, (-WallNormal).Rotation().Yaw, 0.f));
		const float Gap = Hit.Distance - GetCapsuleComponent()->GetScaledCapsuleRadius() - 5.f;
		AddActorWorldOffset(-WallNormal * FMath::Clamp(Gap, -10.f, 10.f), true);
		UpdateClimbAnim();
		return;
	}
	// wall ended above the chest: climbed to the top -> vault onto the ledge
	const FVector Over = -WallNormal;
	StopClimb();
	if (MoveInput.Y > 0.f)
	{
		LaunchCharacter(Over * 350.f + FVector::UpVector * 550.f, true, true);
	}
}

ACoHGameMode::ACoHGameMode()
{
	DefaultPawnClass = ACoHHeroCharacter::StaticClass();
	// zone-to-zone monorail: keep player controllers and ride through the
	// transition level (L_MonorailRide) while the next zone loads
	bUseSeamlessTravel = true;
}

AActor* ACoHGameMode::ChoosePlayerStart_Implementation(AController* Player)
{
	if (UGameplayStatics::ParseOption(OptionsString, TEXT("Arrive")) == TEXT("Monorail"))
	{
		TArray<APlayerStart*> Starts;
		for (TActorIterator<APlayerStart> It(GetWorld()); It; ++It)
		{
			if (It->PlayerStartTag == TEXT("MonorailArrival"))
			{
				Starts.Add(*It);
			}
		}
		if (Starts.Num())
		{
			return Starts[FMath::RandRange(0, Starts.Num() - 1)];
		}
	}
	return Super::ChoosePlayerStart_Implementation(Player);
}

void ACoHHeroCharacter::ServerChooseMonorailDestination_Implementation(ARebornMonorail* Train, int32 Destination)
{
	if (Train)
	{
		Train->ChooseDestination(Destination, this);
	}
}

void ACoHHeroCharacter::LandPunch()
{
 TArray<FHitResult> Hits;
 FCollisionObjectQueryParams Objects; Objects.AddObjectTypesToQuery(ECC_Pawn);
 FCollisionQueryParams Params(SCENE_QUERY_STAT(CoHBrawl), false, this);
 const FVector Start = GetActorLocation() + GetActorForwardVector()*40.f;
 GetWorld()->SweepMultiByObjectType(Hits, Start, Start+GetActorForwardVector()*140.f, FQuat::Identity, Objects, FCollisionShape::MakeSphere(60.f), Params);
 TSet<AActor*> Damaged;
 for (const FHitResult& Hit : Hits)
 {
  auto* Enemy = Cast<ACoHCombatEnemy>(Hit.GetActor());
  if (!Enemy || Enemy->IsDead() || Damaged.Contains(Enemy)) continue;
  FHitResult Block;
  if (GetWorld()->LineTraceSingleByChannel(Block, Start, Enemy->GetActorLocation(), ECC_Visibility, Params) && Block.GetActor()!=Enemy) continue;
  Damaged.Add(Enemy);
  UGameplayStatics::ApplyDamage(Enemy, bUppercutPunch ? UppercutDamage : BrawlDamage, GetController(), this, UDamageType::StaticClass());
  if (bUppercutPunch) Enemy->LaunchRagdoll(GetActorForwardVector()*250.f+FVector(0,0,UppercutLaunchSpeed));
 }
}
float ACoHHeroCharacter::TakeDamage(float Damage, const FDamageEvent& Event, AController* EventInstigator, AActor* Causer)
{
 if (Damage<=0.f) return 0.f;
 Health = FMath::Max(0.f, Health-Damage);
 if (GEngine) GEngine->AddOnScreenDebugMessage(7120, 2.f, FColor::Yellow, FString::Printf(TEXT("Hero health: %.0f / %.0f"), Health, MaxHealth));
 if (Health<=0.f)
 {
  PunchTimeLeft=0.f; bQueuedPunch=false;
  if (bClimbing) StopClimb();
  bFlight = false;
  ApplyMovementMode();
  GetCharacterMovement()->StopMovementImmediately();
  GetCharacterMovement()->SetMovementMode(MOVE_Walking);
  SetActorLocation(RespawnLocation, false, nullptr, ETeleportType::TeleportPhysics);
  Health=MaxHealth; RestoreLocomotion();
  if (GEngine) GEngine->AddOnScreenDebugMessage(7120, 3.f, FColor::Cyan, TEXT("Combat test: hero returned to spawn with full health"));
 }
 return Damage;
}

void ACoHHeroCharacter::SetFlightEnabled(bool bEnabled)
{
 if (bFlight == bEnabled) return;
 if (bClimbing) StopClimb();
 bFlight = bEnabled;
 StopJumping();
 ApplyMovementMode();
 if (PunchTimeLeft <= 0.f) GetCharacterMovement()->SetMovementMode(bFlight ? MOVE_Flying : MOVE_Falling);
 if (GEngine) GEngine->AddOnScreenDebugMessage(7121, 2.f, FColor::Cyan, bFlight ? TEXT("Flight ON: Space rises, Ctrl descends") : TEXT("Flight OFF"));
}
void ACoHHeroCharacter::SetSuperSpeedEnabled(bool bEnabled)
{
 bSuperSpeed = bEnabled;
 ApplyMovementMode();
 if (GEngine) GEngine->AddOnScreenDebugMessage(7122, 2.f, FColor::Cyan, bSuperSpeed ? TEXT("Super Speed ON") : TEXT("Super Speed OFF"));
}
void ACoHHeroCharacter::ToggleFlight(const FInputActionValue&) { SetFlightEnabled(!bFlight); }
void ACoHHeroCharacter::ToggleSuperSpeed(const FInputActionValue&) { SetSuperSpeedEnabled(!bSuperSpeed); }
void ACoHHeroCharacter::FlyUp(const FInputActionValue&) { if (bFlight) AddMovementInput(FVector::UpVector); }
void ACoHHeroCharacter::FlyDown(const FInputActionValue&) { if (bFlight) AddMovementInput(-FVector::UpVector); }

void ACoHHeroCharacter::PerformBrawl() { Punch(FInputActionValue()); }

void ACoHHeroCharacter::UppercutInput(const FInputActionValue&) { PerformUppercut(); }
void ACoHHeroCharacter::PerformUppercut()
{
 if (bClimbing || PunchTimeLeft>0 || GetWorld()->GetTimeSeconds()<NextUppercutTime) return;
 Punch(FInputActionValue());
 if (PunchTimeLeft>0) { bUppercutPunch=true; NextUppercutTime=GetWorld()->GetTimeSeconds()+3.f; }
}

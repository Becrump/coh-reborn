#include "CoHHeroCharacter.h"
#include "CoHPowers.h"
#include "CoHPowerUI.h"
#include "Animation/AnimSequenceBase.h"
#include "Animation/Skeleton.h"
#include "Engine/SkeletalMeshSocket.h"
#include "Engine/GameViewportClient.h"
#include "Framework/Commands/InputChord.h"
#include "CoHCombat.h"
#include "CoHGraphicsMenu.h"
#include "RebornMonorail.h"
#include "GameFramework/PlayerStart.h"
#include "Kismet/GameplayStatics.h"
#include "EngineUtils.h"
#include "GameFramework/Volume.h"
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

	Powers = CreateDefaultSubobject<UCoHPowerComponent>(TEXT("Powers"));
	Powers->bPlayerSide = true;
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
	if (HasAuthority())
	{
		Powers->ClassName = TestArchetype;
		Powers->Level = FMath::Clamp(TestLevel, 1, 50);
		Powers->DisplayName = TEXT("Test Hero");
		Powers->Tray.SetNum(10);
		for (int32 i = 0; i < StartTray.Num() && i < 10; ++i) Powers->Tray[i] = StartTray[i];
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
		if (PC->IsLocalController())
		{
			Hud = CreateWidget<UCoHHudWidget>(PC, UCoHHudWidget::StaticClass());
			if (Hud) Hud->AddToViewport(5);
			RestoreGameInput(PC);
			UCoHGraphicsMenu::ApplyComic(this, UCoHGraphicsMenu::SavedComic());
		}
	}
}

void ACoHHeroCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
	Super::SetupPlayerInputComponent(Input);
	Input->BindKey(EKeys::F10, IE_Pressed, this, &ACoHHeroCharacter::ToggleGraphicsMenu);
	// power tray: 1..0 fire the slot once; Ctrl + 1..0 locks that power as
	// the auto attack (Ctrl + the same number again unlocks). Each press is
	// logged ("CoH key ...") so a test shows which key did what.
	const FKey SlotKeys[10] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six, EKeys::Seven, EKeys::Eight, EKeys::Nine, EKeys::Zero };
	for (int32 i = 0; i < 10; ++i)
	{
		FInputKeyBinding KB(FInputChord(SlotKeys[i]), IE_Pressed);
		KB.KeyDelegate.GetDelegateForManualSet().BindLambda([this, i]
		{
			const APlayerController* PC = Cast<APlayerController>(GetController());
			if (!Powers || (PC && (PC->IsInputKeyDown(EKeys::LeftControl) || PC->IsInputKeyDown(EKeys::RightControl)))) return;
			UE_LOG(LogTemp, Log, TEXT("CoH key: %d -> fire slot %d once%s"), (i + 1) % 10, i + 1,
				PC && (PC->IsInputKeyDown(EKeys::LeftShift) || PC->IsInputKeyDown(EKeys::RightShift)) ? TEXT(" (Shift held: no effect)") : TEXT(""));
			Powers->ActivateSlot(i);
		});
		Input->KeyBindings.Add(KB);
		FInputKeyBinding Lock(FInputChord(SlotKeys[i], false, true, false, false), IE_Pressed);
		Lock.KeyDelegate.GetDelegateForManualSet().BindLambda([this, i]
		{
			UE_LOG(LogTemp, Log, TEXT("CoH key: Ctrl+%d -> auto lock toggle on slot %d"), (i + 1) % 10, i + 1);
			if (Powers) Powers->ToggleAutoSlot(i);
		});
		Input->KeyBindings.Add(Lock);
	}
	Input->BindKey(EKeys::Tab, IE_Pressed, this, &ACoHHeroCharacter::CycleTarget);
	Input->BindKey(EKeys::P, IE_Pressed, this, &ACoHHeroCharacter::TogglePowerBrowser);
	Input->BindKey(EKeys::F8, IE_Pressed, this, &ACoHHeroCharacter::ToggleAnimBench);

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
	SelectAction = NewObject<UInputAction>(this);
	CameraDragAction = NewObject<UInputAction>(this);
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
 Mapping->MapKey(FlyDownAction, EKeys::X);     // as in the original game; Ctrl is the auto-attack lock
	Mapping->MapKey(LetGoAction, EKeys::C);
	Mapping->MapKey(SelectAction, EKeys::LeftMouseButton);     // select, never attack
	Mapping->MapKey(CameraDragAction, EKeys::RightMouseButton); // hold to turn the camera
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
		EI->BindAction(SelectAction, ETriggerEvent::Started, this, &ACoHHeroCharacter::SelectTarget);
		EI->BindAction(CameraDragAction, ETriggerEvent::Started, this, &ACoHHeroCharacter::CameraDragOn);
		EI->BindAction(CameraDragAction, ETriggerEvent::Completed, this, &ACoHHeroCharacter::CameraDragOff);
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
    if (Hud) { Hud->RemoveFromParent(); Hud = nullptr; }
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

void ACoHHeroCharacter::RestoreGameInput(APlayerController* PC)
{
	if (!PC) return;
	PC->SetShowMouseCursor(true);
	FInputModeGameAndUI Mode;
	Mode.SetHideCursorDuringCapture(false);
	Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	PC->SetInputMode(Mode);
}

void ACoHHeroCharacter::CameraDragOn(const FInputActionValue&)
{
	bCameraDrag = true;
	if (APlayerController* PC = Cast<APlayerController>(GetController())) PC->SetShowMouseCursor(false);
}

void ACoHHeroCharacter::CameraDragOff(const FInputActionValue&)
{
	bCameraDrag = false;
	if (APlayerController* PC = Cast<APlayerController>(GetController())) PC->SetShowMouseCursor(true);
}

void ACoHHeroCharacter::Look(const FInputActionValue& Value)
{
	// the camera turns only while the right button is held (first person
	// keeps free mouse-look)
	if (!bCameraDrag && !bFirstPerson) return;
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
	GetMesh()->SetPlayRate(1.f);
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
 // all damage goes through the power component (resistance, numbers, defeat)
 if (Damage<=0.f || !Powers) return 0.f;
 AActor* Who = EventInstigator && EventInstigator->GetPawn() ? EventInstigator->GetPawn() : Causer;
 const float Done = Powers->ApplyDamage(Damage, ECoHDamage::Smashing, Who);
 Health = Powers->Health;
 return Done;
}

void ACoHHeroCharacter::OnDefeated()
{
 PunchTimeLeft=0.f; bQueuedPunch=false;
 if (bClimbing) StopClimb();
 bFlight = false;
 ApplyMovementMode();
 GetCharacterMovement()->StopMovementImmediately();
 GetCharacterMovement()->SetMovementMode(MOVE_Walking);
 SetActorLocation(RespawnLocation, false, nullptr, ETeleportType::TeleportPhysics);
 Powers->Reset();
 Health=Powers->Health; RestoreLocomotion();
 if (GEngine) GEngine->AddOnScreenDebugMessage(7120, 3.f, FColor::Cyan, TEXT("Defeated: back at the start point, fully healed"));
}

void ACoHHeroCharacter::PlayPowerAnimation(int32 Kind, float Duration, int32 AnimIndex, const FSoftObjectPath& Clip)
{
 if (bClimbing) return;
 const TArray<FSoftObjectPath>& Set =
  Kind == 4 ? SelfAnims :
  Kind == 3 ? (ThrowAnims.Num() ? ThrowAnims : RangedAnims) :
  Kind == 2 ? (AreaAnims.Num() ? AreaAnims : PunchAnims) :
  Kind == 1 ? (RangedAnims.Num() ? RangedAnims : PunchAnims) : PunchAnims;
 UAnimSequenceBase* Anim = Clip.IsValid() ? Cast<UAnimSequenceBase>(Clip.TryLoad()) : nullptr;
 if (!Anim && Set.Num())
 {
  const int32 Pick = AnimIndex >= 0 ? AnimIndex % Set.Num() : (Kind == 0 ? ComboStep++ % Set.Num() : FMath::RandRange(0, Set.Num() - 1));
  Anim = Cast<UAnimSequenceBase>(Set[Pick].TryLoad());
 }
 if (!Anim) return;
 // the power's own activation time rules; the clip is fitted to it
 const float Time = FMath::Max(0.4f, Duration);
 GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
 GetMesh()->PlayAnimation(Anim, false);
 GetMesh()->SetPlayRate(FMath::Clamp(Anim->GetPlayLength() / Time, 0.5f, 2.5f));
 PunchTimeLeft = Time;
 bPunchLanded = true;          // no brawl hit: the power system applies the effects
 bQueuedPunch = false;
 GetCharacterMovement()->StopMovementImmediately();
 GetCharacterMovement()->DisableMovement();
}

bool ACoHHeroCharacter::PreviewAnimation(const FString& ClipNameOrPath)
{
 UAnimSequenceBase* Anim = Cast<UAnimSequenceBase>(UCoHPowerComponent::FindClip(ClipNameOrPath).TryLoad());
 if (!Anim || bClimbing) return false;
 // at its own speed (a power fits a clip to its activation time instead)
 GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
 GetMesh()->PlayAnimation(Anim, false);
 GetMesh()->SetPlayRate(1.f);
 PunchTimeLeft = FMath::Max(0.2f, Anim->GetPlayLength());
 bPunchLanded = true; bQueuedPunch = false;
 GetCharacterMovement()->StopMovementImmediately();
 GetCharacterMovement()->DisableMovement();
 return true;
}

float ACoHHeroCharacter::ReleaseTime(const UAnimSequenceBase* Clip, bool* bFromNotify)
{
 if (bFromNotify) *bFromNotify = false;
 if (!Clip) return 0.f;
 for (const FAnimNotifyEvent& N : Clip->Notifies)
 {
  const FString Name = N.NotifyName.ToString();
  if (Name.Contains(TEXT("CoHRelease")) || Name.Equals(TEXT("Release"), ESearchCase::IgnoreCase) || Name.Equals(TEXT("Fire"), ESearchCase::IgnoreCase) || Name.Equals(TEXT("Hit"), ESearchCase::IgnoreCase))
  {
   if (bFromNotify) *bFromNotify = true;
   return N.GetTriggerTime();
  }
 }
 return Clip->GetPlayLength() * 0.45f;
}

bool ACoHHeroCharacter::AddSkeletonSocket(USkeleton* Skeleton, FName Socket, FName Bone, FVector Location)
{
#if WITH_EDITOR
 if (!Skeleton || Skeleton->GetReferenceSkeleton().FindBoneIndex(Bone) == INDEX_NONE) return false;
 USkeletalMeshSocket* S = Skeleton->FindSocket(Socket);
 if (!S)
 {
  S = NewObject<USkeletalMeshSocket>(Skeleton);
  S->SocketName = Socket;
  Skeleton->Sockets.Add(S);
 }
 S->BoneName = Bone;
 S->RelativeLocation = Location;
 Skeleton->MarkPackageDirty();
 return true;
#else
 return false;
#endif
}

void ACoHHeroCharacter::ToggleAnimBench()
{
 if (Hud) Hud->ToggleBench();
}

void ACoHHeroCharacter::CycleTarget()
{
 if (!Powers) return;
 // foes in view (buildings block, people don't) within 50 m, nearest first;
 // the ones behind the camera count as a little further away
 TArray<TPair<float, AActor*>> Foes;
 const FVector Eye = GetActorLocation() + FVector(0, 0, 60);
 const FVector Look = Controller ? Controller->GetControlRotation().Vector() : GetActorForwardVector();
 for (TActorIterator<ACharacter> It(GetWorld()); It; ++It)
 {
  const UCoHPowerComponent* C = UCoHPowerComponent::Of(*It);
  if (!C || C->bPlayerSide || C->IsDefeated()) continue;
  const FVector To = It->GetActorLocation() - Eye;
  const float D = To.Size();
  if (D > 5000.f) continue;
  FHitResult Block;
  FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHTab), false, this); Q.AddIgnoredActor(*It);
  if (GetWorld()->LineTraceSingleByObjectType(Block, Eye, It->GetActorLocation(), FCollisionObjectQueryParams(ECC_WorldStatic), Q) && !Cast<AVolume>(Block.GetActor())) continue;
  const float Front = FVector::DotProduct(To.GetSafeNormal2D(), Look.GetSafeNormal2D());
  Foes.Add({ D * (Front < 0.f ? 1.6f : 1.f), *It });
 }
 Foes.Sort([](const TPair<float, AActor*>& A, const TPair<float, AActor*>& B) { return A.Key < B.Key; });
 const double Now = GetWorld()->GetTimeSeconds();
 const bool bCycling = Now - LastTabTime < 2.0;     // a fresh press starts at the nearest
 LastTabTime = Now;
 if (Foes.Num() == 0) { Powers->Target = nullptr; UE_LOG(LogTemp, Log, TEXT("CoH key: Tab -> no foe in view")); return; }
 int32 Next = 0;
 if (bCycling)
  for (int32 i = 0; i < Foes.Num(); ++i) if (Foes[i].Value == Powers->Target.Get()) { Next = (i + 1) % Foes.Num(); break; }
 Powers->Target = Foes[Next].Value;
 UE_LOG(LogTemp, Log, TEXT("CoH key: Tab -> target %s at %.0f m (%d of %d)"), *GetNameSafe(Foes[Next].Value),
  FVector::Dist(GetActorLocation(), Foes[Next].Value->GetActorLocation()) / 100.f, Next + 1, Foes.Num());
}

void ACoHHeroCharacter::SelectTarget(const FInputActionValue&)
{
 APlayerController* PC = Cast<APlayerController>(GetController());
 if (!PC || !Powers) return;
 // the aim ray: through the cursor when it shows, else the screen centre
 FVector Origin, Dir;
 bool bRay = false;
 if (PC->bShowMouseCursor) bRay = PC->DeprojectMousePositionToWorld(Origin, Dir);
 if (!bRay)
 {
  int32 W = 0, H = 0; PC->GetViewportSize(W, H);
  bRay = PC->DeprojectScreenPositionToWorld(W * 0.5f, H * 0.5f, Origin, Dir);
 }
 if (!bRay) return;
 // whoever is closest to the ray (looser further out) and in view
 AActor* Best = nullptr; float BestScore = TNumericLimits<float>::Max();
 for (TActorIterator<ACharacter> It(GetWorld()); It; ++It)
 {
  if (*It == this) continue;
  const UCoHPowerComponent* C = UCoHPowerComponent::Of(*It);
  if (!C || C->IsDefeated()) continue;
  const FVector P = It->GetActorLocation();
  const float Along = FVector::DotProduct(P - Origin, Dir);
  if (Along < 0.f || Along > 10000.f) continue;
  const float Off = FVector::Dist(P, Origin + Dir * Along);
  const float Tol = 80.f + Along * 0.03f;
  if (Off > Tol) continue;
  FHitResult Block;
  FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHPick), false, this); Q.AddIgnoredActor(*It);
  if (GetWorld()->LineTraceSingleByObjectType(Block, Origin, P, FCollisionObjectQueryParams(ECC_WorldStatic), Q) && !Cast<AVolume>(Block.GetActor())) continue;
  const float Score = Off / Tol + Along / 10000.f;
  if (Score < BestScore) { BestScore = Score; Best = *It; }
 }
 UE_LOG(LogTemp, Log, TEXT("CoH key: Left mouse -> select %s"), Best ? *GetNameSafe(Best) : TEXT("nothing (target kept)"));
 if (Best) Powers->Target = Best;
}

void ACoHHeroCharacter::PlayHitReaction(float Amount)
{
 // never cut a power animation, a climb or flight; at most every 0.6 s
 if (bClimbing || bFlight || PunchTimeLeft > 0.f || HitReactAnims.Num() == 0) return;
 const double Now = GetWorld()->GetTimeSeconds();
 if (Now < NextHitReact) return;
 NextHitReact = Now + 0.6;
 const bool bHeavy = Powers && Amount > Powers->MaxHealth * 0.12f;
 const int32 Pick = bHeavy || HitReactAnims.Num() == 1 ? 0 : FMath::RandRange(1, HitReactAnims.Num() - 1);
 UAnimSequenceBase* Anim = Cast<UAnimSequenceBase>(HitReactAnims[Pick].TryLoad());
 if (!Anim) return;
 GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
 GetMesh()->PlayAnimation(Anim, false);
 GetMesh()->SetPlayRate(1.f);
 // a short stagger: movement pauses, then locomotion takes over again
 PunchTimeLeft = FMath::Min(Anim->GetPlayLength(), bHeavy ? 0.8f : 0.45f);
 bPunchLanded = true; bQueuedPunch = false;
 GetCharacterMovement()->StopMovementImmediately();
 GetCharacterMovement()->DisableMovement();
}

void ACoHHeroCharacter::TogglePowerBrowser()
{
 if (Hud) Hud->ToggleBrowser();
}

void ACoHHeroCharacter::SetFlightEnabled(bool bEnabled)
{
 if (bFlight == bEnabled) return;
 if (bClimbing) StopClimb();
 bFlight = bEnabled;
 StopJumping();
 ApplyMovementMode();
 if (PunchTimeLeft <= 0.f) GetCharacterMovement()->SetMovementMode(bFlight ? MOVE_Flying : MOVE_Falling);
 if (GEngine) GEngine->AddOnScreenDebugMessage(7121, 2.f, FColor::Cyan, bFlight ? TEXT("Flight ON: Space rises, X descends") : TEXT("Flight OFF"));
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

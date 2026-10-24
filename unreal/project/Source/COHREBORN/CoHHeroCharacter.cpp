#include "CoHHeroCharacter.h"
#include "CoHPowers.h"
#include "CoHBodyAnim.h"
#include "CoHGameRules.h"
#include "CoHHeroProgress.h"
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
	Progress = CreateDefaultSubobject<UCoHHeroProgress>(TEXT("Progress"));
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
	bool bBuilt = false;
	if (HasAuthority() && !HeroFile.IsEmpty())
	{
		// a hero built by the original rules; the save continues it
		const UCoHGameRules* R = UCoHGameRules::Get(this);
		const FString Save = FPaths::GetBaseFilename(HeroFile) + TEXT("_save.json");
		bBuilt = R && R->HasHeroRules() && ((bResumeSave && FPaths::FileExists(R->HeroesDir / Save) && Progress->LoadHeroFile(Save)) || Progress->LoadHeroFile(HeroFile));
		if (bBuilt) Progress->SaveFile = Save;
	}
	if (bBuilt) ApplyCoHBody();
	else if (HasAuthority())
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
			if (!Powers || (PC && (PC->IsInputKeyDown(EKeys::LeftControl) || PC->IsInputKeyDown(EKeys::RightControl)
				|| PC->IsInputKeyDown(EKeys::LeftAlt) || PC->IsInputKeyDown(EKeys::RightAlt)))) return;
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
		// Alt + number: use that inspiration
		FInputKeyBinding Insp(FInputChord(SlotKeys[i], false, false, true, false), IE_Pressed);
		Insp.KeyDelegate.GetDelegateForManualSet().BindLambda([this, i] { if (Progress) Progress->UseInspiration(i); });
		Input->KeyBindings.Add(Insp);
	}
	Input->BindKey(EKeys::Tab, IE_Pressed, this, &ACoHHeroCharacter::CycleTarget);
	Input->BindKey(EKeys::P, IE_Pressed, this, &ACoHHeroCharacter::TogglePowerBrowser);
	Input->BindKey(EKeys::V, IE_Pressed, this, &ACoHHeroCharacter::ToggleClimbPower);
	Input->BindKey(EKeys::F8, IE_Pressed, this, &ACoHHeroCharacter::ToggleAnimBench);
	// L: train to the next level (the original trainer step)
	{
		FInputKeyBinding Train(FInputChord(EKeys::L), IE_Pressed);
		Train.KeyDelegate.GetDelegateForManualSet().BindLambda([this] { if (Progress) Progress->Train(); });
		Input->KeyBindings.Add(Train);
	}

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

bool ACoHHeroCharacter::ClimbPowerOn() const { return Powers && Powers->IsToggleOn(CoHTravel::Climb); }
bool ACoHHeroCharacter::SprintPowerOn() const { return Powers && Powers->IsToggleOn(CoHTravel::Sprint); }

void ACoHHeroCharacter::ToggleClimbPower()
{
	if (Powers) Powers->ActivatePower(CoHTravel::Climb);
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
	M->MaxWalkSpeed = (bSprint || SprintPowerOn()) ? FMath::Max(Run, SprintSpeed) : Run;
	M->JumpZVelocity = bSuperJump ? SuperJumpVelocity : 900.f;
	M->AirControl = bSuperJump ? 0.9f : 0.4f;
	M->GravityScale = bSuperJump ? 1.5f : 1.f;
	M->MaxFlySpeed = bClimbing ? ClimbSpeed * (ClimbPowerOn() ? ClimbPowerSpeedScale : 1.f) : (bSuperSpeed ? SuperSpeedRunSpeed : FlightSpeed);
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
	if (!CoHBodyType.IsEmpty()) { if (PunchTimeLeft <= 0.f) PlayPowerAnimation(0, 0.8f, -1); return; }
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
		// a CoH body keeps its anim instance: moves end back in locomotion by themselves
		if (BodyAnim()) return;
		GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		GetMesh()->SetAnimInstanceClass(LocomotionAnimClass);
		SetupBodyAnim();
	}
}

UCoHBodyAnim* ACoHHeroCharacter::BodyAnim() const
{
	return GetMesh()->GetAnimationMode() == EAnimationMode::AnimationBlueprint ? Cast<UCoHBodyAnim>(GetMesh()->GetAnimInstance()) : nullptr;
}

void ACoHHeroCharacter::ApplyCoHBody()
{
	// the preset the hero file names: an original player body on its skeleton
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!bCoHBody || !R || !Progress || !Progress->bHasRecord || bBodyApplied) return;
	FString Body;
	const FString Preset = Progress->Hero.Preset.IsEmpty() ? TEXT("Model_Positron") : Progress->Hero.Preset;
	USkeletalMesh* BodyMesh = R->PresetMesh(Preset, Body);
	bBodyApplied = true;
	if (!BodyMesh) { UE_LOG(LogTemp, Warning, TEXT("CoH hero: preset %s is not imported (/Game/CoH/Player/Presets)"), *Preset); return; }
	BodyPreset = Preset;
	CoHBodyType = Body;
	Powers->Body = Body;
	GetMesh()->SetSkeletalMeshAsset(BodyMesh);
	GetMesh()->SetRelativeRotation(FRotator(0.f, CoHMeshYaw, 0.f));
	LocomotionAnimClass = UCoHBodyAnim::StaticClass();
	GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
	GetMesh()->SetAnimInstanceClass(LocomotionAnimClass);
	SetupBodyAnim();
	UE_LOG(LogTemp, Log, TEXT("CoH hero: body %s (%s)"), *Preset, *Body);
}

void ACoHHeroCharacter::SetupBodyAnim()
{
	UCoHBodyAnim* A = BodyAnim();
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!A || !R || CoHBodyType.IsEmpty()) return;
	const FString Folder = R->PresetRoot / CoHBodyType / BodyPreset;
	A->Idle = R->ClipIn(Folder, TEXT("idle"));
	A->CombatIdle = R->ClipIn(Folder, TEXT("combat_idle"));
	A->Run = R->ClipIn(Folder, TEXT("run"));
	// jumps: the player sequencer's jumpPre / jumpUp / jumpApex / jumpFall all
	// play one track, <body>/superjump (frames 3-93, then the fall holds), so
	// one clip carries the whole jump; landing blends back to ready or run
	A->JumpUp = R->ClipIn(R->PlayerAnimRoot / CoHBodyType, CoHBodyType + TEXT("__superjump"));
	A->Fall = A->JumpUp;
	if (!A->JumpUp) UE_LOG(LogTemp, Warning, TEXT("CoH hero: no %s__superjump clip for jumps"), *CoHBodyType);
	A->RunCycleSpeed = RunSpeed;
	A->bAutoLocomotion = true;
}

bool ACoHHeroCharacter::PlayMoves(const TArray<FCoHAnimSegment>& Segments, float Lock)
{
	if (bClimbing || Segments.Num() == 0) return false;
	if (!BodyAnim() && LocomotionAnimClass == UCoHBodyAnim::StaticClass())
	{
		GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		GetMesh()->SetAnimInstanceClass(LocomotionAnimClass);
		SetupBodyAnim();
	}
	UCoHBodyAnim* A = BodyAnim();
	if (!A) return false;
	A->PlaySegments(Segments);
	A->MarkCombat();
	if (Lock > 0.f)
	{
		// rooted while the power activates (TimeToActivate, the server rule);
		// in the air the hero keeps the jump arc, as in the original
		PunchTimeLeft = Lock;
		bPunchLanded = true; bQueuedPunch = false;
		UCharacterMovementComponent* CM = GetCharacterMovement();
		if (!CM->IsFalling() && !CM->IsFlying())
		{
			CM->StopMovementImmediately();
			CM->DisableMovement();
		}
	}
	return true;
}

bool ACoHHeroCharacter::PlayPowerMoves(FName Power, bool bActivation)
{
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	const FCoHPowerAnim* PA = R ? R->PowerAnim(Power) : nullptr;
	if (!PA || CoHBodyType.IsEmpty()) return false;
	TArray<FCoHAnimSegment> Segs;
	const TCHAR* First = bActivation ? TEXT("ActivationBits") : TEXT("AttackBits");
	const TCHAR* Second = bActivation ? TEXT("AttackBits") : TEXT("ActivationBits");
	if (!R->Segments(*PA, CoHBodyType, First, Segs) && !R->Segments(*PA, CoHBodyType, Second, Segs)) return false;
	const UCoHPowerDatabase* DB = UCoHPowerDatabase::Get(this);
	const FCoHPowerDef* Def = DB ? DB->FindPower(Power) : nullptr;
	const bool bToggle = Def && Def->Type == TEXT("kToggle");
	return PlayMoves(Segs, bToggle ? 0.f : FMath::Max(0.3f, Def ? Def->Activate : 1.f));
}

bool ACoHHeroCharacter::PlayEmitterPose(uint8 Emitter, float Duration)
{
	// original generic moves (anim_list.json), first one the body has; order of ECoHEmitter
	static const TArray<TArray<FString>> Poses = {
		{ TEXT("onehand_palmcast"), TEXT("palmcast"), TEXT("point") },            // right arm out
		{ TEXT("magic_l"), TEXT("comb_wristshoot_l") },                            // left arm out
		{ TEXT("2hand_cast"), TEXT("alt_stopcast") },                              // both arms out
		{ TEXT("eye") },                                                           // eyes
		{ TEXT("alt_beatchest"), TEXT("comb_beatchest") },                         // chest
		{ TEXT("scream"), TEXT("sonic_yell") },                                    // mouth
		{ TEXT("stomp") },                                                         // feet
		{ TEXT("flight_afterburner"), TEXT("boost") },                             // back
		{ TEXT("sky_summon"), TEXT("raise_hand") } };                              // overhead
	const UCoHGameRules* R = UCoHGameRules::Get(this);
	if (!R || CoHBodyType.IsEmpty() || !Poses.IsValidIndex(Emitter)) return false;
	for (const FString& Name : Poses[Emitter])
		if (UAnimSequenceBase* Clip = R->ClipIn(R->PlayerAnimRoot / CoHBodyType, CoHBodyType + TEXT("__") + Name))
		{
			FCoHAnimSegment Seg;
			Seg.Clip = Clip; Seg.End = Clip->GetPlayLength();
			const bool bOk = PlayMoves({ Seg }, FMath::Max(0.4f, Duration));
			// eye beam, breath: the head goes forward with the pose
			if (bOk && (Emitter == 3 || Emitter == 5)) if (UCoHBodyAnim* B = BodyAnim()) B->LeanHead(Emitter == 3 ? 22.f : 28.f, FMath::Max(0.4f, Duration) + 0.2f);
			return bOk;
		}
	return false;
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
	if (!bBodyApplied && Progress && Progress->bHasRecord) ApplyCoHBody();
	ClimbCooldown = FMath::Max(0.f, ClimbCooldown - DeltaSeconds);
	// the Sprint and Climb toggles change speeds: follow them
	if (SprintPowerOn() != bSprintPowerSeen || ClimbPowerOn() != bClimbPowerSeen)
	{
		bSprintPowerSeen = SprintPowerOn(); bClimbPowerSeen = ClimbPowerOn();
		ApplyMovementMode();
	}
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
		// a wall grab needs a little endurance; with Climb on a walk into a wall is enough, else jump or fall into it
		const bool bCanGrab = !Powers || Powers->Endurance >= 3.f;
		if (!bFlight && bCanGrab && ClimbCooldown <= 0.f && (M->IsFalling() || ClimbPowerOn()) && MoveInput.Y > 0.5f && TraceWall(Hit, 40.f, 80.f))
		{
			StartClimb(Hit.ImpactNormal);
		}
		return;
	}
	// without the Climb power a wall climb costs Endurance fast; at zero the grip gives out
	if (Powers && !ClimbPowerOn() && HasAuthority())
	{
		Powers->Endurance = FMath::Max(0.f, Powers->Endurance - ClimbFastDrain * DeltaSeconds);
		if (Powers->Endurance <= 0.f)
		{
			const FVector Away = WallNormal.IsNearlyZero() ? -GetActorForwardVector() : WallNormal;
			StopClimb();
			LaunchCharacter(Away * 250.f + FVector::UpVector * 100.f, true, true);
			Powers->MulticastText(TEXT("Out of Endurance: you lose your grip"), FLinearColor(0.4f, 0.6f, 1.f));
			return;
		}
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

void ACoHGameMode::StartPlay()
{
	Super::StartPlay();
	UWorld* W = GetWorld();
	if (W && !TActorIterator<ACoHEnemySpawner>(W))
	{
		W->SpawnActor<ACoHEnemySpawner>(ACoHEnemySpawner::StaticClass(), FTransform::Identity);
		UE_LOG(LogTemp, Log, TEXT("CoH: no enemy spawner on the map, added one"));
	}
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
 if (Progress) Progress->OnDefeatedByVillains();
 Health=Powers->Health; RestoreLocomotion();
 if (GEngine) GEngine->AddOnScreenDebugMessage(7120, 3.f, FColor::Cyan, TEXT("Defeated: back at the start point, fully healed"));
}

void ACoHHeroCharacter::PlayPowerAnimation(int32 Kind, float Duration, int32 AnimIndex, const FSoftObjectPath& Clip)
{
 if (bClimbing) return;
 if (!CoHBodyType.IsEmpty())
 {
  // a CoH body with no original moves for the power (inherents such as Brawl
  // are not in power_anims.json): the preset's attack clip, never a clip of
  // another skeleton (that shows the reference T-pose)
  const UCoHGameRules* R = UCoHGameRules::Get(this);
  FCoHAnimSegment Seg;
  Seg.Clip = R ? R->ClipIn(R->PresetRoot / CoHBodyType / BodyPreset, TEXT("attack")) : nullptr;
  if (Seg.Clip) { Seg.End = Seg.Clip->GetPlayLength(); PlayMoves({ Seg }, FMath::Max(0.4f, Duration)); }
  else UE_LOG(LogTemp, Warning, TEXT("CoH hero: no moves and no attack clip for %s"), *BodyPreset);
  return;
 }
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
 // as in the original: the first Tab takes the nearest foe, each further Tab
 // the next nearest, wrapping round; Shift+Tab goes back. Every living foe
 // within 200 ft counts, in view or not (allies and the defeated never do).
 TArray<TPair<float, AActor*>> Foes;
 for (TActorIterator<ACharacter> It(GetWorld()); It; ++It)
 {
  const UCoHPowerComponent* C = UCoHPowerComponent::Of(*It);
  if (!C || C->bPlayerSide == Powers->bPlayerSide || C->IsDefeated()) continue;
  const float D = FVector::Dist(GetActorLocation(), It->GetActorLocation());
  if (D > 200.f * 30.48f) continue;
  Foes.Add({ D, *It });
 }
 Foes.Sort([](const TPair<float, AActor*>& A, const TPair<float, AActor*>& B) { return A.Key < B.Key; });
 const double Now = GetWorld()->GetTimeSeconds();
 const APlayerController* PC = Cast<APlayerController>(GetController());
 const bool bBack = PC && (PC->IsInputKeyDown(EKeys::LeftShift) || PC->IsInputKeyDown(EKeys::RightShift));
 // a fresh press (2 s since the last) or a lost target starts at the nearest
 int32 Current = INDEX_NONE;
 for (int32 i = 0; i < Foes.Num(); ++i) if (Foes[i].Value == Powers->Target.Get()) { Current = i; break; }
 const bool bCycling = Now - LastTabTime < 2.0 && Current != INDEX_NONE;
 LastTabTime = Now;
 if (Foes.Num() == 0) { Powers->Target = nullptr; UE_LOG(LogTemp, Log, TEXT("CoH key: Tab -> no foe within 200 ft")); return; }
 const int32 Next = bCycling ? (Current + (bBack ? Foes.Num() - 1 : 1)) % Foes.Num() : 0;
 Powers->Target = Foes[Next].Value;
 UE_LOG(LogTemp, Log, TEXT("CoH key: %sTab -> target %s at %.0f m (%d of %d)"), bBack ? TEXT("Shift+") : TEXT(""), *GetNameSafe(Foes[Next].Value),
  Foes[Next].Key / 100.f, Next + 1, Foes.Num());
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
 if (Hud && Hud->TryPickPoint(Origin, Dir)) return;      // the customize panel's pick of a cast point
 // whoever the ray passes closest to: the whole body counts (feet to head,
 // a generous capsule, looser further out), and only real geometry in front
 // of them blocks the pick (complex collision: the original tiles' simple
 // collision boxes take in the air above the streets)
 const FVector RayEnd = Origin + Dir * 10000.f;
 AActor* Best = nullptr; float BestScore = TNumericLimits<float>::Max();
 for (TActorIterator<ACharacter> It(GetWorld()); It; ++It)
 {
  if (*It == this) continue;
  const UCoHPowerComponent* C = UCoHPowerComponent::Of(*It);
  if (!C || C->IsDefeated()) continue;
  const FVector P = It->GetActorLocation();
  const float Half = It->GetCapsuleComponent() ? It->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f;
  FVector OnRay, OnBody;
  FMath::SegmentDistToSegmentSafe(Origin, RayEnd, P - FVector(0, 0, Half), P + FVector(0, 0, Half), OnRay, OnBody);
  const float Along = FVector::DotProduct(OnRay - Origin, Dir);
  if (Along < 0.f) continue;
  const float Off = FVector::Dist(OnRay, OnBody);
  const float Tol = 70.f + Along * 0.02f;
  if (Off > Tol) continue;
  FHitResult Block;
  FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHPick), true, this); Q.AddIgnoredActor(*It);
  if (GetWorld()->LineTraceSingleByObjectType(Block, Origin, OnBody, FCollisionObjectQueryParams(ECC_WorldStatic), Q)
   && !Cast<AVolume>(Block.GetActor()) && Block.Distance < FVector::Dist(Origin, OnBody) - 60.f) continue;
  const float Score = Off / Tol + Along / 10000.f;
  if (Score < BestScore) { BestScore = Score; Best = *It; }
 }
 // a click on empty ground clears the target, as in the original
 UE_LOG(LogTemp, Log, TEXT("CoH key: Left mouse -> select %s"), Best ? *GetNameSafe(Best) : TEXT("nothing (target cleared)"));
 Powers->Target = Best;
}

void ACoHHeroCharacter::PlayHitReaction(float Amount)
{
 // never cut a power animation, a climb or flight; at most every 0.6 s
 if (bClimbing || bFlight || PunchTimeLeft > 0.f) return;
 const double Now = GetWorld()->GetTimeSeconds();
 if (Now < NextHitReact) return;
 if (!CoHBodyType.IsEmpty())
 {
  // C_HitQuick on the original body
  const UCoHGameRules* R = UCoHGameRules::Get(this);
  FCoHAnimSegment Hit;
  Hit.Clip = R ? R->ClipIn(R->PresetRoot / CoHBodyType / BodyPreset, TEXT("hit")) : nullptr;
  if (Hit.Clip) { NextHitReact = Now + 0.6; Hit.End = Hit.Clip->GetPlayLength(); PlayMoves({ Hit }, 0.f); }
  return;
 }
 if (HitReactAnims.Num() == 0) return;
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

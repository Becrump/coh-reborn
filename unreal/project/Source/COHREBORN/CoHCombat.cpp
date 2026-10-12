#include "CoHCombat.h"
#include "CoHPowers.h"
#include "GameFramework/PlayerController.h"
#include "AIController.h"
#include "Animation/AnimSequence.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "NavigationSystem.h"
#include "NavigationInvokerComponent.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "TimerManager.h"
#include "PhysicsEngine/PhysicsAsset.h"
#if WITH_EDITOR
#include "PhysicsAssetUtils.h"
#include "AssetRegistry/AssetRegistryModule.h"
#endif
ACoHCombatEnemy::ACoHCombatEnemy()
{
 PrimaryActorTick.bCanEverTick=true; PrimaryActorTick.TickInterval=.1f;
 AIControllerClass=AAIController::StaticClass(); AutoPossessAI=EAutoPossessAI::PlacedInWorldOrSpawned;
 GetCapsuleComponent()->InitCapsuleSize(36.f,90.f);
 GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
 GetMesh()->SetCanEverAffectNavigation(false);
 GetCharacterMovement()->bOrientRotationToMovement=true;
 GetCharacterMovement()->RotationRate=FRotator(0,540,0);
 GetCharacterMovement()->MaxWalkSpeed=360;
 Tags.Add(TEXT("CoHCombatEnemy"));
 Powers=CreateDefaultSubobject<UCoHPowerComponent>(TEXT("Powers"));
 Powers->bPlayerSide=false;
 Powers->ClassName=TEXT("Class_Minion_Grunt");
 Powers->Level=5;
}
void ACoHCombatEnemy::InitializeFromCatalog(const TMap<FString,FString>& Entry,const FString& Faction,const FString& RankClass,int32 InLevel)
{
 Home=GetActorLocation();
 auto Path=[&](const TCHAR* K){const FString* P=Entry.Find(K);return P?*P:FString();};
 USkeletalMesh* Body=LoadObject<USkeletalMesh>(nullptr,*Path(TEXT("mesh")));
 if(!Body) return;
 GetMesh()->SetSkeletalMeshAsset(Body);
 GetMesh()->SetRelativeLocationAndRotation(FVector(0,0,-90),FRotator(0,180,0));
 auto Load=[&](const TCHAR* Name)->UAnimSequence*{auto* Clip=LoadObject<UAnimSequence>(nullptr,*Path(Name));return Clip && Clip->GetSkeleton()==Body->GetSkeleton()?Clip:nullptr;};
 IdleClip=Load(TEXT("idle"));RunClip=Load(TEXT("run"));AttackClip=Load(TEXT("attack"));HitClip=Load(TEXT("hit"));DeathClip=Load(TEXT("death"));
 GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
 if(IdleClip) GetMesh()->PlayAnimation(IdleClip,true);
 GetMesh()->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
 // numbers from the original critter class tables
 Powers->ClassName=RankClass; Powers->Level=InLevel;
 Powers->DisplayName=Faction+(RankClass.Contains(TEXT("Boss"))?TEXT(" Boss"):RankClass.Contains(TEXT("Lt_"))?TEXT(" Lieutenant"):TEXT(""));
 if(const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this))
  if(const FCoHClassDef* C=DB->FindClass(RankClass)) AttackDamage=FMath::Max(1.f,-C->TableValue(TEXT("Melee_Damage"),InLevel));
 Powers->InitStats();
 SpawnDefaultController();
}
void ACoHCombatEnemy::ApplyVillain(const FString& VillainName,int32 InLevel)
{
 const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this);
 const FCoHVillainDef* V=DB?DB->Villains.Find(VillainName):nullptr;
 if(!V) return;
 Villain=VillainName;
 Powers->SetClassAndLevel(V->Class,InLevel);
 Powers->DisplayName=V->Name.Replace(TEXT("_"),TEXT(" "));
 Attacks.Reset(); Powers->Tray.Reset(); Powers->Tray.SetNum(10);
 int32 Auto=0;
 for(const FName& Id:V->Powers)
 {
  const FCoHPowerDef* P=DB->FindPower(Id); if(!P) continue;
  if(P->Type==TEXT("kAuto")){ if(Auto<10) Powers->Tray[Auto++]=Id; }
  else if(P->Type==TEXT("kClick") && P->Target==TEXT("kFoe")) Attacks.Add(Id);
 }
}
FName ACoHCombatEnemy::PickAttack(float Distance,float& OutReach) const
{
 // the strongest ready attack that reaches; OutReach = reach of the shortest
 // one, so the villain knows how close to get
 const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this);
 FName Best; float BestScore=-1; OutReach=0;
 if(!DB) return Best;
 for(const FName& Id:Attacks)
 {
  const FCoHPowerDef* P=DB->FindPower(Id); if(!P) continue;
  const float Reach=FMath::Max(P->Range,7.f)*30.48f+60.f;
  OutReach=OutReach<=0?Reach:FMath::Min(OutReach,Reach);
  if(Reach<Distance || Powers->RechargeLeft(Id)>0.f || Powers->Endurance<P->EndCost) continue;
  float Score=0; for(const FCoHMod& M:P->Mods) if(M.Aspect==TEXT("kAbs")) Score+=FMath::Abs(M.Scale);
  if(Score>BestScore){BestScore=Score;Best=Id;}
 }
 return Best;
}
void ACoHCombatEnemy::OnHurt(AActor* Causer)
{
 if(APawn* P=Cast<APawn>(Causer)) Target=P;
 if(bRagdoll || IsDead()) return;
 GetWorldTimerManager().ClearTimer(AttackTimer);GetWorldTimerManager().ClearTimer(ReactionTimer);
 if(auto* AI=Cast<AAIController>(GetController()))AI->StopMovement();
 SetState(ECoHEnemyState::Hit);
 GetWorldTimerManager().SetTimer(ReactionTimer,this,&ACoHCombatEnemy::FinishReaction,HitClip ? FMath::Max(.2f,HitClip->GetPlayLength()) : .35f,false);
}
void ACoHCombatEnemy::OnDefeated(AActor* Causer)
{
 if(IsDead()) return;
 GetWorldTimerManager().ClearTimer(AttackTimer);GetWorldTimerManager().ClearTimer(ReactionTimer);
 if(auto* AI=Cast<AAIController>(GetController()))AI->StopMovement();
 SetState(ECoHEnemyState::Dead);GetCharacterMovement()->DisableMovement();GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);SetLifeSpan(10.f);
 FVector Away=Causer ? GetActorLocation()-Causer->GetActorLocation() : GetActorForwardVector();
 Away.Z=0; LaunchRagdoll(Away.GetSafeNormal()*240.f+FVector(0,0,120.f));
}
void ACoHCombatEnemy::OnMezzed(float Seconds)
{
 GetWorldTimerManager().ClearTimer(AttackTimer);
 if(auto* AI=Cast<AAIController>(GetController()))AI->StopMovement();
 GetCharacterMovement()->StopMovementImmediately();
 if(!bRagdoll && !IsDead()) SetState(ECoHEnemyState::Idle);
}
void ACoHCombatEnemy::Aggro(APawn* Who){ if(Who) Target=Who; }
void ACoHCombatEnemy::PlayAttackAnimation(){ if(AttackClip && !bRagdoll && !IsDead()) GetMesh()->PlayAnimation(AttackClip,false); }
void ACoHCombatEnemy::InitializeFromPreview(AActor* Preview,const TMap<FString,FString>& Clips)
{
 Home=GetActorLocation();
 auto* Source=Preview->FindComponentByClass<USkeletalMeshComponent>();
 if (!Source) return;
 GetMesh()->SetSkeletalMeshAsset(Source->GetSkeletalMeshAsset());
 GetMesh()->SetRelativeLocation(FVector(0,0,-90));
 GetMesh()->SetRelativeScale3D(Source->GetComponentScale());
 // CoH exports carry a 180-degree facing correction in their preview actor.
 GetMesh()->SetRelativeRotation(FRotator(0,180,0));
 for(int32 i=0;i<Source->GetNumMaterials();++i) GetMesh()->SetMaterial(i,Source->GetMaterial(i));
 auto Load=[&](const TCHAR* Name)->UAnimSequence* {
  const FString* Path=Clips.Find(Name);
  auto* Clip=Path ? LoadObject<UAnimSequence>(nullptr,**Path) : nullptr;
  return Clip && Clip->GetSkeleton()==Source->GetSkeletalMeshAsset()->GetSkeleton() ? Clip : nullptr;
 };
 IdleClip=Load(TEXT("idle"));RunClip=Load(TEXT("run"));AttackClip=Load(TEXT("attack"));HitClip=Load(TEXT("hit"));DeathClip=Load(TEXT("death"));
 GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
 if(IdleClip) GetMesh()->PlayAnimation(IdleClip,true);
 GetMesh()->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
 SpawnDefaultController();
}
bool ACoHCombatEnemy::CanSee(APawn* Pawn) const
{
 if(!Pawn) return false;
 FHitResult Hit;FCollisionQueryParams Params(SCENE_QUERY_STAT(CoHEnemySight),false,this);
 const FVector Eye=GetActorLocation()+FVector(0,0,55);
 return !GetWorld()->LineTraceSingleByChannel(Hit,Eye,Pawn->GetActorLocation(),ECC_Visibility,Params) || Hit.GetActor()==Pawn;
}
void ACoHCombatEnemy::SetState(ECoHEnemyState Next)
{
 if(State==Next) return;
 State=Next;
 UAnimSequence* Clip=Next==ECoHEnemyState::Chase || Next==ECoHEnemyState::ReturnHome ? RunClip : Next==ECoHEnemyState::Attack ? AttackClip : Next==ECoHEnemyState::Hit ? HitClip : Next==ECoHEnemyState::Dead ? DeathClip : IdleClip;
 if(!Clip) Clip=IdleClip;
 if(Clip) GetMesh()->PlayAnimation(Clip,Next==ECoHEnemyState::Idle || Next==ECoHEnemyState::Chase || Next==ECoHEnemyState::ReturnHome);
}
void ACoHCombatEnemy::Tick(float Delta)
{
 Super::Tick(Delta);
 if(bRagdoll || State==ECoHEnemyState::Dead || State==ECoHEnemyState::Hit || State==ECoHEnemyState::Attack) return;
 auto* AI=Cast<AAIController>(GetController()); if(!AI) return;
 if(Powers && Powers->IsMezzed()){AI->StopMovement();return;}
 // the nearest player (any of the group) is who we care about
 APawn* Player=nullptr; float Best=TNumericLimits<float>::Max();
 for(FConstPlayerControllerIterator It=GetWorld()->GetPlayerControllerIterator();It;++It)
 {
  APawn* P=It->Get()?It->Get()->GetPawn():nullptr; const UCoHPowerComponent* C=UCoHPowerComponent::Of(P);
  if(!P || (C && C->IsDefeated())) continue;
  const float D=FVector::DistSquared(P->GetActorLocation(),GetActorLocation()); if(D<Best){Best=D;Player=P;}
 }
 if(Target && (!IsValid(Target) || (UCoHPowerComponent::Of(Target) && UCoHPowerComponent::Of(Target)->IsDefeated()))) Target=nullptr;
 if(!IsValid(Player)) return;
 if(FVector::DistSquared(GetActorLocation(),Home)>FMath::Square(LeashRange) || (Target && FVector::DistSquared(Player->GetActorLocation(),Home)>FMath::Square(LeashRange*1.2f)))
 {Target=nullptr;SetState(ECoHEnemyState::ReturnHome);}
 if(State==ECoHEnemyState::ReturnHome)
 {
  if(FVector::DistSquared(GetActorLocation(),Home)<FMath::Square(110.f)){AI->StopMovement();SetState(ECoHEnemyState::Idle);}
  else if(GetWorld()->GetTimeSeconds()>NextPathTime){AI->MoveToLocation(Home,50);NextPathTime=GetWorld()->GetTimeSeconds()+.5;}
  return;
 }
 if(!Target && FVector::DistSquared(Player->GetActorLocation(),GetActorLocation())<FMath::Square(AggroRange) && CanSee(Player)) Target=Player;
 if(Target && Target!=Player && FVector::DistSquared(Target->GetActorLocation(),Home)>FMath::Square(LeashRange*1.2f)) Target=nullptr;
 if(!Target)
 {
  // idle: drift back to (a possibly moved) home, so groups wander together
  if(FVector::DistSquared2D(GetActorLocation(),Home)>FMath::Square(300.f)){SetState(ECoHEnemyState::ReturnHome);return;}
  SetState(ECoHEnemyState::Idle);return;
 }
 const float Distance=FVector::Dist(GetActorLocation(),Target->GetActorLocation());
 if(Attacks.Num())
 {
  // villain from the rules: use its own powers (range, recharge, endurance)
  float Reach=0; const FName Use=PickAttack(Distance,Reach);
  const bool bInReach=Reach>0 && Distance<=Reach && CanSee(Target);
  if(bInReach)
  {
   AI->StopMovement();GetCharacterMovement()->StopMovementImmediately();
   FVector Aim=Target->GetActorLocation()-GetActorLocation();Aim.Z=0;SetActorRotation(Aim.Rotation());
   if(!Use.IsNone() && GetWorld()->GetTimeSeconds()>=NextAttackTime)
   {
    const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this);
    const FCoHPowerDef* P=DB?DB->FindPower(Use):nullptr;
    const float Cast=P?FMath::Max(.5f,P->Activate):1.f;
    SetState(ECoHEnemyState::Attack);
    Powers->ServerActivate(Use,Target,Target->GetActorLocation());
    NextAttackTime=GetWorld()->GetTimeSeconds()+Cast+0.4f;
    GetWorldTimerManager().SetTimer(ReactionTimer,this,&ACoHCombatEnemy::FinishReaction,Cast,false);
   }
   else SetState(ECoHEnemyState::Idle);
  }
  else
  {
   SetState(ECoHEnemyState::Chase);
   if(GetWorld()->GetTimeSeconds()>=NextPathTime){AI->MoveToActor(Target,FMath::Max(80.f,(Reach>0?Reach:AttackRange)*.7f));NextPathTime=GetWorld()->GetTimeSeconds()+.4;}
  }
  return;
 }
 if(Distance<=AttackRange && CanSee(Target))
 {
  AI->StopMovement();GetCharacterMovement()->StopMovementImmediately();
  FVector Aim=Target->GetActorLocation()-GetActorLocation();Aim.Z=0;SetActorRotation(Aim.Rotation());
  if(GetWorld()->GetTimeSeconds()>=NextAttackTime)
  {
   SetState(ECoHEnemyState::Attack);NextAttackTime=GetWorld()->GetTimeSeconds()+AttackCooldown;
   const float Duration=AttackClip ? FMath::Max(.35f,AttackClip->GetPlayLength()) : .8f;
   GetWorldTimerManager().SetTimer(AttackTimer,this,&ACoHCombatEnemy::LandAttack,Duration*.4f,false);
   GetWorldTimerManager().SetTimer(ReactionTimer,this,&ACoHCombatEnemy::FinishReaction,Duration,false);
  }
  else SetState(ECoHEnemyState::Idle);
 }
 else
 {
  SetState(ECoHEnemyState::Chase);
  if(GetWorld()->GetTimeSeconds()>=NextPathTime){AI->MoveToActor(Target,AttackRange*.7f);NextPathTime=GetWorld()->GetTimeSeconds()+.4;}
 }
}
void ACoHCombatEnemy::LandAttack()
{
 if(State==ECoHEnemyState::Attack && IsValid(Target) && FVector::Dist(GetActorLocation(),Target->GetActorLocation())<=AttackRange+30 && CanSee(Target))
  UGameplayStatics::ApplyDamage(Target,AttackDamage,GetController(),this,UDamageType::StaticClass());
}
void ACoHCombatEnemy::FinishReaction(){if(!bRagdoll && State!=ECoHEnemyState::Dead)SetState(ECoHEnemyState::Idle);}
float ACoHCombatEnemy::TakeDamage(float Damage,const FDamageEvent& Event,AController* EventInstigator,AActor* Causer)
{
 // everything goes through the power component (resistances, defeat, numbers)
 if(IsDead() || Damage<=0 || !Powers)return 0;
 AActor* Who=EventInstigator && EventInstigator->GetPawn() ? EventInstigator->GetPawn() : Causer;
 const float Done=Powers->ApplyDamage(Damage,ECoHDamage::Smashing,Who);
 Health=Powers->Health;
 return Done;
}
ACoHCombatDirector::ACoHCombatDirector(){PrimaryActorTick.bCanEverTick=true;PrimaryActorTick.TickInterval=.5f;}
void ACoHCombatDirector::BeginPlay()
{
 Super::BeginPlay();FString Json;TSharedPtr<FJsonObject> Root;
 if(FFileHelper::LoadFileToString(Json,*(FPaths::ProjectContentDir()/CatalogRelativePath)) && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json),Root))
  for(const auto& Entry:Root->Values)
  {const auto& Object=Entry.Value->AsObject();if(!Object)continue;TMap<FString,FString> Clips;for(const auto& C:Object->Values){FString Path;if(C.Value->TryGetString(Path))Clips.Add(FString(C.Key),Path);}Catalog.Add(FString(Entry.Key),MoveTemp(Clips));}
 UE_LOG(LogTemp,Log,TEXT("CoH combat director loaded %d animation sets"),Catalog.Num());
}
void ACoHCombatDirector::Tick(float Delta)
{
 Super::Tick(Delta);APawn* Player=UGameplayStatics::GetPlayerPawn(this,0);if(!Player)return;
 for(auto It=Active.CreateIterator();It;++It)
 {
  AActor* Preview=It.Key().Get();ACoHCombatEnemy* Enemy=It.Value().Get();
  if(Enemy && Enemy->IsDead())Defeated.Add(It.Key());
  if(!Enemy || FVector::DistSquared(Enemy->GetActorLocation(),Player->GetActorLocation())>FMath::Square(ActivationRadius+1200))
  {if(Enemy)Enemy->Destroy();if(Preview && !Defeated.Contains(It.Key()))Preview->SetActorHiddenInGame(false);It.RemoveCurrent();}
 }
 struct FCandidate{AActor* Actor;float Distance;};TArray<FCandidate> Candidates;
 for(TActorIterator<AActor> It(GetWorld());It;++It)
 {
  AActor* A=*It;if(!A->ActorHasTag(TEXT("CoHCombatCandidate")) || A->IsHidden() || Active.Contains(A) || Defeated.Contains(A))continue;
  const float D=FVector::DistSquared(A->GetActorLocation(),Player->GetActorLocation());if(D<FMath::Square(ActivationRadius))Candidates.Add({A,D});
 }
 Candidates.Sort([](const FCandidate& A,const FCandidate& B){return A.Distance<B.Distance;});
 auto* Nav=FNavigationSystem::GetCurrent<UNavigationSystemV1>(GetWorld());
 for(const auto& Candidate:Candidates)
 {
  if(Active.Num()>=MaxActiveEnemies || !Nav)break;
  AActor* Preview=Candidate.Actor;FString Costume;
  for(const FName& Tag:Preview->Tags){const FString S=Tag.ToString();if(S.StartsWith(TEXT("Costume_")))Costume=S.Mid(8);}
  const auto* Clips=Catalog.Find(Costume);if(!Clips)continue;
  FNavLocation Ground;if(!Nav->ProjectPointToNavigation(Preview->GetActorLocation(),Ground,FVector(150,150,200)))continue;
  FActorSpawnParameters Params;Params.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButDontSpawnIfColliding;
  auto* Enemy=GetWorld()->SpawnActor<ACoHCombatEnemy>(Ground.Location+FVector(0,0,92),FRotator(0,Preview->GetActorRotation().Yaw-180,0),Params);
  if(!Enemy)continue;Enemy->InitializeFromPreview(Preview,*Clips);Preview->SetActorHiddenInGame(true);Active.Add(Preview,Enemy);
 }
 ActiveCount=Active.Num();
}
void ACoHCombatDirector::EndPlay(const EEndPlayReason::Type Reason)
{
 for(auto& Pair:Active){if(Pair.Key.IsValid() && !Defeated.Contains(Pair.Key))Pair.Key->SetActorHiddenInGame(false);if(Pair.Value.IsValid())Pair.Value->Destroy();}
 Active.Empty();Super::EndPlay(Reason);
}

void ACoHCombatEnemy::BeginPlay()
{
 Super::BeginPlay();
 Home=GetActorLocation();
 SpawnDefaultController();
 GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
 if (IdleClip) GetMesh()->PlayAnimation(IdleClip,true);
}

void ACoHCombatEnemy::LaunchRagdoll(FVector LaunchVelocity)
{
 USkeletalMeshComponent* BodyMesh = GetMesh();
 UPhysicsAsset* Physics = BodyMesh->GetPhysicsAsset();
 if (!Physics || Physics->SkeletalBodySetups.Num()==0)
 {
  UE_LOG(LogTemp, Warning, TEXT("CoH ragdoll unavailable: %s has no physics bodies"), *GetName());
  if (!IsDead()) LaunchCharacter(LaunchVelocity,true,true);
  return;
 }
 GetWorldTimerManager().ClearTimer(AttackTimer);
 GetWorldTimerManager().ClearTimer(ReactionTimer);
 if (auto* AI=Cast<AAIController>(GetController())) AI->StopMovement();
 GetCharacterMovement()->StopMovementImmediately();
 GetCharacterMovement()->DisableMovement();
 GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
 BodyMesh->SetCollisionProfileName(TEXT("Ragdoll"));
 BodyMesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
 BodyMesh->SetEnableGravity(true);
 BodyMesh->SetAllBodiesSimulatePhysics(true);
 BodyMesh->WakeAllRigidBodies();
 BodyMesh->AddImpulse(LaunchVelocity,NAME_None,true);
 bRagdoll=true;
 RagdollStarted=GetWorld()->GetTimeSeconds();
 if (!IsDead()) GetWorldTimerManager().SetTimer(RagdollTimer,this,&ACoHCombatEnemy::RecoverRagdoll,1.f,false);
}
void ACoHCombatEnemy::RecoverRagdoll()
{
 if (IsDead()) return;
 USkeletalMeshComponent* BodyMesh=GetMesh();
 const FVector Body=BodyMesh->GetBoneLocation(BodyMesh->GetBoneName(0));
 FHitResult Floor;
 FCollisionQueryParams Params(SCENE_QUERY_STAT(CoHRagdollLanding),false,this);
 const bool bFloor=GetWorld()->LineTraceSingleByChannel(Floor,Body+FVector(0,0,40),Body-FVector(0,0,220),ECC_Visibility,Params) && Floor.ImpactNormal.Z>.5f;
 const bool bSettled=BodyMesh->GetPhysicsLinearVelocity().Size()<160.f;
 if ((!bFloor || !bSettled) && GetWorld()->GetTimeSeconds()-RagdollStarted<8.f)
 {
  GetWorldTimerManager().SetTimer(RagdollTimer,this,&ACoHCombatEnemy::RecoverRagdoll,.25f,false);
  return;
 }
 BodyMesh->SetAllBodiesSimulatePhysics(false);
 BodyMesh->SetSimulatePhysics(false);
 BodyMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
 BodyMesh->AttachToComponent(GetCapsuleComponent(),FAttachmentTransformRules::KeepRelativeTransform);
 BodyMesh->SetRelativeLocationAndRotation(FVector(0,0,-90),FRotator(0,180,0));
 FVector Destination=bFloor ? Floor.ImpactPoint+FVector(0,0,92) : Home;
 FHitResult Block;
 if (GetWorld()->SweepSingleByChannel(Block,Destination,Destination,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(36,90),Params)) Destination=Home;
 SetActorLocation(Destination,false,nullptr,ETeleportType::TeleportPhysics);
 GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
 GetCharacterMovement()->SetMovementMode(MOVE_Falling);
 bRagdoll=false;
 State=ECoHEnemyState::Hit;
 SetState(ECoHEnemyState::Idle);
}

bool ACoHCombatEnemy::EnsureRagdollPhysics(USkeletalMesh* BodyMesh)
{
#if WITH_EDITOR
 if (!BodyMesh) return false;
 if (BodyMesh->GetPhysicsAsset() && BodyMesh->GetPhysicsAsset()->SkeletalBodySetups.Num()>0) return true;
 const FString PackageName=FString(TEXT("/Game/CoH/Combat/Physics/PA_"))+BodyMesh->GetName();
 UPackage* Package=CreatePackage(*PackageName);
 const FName Name(*(FString(TEXT("PA_"))+BodyMesh->GetName()));
 UPhysicsAsset* Physics=FindObject<UPhysicsAsset>(Package,*Name.ToString());
 if (!Physics) Physics=NewObject<UPhysicsAsset>(Package,Name,RF_Public|RF_Standalone|RF_Transactional);
 FPhysAssetCreateParams Params; Params.MinBoneSize=8.f;
 FText Error;
 if (!FPhysicsAssetUtils::CreateFromSkeletalMesh(Physics,BodyMesh,Params,Error,true,false)) { UE_LOG(LogTemp,Error,TEXT("Ragdoll generation failed: %s"),*Error.ToString()); return false; }
 FAssetRegistryModule::AssetCreated(Physics);
 Physics->MarkPackageDirty(); BodyMesh->MarkPackageDirty();
 return Physics->SkeletalBodySetups.Num()>0;
#else
 return false;
#endif
}

// ------------------------------------------------------------------ spawner
ACoHEnemySpawner::ACoHEnemySpawner()
{
 PrimaryActorTick.bCanEverTick=true; PrimaryActorTick.TickInterval=1.f;
 Factions.Add(TEXT("Hellions"),3.f); Factions.Add(TEXT("Skulls"),3.f); Factions.Add(TEXT("Clockwork"),2.f);
 Factions.Add(TEXT("Outcasts"),2.f); Factions.Add(TEXT("Vahzilok"),1.5f); Factions.Add(TEXT("Arachnos"),0.5f);
}
void ACoHEnemySpawner::BeginPlay()
{
 Super::BeginPlay();
 FString Json;TSharedPtr<FJsonObject> Root;
 if(FFileHelper::LoadFileToString(Json,*(FPaths::ProjectContentDir()/CatalogRelativePath)) && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json),Root))
  for(const auto& F:Root->Values)
   for(const auto& E:F.Value->AsArray())
   {
    TMap<FString,FString> Entry; for(const auto& KV:E->AsObject()->Values) Entry.Add(FString(KV.Key),KV.Value->AsString());
    Catalog.FindOrAdd(FString(F.Key)).Add(MoveTemp(Entry));
   }
 UE_LOG(LogTemp,Log,TEXT("CoH enemy spawner: %d factions in the catalog"),Catalog.Num());
}
static bool OpenGround(UWorld* W,FVector XY,FVector& Out)
{
 // a spot on the landscape or a street, not a roof or inside a building
 FHitResult Hit;FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHSpawnGround),false);
 if(!W->LineTraceSingleByChannel(Hit,FVector(XY.X,XY.Y,30000.f),FVector(XY.X,XY.Y,-5000.f),ECC_Visibility,Q)) return false;
 const AActor* A=Hit.GetActor();
 if(!A || !A->GetClass()->GetName().Contains(TEXT("Landscape"))) return false;
 if(Hit.ImpactPoint.Z< -50.f) return false;      // under the bay
 Out=Hit.ImpactPoint;return true;
}
const TMap<FString,FString>& ACoHEnemySpawner::BodyFor(const FCoHVillainDef* V,int32 Level,const TArray<TMap<FString,FString>>& Members) const
{
 // the villain's own costumes at that level (Thug_Hellion_01...) when we have the mesh
 if(V)
  if(const TArray<FString>* Names=V->CostumesAt(Level))
  {
   TArray<const TMap<FString,FString>*> Match;
   for(const auto& M:Members) for(const FString& N:*Names) if(M.FindRef(TEXT("name")).Equals(N,ESearchCase::IgnoreCase)) Match.Add(&M);
   if(Match.Num()) return *Match[FMath::RandRange(0,Match.Num()-1)];
  }
 return Members[FMath::RandRange(0,Members.Num()-1)];
}
bool ACoHEnemySpawner::SpawnGroup(APawn* Near)
{
 UWorld* W=GetWorld();
 float Total=0; for(const auto& F:Factions) if(Catalog.Contains(F.Key)) Total+=F.Value;
 if(Total<=0) return false;
 float Pick=FMath::FRand()*Total; FString Faction;
 for(const auto& F:Factions){ if(!Catalog.Contains(F.Key)) continue; Pick-=F.Value; if(Pick<=0){Faction=F.Key;break;} }
 if(Faction.IsEmpty()) return false;
 FVector Center; bool bFound=false;
 for(int32 Try=0;Try<12 && !bFound;++Try)
 {
  const FVector Dir=FVector(FMath::FRandRange(-1.f,1.f),FMath::FRandRange(-1.f,1.f),0).GetSafeNormal();
  bFound=OpenGround(W,Near->GetActorLocation()+Dir*FMath::FRandRange(MinDistance,MaxDistance),Center);
 }
 if(!bFound) return false;
 const UCoHPowerComponent* PC=UCoHPowerComponent::Of(Near);
 const int32 Base=PC?PC->Level:5;
 const auto& Members=Catalog[Faction];
 FGroup G; G.Faction=Faction; G.Center=Center; G.NextWander=W->GetTimeSeconds()+FMath::FRandRange(20.f,40.f);
 const int32 Count=FMath::RandRange(3,5);
 for(int32 i=0;i<Count;++i)
 {
  FVector At; if(!OpenGround(W,Center+FVector(FMath::FRandRange(-400.f,400.f),FMath::FRandRange(-400.f,400.f),0),At)) At=Center;
  FActorSpawnParameters P;P.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
  auto* E=W->SpawnActor<ACoHCombatEnemy>(At+FVector(0,0,95),FRotator(0,FMath::FRandRange(0.f,360.f),0),P);
  if(!E) continue;
  // the villain: the group's leader is a lieutenant (sometimes a boss), the
  // rest minions, all from this faction's definitions in the rules
  const FString Want=i==0 ? (FMath::FRand()<0.12f?TEXT("Boss"):TEXT("Lieutenant")) : TEXT("Minion");
  TArray<const FCoHVillainDef*> Pool;
  if(const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this))
   for(const auto& KV:DB->Villains) if(KV.Value.Group==Faction && KV.Value.Rank==Want && KV.Value.Powers.Num()) Pool.Add(&KV.Value);
  const int32 Lvl=FMath::Max(1,Base+FMath::RandRange(-LevelBelow,LevelAbove)+(i==0?1:0));
  const FCoHVillainDef* Who=Pool.Num()?Pool[FMath::RandRange(0,Pool.Num()-1)]:nullptr;
  E->InitializeFromCatalog(BodyFor(Who,Lvl,Members),Faction,Who?Who->Class:TEXT("Class_Minion_Grunt"),Lvl);
  if(Who) E->ApplyVillain(Who->Name,Lvl);
  if(i==0)
  {
   // the group's own nav mesh, so it can walk wherever it was put
   auto* Inv=NewObject<UNavigationInvokerComponent>(E); Inv->SetGenerationRadii(2500.f,3500.f); Inv->RegisterComponent();
  }
  G.Members.Add(E);
 }
 if(G.Members.Num()==0) return false;
 Groups.Add(MoveTemp(G));
 return true;
}
void ACoHEnemySpawner::Tick(float Delta)
{
 Super::Tick(Delta);
 if(!HasAuthority()) return;
 UWorld* W=GetWorld(); const double Now=W->GetTimeSeconds();
 TArray<APawn*> Players;
 for(FConstPlayerControllerIterator It=W->GetPlayerControllerIterator();It;++It) if(It->Get() && It->Get()->GetPawn()) Players.Add(It->Get()->GetPawn());
 if(Players.Num()==0) return;
 for(int32 g=Groups.Num()-1;g>=0;--g)
 {
  FGroup& G=Groups[g];
  G.Members.RemoveAll([](const TWeakObjectPtr<ACoHCombatEnemy>& E){return !E.IsValid() || E->IsDead();});
  float Nearest=TNumericLimits<float>::Max();
  for(APawn* P:Players) Nearest=FMath::Min(Nearest,(float)FVector::Dist(P->GetActorLocation(),G.Center));
  if(G.Members.Num()==0 || Nearest>DespawnDistance)
  {
   for(auto& E:G.Members) if(E.IsValid()) E->Destroy();
   Groups.RemoveAt(g); continue;
  }
  if(Now>G.NextWander)
  {
   FVector To; const FVector Dir=FVector(FMath::FRandRange(-1.f,1.f),FMath::FRandRange(-1.f,1.f),0).GetSafeNormal();
   if(OpenGround(W,G.Center+Dir*FMath::FRandRange(800.f,2500.f),To))
   {
    G.Center=To;
    for(auto& E:G.Members) if(E.IsValid()) E->SetHome(To+FVector(FMath::FRandRange(-300.f,300.f),FMath::FRandRange(-300.f,300.f),0));
   }
   G.NextWander=Now+FMath::FRandRange(25.f,45.f);
  }
 }
 AliveGroups=Groups.Num();
 if(bSpawning && Groups.Num()<MaxGroups && Now>=NextSpawn)
 {
  SpawnGroup(Players[FMath::RandRange(0,Players.Num()-1)]);
  NextSpawn=Now+2.0;
 }
}
void ACoHEnemySpawner::EndPlay(const EEndPlayReason::Type Reason)
{
 for(auto& G:Groups) for(auto& E:G.Members) if(E.IsValid()) E->Destroy();
 Groups.Empty(); Super::EndPlay(Reason);
}

void ACoHEnemySpawner::SetSpawning(bool bOn)
{
 bSpawning=bOn;
 if(!bOn){ for(auto& G:Groups) for(auto& E:G.Members) if(E.IsValid()) E->Destroy(); Groups.Empty(); }
}
ACoHCombatEnemy* ACoHEnemySpawner::SpawnVillainNear(const FString& VillainName,int32 Level,APawn* Near,float Distance)
{
 const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this);
 const FCoHVillainDef* V=DB?DB->Villains.Find(VillainName):nullptr;
 if(!V || !Near) return nullptr;
 const auto* Members=Catalog.Find(V->Group);
 if(!Members || Members->Num()==0) return nullptr;
 // open ground in front of the player (not a roof or a tree)
 FVector At=Near->GetActorLocation();
 bool bFound=false;
 for(int32 Try=0;Try<16 && !bFound;++Try)
 {
  const FVector Dir=Try==0?Near->GetActorForwardVector():FVector(FMath::FRandRange(-1.f,1.f),FMath::FRandRange(-1.f,1.f),0).GetSafeNormal();
  bFound=OpenGround(GetWorld(),Near->GetActorLocation()+Dir*Distance,At);
 }
 if(!bFound) return nullptr;
 FActorSpawnParameters P;P.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
 auto* E=GetWorld()->SpawnActor<ACoHCombatEnemy>(At+FVector(0,0,95),(Near->GetActorLocation()-At).Rotation(),P);
 if(!E) return nullptr;
 E->InitializeFromCatalog(BodyFor(V,Level,*Members),V->Group,V->Class,Level);
 E->ApplyVillain(VillainName,Level);
 auto* Inv=NewObject<UNavigationInvokerComponent>(E); Inv->SetGenerationRadii(2500.f,3500.f); Inv->RegisterComponent();
 FGroup G; G.Faction=V->Group; G.Center=At; G.Members.Add(E); G.NextWander=GetWorld()->GetTimeSeconds()+1e6; Groups.Add(MoveTemp(G));
 return E;
}

#include "CoHCombat.h"
#include "CoHPowers.h"
#include "CoHBodyAnim.h"
#include "CoHGameRules.h"
#include "CoHHeroProgress.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "CoHLifeManager.h"
#include "GameFramework/PlayerController.h"
#include "AIController.h"
#include "Animation/AnimSequence.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "EngineUtils.h"
#include "Navigation/PathFollowingComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "NavigationSystem.h"
#include "NavigationData.h"
#include "NavigationInvokerComponent.h"
#include "EngineUtils.h"
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
 // turning is smooth: the controller's focus (the target, or the path while
 // walking) turns the pawn every frame at RotationRate instead of snapping
 GetCharacterMovement()->bOrientRotationToMovement=false;
 GetCharacterMovement()->bUseControllerDesiredRotation=true;
 GetCharacterMovement()->RotationRate=FRotator(0,420,0);
 bUseControllerRotationYaw=false;
 GetCharacterMovement()->MaxWalkSpeed=360;
 Tags.Add(TEXT("CoHCombatEnemy"));
 Powers=CreateDefaultSubobject<UCoHPowerComponent>(TEXT("Powers"));
 Powers->bPlayerSide=false;
 Powers->ClassName=TEXT("Class_Minion_Grunt");
 Powers->Level=5;
}
void ACoHCombatEnemy::InitializeFromCatalog(const TMap<FString,FString>& Entry,const FString& FactionName,const FString& RankClass,int32 InLevel)
{
 Home=GetActorLocation();
 auto Path=[&](const TCHAR* K){const FString* P=Entry.Find(K);return P?*P:FString();};
 USkeletalMesh* Body=LoadObject<USkeletalMesh>(nullptr,*Path(TEXT("mesh")));
 if(!Body) return;
 GetMesh()->SetSkeletalMeshAsset(Body);
 // the original villain meshes face -Y in their rest pose, and their
 // animations turn the body round to +Y: in motion they face +Y, so a -90
 // turn makes them face the way the villain moves and aims (checked with the
 // nose bone while animating)
 MeshYaw=-90.f;
 GetMesh()->SetRelativeLocationAndRotation(FVector(0,0,-90),FRotator(0,MeshYaw,0));
 auto Load=[&](const TCHAR* Name)->UAnimSequence*{auto* Clip=LoadObject<UAnimSequence>(nullptr,*Path(Name));return Clip && Clip->GetSkeleton()==Body->GetSkeleton()?Clip:nullptr;};
 IdleClip=Load(TEXT("idle"));RunClip=Load(TEXT("run"));AttackClip=Load(TEXT("attack"));HitClip=Load(TEXT("hit"));DeathClip=Load(TEXT("death"));
 GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
 if(IdleClip) GetMesh()->PlayAnimation(IdleClip,true);
 GetMesh()->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
 // numbers from the original critter class tables
 Powers->ClassName=RankClass; Powers->Level=InLevel;
 Faction=FactionName;
 Powers->DisplayName=FactionName+(RankClass.Contains(TEXT("Boss"))?TEXT(" Boss"):RankClass.Contains(TEXT("Lt_"))?TEXT(" Lieutenant"):TEXT(""));
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
 AIConfigName=V->AIConfig;
 Rank=V->Rank;
 // the leash: the config's protect-spawn radius plus the distance allowed
 // outside it (100 + 20 ft by default) with some slack for the chase
 const FCoHAIConfig& Cfg=DB->AIConfig(V->AIConfig);
 LeashRange=(Cfg.ProtectSpawnRadius+Cfg.ProtectSpawnOutsideRadius)*30.48f+1500.f;
 AggroRange=1800.f;
 IdleBehavior=FMath::FRand()<0.5f?TEXT("Loiter"):TEXT("Wander");
 IdleUntil=GetWorld()->GetTimeSeconds()+FMath::FRandRange(0.f,6.f);
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
 // support villains (runes, healers) still swing when cornered, and so run the full brain
 if(Attacks.Num()==0 && DB->FindPower(TEXT("Inherent.Inherent.Brawl"))) Attacks.Add(TEXT("Inherent.Inherent.Brawl"));
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
void ACoHCombatEnemy::OnHurt(AActor* Causer,float Damage)
{
 if(APawn* P=Cast<APawn>(Causer))
 {
  const bool bNew=!Threat.Contains(P);
  Threat.FindOrAdd(P)+=FMath::Max(1.f,Damage);
  LastEvent.Add(P,GetWorld()->GetTimeSeconds());
  bReturning=false;
  if(bNew) Shout(P);
  if(!Target) Target=P;
 }
 if(bRagdoll || IsDead()) return;
 GetWorldTimerManager().ClearTimer(AttackTimer);GetWorldTimerManager().ClearTimer(ReactionTimer);
 if(auto* AI=Cast<AAIController>(GetController()))AI->StopMovement();
 // every hit flinches: SetState skips an unchanged state, so a second hit
 // during the first flinch restarts the clip here
 if(State==ECoHEnemyState::Hit && HitClip) PlayClip(HitClip,false);
 if(UCoHBodyAnim* BA=BodyAnim()) BA->StopSegments();
 SetState(ECoHEnemyState::Hit);
 GetWorldTimerManager().SetTimer(ReactionTimer,this,&ACoHCombatEnemy::FinishReaction,HitClip ? FMath::Max(.2f,HitClip->GetPlayLength()) : .35f,false);
}
void ACoHCombatEnemy::OnDefeated(AActor* Causer)
{
 if(IsDead()) return;
 UCoHHeroProgress::RewardDefeat(Powers,Rank.IsEmpty()?TEXT("Minion"):Rank,Faction);
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
void ACoHCombatEnemy::PlayAttackAnimation(){ if(AttackClip && !bRagdoll && !IsDead()) PlayClip(AttackClip,false); }
UCoHBodyAnim* ACoHCombatEnemy::BodyAnim() const
{
 return GetMesh()->GetAnimationMode()==EAnimationMode::AnimationBlueprint ? Cast<UCoHBodyAnim>(GetMesh()->GetAnimInstance()) : nullptr;
}
void ACoHCombatEnemy::PlayClip(UAnimSequence* Clip,bool bLoop,float Rate)
{
 if(!Clip) return;
 if(UCoHBodyAnim* BA=BodyAnim()){ BA->SetBase(Clip,bLoop,Rate); return; }
 GetMesh()->PlayAnimation(Clip,bLoop);
 GetMesh()->SetPlayRate(Rate);
}
bool ACoHCombatEnemy::InitializeFromKit(const FString& VillainName,int32 InLevel)
{
 const UCoHGameRules* R=UCoHGameRules::Get(this);
 const FCoHKitVillain* K=R?R->Kit(VillainName):nullptr;
 if(!K) return false;
 // the villain's own model (the first costume exported), clips named after moves
 USkeletalMesh* Body=nullptr; FString Model;
 IAssetRegistry& AR=FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry").Get();
 TArray<FString> Order=K->Models;
 for(int32 i=Order.Num()-1;i>0;--i) Order.Swap(i,FMath::RandRange(0,i));      // a random costume of the villain
 for(const FString& M:Order)
 {
  TArray<FAssetData> Found; AR.GetAssetsByPath(FName(*(R->EnemyRoot/M)),Found,true);
  for(const FAssetData& D:Found) if(D.IsInstanceOf(USkeletalMesh::StaticClass())){ Body=Cast<USkeletalMesh>(D.GetAsset()); break; }
  if(Body){ Model=M; break; }
 }
 if(!Body) return false;
 Home=GetActorLocation();
 KitModel=Model;
 GetMesh()->SetSkeletalMeshAsset(Body);
 // the same facing as the earlier villain exports (they face +Y in motion)
 MeshYaw=-90.f;
 GetMesh()->SetRelativeLocationAndRotation(FVector(0,0,-90),FRotator(0,MeshYaw,0));
 const FString Folder=R->EnemyRoot/Model;
 auto Load=[&](const TCHAR* Name){ return Cast<UAnimSequence>(R->ClipIn(Folder,Name)); };
 IdleClip=Load(TEXT("idle"));RunClip=Load(TEXT("run"));AttackClip=Load(TEXT("attack"));HitClip=Load(TEXT("hit"));DeathClip=Load(TEXT("death"));
 GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
 GetMesh()->SetAnimInstanceClass(UCoHBodyAnim::StaticClass());
 if(UCoHBodyAnim* BA=BodyAnim()){ BA->bAutoLocomotion=false; BA->SetBase(IdleClip,true); }
 GetMesh()->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
 Faction=K->Group;
 Powers->Body=K->SeqType;
 ApplyVillain(VillainName,InLevel);
 if(Villain.IsEmpty())
 {
  // not in villains.json: numbers from the critter class
  Villain=VillainName; Rank=K->Rank; Powers->SetClassAndLevel(K->Class,InLevel); Powers->DisplayName=VillainName.Replace(TEXT("_"),TEXT(" "));
 }
 SpawnDefaultController();
 return true;
}
bool ACoHCombatEnemy::PlayPowerMoves(FName Power)
{
 const UCoHGameRules* R=UCoHGameRules::Get(this);
 const FCoHKitVillain* K=R?R->Kit(Villain):nullptr;
 UCoHBodyAnim* BA=BodyAnim();
 if(!K || !BA || KitModel.IsEmpty() || bRagdoll || IsDead()) return false;
 const FCoHPowerAnim* A=R->VillainPowerAnim(Villain,Power);
 TArray<FCoHAnimSegment> Segs;
 if(!A || (!R->VillainSegments(*K,KitModel,*A,TEXT("AttackBits"),Segs) && !R->VillainSegments(*K,KitModel,*A,TEXT("ActivationBits"),Segs))) return false;
 BA->PlaySegments(Segs);
 return true;
}
void ACoHCombatEnemy::SetEncounterIdle(const FString& Behavior)
{
 EncounterIdle=Behavior;
 ProtectUntil=0;
}
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
 if(UCoHBodyAnim* BA=BodyAnim())
 {
  // a power's moves run over the attack state; a hit or defeat cuts them
  if(Next==ECoHEnemyState::Hit || Next==ECoHEnemyState::Dead) BA->StopSegments();
  if(Next==ECoHEnemyState::Attack) return;
 }
 if(Clip) PlayClip(Clip,Next==ECoHEnemyState::Idle || Next==ECoHEnemyState::Chase || Next==ECoHEnemyState::ReturnHome);
}
void ACoHCombatEnemy::Tick(float Delta)
{
 Super::Tick(Delta);
 if((State==ECoHEnemyState::Chase || State==ECoHEnemyState::ReturnHome) && !bRagdoll && RunClip)
  { const float Rate=FMath::Clamp(GetVelocity().Size2D()/380.f,0.35f,1.4f); if(UCoHBodyAnim* BA=BodyAnim()) BA->SetBase(RunClip,true,Rate); else GetMesh()->SetPlayRate(Rate); }
 if(bRagdoll || State==ECoHEnemyState::Dead || State==ECoHEnemyState::Hit || State==ECoHEnemyState::Attack) return;
 auto* AI=Cast<AAIController>(GetController()); if(!AI) return;
 if(Powers && Powers->IsMezzed()){AI->StopMovement();return;}
 if(Think(Delta,AI)) return;
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
   AI->SetFocus(Target);
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
  AI->SetFocus(Target);
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
 if(!BodyAnim())
 {
  GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
  if (IdleClip) GetMesh()->PlayAnimation(IdleClip,true);
 }
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
 BodyMesh->SetRelativeLocationAndRotation(FVector(0,0,-90),FRotator(0,MeshYaw,0));
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


// ------------------------------------------------------------------ brain (rules villains)
void ACoHCombatEnemy::Taunt(APawn* Who,float Seconds)
{
 if(!Who) return;
 TauntedBy=Who; TauntUntil=GetWorld()->GetTimeSeconds()+Seconds;
 Threat.FindOrAdd(Who)+=100.f;
 Target=Who;
}
void ACoHCombatEnemy::Alert(APawn* Who)
{
 if(!Who || IsDead()) return;
 Threat.FindOrAdd(Who)+=1.f;
 if(!Target) Target=Who;
}
void ACoHCombatEnemy::Shout(APawn* Who)
{
 // call for help (AI config: ShoutChance % to each friend within ShoutRadius;
 // the spawn group always hears it)
 const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this);
 const FCoHAIConfig& Cfg=DB?DB->AIConfig(AIConfigName):FCoHAIConfig();
 for(TActorIterator<ACoHCombatEnemy> It(GetWorld());It;++It)
 {
  ACoHCombatEnemy* F=*It;
  if(F==this || F->IsDead() || F->Target) continue;
  const bool bGroup=GroupId!=INDEX_NONE && F->GroupId==GroupId;
  const bool bNear=FVector::Dist(F->GetActorLocation(),GetActorLocation())<=Cfg.ShoutRadius*30.48f;
  if(bGroup || (bNear && FMath::FRand()*100.f<Cfg.ShoutChance)) F->Alert(Who);
 }
}
APawn* ACoHCombatEnemy::ChooseTarget()
{
 const double Now=GetWorld()->GetTimeSeconds();
 auto Valid=[](APawn* P){ const UCoHPowerComponent* C=UCoHPowerComponent::Of(P); return IsValid(P) && (!C || !C->IsDefeated()); };
 if(TauntedBy.IsValid() && Now<TauntUntil && Valid(TauntedBy.Get())) return TauntedBy.Get();
 // highest threat (damage done to me, decaying), ties to the nearest
 APawn* Best=nullptr; float BestT=-1;
 for(auto It=Threat.CreateIterator();It;++It)
 {
  APawn* P=It.Key().Get();
  if(!Valid(P) || FVector::DistSquared(P->GetActorLocation(),Home)>FMath::Square(LeashRange*1.3f))
  {
   UE_LOG(LogTemp,Log,TEXT("CoH AI %s drops %s: %s (%.0f m from home)"),*GetName(),*GetNameSafe(P),Valid(P)?TEXT("too far from home"):TEXT("gone or defeated"),P?FVector::Dist(P->GetActorLocation(),Home)/100.f:0.f);
   It.RemoveCurrent(); continue;
  }
  const float T=It.Value()-FVector::Dist(P->GetActorLocation(),GetActorLocation())*0.0001f;
  if(T>BestT){BestT=T;Best=P;}
 }
 return Best;
}
bool ACoHCombatEnemy::UseSupportPower(const TCHAR* Group)
{
 const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this);
 if(!DB) return false;
 const FCoHVillainDef* V=DB->Villains.Find(Villain);
 if(!V) return false;
 for(const FName& Id:V->Powers)
 {
  const FCoHPowerDef* P=DB->FindPower(Id);
  if(!P || !P->AIGroups.Contains(Group) || P->Type==TEXT("kAuto") || Powers->RechargeLeft(Id)>0.f || Powers->Endurance<P->EndCost) continue;
  if(P->Type==TEXT("kToggle") && Powers->IsToggleOn(Id)) continue;
  Powers->ServerActivate(Id,this,GetActorLocation());
  return true;
 }
 return false;
}
bool ACoHCombatEnemy::Think(float Delta,AAIController* AI)
{
 // villains from the rules: perception with a field of view, shouting for
 // help, threat and taunt, attack choice by the AI config's melee / ranged
 // preference, ranged standoff, support powers and running away when hurt
 const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this);
 if(!DB || Attacks.Num()==0) return false;
 const FCoHAIConfig& Cfg=DB->AIConfig(AIConfigName);
 const double Now=GetWorld()->GetTimeSeconds();
 for(auto& KV:Threat) KV.Value*=FMath::Pow(0.95f,Delta);      // threat fades ~5% a second
 // notice players in front (field of view) and within aggro range
 for(FConstPlayerControllerIterator It=GetWorld()->GetPlayerControllerIterator();It;++It)
 {
  APawn* P=It->Get()?It->Get()->GetPawn():nullptr; const UCoHPowerComponent* C=UCoHPowerComponent::Of(P);
  if(!P || (C && C->IsDefeated()) || bReturning) continue;
  const FVector To=P->GetActorLocation()-GetActorLocation();
  if(To.Size()>AggroRange) continue;
  const float Ang=FMath::RadiansToDegrees(FMath::Acos(FVector::DotProduct(To.GetSafeNormal2D(),GetActorForwardVector())));
  if((!Threat.Contains(P) && Ang>Cfg.FOVDegrees*0.5f) || !CanSee(P)) continue;
  LastEvent.Add(P,Now);
  if(Threat.Contains(P)) continue;
  Threat.Add(P,1.f);
  Shout(P);
 }
 for(auto It=Threat.CreateIterator();It;++It)
 {
  const UCoHPowerComponent* TC=UCoHPowerComponent::Of(It.Key().Get());
  int32& D=DefeatsSeen.FindOrAdd(It.Key(),TC?TC->Defeats:0);
  if(TC && TC->Defeats!=D){ DefeatsSeen.Remove(It.Key()); LastEvent.Remove(It.Key()); It.RemoveCurrent(); continue; }
  const double* Seen=LastEvent.Find(It.Key());
  if(Seen && Now-*Seen>Cfg.EventMemoryDuration){ LastEvent.Remove(It.Key()); It.RemoveCurrent(); }
 }
 APawn* Was=Target;
 Target=ChooseTarget();
 if(!Target)
 {
  if(Was)
  {
   // lost the fight's target: go back and guard the spawn for ProtectSpawnTime
   bReturning=FVector::Dist2D(GetActorLocation(),Home)>300.f;
   ProtectUntil=Now+Cfg.ProtectSpawnTime;
  }
  bFled=false; bBuffed=false; bCalledHelp=false;
  if(HarassRole==0) AI->ClearFocus(EAIFocusPriority::Gameplay);
  if(HarassRole!=0 && Harass(AI,Now)) return true;
  Idle(AI,Now);
  return true;
 }
 GetCharacterMovement()->MaxWalkSpeed=360.f;
 if(HarassRole!=0 || bHarassPosed){ HarassRole=0; bHarassPosed=false; GetMesh()->SetPlayRate(1.f); }
 if(Target!=Was && !Was) Shout(Target);
 const float Distance=FVector::Dist(GetActorLocation(),Target->GetActorLocation());
 // leashed too far from home: give up and go back
 // a helper on its way to the caller is not leashed until it gets there
 if(bHelping && FVector::DistSquared(GetActorLocation(),Home)<FMath::Square(LeashRange*0.5f)) bHelping=false;
 if(!bHelping && FVector::DistSquared(GetActorLocation(),Home)>FMath::Square(LeashRange))
 {
  Threat.Reset(); LastEvent.Reset(); Target=nullptr; Thought=TEXT("going home");
  bReturning=true; ProtectUntil=Now+Cfg.ProtectSpawnTime;
  UE_LOG(LogTemp,Log,TEXT("CoH AI %s leashed: %.0f m from home"),*GetName(),FVector::Dist(GetActorLocation(),Home)/100.f);
  SetState(ECoHEnemyState::ReturnHome); GoTo(Home,50); NextPathTime=Now+.5;
  return true;
 }
 // hurt: call every villain within 500 ft for help (once per fight)
 const float HPNow=Powers->MaxHealth>0?Powers->Health/Powers->MaxHealth:1.f;
 if(!bCalledHelp && HPNow<0.7f)
 {
  bCalledHelp=true; CallForHelp(Target,500.f);
  Thought=TEXT("calling for help");
 }
 // hurt badly: some minions run for it (grief), once per fight
 const float HP=Powers->MaxHealth>0?Powers->Health/Powers->MaxHealth:1.f;
 if(!bFled && !Powers->ClassName.Contains(TEXT("Boss")) && HP<1.f-Cfg.GriefHPRatio && FMath::FRand()<Cfg.Fear*2.f)
 {
  bFled=true; FleeUntil=Now+FMath::FRandRange(Cfg.GriefTimeBegin,Cfg.GriefTimeEnd)*0.4f;
 }
 if(Now<FleeUntil)
 {
  Thought=TEXT("fleeing");
  AI->ClearFocus(EAIFocusPriority::Gameplay);
  SetState(ECoHEnemyState::Chase);
  if(Now>NextPathTime)
  {
   const FVector Away=(GetActorLocation()-Target->GetActorLocation()).GetSafeNormal2D();
   AI->MoveToLocation(GetActorLocation()+Away*1200.f,100); NextPathTime=Now+1.0;
  }
  return true;
 }
 // support powers: buffs and toggles once the fight starts, a self heal when low
 if(Now>=NextSupportTime && Now>=NextAttackTime)
 {
  NextSupportTime=Now+2.0;
  if((!bBuffed && (UseSupportPower(TEXT("kBuff")) || UseSupportPower(TEXT("kToggleDefense")))) || (HP<0.5f && UseSupportPower(TEXT("kHealSelf"))))
  {
   bBuffed=true; Thought=TEXT("support power"); NextAttackTime=Now+1.2; return true;
  }
  bBuffed=true;
 }
 // attack: the config's preference weights melee or ranged powers
 FName Use; float Reach=0, BestScore=-1, MinReach=0, MaxReach=0;
 for(const FName& Id:Attacks)
 {
  const FCoHPowerDef* P=DB->FindPower(Id); if(!P) continue;
  const float R=FMath::Max(P->Range,7.f)*30.48f+60.f;
  MinReach=MinReach<=0?R:FMath::Min(MinReach,R); MaxReach=FMath::Max(MaxReach,R);
  if(R<Distance || Powers->RechargeLeft(Id)>0.f || Powers->Endurance<P->EndCost) continue;
  float Score=0; for(const FCoHMod& M:P->Mods) if(M.Aspect==TEXT("kAbs")) Score+=FMath::Abs(M.Scale);
  const bool bMeleePower=P->IsMelee();
  const bool bRangedRank=Cfg.bPreferRanged || Rank==TEXT("Lieutenant");
  if(Cfg.bPreferMelee && bMeleePower) Score*=Cfg.MeleeScale;
  if(bRangedRank && !bMeleePower) Score*=FMath::Max(Cfg.RangedScale,2.f);
  if(bRangedRank && bMeleePower) Score*=0.25f;
  // area and lingering powers (Molotov, grenades) by their AI group or area:
  // worth using whenever they are ready, whatever their small damage
  if(P->Area!=TEXT("kCharacter") || P->AIGroups.Num()) Score=FMath::Max(Score,0.8f);
  if(Id==LastAttack) Score*=0.6f;
  Score*=FMath::FRandRange(0.75f,1.25f);
  if(Score>BestScore){BestScore=Score;Use=Id;Reach=R;}
 }
 const bool bRangedStyle=Cfg.bPreferRanged || Rank==TEXT("Lieutenant") || (!Cfg.bPreferMelee && MaxReach>800.f && Distance>MinReach);
 const float Standoff=FMath::Max(Cfg.Standoff*30.48f,500.f);
 FVector Aim=Target->GetActorLocation()-GetActorLocation();Aim.Z=0;
 if(!Use.IsNone() && CanSee(Target))
 {
  // ranged villains keep their distance: step back when crowded, but shoot first
  if(bRangedStyle && Distance<Standoff*0.6f && MaxReach>Standoff && !Cfg.bDoNotMove && FMath::FRand()<0.5f)
  {
   Thought=TEXT("backing off"); SetState(ECoHEnemyState::Chase);
   if(Now>NextPathTime){AI->MoveToLocation(GetActorLocation()-Aim.GetSafeNormal()*Standoff,80);NextPathTime=Now+0.8;}
   return true;
  }
  AI->StopMovement();GetCharacterMovement()->StopMovementImmediately();
  AI->SetFocus(Target);
  if(Now>=NextAttackTime)
  {
   const FCoHPowerDef* P=DB->FindPower(Use);
   const float Cast=P?FMath::Max(.5f,P->Activate):1.f;
   Thought=FString::Printf(TEXT("attacking with %s"),*Use.ToString());
   SetState(ECoHEnemyState::Attack);
   Powers->ServerActivate(Use,Target,Target->GetActorLocation());
   LastAttack=Use;
   LastEvent.Add(Target,Now);
   NextAttackTime=Now+Cast+0.4f;
   GetWorldTimerManager().SetTimer(ReactionTimer,this,&ACoHCombatEnemy::FinishReaction,Cast,false);
  }
  else { Thought=TEXT("waiting for recharge"); SetState(ECoHEnemyState::Idle); }
  return true;
 }
 // ranged villains in reach of their longest power wait for it instead of walking in
 if(bRangedStyle && Distance<=MaxReach && CanSee(Target))
 {
  AI->StopMovement(); AI->SetFocus(Target);
  Thought=TEXT("holding range, recharging"); SetState(ECoHEnemyState::Idle); return true;
 }
 // close in: ranged villains stop at their standoff, melee ones get close
 if(Cfg.bDoNotMove){ SetState(ECoHEnemyState::Idle); Thought=TEXT("holding position"); return true; }
 Thought=FString::Printf(TEXT("closing in (%.0f m, nav %s)"),Distance/100.f,AI->GetPathFollowingComponent() && AI->GetPathFollowingComponent()->GetStatus()==EPathFollowingStatus::Moving?TEXT("moving"):TEXT("no path")); SetState(ECoHEnemyState::Chase);
 const float Want=bRangedStyle?FMath::Min(MaxReach*0.8f,FMath::Max(Standoff,MinReach*0.8f)):FMath::Max(80.f,MinReach*0.7f);
 if(Now>=NextPathTime){GoToActor(Target,Want);NextPathTime=Now+.4;}
 return true;
}

// ------------------------------------------------------------------ spawner

void ACoHCombatEnemy::GoTo(const FVector& Where,float Acceptance)
{
 auto* AI=Cast<AAIController>(GetController()); if(!AI) return;
 if(AI->MoveToLocation(Where,Acceptance)==EPathFollowingRequestResult::Failed)
  AI->MoveToLocation(Where,Acceptance,true,false,false); // straight line: no path, no projection onto the nav mesh
}
void ACoHCombatEnemy::GoToActor(AActor* Who,float Acceptance)
{
 auto* AI=Cast<AAIController>(GetController()); if(!AI || !Who) return;
 if(AI->MoveToActor(Who,Acceptance)==EPathFollowingRequestResult::Failed)
  AI->MoveToLocation(Who->GetActorLocation(),Acceptance,true,false,false);
}
void ACoHCombatEnemy::CallForHelp(APawn* Who,float RadiusFeet)
{
 // every villain within the radius joins (OldCallForHelp: Radius(500))
 for(TActorIterator<ACoHCombatEnemy> It(GetWorld());It;++It)
 {
  ACoHCombatEnemy* F=*It;
  if(F==this || F->IsDead() || F->Target || F->Faction!=Faction) continue;
  if(FVector::Dist(F->GetActorLocation(),GetActorLocation())<=RadiusFeet*30.48f)
  {
   // helpers come to the caller: the fight there becomes their home ground,
   // and they carry their own nav mesh so they can path all the way
   F->Home=GetActorLocation(); F->bReturning=false; F->ProtectUntil=0; F->bHelping=true;
   if(!F->FindComponentByClass<UNavigationInvokerComponent>())
   {
    auto* Inv=NewObject<UNavigationInvokerComponent>(F); Inv->SetGenerationRadii(2500.f,3500.f); Inv->RegisterComponent();
   }
   F->Alert(Who);
  }
 }
}
void ACoHCombatEnemy::Idle(AAIController* AI,double Now)
{
 // no one to fight: walk home first, guard the spawn for a while after a
 // chase, then the idle routine from behavior_aliases (Loiter / Wander)
 const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this);
 const FCoHIdleRecipe& R=DB?DB->IdleRecipe(IdleBehavior):FCoHIdleRecipe();
 const float FromHome=FVector::Dist2D(GetActorLocation(),Home);
 if(bReturning || FromHome>R.Radius*30.48f+400.f)
 {
  if(FromHome<200.f){ bReturning=false; AI->StopMovement(); SetState(ECoHEnemyState::Idle); IdleUntil=Now+FMath::FRandRange(R.StandMin,R.StandMax); bIdleWalking=false; return; }
  Thought=FString::Printf(TEXT("%s (%.0f m to go)"),bReturning?TEXT("going home"):TEXT("rejoining the group"),FromHome/100.f);
  GetCharacterMovement()->MaxWalkSpeed=360.f;
  SetState(ECoHEnemyState::ReturnHome);
  if(Now>NextPathTime){GoTo(Home,80);NextPathTime=Now+.6;}
  return;
 }
 if(!EncounterIdle.IsEmpty() && FromHome<=R.Radius*30.48f+400.f)
 {
  // the original encounter idle (AI_InActive): stay and play its moves
  Thought=FString::Printf(TEXT("idle: %s"),*EncounterIdle);
  if(State!=ECoHEnemyState::Idle){AI->StopMovement();SetState(ECoHEnemyState::Idle);}
  UCoHBodyAnim* BA=BodyAnim();
  const UCoHGameRules* GR=UCoHGameRules::Get(this);
  const FCoHKitVillain* K=GR?GR->Kit(Villain):nullptr;
  const TArray<FString>* Moves=K?K->IdleMoves(EncounterIdle):nullptr;
  if(BA && Moves && !BA->IsPlayingSegments())
  {
   TArray<FCoHAnimSegment> Segs;
   if(GR->MoveSegments(KitModel,*Moves,Segs)) BA->PlaySegments(Segs);
  }
  return;
 }
 if(Now<ProtectUntil){ Thought=TEXT("guarding its spot"); if(State!=ECoHEnemyState::Idle){AI->StopMovement();SetState(ECoHEnemyState::Idle);} return; }
 if(Now<IdleUntil)
 {
  Thought=bIdleWalking?FString::Printf(TEXT("%s: strolling"),*IdleBehavior):FString::Printf(TEXT("%s: standing (%s)"),*IdleBehavior,*R.StandAnim);
  if(bIdleWalking && AI->GetPathFollowingComponent() && AI->GetPathFollowingComponent()->GetStatus()!=EPathFollowingStatus::Moving) SetState(ECoHEnemyState::Idle);
  return;
 }
 if(!bIdleWalking)
 {
  // stroll to a random reachable spot within the recipe radius of home
  FNavLocation To;
  auto* Nav=FNavigationSystem::GetCurrent<UNavigationSystemV1>(GetWorld());
  if(Nav && Nav->GetRandomReachablePointInRadius(Home,R.Radius*30.48f,To))
  {
   GetCharacterMovement()->MaxWalkSpeed=150.f;      // a walk, not the combat run
   AI->MoveToLocation(To.Location,40);
   SetState(ECoHEnemyState::ReturnHome);            // plays the move clip
  }
  bIdleWalking=true; IdleUntil=Now+FMath::FRandRange(R.WalkMin,R.WalkMax);
 }
 else
 {
  AI->StopMovement(); SetState(ECoHEnemyState::Idle);
  bIdleWalking=false; IdleUntil=Now+FMath::FRandRange(R.StandMin,R.StandMax);
 }
}


bool ACoHCombatEnemy::Harass(AAIController* AI,double Now)
{
 // the grabber stands at the civilian holding them, the other leans in and threatens
 const FVector To=HarassSpot-GetActorLocation();
 const float Want=HarassRole==1?110.f:230.f;
 if(To.Size2D()>Want+60.f)
 {
  Thought=HarassRole==1?TEXT("going to grab a civilian"):TEXT("joining the shakedown");
  bHarassPosed=false;
  GetCharacterMovement()->MaxWalkSpeed=200.f;
  SetState(ECoHEnemyState::ReturnHome);
  if(Now>NextPathTime){GoTo(HarassSpot,Want);NextPathTime=Now+.5;}
  return true;
 }
 AI->StopMovement();
 AI->SetFocalPoint(HarassSpot);
 if(!bHarassPosed && AttackClip)
 {
  // placeholder poses until proper clips exist: the attack clip held at its
  // reach (grab) or played slowly on a loop (threaten). State stays Idle so
  // the brain keeps looking around while posing.
  bHarassPosed=true; State=ECoHEnemyState::Idle;
  if(BodyAnim()) PlayClip(AttackClip,true,HarassRole==1?0.f:0.35f);
  else
  {
   GetMesh()->PlayAnimation(AttackClip,HarassRole==2);
   if(HarassRole==1){ GetMesh()->SetPosition(AttackClip->GetPlayLength()*0.4f); GetMesh()->SetPlayRate(0.f); }
   else GetMesh()->SetPlayRate(0.35f);
  }
 }
 Thought=HarassRole==1?TEXT("holding a civilian"):TEXT("threatening a civilian");
 return true;
}

float ACoHCombatEnemy::ScatterChance(APawn* Hero) const
{
 const UCoHPowerComponent* H=UCoHPowerComponent::Of(Hero);
 if(!H || !Powers) return 0.f;
 // level gap: nothing until the hero is 3+ levels above, then 5% a level
 float C=FMath::Max(0,H->Level-Powers->Level-2)*0.05f;
 // reputation (vigilantes) / notoriety (heroes): up to +25%
 C+=FMath::Clamp(H->Reputation,0.f,1.f)*0.25f;
 // lieutenants and bosses are steadier
 if(Rank==TEXT("Lieutenant")) C*=0.6f; else if(Rank!=TEXT("Minion")) C*=0.25f;
 return FMath::Clamp(C,0.f,0.9f);
}

bool ACoHCombatEnemy::ShouldScatter(APawn* Hero) const
{
 return ACoHEnemySpawner::bMoraleOn && FMath::FRand()<ScatterChance(Hero);
}

void ACoHEnemySpawner::TickHarassment(double Now)
{
 // an idle gang picks one civilian walking within ~20 m, one villain grabs,
 // one threatens; the civilian cowers. 30-60 s later (no hero near) they let
 // go and the civilian flees; a fight lets them go at once and the
 // civilian thanks the hero and runs
 ACoHLifeManager* Life=ACoHLifeManager::Get(this);
 if(!Life) return;
 for(FGroup& G:Groups)
 {
  TArray<ACoHCombatEnemy*> Free;
  bool bFighting=false;
  for(auto& E:G.Members) if(E.IsValid() && !E->IsDead()){ if(E->Target) bFighting=true; else Free.Add(E.Get()); }
  if(G.bHolding)
  {
   AActor* Hero=nullptr;
   for(auto& E:G.Members) if(E.IsValid() && E->Target){ Hero=E->Target; break; }
   const bool bDone=bFighting || Now>G.HarassUntil || Free.Num()<2 || !bCivilianHarassment;
   if(bDone)
   {
    Life->ReleaseCivilian(G.Victim,G.Id,G.Center,Hero);
    for(auto& E:G.Members) if(E.IsValid()){ if(E->bHarassPosed && !E->Target){ E->GetMesh()->SetPlayRate(1.f); E->State=ECoHEnemyState::Hit; E->SetState(ECoHEnemyState::Idle); } E->HarassRole=0; E->bHarassPosed=false; }
    G.bHolding=false; G.Victim=INDEX_NONE; G.NextHarass=Now+FMath::FRandRange(40.f,90.f);
    continue;
   }
   // renew the hold once the grabber has reached them
   ACoHCombatEnemy* Grabber=nullptr; for(ACoHCombatEnemy* E:Free) if(E->HarassRole==1) Grabber=E;
   if(Grabber && FVector::Dist2D(Grabber->GetActorLocation(),Life->CivilianLocation(G.Victim))<260.f)
    Life->HoldCivilian(G.Victim,G.Id,Grabber->GetActorLocation(),3.f);
   else if(Grabber) Life->HoldCivilian(G.Victim,G.Id,Grabber->GetActorLocation(),3.f);   // freeze them as the grabber walks up
   continue;
  }
  if(!bCivilianHarassment || bFighting || Free.Num()<2 || Now<G.NextHarass) continue;
  G.NextHarass=Now+5.0;
  const int32 Civ=Life->FindCivilianNear(G.Center,2000.f);
  if(Civ==INDEX_NONE) continue;
  const FVector Spot=Life->CivilianLocation(Civ);
  bool bBlocked=false; for(const FVector& Z:NoSpawn) if(FVector::Dist2D(Spot,FVector(Z.X,Z.Y,0))<Z.Z) bBlocked=true;
  if(bBlocked) continue;
  if(!Life->HoldCivilian(Civ,G.Id,Free[0]->GetActorLocation(),3.f)) continue;
  G.bHolding=true; G.Victim=Civ; G.HarassUntil=Now+FMath::FRandRange(30.f,60.f);
  // grabber: a minion if there is one; threatener: the next
  Free.Sort([](const ACoHCombatEnemy& A,const ACoHCombatEnemy& B){ return (A.Rank==TEXT("Minion"))>(B.Rank==TEXT("Minion")); });
  Free[0]->HarassRole=1; Free[0]->HarassSpot=Spot;
  Free[1]->HarassRole=2; Free[1]->HarassSpot=Spot;
 }
}

bool ACoHEnemySpawner::bMoraleOn=true;

ACoHEnemySpawner::ACoHEnemySpawner()
{
 PrimaryActorTick.bCanEverTick=true; PrimaryActorTick.TickInterval=1.f;
 Factions.Add(TEXT("Hellions"),3.f); Factions.Add(TEXT("Skulls"),3.f); Factions.Add(TEXT("Clockwork"),2.f);
 Factions.Add(TEXT("Outcasts"),2.f); Factions.Add(TEXT("Vahzilok"),1.5f); Factions.Add(TEXT("Arachnos"),0.5f);
}
TArray<FVector> ACoHEnemySpawner::NoSpawn;
void ACoHEnemySpawner::BeginPlay()
{
 Super::BeginPlay();
 NoSpawn=NoSpawnZones;
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
static float GOpenGroundRefZ=TNumericLimits<float>::Max();
static bool OpenGround(UWorld* W,FVector XY,FVector& Out)
{
 // a spot on the landscape or a street, not a roof or inside a building
 FHitResult Hit;FCollisionQueryParams Q(SCENE_QUERY_STAT(CoHSpawnGround),false);
 for(const FVector& Z:ACoHEnemySpawner::NoSpawn) if(FVector::Dist2D(XY,FVector(Z.X,Z.Y,0))<Z.Z) return false;
 if(GOpenGroundRefZ<TNumericLimits<float>::Max())
 {
  // maps built from the original tiles have no landscape: the ground near
  // the player's street level (a short trace, so roofs above are skipped)
  if(!W->LineTraceSingleByChannel(Hit,FVector(XY.X,XY.Y,GOpenGroundRefZ+400.f),FVector(XY.X,XY.Y,GOpenGroundRefZ-1200.f),ECC_Visibility,Q)) return false;
  if(Hit.bStartPenetrating || Hit.ImpactNormal.Z<0.85f || Cast<APawn>(Hit.GetActor())) return false;
  Out=Hit.ImpactPoint;return true;
 }
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
bool ACoHEnemySpawner::SpawnGroup(APawn* Near,const FString& ForceFaction,int32 ForceLevel,float ForceDistance)
{
 UWorld* W=GetWorld();
 float Total=0; for(const auto& F:Factions) if(Catalog.Contains(F.Key)) Total+=F.Value;
 if(Total<=0) return false;
 float Pick=FMath::FRand()*Total; FString Faction;
 for(const auto& F:Factions){ if(!Catalog.Contains(F.Key)) continue; Pick-=F.Value; if(Pick<=0){Faction=F.Key;break;} }
 if(!ForceFaction.IsEmpty()) Faction=ForceFaction;
 if(Faction.IsEmpty() || !Catalog.Contains(Faction)) return false;
 FVector Center; bool bFound=false;
 for(int32 Try=0;Try<12 && !bFound;++Try)
 {
  const FVector Dir=FVector(FMath::FRandRange(-1.f,1.f),FMath::FRandRange(-1.f,1.f),0).GetSafeNormal();
  bFound=OpenGround(W,Near->GetActorLocation()+Dir*(ForceDistance>0?ForceDistance:FMath::FRandRange(MinDistance,MaxDistance)),Center);
 }
 if(!bFound) return false;
 const UCoHPowerComponent* PC=UCoHPowerComponent::Of(Near);
 const int32 Base=ForceLevel>0?ForceLevel:(PC?PC->Level:5);
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
   for(const auto& KV:DB->Villains)
    if(KV.Value.Group==Faction && KV.Value.Rank==Want && KV.Value.Powers.Num()
       && !KV.Key.Contains(TEXT("Trial")) && !KV.Key.Contains(TEXT("Tutorial")) && !KV.Key.Contains(TEXT("_TF")) && !KV.Key.Contains(TEXT("Event")))
     Pool.Add(&KV.Value);
  const int32 Lvl=FMath::Max(1,Base+FMath::RandRange(-LevelBelow,LevelAbove)+(i==0?1:0));
  const FCoHVillainDef* Who=Pool.Num()?Pool[FMath::RandRange(0,Pool.Num()-1)]:nullptr;
  E->InitializeFromCatalog(BodyFor(Who,Lvl,Members),Faction,Who?Who->Class:TEXT("Class_Minion_Grunt"),Lvl);
  if(Who) E->ApplyVillain(Who->Name,Lvl);
  if(i==0)
  {
   // the group's own nav mesh, so it can walk wherever it was put
   auto* Inv=NewObject<UNavigationInvokerComponent>(E); Inv->SetGenerationRadii(2500.f,3500.f); Inv->RegisterComponent();
  }
  E->GroupId=NextGroupId;
  G.Members.Add(E);
 }
 G.Id=NextGroupId; G.NextHarass=W->GetTimeSeconds()+FMath::FRandRange(5.f,20.f);
 ++NextGroupId;
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
   if(G.bHolding) if(ACoHLifeManager* Life=ACoHLifeManager::Get(this)) Life->ReleaseCivilian(G.Victim,G.Id,G.Center,nullptr);
   for(auto& E:G.Members) if(E.IsValid()) E->Destroy();
   Groups.RemoveAt(g); continue;
  }
  if(Now>G.NextWander && (bWanderingGangs || !G.bEncounter))
  {
   FVector To; const FVector Dir=FVector(FMath::FRandRange(-1.f,1.f),FMath::FRandRange(-1.f,1.f),0).GetSafeNormal();
   if(OpenGround(W,G.Center+Dir*FMath::FRandRange(800.f,2500.f),To))
   {
    G.Center=To;
    for(auto& E:G.Members) if(E.IsValid() && !E->IsBusy()) E->SetHome(To+FVector(FMath::FRandRange(-300.f,300.f),FMath::FRandRange(-300.f,300.f),0));
   }
   G.NextWander=Now+FMath::FRandRange(25.f,45.f);
  }
 }
 AliveGroups=Groups.Num();
 bMoraleOn=bMorale;
 TickHarassment(Now);
 // wandering gangs: a server setting (on by default), capped by the player
 // count so 7 players do not fill the zone
 const int32 Cap=FMath::Min(MaxGroups,FMath::Max(1,Players.Num())*GroupsPerPlayer);
 const UCoHGameRules* GR=UCoHGameRules::Get(this);
 const bool bEnc=bOriginalEncounters && GR && GR->Encounters.Num()>0;
 if(bSpawning && (bWanderingGangs || bEnc) && Groups.Num()<Cap && Now>=NextSpawn)
 {
  APawn* Near=Players[FMath::RandRange(0,Players.Num()-1)];
  if(bEnc)
  {
   // a zone spawn: a group and kind picked by how many original spots use them
   const UCoHPowerComponent* PC=UCoHPowerComponent::Of(Near);
   SpawnEncounter(Near,FString(),FString(),PC?PC->Level:1,FMath::FRandRange(MinDistance,MaxDistance));
  }
  else SpawnGroup(Near);
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

bool ACoHEnemySpawner::SpawnTestGroup(APawn* Near,const FString& Faction,int32 Level,float Distance,const FString& Kind)
{
 const UCoHGameRules* GR=UCoHGameRules::Get(this);
 if(bOriginalEncounters && GR && GR->Encounters.Num() && SpawnEncounter(Near,Faction,Kind,Level,Distance)) return true;
 return SpawnGroup(Near,Faction,Level,Distance);
}
ACoHCombatEnemy* ACoHEnemySpawner::SpawnKitVillain(const FString& VillainName,int32 Level,const FVector& At,const FRotator& Rot)
{
 FActorSpawnParameters P;P.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
 auto* E=GetWorld()->SpawnActor<ACoHCombatEnemy>(At+FVector(0,0,95),Rot,P);
 if(!E) return nullptr;
 if(E->InitializeFromKit(VillainName,Level)) return E;
 // model not imported: the earlier catalog mesh with the same rules
 const UCoHPowerDatabase* DB=UCoHPowerDatabase::Get(this);
 const FCoHVillainDef* V=DB?DB->Villains.Find(VillainName):nullptr;
 const auto* Members=V?Catalog.Find(V->Group):nullptr;
 if(!V || !Members || Members->Num()==0){ E->Destroy(); return nullptr; }
 E->InitializeFromCatalog(BodyFor(V,Level,*Members),V->Group,V->Class,Level);
 E->ApplyVillain(VillainName,Level);
 return E;
}
bool ACoHEnemySpawner::SpawnEncounter(APawn* Near,const FString& Group,const FString& Kind,int32 Level,float Distance)
{
 const UCoHGameRules* GR=UCoHGameRules::Get(this);
 UWorld* W=GetWorld();
 if(!GR || !Near || !W) return false;
 // spawn definitions of the group / kind at this level, weighted by the
 // number of spots in the zone's layers that use them (mission and named
 // spawns are left to their own systems)
 // Paragon Police and Freedom Corps are on the heroes' side in Atlas Park:
 // they are not spawned as foes (as allies fighting villains: later)
 static const TArray<FString> Friendly={TEXT("ParagonPolice"),TEXT("FreedomCorps"),TEXT("Objects"),TEXT("PraetorianAngryCitizens")};
 TArray<const FCoHEncounter*> Pool; int32 Total=0;
 for(const FCoHEncounter& E:GR->Encounters)
 {
  if(!Group.IsEmpty() && !E.Groups().Contains(Group)) continue;
  if(Group.IsEmpty() && !E.Groups().ContainsByPredicate([&](const FString& G){ return !Friendly.Contains(G); })) continue;
  if(!Kind.IsEmpty() ? !E.Kind.Equals(Kind,ESearchCase::IgnoreCase) : (E.Kind.Contains(TEXT("/")) || E.Kind.StartsWith(TEXT("mission")))) continue;
  if(Level<E.MinLevel-1 || Level>E.MaxLevel+1) continue;
  Pool.Add(&E); Total+=E.Spots;
 }
 if(Pool.Num()==0){ UE_LOG(LogTemp,Warning,TEXT("CoH encounters: none for %s %s at level %d"),*Group,*Kind,Level); return false; }
 int32 Roll=FMath::RandRange(0,Total-1); const FCoHEncounter* Enc=Pool.Last();
 for(const FCoHEncounter* E:Pool){ if((Roll-=E->Spots)<0){ Enc=E; break; } }
 // a spot: open ground at the distance asked (the new map's layout differs
 // from the original, so spots are placed around the players)
 FVector Center; bool bFound=false;
 struct FRef{ FRef(UWorld* W,const APawn* N){ bool bLand=false; for(TActorIterator<AActor> It(W);It && !bLand;++It) bLand=It->GetClass()->GetName().Contains(TEXT("Landscape"));
  GOpenGroundRefZ=bLand?TNumericLimits<float>::Max():N->GetActorLocation().Z-90.f; } ~FRef(){ GOpenGroundRefZ=TNumericLimits<float>::Max(); } } Ref(W,Near);
 for(int32 Try=0;Try<16 && !bFound;++Try)
 {
  const FVector Dir=Try==0?Near->GetActorForwardVector():FVector(FMath::FRandRange(-1.f,1.f),FMath::FRandRange(-1.f,1.f),0).GetSafeNormal();
  bFound=OpenGround(W,Near->GetActorLocation()+Dir*Distance,Center);
 }
 if(!bFound) return false;
 // team size: the heroes near the spot, within the definition's range
 int32 Heroes=0;
 for(FConstPlayerControllerIterator It=W->GetPlayerControllerIterator();It;++It)
  if(It->Get() && It->Get()->GetPawn() && FVector::Dist(It->Get()->GetPawn()->GetActorLocation(),Center)<6000.f) ++Heroes;
 const int32 Team=FMath::Clamp(FMath::Max(1,Heroes),Enc->MinTeam,Enc->MaxTeam);
 const int32 Lvl=FMath::Clamp(Level,Enc->MinLevel,Enc->MaxLevel);
 FGroup G; G.Faction=Group.IsEmpty()?(Enc->Groups().Num()?Enc->Groups()[0]:FString()):Group; G.Center=Center; G.bEncounter=true;
 G.NextWander=W->GetTimeSeconds()+FMath::FRandRange(25.f,45.f);
 int32 Slot=0;
 for(const FCoHEncounterActor& A:Enc->Actors)
 {
  if(Team<A.MinHeroes || Team>A.MaxHeroes || Friendly.Contains(A.Group)) continue;
  for(int32 n=0;n<A.Count;++n,++Slot)
  {
   FString Who=A.Villain;
   if(Who.IsEmpty())
   {
    // the slot's roll at this level (the nearest level listed)
    const TArray<FString>* Rolls=nullptr; int32 BestD=MAX_int32;
    for(const auto& KV:A.Rolls) if(KV.Value.Num() && FMath::Abs(KV.Key-Lvl)<BestD){ BestD=FMath::Abs(KV.Key-Lvl); Rolls=&KV.Value; }
    if(!Rolls) continue;
    Who=(*Rolls)[FMath::RandRange(0,Rolls->Num()-1)];
   }
   // a loose circle facing its middle, as the original spot layouts do
   const float Ang=Slot*2.1f;
   FVector At; if(!OpenGround(W,Center+FVector(FMath::Cos(Ang),FMath::Sin(Ang),0)*FMath::FRandRange(150.f,320.f),At)) At=Center;
   ACoHCombatEnemy* E=SpawnKitVillain(Who,Lvl,At,(Center-At).GetSafeNormal2D().Rotation());
   if(!E) continue;
   E->SetHome(At);
   E->SetEncounterIdle(A.AIInactive);
   if(G.Members.Num()==0){ auto* Inv=NewObject<UNavigationInvokerComponent>(E); Inv->SetGenerationRadii(2500.f,3500.f); Inv->RegisterComponent(); }
   E->GroupId=NextGroupId;
   G.Members.Add(E);
  }
 }
 if(G.Members.Num()==0) return false;
 UE_LOG(LogTemp,Log,TEXT("CoH encounter %s (%s) level %d team %d: %d villains"),*Enc->Name,*Enc->Kind,Lvl,Team,G.Members.Num());
 G.Id=NextGroupId++; G.NextHarass=W->GetTimeSeconds()+1e9;
 Groups.Add(MoveTemp(G));
 return true;
}

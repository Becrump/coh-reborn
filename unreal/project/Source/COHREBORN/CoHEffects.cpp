#include "CoHEffects.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/GameInstance.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "ProceduralMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "HAL/IConsoleManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"
#include "TimerManager.h"

static constexpr float Ft = 30.48f;          // feet -> cm
static constexpr float TickSeconds = 1.f / 30.f;
static float Rnd() { return FMath::FRandRange(-1.f, 1.f); }
// effect models in hand (weapons): their turn relative to the hand bone, and
// for free nodes relative to the node's facing, as "pitch,yaw,roll" (tuning)
static TAutoConsoleVariable<FString> CVarGeomBoneRot(TEXT("coh.GeomBoneRot"), TEXT("0,0,0"), TEXT("CoH effect models on a bone: relative rotation pitch,yaw,roll"));
static TAutoConsoleVariable<FString> CVarGeomNodeRot(TEXT("coh.GeomNodeRot"), TEXT("0,0,0"), TEXT("CoH effect models on a free node: relative rotation pitch,yaw,roll"));
static FRotator CVarRot(const TAutoConsoleVariable<FString>& V)
{
	TArray<FString> P; V.GetValueOnGameThread().ParseIntoArray(P, TEXT(","));
	return P.Num() >= 3 ? FRotator(FCString::Atof(*P[0]), FCString::Atof(*P[1]), FCString::Atof(*P[2])) : FRotator::ZeroRotator;
}
/** Game world axes (x, y up, z) -> Unreal (x forward, y right, z up). */
static FVector W(const FVector& G) { return FVector(G.Z, -G.X, G.Y); }
static FVector JitW(const FVector& J) { return W(FVector(J.X * Rnd(), J.Y * Rnd(), J.Z * Rnd())) * Ft; }

static FVector V3(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
{
	const TArray<TSharedPtr<FJsonValue>>* A;
	if (!O.IsValid() || !O->TryGetArrayField(K, A) || A->Num() < 3) return FVector::ZeroVector;
	return FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber());
}
static double Num(const TSharedPtr<FJsonObject>& O, const TCHAR* K, double D = 0)
{
	const TSharedPtr<FJsonValue> V = O.IsValid() ? O->TryGetField(K) : nullptr;
	if (!V.IsValid() || V->IsNull()) return D;
	if (V->Type == EJson::Array) return V->AsArray().Num() ? V->AsArray()[0]->AsNumber() : D;   // [full, low power]
	if (V->Type == EJson::String) return FCString::Atod(*V->AsString());
	return V->AsNumber();
}
static FString Str(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
{
	FString S;
	return O.IsValid() && O->TryGetStringField(K, S) ? S : FString();
}
static FString AssetName(const FString& File)
{
	FString S = FPaths::GetBaseFilename(File).ToLower();
	for (TCHAR& C : S) if (!FChar::IsAlnum(C) && C != TEXT('_')) C = TEXT('_');
	return S;
}

// ------------------------------------------------------------------ library
void UCoHFxLibrary::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	const double T0 = FPlatformTime::Seconds();
	if (FxDirs.Num() == 0)
	{
		FString Rules;
		GConfig->GetString(TEXT("/Script/COHREBORN.CoHPowerDatabase"), TEXT("RulesDir"), Rules, GGameIni);
		const FString Out = FPaths::GetPath(Rules);
		FxDirs = { Out / TEXT("fx"), Out / TEXT("enemies/fx") };
	}
	for (const FString& Dir : FxDirs)
	{
		FString Text;
		TSharedPtr<FJsonObject> Lib;
		if (!FFileHelper::LoadFileToString(Text, *(Dir / TEXT("fx_library.json")))) { UE_LOG(LogTemp, Warning, TEXT("CoH fx: no library in %s"), *Dir); continue; }
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Lib) || !Lib.IsValid()) continue;
		auto Take = [&](const TCHAR* Key, TMap<FString, TSharedPtr<FJsonObject>>& Into)
		{
			const TSharedPtr<FJsonObject>* Sub;
			if (Lib->TryGetObjectField(Key, Sub))
				for (const auto& KV : (*Sub)->Values) if (KV.Value->Type == EJson::Object && !Into.Contains(FString(KV.Key))) Into.Add(FString(KV.Key).ToLower(), KV.Value->AsObject());
		};
		Take(TEXT("fx"), FxTable); Take(TEXT("parts"), PartJson); Take(TEXT("behaviors"), BhvrJson);
		Take(TEXT("geoms"), Geoms); Take(TEXT("textures"), Textures); Take(TEXT("sounds"), Sounds);
		TSharedPtr<FJsonObject> PF;
		if (FFileHelper::LoadFileToString(Text, *(Dir / TEXT("power_fx.json"))) && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), PF) && PF.IsValid())
			for (const auto& KV : PF->Values) if (KV.Value->Type == EJson::Object && !PowerTable.Contains(FString(KV.Key))) PowerTable.Add(FString(KV.Key), KV.Value->AsObject());
	}
	UE_LOG(LogTemp, Log, TEXT("CoH fx: %d effects, %d particle systems, %d behaviors, %d textures, %d sounds, %d powers (%.1f s)"),
		FxTable.Num(), PartJson.Num(), BhvrJson.Num(), Textures.Num(), Sounds.Num(), PowerTable.Num(), FPlatformTime::Seconds() - T0);
}

UCoHFxLibrary* UCoHFxLibrary::Get(const UObject* WorldContext)
{
	const UWorld* Wd = WorldContext ? WorldContext->GetWorld() : nullptr;
	return Wd && Wd->GetGameInstance() ? Wd->GetGameInstance()->GetSubsystem<UCoHFxLibrary>() : nullptr;
}

TSharedPtr<FJsonObject> UCoHFxLibrary::Fx(const FString& Path) const
{
	const TSharedPtr<FJsonObject>* F = FxTable.Find(Path.ToLower().Replace(TEXT("\\"), TEXT("/")));
	return F ? *F : nullptr;
}

TSharedPtr<FJsonObject> UCoHFxLibrary::PowerFx(FName Power) const
{
	const TSharedPtr<FJsonObject>* P = PowerTable.Find(Power.ToString());
	return P ? *P : nullptr;
}

const TArray<TArray<float>>* UCoHFxLibrary::AltPivots(const FString& Geom) const
{
	static TMap<FString, TArray<TArray<float>>> Cache;
	if (const TArray<TArray<float>>* C = Cache.Find(Geom)) return C->Num() ? C : nullptr;
	TArray<TArray<float>>& Out = Cache.Add(Geom);
	const TSharedPtr<FJsonObject>* G = Geoms.Find(Geom.ToLower());
	const TArray<TSharedPtr<FJsonValue>>* Pivs;
	if (G && (*G)->TryGetArrayField(TEXT("alt_pivots"), Pivs))
		for (const auto& PV : *Pivs)
		{
			TArray<float>& M = Out.AddDefaulted_GetRef();
			for (const auto& Row : PV->AsArray()) for (const auto& X : Row->AsArray()) M.Add(X->AsNumber());
		}
	return Out.Num() ? &Out : nullptr;
}

/** One rgb per tick (partBuildColorPath); nav points [tick, r, g, b, primary%, secondary%]. */
static TArray<FVector3f> ColorPath(const TArray<TSharedPtr<FJsonValue>>& Nav)
{
	TArray<FVector3f> Path;
	if (Nav.Num() == 0) { Path.Add(FVector3f(255)); return Path; }
	auto Pt = [&](int32 i, int32 k) { return (float)Nav[i]->AsArray()[k]->AsNumber(); };
	int32 Len = 0;
	for (int32 i = 0; i < Nav.Num(); ++i) Len = FMath::Max(Len, (int32)Pt(i, 0) + 1);
	for (int32 i = 0; i + 1 < Nav.Num(); ++i)
	{
		const float Dt = FMath::Max(1.f, Pt(i + 1, 0) - Pt(i, 0));
		FVector3f Cur(Pt(i, 1), Pt(i, 2), Pt(i, 3));
		const FVector3f Dv = (FVector3f(Pt(i + 1, 1), Pt(i + 1, 2), Pt(i + 1, 3)) - Cur) / Dt;
		Path.Add(Cur);
		for (int32 T = (int32)Pt(i, 0) + 1; T <= (int32)Pt(i + 1, 0); ++T) { Cur += Dv; Path.Add(Cur); }
	}
	const int32 Last = Nav.Num() - 1;
	while (Path.Num() < Len) Path.Add(FVector3f(Pt(Last, 1), Pt(Last, 2), Pt(Last, 3)));
	Path.SetNum(FMath::Max(1, Len));
	return Path;
}

const FCoHPart* UCoHFxLibrary::Part(const FString& Path)
{
	const FString Key = Path.ToLower();
	if (const TUniquePtr<FCoHPart>* C = PartCache.Find(Key)) return C->Get();
	const TSharedPtr<FJsonObject>* J = PartJson.Find(Key);
	if (!J) return nullptr;
	const TSharedPtr<FJsonObject>& O = *J;
	FCoHPart P;
	P.NewPerFrame = Num(O, TEXT("NewPerFrame")); P.Burst = Num(O, TEXT("Burst")); P.Burble = Num(O, TEXT("BurbleAmplitude"));
	P.BurbleType = Num(O, TEXT("BurbleType")); P.BurbleFrequency = FMath::Max(0.001, Num(O, TEXT("BurbleFrequency"), 1)); P.BurbleThreshold = Num(O, TEXT("BurbleThreshold"));
	P.KillOnZero = Num(O, TEXT("KillOnZero")); P.bLocal = Num(O, TEXT("WorldOrLocalPosition")) == 1;
	P.MoveScale = Num(O, TEXT("MoveScale")); P.EmissionType = Num(O, TEXT("EmissionType"));
	P.EmissionLifeSpan = Num(O, TEXT("EmissionLifeSpan")); P.EmissionLifeSpanJitter = Num(O, TEXT("EmissionLifeSpanJitter"));
	P.EmissionRadius = Num(O, TEXT("EmissionRadius")); P.EmissionHeight = Num(O, TEXT("EmissionHeight"));
	P.EmissionStartJitter = V3(O, TEXT("EmissionStartJitter")); P.InitialVelocity = V3(O, TEXT("InitialVelocity"));
	P.InitialVelocityJitter = V3(O, TEXT("InitialVelocityJitter")); P.VelocityJitter = V3(O, TEXT("VelocityJitter"));
	P.Spin = Num(O, TEXT("Spin")); P.SpinJitter = Num(O, TEXT("SpinJitter")); P.OrientationJitter = Num(O, TEXT("OrientationJitter"));
	P.Magnetism = Num(O, TEXT("Magnetism")); P.Gravity = Num(O, TEXT("Gravity")); P.Drag = Num(O, TEXT("Drag")); P.Stickiness = Num(O, TEXT("Stickiness"));
	P.Alpha = Num(O, TEXT("Alpha"), 255); if (P.Alpha <= 0) P.Alpha = 255;
	P.FadeInBy = Num(O, TEXT("FadeInBy")); P.FadeOutStart = Num(O, TEXT("FadeOutStart")); P.FadeOutBy = Num(O, TEXT("FadeOutBy"), 30);
	P.StartSize = Num(O, TEXT("StartSize"), 1); P.StartSizeJitter = Num(O, TEXT("StartSizeJitter")); P.EndSize = Num(O, TEXT("EndSize"), 1);
	P.ExpandRate = Num(O, TEXT("ExpandRate")); P.ExpandType = Num(O, TEXT("ExpandType")); P.ColorChangeType = Num(O, TEXT("ColorChangeType"));
	P.StreakType = Num(O, TEXT("StreakType")); P.StreakScale = Num(O, TEXT("StreakScale"), 1); P.StreakOrient = Num(O, TEXT("StreakOrient")); P.StreakDirection = Num(O, TEXT("StreakDirection"));
	P.AnimFrames = Num(O, TEXT("AnimFrames1")); P.AnimPace = Num(O, TEXT("AnimPace1"));
	P.Blend = Str(O, TEXT("Blend_mode")); P.Texture = Str(O, TEXT("TextureName"));
	const TArray<TSharedPtr<FJsonValue>>* Flags;
	if (O->TryGetArrayField(TEXT("Flags"), Flags)) for (const auto& F : *Flags) P.bFadeImmediately |= F->AsString() == TEXT("FadeImmediatelyOnDeath");
	const TArray<TSharedPtr<FJsonValue>>* Nav;
	if (O->TryGetArrayField(TEXT("ColorNav"), Nav)) P.ColorPath = ColorPath(*Nav); else P.ColorPath.Add(FVector3f(255));
	return PartCache.Add(Key, MakeUnique<FCoHPart>(MoveTemp(P))).Get();
}

FCoHBhvr UCoHFxLibrary::Behavior(const FString& Path, const TSharedPtr<FJsonObject>& Override) const
{
	FCoHBhvr B;
	auto Apply = [&](const TSharedPtr<FJsonObject>& O)
	{
		if (!O.IsValid()) return;
		if (O->HasField(TEXT("StartJitter"))) B.StartJitter = V3(O, TEXT("StartJitter"));
		if (O->HasField(TEXT("InitialVelocity"))) B.InitialVelocity = V3(O, TEXT("InitialVelocity"));
		if (O->HasField(TEXT("InitialVelocityJitter"))) B.InitialVelocityJitter = V3(O, TEXT("InitialVelocityJitter"));
		if (O->HasField(TEXT("PositionOffset"))) B.PositionOffset = V3(O, TEXT("PositionOffset"));
		if (O->HasField(TEXT("Gravity"))) B.Gravity = Num(O, TEXT("Gravity"));
		if (O->HasField(TEXT("Drag"))) B.Drag = Num(O, TEXT("Drag"));
		if (O->HasField(TEXT("TrackRate"))) B.TrackRate = Num(O, TEXT("TrackRate"));
	};
	if (const TSharedPtr<FJsonObject>* J = BhvrJson.Find(Path.ToLower())) Apply(*J);
	Apply(Override);
	return B;
}

UMaterialInterface* UCoHFxLibrary::Material(const FString& Texture, const FString& Blend)
{
	const FString Mode = Blend == TEXT("Additive") ? TEXT("Additive")
		: Blend == TEXT("Multiply") ? TEXT("Multiply")
		: Blend.StartsWith(TEXT("Subtractive")) ? TEXT("Subtractive")
		: Blend == TEXT("PremultipliedAlpha") ? TEXT("Premultiplied")
		: Blend.IsEmpty() ? TEXT("Additive") : TEXT("Normal");
	const FString Key = Texture.ToLower() + TEXT("|") + Mode;
	if (const TObjectPtr<UMaterialInstanceDynamic>* C = MatCache.Find(Key)) return C->Get();
	TObjectPtr<UMaterialInterface>& Master = Masters.FindOrAdd(Mode);
	if (!Master)
	{
		const FString Name = TEXT("M_CoHParticle_") + Mode;
		Master = LoadObject<UMaterialInterface>(nullptr, *(MaterialRoot / Name + TEXT(".") + Name));
		if (!Master) { UE_LOG(LogTemp, Warning, TEXT("CoH fx: no master material %s"), *Name); return nullptr; }
	}
	UTexture2D* Tex = nullptr;
	FString TexKey = Texture.ToLower();
	const TSharedPtr<FJsonObject>* TI = Textures.Find(TexKey);
	if (!TI) TI = Textures.Find(TexKey + TEXT(".tga"));
	if (TI)
	{
		const FString A = AssetName(Str(*TI, TEXT("png")));
		Tex = LoadObject<UTexture2D>(nullptr, *(TextureRoot / A + TEXT(".") + A));
	}
	if (!Tex) Tex = LoadObject<UTexture2D>(nullptr, TEXT("/Engine/EngineResources/WhiteSquareTexture.WhiteSquareTexture"));
	UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(Master, this);
	if (Tex) M->SetTextureParameterValue(TEXT("Tex"), Tex);
	MatCache.Add(Key, M);
	return M;
}

UStaticMesh* UCoHFxLibrary::GeomMesh(const FString& Geom)
{
	const FString Key = Geom.ToLower();
	if (const TObjectPtr<UStaticMesh>* C = GeomCache.Find(Key)) return C->Get();
	UStaticMesh* M = nullptr;
	if (const TSharedPtr<FJsonObject>* G = Geoms.Find(Key))
	{
		const FString File = Str(*G, TEXT("mesh"));
		if (!File.IsEmpty())
		{
			const FString A = AssetName(File);
			M = LoadObject<UStaticMesh>(nullptr, *(GeomRoot / A + TEXT(".") + A));
			if (!M) UE_LOG(LogTemp, Warning, TEXT("CoH fx: effect model %s not imported (%s)"), *Geom, *(GeomRoot / A));
		}
	}
	GeomCache.Add(Key, M);
	return M;
}

UMaterialInterface* UCoHFxLibrary::GeomMaterial(const FString& Geom)
{
	const FString Key = Geom.ToLower();
	if (const TObjectPtr<UMaterialInterface>* C = GeomMatCache.Find(Key)) return C->Get();
	UMaterialInterface* Out = nullptr;
	const TSharedPtr<FJsonObject>* G = Geoms.Find(Key);
	const TArray<TSharedPtr<FJsonValue>>* Texs;
	UMaterialInterface* Master = LoadObject<UMaterialInterface>(nullptr, *(MaterialRoot / TEXT("M_CoHGeom.M_CoHGeom")));
	if (G && Master && (*G)->TryGetArrayField(TEXT("textures"), Texs) && Texs->Num())
	{
		FString T = (*Texs)[0]->AsString().ToLower();
		const TSharedPtr<FJsonObject>* TI = Textures.Find(T);
		if (!TI) TI = Textures.Find(T + TEXT(".tga"));
		if (TI)
		{
			const FString A = AssetName(Str(*TI, TEXT("png")));
			if (UTexture2D* Tex = LoadObject<UTexture2D>(nullptr, *(TextureRoot / A + TEXT(".") + A)))
			{
				UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(Master, this);
				M->SetTextureParameterValue(TEXT("Tex"), Tex);
				Out = M;
			}
		}
	}
	GeomMatCache.Add(Key, Out);
	return Out;
}

USoundBase* UCoHFxLibrary::Sound(const FString& Name)
{
	const FString Key = Name.ToLower();
	if (const TObjectPtr<USoundBase>* C = SoundCache.Find(Key)) return C->Get();
	USoundBase* S = nullptr;
	if (const TSharedPtr<FJsonObject>* SI = Sounds.Find(Key))
	{
		const FString A = AssetName(Str(*SI, TEXT("file")));
		S = LoadObject<USoundBase>(nullptr, *(SoundRoot / A + TEXT(".") + A));
	}
	SoundCache.Add(Key, S);
	return S;
}

USoundAttenuation* UCoHFxLibrary::Attenuation(float RadiusFeet)
{
	const int32 Key = FMath::Max(1, FMath::RoundToInt(RadiusFeet));
	if (const TObjectPtr<USoundAttenuation>* C = AttenCache.Find(Key)) return C->Get();
	USoundAttenuation* A = NewObject<USoundAttenuation>(this);
	A->Attenuation.bAttenuate = true;
	A->Attenuation.bSpatialize = true;
	A->Attenuation.AttenuationShape = EAttenuationShape::Sphere;
	A->Attenuation.AttenuationShapeExtents = FVector(Key * Ft * 0.25f, 0, 0);
	A->Attenuation.FalloffDistance = Key * Ft;
	AttenCache.Add(Key, A);
	return A;
}

ACoHFxRunner* UCoHFxLibrary::Play(AActor* Owner, const FString& Path, AActor* Target, float Delay)
{
	UWorld* Wd = Owner ? Owner->GetWorld() : nullptr;
	UCoHFxLibrary* Lib = Get(Owner);
	if (!Wd || !Lib || Path.IsEmpty() || !Lib->Fx(Path).IsValid() || Wd->GetNetMode() == NM_DedicatedServer) return nullptr;
	if (Delay > 0.f)
	{
		TWeakObjectPtr<AActor> O(Owner), T(Target);
		const FString P = Path;
		FTimerHandle H;
		Wd->GetTimerManager().SetTimer(H, FTimerDelegate::CreateLambda([O, T, P]() { if (O.IsValid()) Play(O.Get(), P, T.Get(), 0.f); }), Delay, false);
		return nullptr;
	}
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ACoHFxRunner* R = Wd->SpawnActor<ACoHFxRunner>(ACoHFxRunner::StaticClass(), FTransform::Identity, SP);
	if (R) R->Start(Path, Owner, Target);
	return R;
}

bool UCoHFxLibrary::PlayPower(AActor* Owner, FName Power, AActor* Target, float HitDelay)
{
	UCoHFxLibrary* Lib = Get(Owner);
	const TSharedPtr<FJsonObject> P = Lib ? Lib->PowerFx(Power) : nullptr;
	if (!P.IsValid()) return false;
	bool bAny = false;
	for (const TCHAR* K : { TEXT("WindUpFX"), TEXT("ActivationFX"), TEXT("AttackFX"), TEXT("InitialAttackFX") })
		if (Play(Owner, Str(P, K), Target)) bAny = true;
	const FString Hit = Str(P, TEXT("HitFX"));
	if (!Hit.IsEmpty() && Target && Target != Owner)
	{
		Play(Target, Hit, Owner, FMath::Max(0.f, HitDelay));
		bAny = true;
	}
	return bAny;
}

// ------------------------------------------------------------------ runner state
struct FCoHBasis
{
	FVector X = -FVector::RightVector, Y = FVector::UpVector, Z = FVector::ForwardVector;   // game x (left), y (up), z (forward)
	FVector L(const FVector& V) const { return X * V.X + Y * V.Y + Z * V.Z; }
};

struct FCoHParticle { FVector Pos, Vel; float Age = 0, Size = 1, Theta = 0; int32 Spin = 0; bool bPulse = true; };

struct ACoHFxRunner::FGeo
{
	FString Name, At, Magnet, Other;
	FCoHBasis Rot;
	FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector, Offset = FVector::ZeroVector;
	bool bAlive = true, bHit = false, bMoving = false, bFollowBone = false, bPiv = false;
	float Age = 0, Life = 0;
	TSharedPtr<FGeo> Follow;
	TArray<float> Piv;                   // 12 floats: axes rows, then position (feet)
	FString Geom;
	FCoHBhvr B;
	TArray<TSharedPtr<FSystem>> Systems;
	UStaticMeshComponent* Visual = nullptr;   // a visible effect model (weapon in hand, beam)
	bool bVisualOnBone = false;
};

struct ACoHFxRunner::FSystem
{
	const FCoHPart* I = nullptr;
	TSharedPtr<FGeo> Geo;
	float Age = 0, NewBuffer = 0, Npf = 0, Burst = 0, Burble = 0, EmissionLife = 0, Frame = 0;
	int32 KillOnZero = 0, Max = 100;
	bool bDying = false, bHasPrev = false;
	FVector Prev = FVector::ZeroVector;
	TArray<FCoHParticle> P;
	UProceduralMeshComponent* Mesh = nullptr;
	UMaterialInterface* Mat = nullptr;
	void SoftKill()
	{
		bDying = true; Npf = 0; Burble = 0; KillOnZero = 1;
		if (I->bFadeImmediately) for (FCoHParticle& X : P) X.Age = FMath::Max(X.Age, I->FadeOutStart);
	}
};

struct ACoHFxRunner::FRun
{
	TSharedPtr<FJsonObject> D;
	TWeakObjectPtr<AActor> Entity, Target;
	TSharedPtr<FGeo> At;
	float Age = 0, Lifespan = 0;
	bool bAlive = true;
	TArray<TSharedPtr<FJsonValue>> Conds;
	TSet<int32> Fired;
	TMap<FString, TSharedPtr<FGeo>> Geos;
	TArray<TSharedPtr<FGeo>> All;
	TArray<TSharedPtr<FSystem>> Systems;
	TArray<TSharedPtr<FRun>> Children;
};

// fallback body points (feet) when a skeleton has no such bone (fxsim BONES)
static FVector FallbackBone(const FString& Name)
{
	static const TMap<FString, FVector> Bones = {
		{ TEXT("origin"), FVector(0, 0, 0) }, { TEXT("hips"), FVector(0, 3.1, 0) }, { TEXT("waist"), FVector(0, 3.6, 0) },
		{ TEXT("chest"), FVector(0, 4.7, 0.2) }, { TEXT("neck"), FVector(0, 5.4, 0.1) }, { TEXT("head"), FVector(0, 5.9, 0.2) },
		{ TEXT("wepr"), FVector(-0.7, 4.4, 1.3) }, { TEXT("wepl"), FVector(0.7, 4.4, 1.3) }, { TEXT("handr"), FVector(-0.7, 4.4, 1.3) },
		{ TEXT("handl"), FVector(0.7, 4.4, 1.3) }, { TEXT("footr"), FVector(-0.4, 0.2, 0) }, { TEXT("footl"), FVector(0.4, 0.2, 0) } };
	const FVector* B = Bones.Find(Name);
	return B ? *B : Bones[TEXT("chest")];
}

static FCoHBasis Facing(const AActor* A)
{
	FCoHBasis B;
	if (A) { B.X = -A->GetActorRightVector(); B.Z = A->GetActorForwardVector(); }
	return B;
}

static FVector Feet(const AActor* A)
{
	if (const ACharacter* C = Cast<ACharacter>(A)) return C->GetActorLocation() - FVector(0, 0, C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
	return A ? A->GetActorLocation() : FVector::ZeroVector;
}

/** World position of a bone of an entity ("origin" = the feet). */
static FVector BoneOf(const AActor* A, FString Name)
{
	Name = Name.ToLower();
	if (!A) return FVector::ZeroVector;
	if (Name.IsEmpty() || Name == TEXT("origin") || Name == TEXT("root")) return Feet(A);
	if (const ACharacter* C = Cast<ACharacter>(A))
		if (const USkeletalMeshComponent* SK = C->GetMesh())
		{
			const int32 NB = SK->GetNumBones();
			for (int32 i = 0; i < NB; ++i)
			{
				const FName BN = SK->GetBoneName(i);
				if (BN.ToString().Equals(Name, ESearchCase::IgnoreCase)) return SK->GetBoneLocation(BN);
			}
		}
	return Feet(A) + Facing(A).L(FallbackBone(Name)) * Ft;
}

// ------------------------------------------------------------------ runner
ACoHFxRunner::ACoHFxRunner()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	SetReplicates(false);
}

static TSharedPtr<ACoHFxRunner::FRun> MakeRun(UCoHFxLibrary* Lib, const FString& Path, AActor* Entity, AActor* Target, TSharedPtr<ACoHFxRunner::FGeo> At)
{
	TSharedPtr<ACoHFxRunner::FRun> R = MakeShared<ACoHFxRunner::FRun>();
	R->D = Lib->Fx(Path);
	R->Entity = Entity; R->Target = Target; R->At = At;
	if (!R->D.IsValid()) { R->bAlive = false; return R; }
	R->Lifespan = Num(R->D, TEXT("lifespan"));
	const TArray<TSharedPtr<FJsonValue>>* C;
	if (R->D->TryGetArrayField(TEXT("conditions"), C)) R->Conds = *C;
	return R;
}

void ACoHFxRunner::Start(const FString& Path, AActor* InOwner, AActor* InTarget)
{
	UCoHFxLibrary* Lib = UCoHFxLibrary::Get(this);
	if (!Lib) { Destroy(); return; }
	Runs.Add(MakeRun(Lib, Path, InOwner, InTarget, nullptr));
	Step();          // tick 0 fires the time-0 events at once
	Draw();
}

void ACoHFxRunner::Stop()
{
	TFunction<void(FRun&)> Kill = [&](FRun& R)
	{
		R.bAlive = false;
		for (const TSharedPtr<FGeo>& G : R.All) if (G->bAlive) { G->bAlive = false; for (const auto& S : G->Systems) S->SoftKill(); }
		for (const TSharedPtr<FRun>& C : R.Children) Kill(*C);
	};
	for (const TSharedPtr<FRun>& R : Runs) Kill(*R);
}

void ACoHFxRunner::Tick(float Dt)
{
	Super::Tick(Dt);
	Accum += Dt;
	int32 Steps = 0;
	while (Accum >= TickSeconds && Steps < 6) { Accum -= TickSeconds; ++Steps; Step(); }
	if (Steps == 6) Accum = 0.f;
	// a safety net for effects that loop on conditions not played yet
	if (Ticks > 30 * 20) Stop();
	Draw();
	if (Runs.Num() == 0) Destroy();
}

void ACoHFxRunner::Step()
{
	UCoHFxLibrary* Lib = UCoHFxLibrary::Get(this);
	if (!Lib) return;
	++Ticks;

	// points an effect refers to: bones of the entity or target, nodes, the target
	auto Bone = [](FRun& R, const FString& NameIn) -> FVector
	{
		const FString Name = NameIn.ToLower();
		if (R.At.IsValid() && (Name.IsEmpty() || Name == TEXT("origin") || Name == TEXT("root"))) return R.At->Pos;
		if (Name.StartsWith(TEXT("t_")) && R.Target.IsValid()) return BoneOf(R.Target.Get(), Name.Mid(2));
		if (Name == TEXT("target") && R.Target.IsValid()) return BoneOf(R.Target.Get(), TEXT("chest"));
		if (R.At.IsValid()) return R.At->Pos;
		return BoneOf(R.Entity.Get(), Name);
	};
	auto Point = [&](FRun& R, const FString& NameIn) -> FVector
	{
		const FString Name = NameIn.ToLower();
		if ((Name == TEXT("target") || Name == TEXT("t_target")) && R.Target.IsValid()) return BoneOf(R.Target.Get(), TEXT("chest"));
		if (const TSharedPtr<FGeo>* G = R.Geos.Find(Name)) return (*G)->Pos;
		return Bone(R, Name);
	};
	auto PlaceOnFollow = [](FGeo& G)
	{
		const FGeo& F = *G.Follow;
		if (!G.bPiv) { G.Rot = F.Rot; G.Pos = F.Pos; return; }
		const float* M = G.Piv.GetData();
		const FVector A[3] = { F.Rot.X, F.Rot.Y, F.Rot.Z };
		G.Rot.X = A[0] * M[0] + A[1] * M[1] + A[2] * M[2];
		G.Rot.Y = A[0] * M[3] + A[1] * M[4] + A[2] * M[5];
		G.Rot.Z = A[0] * M[6] + A[1] * M[7] + A[2] * M[8];
		G.Pos = F.Pos + F.Rot.L(FVector(M[9], M[10], M[11])) * Ft;
	};

	TFunction<void(FRun&, const TSharedPtr<FJsonObject>&)> Fire;
	Fire = [&](FRun& R, const TSharedPtr<FJsonObject>& Ev)
	{
		const FString Type = Str(Ev, TEXT("type")).IsEmpty() ? TEXT("create") : Str(Ev, TEXT("type"));
		const FString Name = Str(Ev, TEXT("name")).ToLower();
		if (Type == TEXT("destroy"))
		{
			for (const TSharedPtr<FGeo>& G : R.All)
				if (G->bAlive && (Name == TEXT("all") || G->Name == Name)) { G->bAlive = false; for (const auto& S : G->Systems) S->SoftKill(); }
			return;
		}
		if (Type == TEXT("setstate") || Type == TEXT("setlight")) return;
		const TSharedPtr<FJsonObject>* Ovr = nullptr;
		Ev->TryGetObjectField(TEXT("bhvroverride"), Ovr);
		const FString BhvrPath = Str(Ev, TEXT("bhvr"));
		TSharedPtr<FGeo> G = MakeShared<FGeo>();
		G->Name = Name;
		G->B = Lib->Behavior(BhvrPath, Ovr ? *Ovr : nullptr);
		G->At = Str(Ev, TEXT("at")).ToLower();
		if (G->At.IsEmpty()) G->At = TEXT("origin");
		const TArray<TSharedPtr<FJsonValue>>* GeomsA;
		if (Ev->TryGetArrayField(TEXT("geoms"), GeomsA) && GeomsA->Num()) G->Geom = (*GeomsA)[0]->AsString().ToLower();
		if (const TSharedPtr<FGeo>* F = R.Geos.Find(G->At))
		{
			G->Follow = *F;
			const int32 AP = (int32)Num(Ev, TEXT("altpiv"));
			if (AP > 0 && !(*F)->Geom.IsEmpty())
				if (const TArray<TArray<float>>* Pivs = Lib->AltPivots((*F)->Geom))
					if (Pivs->IsValidIndex(AP - 1) && (*Pivs)[AP - 1].Num() >= 12) { G->bPiv = true; G->Piv = (*Pivs)[AP - 1]; }
			PlaceOnFollow(*G);
		}
		else
		{
			const AActor* On = G->At.StartsWith(TEXT("t_")) && R.Target.IsValid() ? R.Target.Get() : R.Entity.Get();
			G->Rot = Facing(On);
			G->Pos = Bone(R, G->At);
		}
		G->Offset = G->Rot.L(FVector(G->B.PositionOffset.X + G->B.StartJitter.X * Rnd(), G->B.PositionOffset.Y + G->B.StartJitter.Y * Rnd(), G->B.PositionOffset.Z + G->B.StartJitter.Z * Rnd())) * Ft;
		G->Pos += G->Offset;
		G->Vel = G->Rot.L(FVector(G->B.InitialVelocity.X + G->B.InitialVelocityJitter.X * Rnd(), G->B.InitialVelocity.Y + G->B.InitialVelocityJitter.Y * Rnd(),
			G->B.InitialVelocity.Z + G->B.InitialVelocityJitter.Z * Rnd())) * Ft;
		G->bMoving = Type == TEXT("start") || Type == TEXT("startpositonly") || !BhvrPath.IsEmpty();
		// Create / Local stay on their bone; Posit only places the node
		G->bFollowBone = !G->Follow.IsValid() && !G->bMoving && (Type == TEXT("create") || Type == TEXT("local"));
		G->Magnet = Str(Ev, TEXT("magnet")).ToLower();
		if (!Str(Ev, TEXT("pmagnet")).IsEmpty()) G->Magnet = Str(Ev, TEXT("pmagnet")).ToLower();
		G->Other = Str(Ev, TEXT("pother")).ToLower();
		float Life = Num(Ev, TEXT("lifespan"));
		if (Life > 0) Life += Rnd() * Num(Ev, TEXT("lifespanjitter"));
		G->Life = Life;
		if (!Name.IsEmpty()) R.Geos.Add(Name, G);
		// a visible model: on the hand (or other) bone when the node sits on
		// one, else carried along with the node
		if (!G->Geom.IsEmpty())
			if (UStaticMesh* SM = Lib->GeomMesh(G->Geom))
			{
				UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
				C->SetStaticMesh(SM);
				C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				if (UMaterialInterface* M = Lib->GeomMaterial(G->Geom)) for (int32 i = 0; i < C->GetNumMaterials(); ++i) C->SetMaterial(i, M);
				C->SetupAttachment(GetRootComponent());
				C->RegisterComponent();
				const AActor* On = G->At.StartsWith(TEXT("t_")) && R.Target.IsValid() ? R.Target.Get() : R.Entity.Get();
				const ACharacter* Ch = Cast<ACharacter>(On);
				USkeletalMeshComponent* SK = Ch && G->bFollowBone ? Ch->GetMesh() : nullptr;
				const FString BoneName = G->At.StartsWith(TEXT("t_")) ? G->At.Mid(2) : G->At;
				FName HandBone;
				if (SK) for (int32 i = 0; i < SK->GetNumBones(); ++i) if (SK->GetBoneName(i).ToString().Equals(BoneName, ESearchCase::IgnoreCase)) { HandBone = SK->GetBoneName(i); break; }
				if (SK && !HandBone.IsNone())
				{
					C->AttachToComponent(SK, FAttachmentTransformRules::SnapToTargetNotIncludingScale, HandBone);
					C->SetRelativeRotation(CVarRot(CVarGeomBoneRot));
					G->bVisualOnBone = true;
				}
				G->Visual = C;
			}
		R.All.Add(G);
		const TArray<TSharedPtr<FJsonValue>>* Parts;
		if (Ev->TryGetArrayField(TEXT("parts"), Parts))
			for (const auto& PV : *Parts)
				if (const FCoHPart* I = Lib->Part(PV->AsString()))
				{
					TSharedPtr<FSystem> S = MakeShared<FSystem>();
					S->I = I; S->Geo = G;
					S->Npf = I->NewPerFrame; S->Burst = I->Burst; S->Burble = I->Burble; S->KillOnZero = I->KillOnZero;
					S->Max = FMath::Min((int32)(I->Burst + I->NewPerFrame * I->FadeOutBy + 10) + (I->MoveScale != 0 || I->Burble != 0 ? 200 : 0), 1500);
					S->EmissionLife = FMath::Max(0.f, I->EmissionLifeSpan + Rnd() * I->EmissionLifeSpanJitter);
					S->Mat = Lib->Material(I->Texture, I->Blend);
					G->Systems.Add(S);
					R.Systems.Add(S);
				}
		const TArray<TSharedPtr<FJsonValue>>* Snd;
		if (Ev->TryGetArrayField(TEXT("sounds"), Snd))
			for (const auto& SV : *Snd)
			{
				const TSharedPtr<FJsonObject> SO = SV->AsObject();
				if (USoundBase* Sound = Lib->Sound(Str(SO, TEXT("name"))))
					UGameplayStatics::PlaySoundAtLocation(this, Sound, G->Pos, FRotator::ZeroRotator, FMath::Clamp((float)Num(SO, TEXT("volume"), 1), 0.f, 2.f), 1.f, 0.f,
						Lib->Attenuation(FMath::Max(10.0, Num(SO, TEXT("radius"), 60))));
			}
		const FString Child = Str(Ev, TEXT("childfx"));
		if (!Child.IsEmpty() && Lib->Fx(Child).IsValid()) R.Children.Add(MakeRun(Lib, Child, R.Entity.Get(), R.Target.Get(), G));
	};

	TFunction<bool(FRun&)> UpdateRun;
	UpdateRun = [&](FRun& R) -> bool
	{
		if (!R.D.IsValid()) return false;
		if (!R.Entity.IsValid()) { R.bAlive = false; }
		if (R.bAlive)
		{
			for (int32 Ci = 0; Ci < R.Conds.Num(); ++Ci)
			{
				if (R.Fired.Contains(Ci)) continue;
				const TSharedPtr<FJsonObject> C = R.Conds[Ci]->AsObject();
				const FString On = Str(C, TEXT("on"));
				bool bDue = false;
				if (On == TEXT("time")) bDue = R.Age >= Num(C, TEXT("time"));
				else if (On.StartsWith(TEXT("prime")) && On.EndsWith(TEXT("hit")))
				{
					const TSharedPtr<FGeo>* G = R.Geos.Find(On.LeftChop(3));
					bDue = G && (*G)->bHit;
				}
				if (!bDue) continue;
				R.Fired.Add(Ci);
				if (Num(C, TEXT("chance")) > 0 && FMath::FRand() * 100.f > Num(C, TEXT("chance"))) continue;
				const int32 Times = 1 + (int32)Num(C, TEXT("repeat"));
				TArray<TSharedPtr<FJsonValue>> Evs;
				const TArray<TSharedPtr<FJsonValue>>* EA;
				if (C->TryGetArrayField(TEXT("events"), EA)) Evs = *EA;
				if (Num(C, TEXT("random")) > 0 && Evs.Num()) Evs = { Evs[FMath::RandRange(0, Evs.Num() - 1)] };
				for (int32 t = 0; t < Times; ++t) for (const auto& E : Evs) if (E->AsObject().IsValid()) Fire(R, E->AsObject());
			}
			if (R.Lifespan > 0 && R.Age >= R.Lifespan)
			{
				R.bAlive = false;
				for (const TSharedPtr<FGeo>& G : R.All) if (G->bAlive) { G->bAlive = false; for (const auto& S : G->Systems) S->SoftKill(); }
			}
		}
		// nodes
		for (const TSharedPtr<FGeo>& Gp : R.All)
		{
			FGeo& G = *Gp;
			if (!G.bAlive) continue;
			G.Age += 1;
			if (G.Follow.IsValid()) PlaceOnFollow(G);
			else if (G.bMoving)
			{
				if (!G.Magnet.IsEmpty() && G.B.TrackRate > 0)
				{
					const FVector T = Point(R, G.Magnet);
					if (G.bHit) G.Pos = T;
					else
					{
						const FVector D = T - G.Pos;
						const float Dist = D.Size(), StepCm = G.B.TrackRate * Ft;
						if (Dist <= StepCm || Dist < 0.1f) { G.Pos = T; G.bHit = true; }
						else G.Pos += D / Dist * StepCm;
					}
				}
				else
				{
					G.Vel.Z -= G.B.Gravity * Ft;
					if (G.B.Drag) G.Vel -= G.Vel * G.B.Drag;
					G.Pos += G.Vel;
				}
			}
			else if (G.bFollowBone)
			{
				const AActor* On = G.At.StartsWith(TEXT("t_")) && R.Target.IsValid() ? R.Target.Get() : R.Entity.Get();
				if (On) { G.Rot = Facing(On); G.Pos = Bone(R, G.At) + G.Offset; }
			}
			if (G.Life > 0 && G.Age >= G.Life) { G.bAlive = false; for (const auto& S : G.Systems) S->SoftKill(); }
		}
		// particle systems (partUpdateSystem)
		for (int32 Si = R.Systems.Num() - 1; Si >= 0; --Si)
		{
			FSystem& S = *R.Systems[Si];
			const FCoHPart& I = *S.I;
			const FVector Start = S.Geo->Pos;
			if (!S.bHasPrev) { S.Prev = Start; S.bHasPrev = true; }
			const FVector Change = Start - S.Prev;
			const FVector Emit = I.bLocal ? FVector::ZeroVector : Start;
			float Nb = 0;
			if (!I.MoveScale || !S.Age) Nb = S.Npf;
			else if (!S.bDying)
			{
				const float Ln = Change.Size() / Ft;
				if (I.MoveScale > 0) Nb = S.Npf * I.MoveScale * Ln;
				else { Nb = S.Npf; Nb += FMath::Max(-Nb, I.MoveScale * Ln); }
			}
			if (S.Age == 0) Nb += S.Burst;
			if (S.Burble)
			{
				const float X = S.Age / I.BurbleFrequency;
				const float Y = I.BurbleType ? FMath::Sin(X / 64.f * 2.f * PI) : FMath::Sin(X * 0.37f) * FMath::Cos(X * 0.11f);
				if (Y >= I.BurbleThreshold * 2 - 1) Nb += (Y + 1) * S.Burble;
			}
			S.NewBuffer += Nb;
			int32 NumNew = (int32)S.NewBuffer;
			S.NewBuffer -= NumNew;
			if (S.P.Num() + NumNew > S.Max) NumNew = FMath::Max(S.Max - S.P.Num(), 0);
			if (S.EmissionLife > 0 && S.Age > S.EmissionLife) NumNew = 0;
			const FVector Iv = S.Geo->Rot.L(I.InitialVelocity) * Ft;
			const FVector Other = S.Geo->Other.IsEmpty() ? Start : Point(R, S.Geo->Other);
			for (int32 n = 0; n < NumNew; ++n)
			{
				FCoHParticle X;
				X.Size = I.StartSize + (I.StartSizeJitter ? Rnd() * I.StartSizeJitter : 0.f);
				X.Spin = I.Spin + (I.SpinJitter ? FMath::RandRange(0, I.SpinJitter) : 0);
				X.Theta = I.OrientationJitter ? FMath::RandRange(0, I.OrientationJitter) : 0;
				X.Vel = Iv + JitW(I.InitialVelocityJitter);
				FVector Pos = Emit;
				switch (I.EmissionType)
				{
				case 1: Pos = Emit + (Other - Start) * FMath::FRand(); break;
				case 2: { const float A = FMath::FRandRange(0.f, 2.f * PI); Pos = Emit + W(FVector(FMath::Cos(A) * I.EmissionRadius, FMath::FRand() * I.EmissionHeight, FMath::Sin(A) * I.EmissionRadius)) * Ft; break; }
				case 3: Pos = Emit - Change * (1.f - n / (float)NumNew); break;
				case 4: Pos = Emit + FMath::VRand() * I.EmissionRadius * Ft; break;
				case 5: Pos = Emit + (Other - Start) / NumNew * n; break;
				default: break;
				}
				X.Pos = Pos + JitW(I.EmissionStartJitter);
				S.P.Add(X);
			}
			const FVector Magnet = S.Geo->Magnet.IsEmpty() ? FVector::ZeroVector : Point(R, S.Geo->Magnet) - (I.bLocal ? Start : FVector::ZeroVector);
			const bool bVJ = !I.VelocityJitter.IsNearlyZero();
			for (int32 Pi = S.P.Num() - 1; Pi >= 0; --Pi)
			{
				FCoHParticle& X = S.P[Pi];
				if (X.Age >= I.FadeOutBy) { S.P.RemoveAt(Pi, EAllowShrinking::No); continue; }
				if (bVJ) X.Vel += JitW(I.VelocityJitter);
				X.Vel.Z -= I.Gravity * Ft;
				if (I.Drag) X.Vel -= X.Vel * I.Drag;
				X.Pos += X.Vel;
				if (I.Magnetism && !S.Geo->Magnet.IsEmpty())
				{
					const float M = I.Magnetism * Ft;
					X.Vel += FVector(X.Pos.X < Magnet.X ? M : -M, X.Pos.Y < Magnet.Y ? M : -M, X.Pos.Z < Magnet.Z ? M : -M);
				}
				if (I.Stickiness && X.Age) X.Pos += Change * I.Stickiness;
				if (const float Er = I.ExpandRate)
				{
					if (I.ExpandType == 0) X.Size += Er;
					else if (I.ExpandType == 1) { X.Size += Er; X.Size = Er < 0 ? FMath::Max(X.Size, I.EndSize) : FMath::Min(X.Size, I.EndSize); }
					else
					{
						const float Old = X.Size;
						X.Size += X.bPulse ? Er : -Er;
						if (X.Size > FMath::Max(I.StartSize, I.EndSize) || X.Size < FMath::Min(I.StartSize, I.EndSize)) { X.Size = Old; X.bPulse = !X.bPulse; }
					}
				}
				if (X.Spin) X.Theta = FMath::Fmod(X.Theta + FMath::Abs(X.Spin) * 0.1f, 256.f);
				X.Age += 1;
			}
			S.Prev = Start;
			if (I.AnimFrames > 1) S.Frame = FMath::Fmod(S.Frame + I.AnimPace, (float)I.AnimFrames);
			S.Age += 1;
			bool bAliveS = true;
			if (S.bDying || (!S.Npf && !I.MoveScale && !S.Burble)) if (S.P.Num() == 0) bAliveS = false;
			if (S.P.Num() == 0 && S.KillOnZero && Nb <= 0 && !(!S.bDying && (S.Burble || I.MoveScale))) bAliveS = false;
			if (!bAliveS)
			{
				if (S.Mesh) { S.Mesh->ClearAllMeshSections(); S.Mesh->SetVisibility(false); Pool.Add(S.Mesh); S.Mesh = nullptr; }
				R.Systems.RemoveAt(Si);
			}
		}
		for (int32 Ci = R.Children.Num() - 1; Ci >= 0; --Ci) if (!UpdateRun(*R.Children[Ci])) R.Children.RemoveAt(Ci);
		R.Age += 1;
		return R.bAlive || R.Systems.Num() > 0 || R.Children.Num() > 0;
	};
	for (int32 i = Runs.Num() - 1; i >= 0; --i) if (!UpdateRun(*Runs[i])) Runs.RemoveAt(i);
}

void ACoHFxRunner::Draw()
{
	// effect models: free ones follow their node; dead nodes drop theirs
	TFunction<void(FRun&)> Models = [&](FRun& R)
	{
		for (const TSharedPtr<FGeo>& G : R.All)
		{
			if (!G->Visual) continue;
			if (!G->bAlive) { G->Visual->DestroyComponent(); G->Visual = nullptr; continue; }
			if (G->bVisualOnBone) continue;
			const FMatrix M(G->Rot.Z, -G->Rot.X, G->Rot.Y, FVector::ZeroVector);   // forward, right, up
			G->Visual->SetWorldLocationAndRotation(G->Pos, (CVarRot(CVarGeomNodeRot).Quaternion() * M.ToQuat()).Rotator());
		}
		for (const TSharedPtr<FRun>& C : R.Children) Models(*C);
	};
	for (const TSharedPtr<FRun>& R : Runs) Models(*R);
	const UWorld* Wd = GetWorld();
	const APlayerController* PC = Wd ? Wd->GetFirstPlayerController() : nullptr;
	if (!PC || !PC->PlayerCameraManager) return;
	const FRotator CamRot = PC->PlayerCameraManager->GetCameraRotation();
	const FVector Fwd = CamRot.Vector(), Right = FRotationMatrix(CamRot).GetUnitAxis(EAxis::Y), Up = FRotationMatrix(CamRot).GetUnitAxis(EAxis::Z);
	auto Corner = [&](float Ang, float Size) { return Right * FMath::Cos(Ang) * Size + Up * FMath::Sin(Ang) * Size; };
	static const float K96 = 96.f / 256.f * 2.f * PI, K32 = 32.f / 256.f * 2.f * PI, K160 = 160.f / 256.f * 2.f * PI;

	TFunction<void(FRun&)> DrawRun = [&](FRun& R)
	{
		for (const TSharedPtr<FSystem>& Sp : R.Systems)
		{
			FSystem& S = *Sp;
			const FCoHPart& I = *S.I;
			if (!S.Mesh)
			{
				if (Pool.Num()) S.Mesh = Pool.Pop();
				else
				{
					S.Mesh = NewObject<UProceduralMeshComponent>(this);
					S.Mesh->SetupAttachment(GetRootComponent());
					S.Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
					S.Mesh->SetCastShadow(false);
					S.Mesh->bUseAsyncCooking = false;
					S.Mesh->RegisterComponent();
				}
				S.Mesh->SetVisibility(true);
				if (S.Mat) S.Mesh->SetMaterial(0, S.Mat);
			}
			if (S.P.Num() == 0) { S.Mesh->ClearAllMeshSections(); continue; }
			// flipbook grid for AnimFrames: 2x1, 2x2, 4x2, 4x4, 8x4
			int32 Fw = 1; float Sx = 1, Sy = 1;
			if (I.AnimFrames > 1)
			{
				if (I.AnimFrames <= 2) { Fw = 2; Sx = .5f; Sy = 1; } else if (I.AnimFrames <= 4) { Fw = 2; Sx = .5f; Sy = .5f; }
				else if (I.AnimFrames <= 8) { Fw = 4; Sx = .25f; Sy = .5f; } else if (I.AnimFrames <= 16) { Fw = 4; Sx = .25f; Sy = .25f; }
				else { Fw = 8; Sx = .125f; Sy = .25f; }
			}
			const int32 Fr = (int32)S.Frame;
			const float U0 = (Fr % Fw) * Sx, V0 = (Fr / Fw) * Sy;
			const FVector Base = I.bLocal ? S.Geo->Pos : FVector::ZeroVector;
			TArray<FVector> Verts; TArray<int32> Tris; TArray<FVector> Normals; TArray<FVector2D> UV; TArray<FLinearColor> Cols; TArray<FProcMeshTangent> Tan;
			Verts.Reserve(S.P.Num() * 4); Tris.Reserve(S.P.Num() * 6); UV.Reserve(S.P.Num() * 4); Cols.Reserve(S.P.Num() * 4);
			for (int32 k = 0; k < S.P.Num(); ++k)
			{
				const FCoHParticle& X = S.P[k];
				FVector A = X.Pos + Base, Bp = A;
				switch (I.StreakType)
				{
				case 1: { const FVector V = X.Vel * I.StreakScale; Bp = I.StreakDirection == 0 ? A - V : A + V; break; }
				case 2: Bp = A + FVector(0, 0, I.Gravity * I.StreakScale * Ft); break;
				case 3: Bp = S.Geo->Pos; break;
				case 4: if (!S.Geo->Magnet.IsEmpty()) Bp = R.Geos.Contains(S.Geo->Magnet) ? R.Geos[S.Geo->Magnet]->Pos : (R.Target.IsValid() ? BoneOf(R.Target.Get(), TEXT("chest")) : A); break;
				case 5: if (!S.Geo->Other.IsEmpty() && R.Geos.Contains(S.Geo->Other)) Bp = R.Geos[S.Geo->Other]->Pos; break;
				case 7: Bp = k + 1 < S.P.Num() ? S.P[k + 1].Pos + Base : S.Geo->Pos; break;
				default: break;
				}
				float Theta;
				if (I.StreakType && I.StreakOrient == 1)
				{
					if (I.StreakDirection == 1) Swap(A, Bp);
					const FVector D = A - Bp;
					Theta = FMath::Atan2(FVector::DotProduct(D, Up), FVector::DotProduct(D, Right)) - PI / 2.f;
				}
				else Theta = X.Theta / 256.f * 2.f * PI;
				const float Size = FMath::Max(X.Size, 0.f) * Ft;
				if (Size <= 0.f) continue;
				const FVector Ul = A + Corner(Theta + K96, Size), Ur = A + Corner(Theta + K32, Size), Ll = Bp + Corner(Theta + K160, Size);
				const FVector Lr = Ur + (Ll - Ul);
				// colour by age in ticks, alpha ramp in / hold / out
				const float Age = X.Age - 1;
				int32 Idx = FMath::RoundToInt(Age);
				if (I.ColorChangeType == 1) Idx = ((Idx % I.ColorPath.Num()) + I.ColorPath.Num()) % I.ColorPath.Num();
				Idx = FMath::Clamp(Idx, 0, I.ColorPath.Num() - 1);
				const FVector3f C = I.ColorPath[Idx] / 255.f;
				float F = 1.f;
				if (Age >= I.FadeOutStart) F = 1.f - (Age - I.FadeOutStart) / FMath::Max(1.f, I.FadeOutBy - I.FadeOutStart);
				else if (Age < I.FadeInBy) F = Age / FMath::Max(0.001f, I.FadeInBy);
				const float Alpha = FMath::Max(1.f, FMath::RoundToFloat(I.Alpha * FMath::Max(F, 0.f))) / 255.f;
				const FLinearColor Col(C.X, C.Y, C.Z, Alpha);
				const int32 V = Verts.Num();
				Verts.Append({ Ul, Ur, Ll, Lr });
				UV.Append({ FVector2D(U0, V0), FVector2D(U0 + Sx, V0), FVector2D(U0, V0 + Sy), FVector2D(U0 + Sx, V0 + Sy) });
				Cols.Append({ Col, Col, Col, Col });
				Normals.Append({ -Fwd, -Fwd, -Fwd, -Fwd });
				Tris.Append({ V, V + 2, V + 1, V + 1, V + 2, V + 3 });
			}
			S.Mesh->CreateMeshSection_LinearColor(0, Verts, Tris, Normals, UV, Cols, Tan, false);
			S.Mesh->SetTranslucentSortPriority((int32)(I.Blend == TEXT("Additive") ? 1 : 0));
		}
		for (const TSharedPtr<FRun>& C : R.Children) DrawRun(*C);
	};
	for (const TSharedPtr<FRun>& R : Runs) DrawRun(*R);
}

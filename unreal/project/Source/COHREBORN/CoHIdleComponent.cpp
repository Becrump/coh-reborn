#include "CoHIdleComponent.h"

#include "Animation/AnimSequence.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "CoHIdleAnimInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "Dom/JsonObject.h"
#include "GameFramework/Actor.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

DEFINE_LOG_CATEGORY_STATIC(LogCoHIdle, Log, All);

static constexpr float CoHFps = 30.f;

UCoHIdleComponent::UCoHIdleComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

bool UCoHIdleComponent::LoadGraphs()
{
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *GraphJson.FilePath))
	{
		UE_LOG(LogCoHIdle, Warning, TEXT("%s: could not read %s"), *GetNameSafe(GetOwner()), *GraphJson.FilePath);
		return false;
	}
	TSharedPtr<FJsonObject> Root;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		UE_LOG(LogCoHIdle, Warning, TEXT("bad idle json %s"), *GraphJson.FilePath);
		return false;
	}
	const TSharedPtr<FJsonObject>* Types;
	const TArray<TSharedPtr<FJsonValue>>* Arr;
	if (!Root->TryGetObjectField(TEXT("types"), Types) ||
		!((*Types)->TryGetArrayField(SeqType.ToLower(), Arr) || (*Types)->TryGetArrayField(TEXT("male"), Arr)))
	{
		UE_LOG(LogCoHIdle, Warning, TEXT("no idle graphs for %s in %s"), *SeqType, *GraphJson.FilePath);
		return false;
	}
	for (const TSharedPtr<FJsonValue>& GV : *Arr)
	{
		const TSharedPtr<FJsonObject>& G = GV->AsObject();
		FGraph& Out = Graphs.AddDefaulted_GetRef();
		Out.Pose = FName(G->GetStringField(TEXT("pose")));
		Out.SpawnCount = int32(G->GetNumberField(TEXT("spawnCount")));
		const TArray<TSharedPtr<FJsonValue>>* Needs;
		Out.bNeedsProp = G->TryGetArrayField(TEXT("needs"), Needs) && Needs->Num() > 0;

		TMap<FName, int32> Index;
		const TArray<TSharedPtr<FJsonValue>>& States = G->GetArrayField(TEXT("states"));
		for (const TSharedPtr<FJsonValue>& SV : States)
		{
			Index.Add(FName(SV->AsObject()->GetStringField(TEXT("move"))), Index.Num());
		}
		for (const TSharedPtr<FJsonValue>& SV : States)
		{
			const TSharedPtr<FJsonObject>& S = SV->AsObject();
			FState& St = Out.States.AddDefaulted_GetRef();
			St.Move = FName(S->GetStringField(TEXT("move")));
			St.PlayRate = float(S->GetNumberField(TEXT("playRate")));
			St.BlendTime = FMath::Max(MinBlendTime, float(S->GetNumberField(TEXT("blendFrames"))) / CoHFps);
			for (const TSharedPtr<FJsonValue>& NV : S->GetArrayField(TEXT("next")))
			{
				const TArray<TSharedPtr<FJsonValue>>& Pair = NV->AsArray();
				if (const int32* I = Index.Find(FName(Pair[0]->AsString())))
				{
					St.Next.Add(*I);
					St.Weight.Add(float(Pair[1]->AsNumber()));
				}
			}
		}
		for (const TSharedPtr<FJsonValue>& EV : G->GetArrayField(TEXT("entries")))
		{
			if (const int32* I = Index.Find(FName(EV->AsString())))
			{
				Out.Entries.Add(*I);
			}
		}
	}
	return Graphs.Num() > 0;
}

void UCoHIdleComponent::FindClips()
{
	if (ClipFolder.Path.IsEmpty())
	{
		return;
	}
	FString Folder = ClipFolder.Path;
	if (!Folder.StartsWith(TEXT("/")))
	{
		Folder = TEXT("/Game/") + Folder;
	}
	TArray<FAssetData> Assets;
	IAssetRegistry& Reg = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry").Get();
	Reg.GetAssetsByPath(FName(*Folder), Assets, true);

	TSet<FName> Wanted;
	for (const FGraph& G : Graphs)
	{
		for (const FState& S : G.States)
		{
			Wanted.Add(S.Move);
		}
	}
	for (const FName& Move : Wanted)
	{
		if (Clips.Contains(Move))
		{
			continue;
		}
		// exact name first, then the shortest "<anything>_<Move>"
		const FString M = Move.ToString();
		const FAssetData* Best = nullptr;
		for (const FAssetData& A : Assets)
		{
			if (!A.IsInstanceOf(UAnimSequence::StaticClass()))
			{
				continue;
			}
			const FString N = A.AssetName.ToString();
			if (N.Equals(M, ESearchCase::IgnoreCase))
			{
				Best = &A;
				break;
			}
			if (N.EndsWith(TEXT("_") + M, ESearchCase::IgnoreCase) &&
				(!Best || N.Len() < Best->AssetName.ToString().Len()))
			{
				Best = &A;
			}
		}
		if (Best)
		{
			Clips.Add(Move, Cast<UAnimSequence>(Best->GetAsset()));
		}
	}
}

void UCoHIdleComponent::BeginPlay()
{
	Super::BeginPlay();
	Rng.Initialize(Seed ? Seed : FMath::Rand());
	RateScale = 1.f + Rng.FRandRange(-PlayRateJitter, PlayRateJitter);

	Mesh = GetOwner() ? GetOwner()->FindComponentByClass<USkeletalMeshComponent>() : nullptr;
	if (!Mesh || !LoadGraphs())
	{
		SetComponentTickEnabled(false);
		return;
	}
	FindClips();

	// drop states with no clip; graphs left empty can't be used
	for (FGraph& G : Graphs)
	{
		for (FState& S : G.States)
		{
			for (int32 i = S.Next.Num() - 1; i >= 0; --i)
			{
				if (!Clips.FindRef(G.States[S.Next[i]].Move))
				{
					S.Next.RemoveAt(i);
					S.Weight.RemoveAt(i);
				}
			}
		}
		G.Entries.RemoveAll([&](int32 I) { return !Clips.FindRef(G.States[I].Move); });
	}

	Mesh->SetAnimInstanceClass(UCoHIdleAnimInstance::StaticClass());
	Anim = Cast<UCoHIdleAnimInstance>(Mesh->GetAnimInstance());
	if (!Anim)
	{
		UE_LOG(LogCoHIdle, Warning, TEXT("%s: could not create the idle anim instance"), *GetNameSafe(GetOwner()));
		SetComponentTickEnabled(false);
		return;
	}

	FName Start = Pose;
	if (Start.IsNone())
	{
		// weighted by how often the original spawns used the pose; Ready
		// (never named by spawns) counts as much as the most common one
		TArray<int32> Pool;
		TArray<float> W;
		float MaxCount = 1.f;
		for (const FGraph& G : Graphs)
		{
			MaxCount = FMath::Max(MaxCount, float(G.SpawnCount));
		}
		for (int32 i = 0; i < Graphs.Num(); ++i)
		{
			const FGraph& G = Graphs[i];
			const bool bListed = PosePool.Num() ? PosePool.Contains(G.Pose) : !G.bNeedsProp;
			if (bListed && G.Entries.Num())
			{
				Pool.Add(i);
				W.Add(G.SpawnCount > 0 ? float(G.SpawnCount) : MaxCount);
			}
		}
		float Total = 0.f;
		for (float X : W)
		{
			Total += X;
		}
		float R = Rng.FRandRange(0.f, Total);
		for (int32 i = 0; i < Pool.Num(); ++i)
		{
			R -= W[i];
			if (R <= 0.f || i == Pool.Num() - 1)
			{
				Start = Graphs[Pool[i]].Pose;
				break;
			}
		}
	}
	if (!SetPose(Start))
	{
		UE_LOG(LogCoHIdle, Warning, TEXT("%s: no clips found for pose %s in %s"),
			*GetNameSafe(GetOwner()), *Start.ToString(), *ClipFolder.Path);
		SetComponentTickEnabled(false);
	}
}

bool UCoHIdleComponent::SetPose(FName NewPose)
{
	if (!Anim)
	{
		Pose = NewPose;     // applied at BeginPlay
		return true;
	}
	const int32 G = Graphs.IndexOfByPredicate([&](const FGraph& X) { return X.Pose == NewPose; });
	if (G == INDEX_NONE || Graphs[G].Entries.Num() == 0)
	{
		return false;
	}
	const bool bFirst = GraphIndex == INDEX_NONE;
	Pose = NewPose;
	GraphIndex = G;
	const TArray<int32>& E = Graphs[G].Entries;
	PlayState(E[Rng.RandRange(0, E.Num() - 1)], bFirst);
	SetComponentTickEnabled(true);
	return true;
}

void UCoHIdleComponent::SetIdleActive(bool bActive)
{
	bIdleActive = bActive;
	if (Mesh && Anim && bActive && Mesh->GetAnimInstance() != Anim)
	{
		// something else took the mesh over; take it back and restart the pose
		Mesh->SetAnimInstanceClass(UCoHIdleAnimInstance::StaticClass());
		Anim = Cast<UCoHIdleAnimInstance>(Mesh->GetAnimInstance());
		GraphIndex = INDEX_NONE;
		SetPose(Pose);
	}
}

FName UCoHIdleComponent::GetCurrentMove() const
{
	return Graphs.IsValidIndex(GraphIndex) && Graphs[GraphIndex].States.IsValidIndex(StateIndex)
		? Graphs[GraphIndex].States[StateIndex].Move : NAME_None;
}

int32 UCoHIdleComponent::PickNext(const FState& S)
{
	if (S.Next.Num() == 0)
	{
		return StateIndex;
	}
	float Total = 0.f;
	for (float W : S.Weight)
	{
		Total += W;
	}
	float R = Rng.FRandRange(0.f, Total);
	for (int32 i = 0; i < S.Next.Num(); ++i)
	{
		R -= S.Weight[i];
		if (R <= 0.f)
		{
			return S.Next[i];
		}
	}
	return S.Next.Last();
}

void UCoHIdleComponent::PlayState(int32 Index, bool bRandomStart)
{
	const FState& S = Graphs[GraphIndex].States[Index];
	UAnimSequence* Seq = Clips.FindRef(S.Move);
	if (!Seq)
	{
		return;
	}
	// a move cycling into itself just loops, like seqCycleFrame; anything
	// else blends from the frame the last move ended on
	const bool bLoop = Index == StateIndex && Anim->GetCurrentClip() == Seq;
	const float Start = bRandomStart ? Rng.FRandRange(0.f, Seq->GetPlayLength()) : 0.f;
	StateIndex = Index;
	Anim->PlayClip(Seq, Start, S.PlayRate * RateScale, bLoop || bRandomStart ? 0.f : S.BlendTime);
}

void UCoHIdleComponent::TickComponent(float DeltaTime, ELevelTick TickType,
	FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (!bIdleActive || !Anim || !Graphs.IsValidIndex(GraphIndex) || !Anim->IsClipFinished())
	{
		return;
	}
	PlayState(PickNext(Graphs[GraphIndex].States[StateIndex]), false);
}

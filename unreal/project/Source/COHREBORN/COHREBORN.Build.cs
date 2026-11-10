using UnrealBuildTool;

public class COHREBORN : ModuleRules
{
	public COHREBORN(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] {
			"Core", "CoreUObject", "Engine", "Json", "JsonUtilities",
			"EnhancedInput", "InputCore", "AIModule", "NavigationSystem",
			"MoviePlayer", "Slate", "SlateCore", "UMG", "AssetRegistry", "ProceduralMeshComponent"
		});
        if (Target.bBuildEditor) PrivateDependencyModuleNames.AddRange(new string[] { "PhysicsUtilities", "AssetRegistry" });
	}
}

using UnrealBuildTool;

public class COHREBORN : ModuleRules
{
	public COHREBORN(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] {
			"Core", "CoreUObject", "Engine", "PhysicsCore", "Json", "JsonUtilities",
			"EnhancedInput", "InputCore", "AIModule", "NavigationSystem",
			"MoviePlayer", "Slate", "SlateCore", "UMG", "AssetRegistry", "ProceduralMeshComponent",
			"Sockets", "Networking", "ApplicationCore"
		});
        if (Target.bBuildEditor) PrivateDependencyModuleNames.AddRange(new string[] { "PhysicsUtilities", "AssetRegistry" });
	}
}

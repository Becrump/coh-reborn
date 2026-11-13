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
			"Sockets", "Networking", "ApplicationCore", "HTTP",
			"LevelSequence", "MovieScene"
		});
        // UPnP router port opening for the HQ lobby (CoHPortMapper)
        if (Target.Platform == UnrealTargetPlatform.Win64) PublicSystemLibraries.AddRange(new string[] { "ole32.lib", "oleaut32.lib" });
        if (Target.bBuildEditor) PrivateDependencyModuleNames.AddRange(new string[] { "PhysicsUtilities", "AssetRegistry" });
	}
}

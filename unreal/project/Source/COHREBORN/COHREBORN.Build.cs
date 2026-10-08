using UnrealBuildTool;

public class COHREBORN : ModuleRules
{
	public COHREBORN(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] {
			"Core", "CoreUObject", "Engine", "Json", "JsonUtilities",
			"EnhancedInput", "InputCore"
		});
	}
}

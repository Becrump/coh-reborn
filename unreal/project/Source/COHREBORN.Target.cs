using UnrealBuildTool;

public class COHREBORNTarget : TargetRules
{
	public COHREBORNTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("COHREBORN");
	}
}

using UnrealBuildTool;

public class COHREBORNEditorTarget : TargetRules
{
	public COHREBORNEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("COHREBORN");
	}
}

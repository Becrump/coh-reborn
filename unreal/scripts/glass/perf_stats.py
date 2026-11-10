"""Toggle the on-screen perf overlays used for the before/after numbers (stat unit + stat rhi).
Read the numbers off a CaptureViewport/HighResShot frame taken after a few seconds of settling."""
import unreal
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
for c in ("stat unit", "stat rhi"):
    unreal.SystemLibrary.execute_console_command(w, c)
print("toggled stat unit / stat rhi")

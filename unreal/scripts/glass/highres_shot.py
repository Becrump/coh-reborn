import unreal, os
name = os.environ.get('SHOT','test')
cam = [float(x) for x in os.environ.get('CAM','40778,29128,13709,24.4,78.2').split(',')]
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ues.set_level_viewport_camera_info(unreal.Vector(*cam[:3]), unreal.Rotator(roll=0, pitch=cam[3], yaw=cam[4]))
w = ues.get_editor_world()
unreal.SystemLibrary.execute_console_command(w, 'HighResShot 1920x1080 filename="%s/glass_%s"' % (unreal.Paths.convert_relative_path_to_full(unreal.Paths.screen_shot_dir()).rstrip('/'), name))
print("requested", unreal.Paths.convert_relative_path_to_full(unreal.Paths.screen_shot_dir()))

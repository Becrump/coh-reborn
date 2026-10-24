import unreal
s=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
w=s.get_editor_world()
a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
print('WORLD',w.get_path_name(),'LOADED',len(a))
print('CAMERA',s.get_level_viewport_camera_info())
print('DESCRIPTORS',len(unreal.WorldPartitionBlueprintLibrary.get_actor_descs()))

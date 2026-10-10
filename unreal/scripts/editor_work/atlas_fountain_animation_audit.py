import unreal,json,pathlib
s=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
print('WORLD',s.get_editor_world().get_path_name(),'ACTORS',len(a),'CAM',s.get_level_viewport_camera_info())
print('WATER',[(x.get_actor_label(),str(x.get_actor_location())) for x in a if any(k in x.get_actor_label().lower() for k in ['water','fountain','cityhall'])][:35])
f=unreal.load_asset('/Game/CoH/FX/NS_CoH_Fountain')
print('FOUNTAIN',f)
print('NIAGARA API',[n for n in dir(f) if any(k in n for k in ['parameter','emitter','valid'])])
print('ANIM LOADED',sum(x.get_actor_label().startswith('CoHOriginal_') for x in a))

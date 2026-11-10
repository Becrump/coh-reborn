import unreal
s=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
d=unreal.WorldPartitionBlueprintLibrary.get_actor_descs()
cam,_=s.get_level_viewport_camera_info()
ids=[]
for x in d:
 if not str(x.label).startswith('CoHOriginal_'):
  ids.append(x.guid)
 else:
  c=(x.bounds.min+x.bounds.max)*0.5
  if (c-cam).length()<18000: ids.append(x.guid)
unreal.WorldPartitionBlueprintLibrary.load_actors(ids)
print('VISIBLE LOADED',len(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()))

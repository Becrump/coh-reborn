import unreal
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
for a in actors:
 if a.get_class().get_name().startswith('BP_CoH_ArcFountain'):
  print('FOUNTAIN',a.get_actor_label(),a.get_actor_transform())
  for c in a.get_components_by_class(unreal.StaticMeshComponent):
   print('COMP',c.get_name(),c.get_editor_property('relative_location'),c.get_editor_property('relative_scale3d'),c.get_material(0))
print('CUSTOM INPUT',[n for n in dir(unreal.CustomInput) if not n.startswith('_')])
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

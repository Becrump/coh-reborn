import unreal
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in sub.get_all_level_actors():
 if a.get_actor_label().startswith('AtlasDressing_'):
  a.modify();c=a.static_mesh_component;c.modify();c.set_collision_profile_name('NoCollision');c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
parent=unreal.load_asset('/Engine/BasicShapes/BasicShapeMaterial')
print('COLOR PARAMETERS',unreal.MaterialEditingLibrary.get_vector_parameter_names(parent))
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

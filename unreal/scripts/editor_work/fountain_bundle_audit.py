import unreal
s=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in s.get_all_level_actors():
 c=a.get_component_by_class(unreal.StaticMeshComponent)
 if c and c.get_editor_property('static_mesh') and 'ArcJet' in c.get_editor_property('static_mesh').get_path_name():
  print('JET',a.get_actor_label(),a.get_path_name(),a.get_actor_transform())

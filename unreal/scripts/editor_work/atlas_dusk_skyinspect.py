import unreal
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
 if any(t in a.get_actor_label().lower() for t in ['sky','atmos','cloud']) or a.get_actor_label() in ['Sun','Moon']:
  print(a.get_actor_label(),a.get_class().get_name(),'hidden',a.get_editor_property('hidden'),'editor',a.is_hidden_ed(),a.get_actor_location())
  c=a.get_component_by_class(unreal.DirectionalLightComponent)
  if c:print('index',c.get_editor_property('atmosphere_sun_light_index'))

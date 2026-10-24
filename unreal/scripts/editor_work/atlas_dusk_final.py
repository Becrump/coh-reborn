import unreal,builtins
sun=builtins.atlas_dusk_sun
sun.set_actor_rotation(unreal.Rotator(pitch=-4,yaw=-40,roll=0),False)
sun.get_component_by_class(unreal.DirectionalLightComponent).set_intensity(50000)
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
 if isinstance(a,unreal.PostProcessVolume):
  s=a.get_editor_property('settings')
  s.set_editor_property('auto_exposure_min_brightness',11)
  s.set_editor_property('auto_exposure_max_brightness',11)
  a.set_editor_property('settings',s)
print('Final dusk exposure')

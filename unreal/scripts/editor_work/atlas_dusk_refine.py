import unreal,builtins
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
print([(a.get_actor_label(),a.get_class().get_name()) for a in actors if a.get_actor_label().endswith('_night')][:25])
for a in actors:
 if a.get_actor_label().endswith('_night') and not isinstance(a,unreal.Light):
  a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True)
 if isinstance(a,unreal.PostProcessVolume):
  original=a.get_editor_property('settings')
  builtins.atlas_dusk_restore.append((a,'settings',original))
  s=a.get_editor_property('settings')
  s.set_editor_property('auto_exposure_min_brightness',10)
  s.set_editor_property('auto_exposure_max_brightness',10)
  a.set_editor_property('settings',s)
builtins.atlas_dusk_sun.set_actor_rotation(unreal.Rotator(pitch=-5,yaw=-40,roll=0),False)
builtins.atlas_dusk_sun.get_component_by_class(unreal.DirectionalLightComponent).set_intensity(1000)
w,mpc,_=builtins.atlas_dusk_mpc
unreal.MaterialLibrary.set_scalar_parameter_value(w,mpc,'Night',0.25)
print('Dusk lighting refined')

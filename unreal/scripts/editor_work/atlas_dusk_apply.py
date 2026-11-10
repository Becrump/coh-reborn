import unreal,builtins
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
builtins.atlas_dusk_restore=[]
def keep(obj,prop):
 value=obj.get_editor_property(prop)
 builtins.atlas_dusk_restore.append((obj,prop,value))
 return value
for a in actors:
 if isinstance(a,unreal.PostProcessVolume):
  s=a.get_editor_property('settings')
  print('PP',a.get_actor_label(),[(p,str(s.get_editor_property(p))) for p in ['auto_exposure_min_brightness','auto_exposure_max_brightness','auto_exposure_bias','override_auto_exposure_bias','override_auto_exposure_min_brightness','override_auto_exposure_max_brightness']])
 if a.get_actor_label()=='Sun':
  builtins.atlas_dusk_sun=a
  builtins.atlas_dusk_sun_rotation=a.get_actor_rotation()
  c=a.get_component_by_class(unreal.DirectionalLightComponent)
  keep(c,'intensity')
  a.set_actor_rotation(unreal.Rotator(pitch=-2.0,yaw=-40,roll=0),False)
  c.set_intensity(800)
 if a.get_actor_label()=='HeightFog':
  c=a.get_component_by_class(unreal.ExponentialHeightFogComponent)
  keep(c,'fog_density');keep(c,'start_distance')
  c.set_editor_property('fog_density',0.000015)
  c.set_editor_property('start_distance',3000)
 if a.get_actor_label().endswith('_night') or a.get_actor_label().startswith('Lamp_Light_'):
  keep(a,'hidden')
  builtins.atlas_dusk_restore.append((a,'__editor_hidden',a.is_temporarily_hidden_in_editor()))
  a.set_actor_hidden_in_game(False)
  a.set_is_temporarily_hidden_in_editor(False)
mpc=unreal.load_asset('/Game/CoH/Materials/MPC_CoH')
w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
builtins.atlas_dusk_mpc=(w,mpc,unreal.MaterialLibrary.get_scalar_parameter_value(w,mpc,'Night'))
unreal.MaterialLibrary.set_scalar_parameter_value(w,mpc,'Night',0.65)
print('DUSK applied, restore entries',len(builtins.atlas_dusk_restore))

import unreal,json,builtins
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_SecondPass' in w.get_path_name()
state={'lights':[],'pp':[]}
for a in sub.get_all_level_actors():
 if a.get_actor_label()=='Sun':
  rot=a.get_actor_rotation();c=a.get_component_by_class(unreal.DirectionalLightComponent)
  state['sun']={'rotation':[rot.pitch,rot.yaw,rot.roll],'intensity':c.get_editor_property('intensity')}
  a.set_actor_rotation(unreal.Rotator(pitch=-4,yaw=-40,roll=0),False);c.set_intensity(50000)
 if a.get_actor_label()=='HeightFog':
  c=a.get_component_by_class(unreal.ExponentialHeightFogComponent);state['fog']={'fog_density':c.get_editor_property('fog_density'),'start_distance':c.get_editor_property('start_distance')}
  c.set_editor_property('fog_density',.000015);c.set_editor_property('start_distance',3000)
 if isinstance(a,unreal.PostProcessVolume):
  s=a.get_editor_property('settings');state['pp'].append({'label':a.get_actor_label(),'min':s.get_editor_property('auto_exposure_min_brightness'),'max':s.get_editor_property('auto_exposure_max_brightness')})
  s.set_editor_property('auto_exposure_min_brightness',11);s.set_editor_property('auto_exposure_max_brightness',11);a.set_editor_property('settings',s)
 if isinstance(a,unreal.Light) and (a.get_actor_label().startswith('Lamp_Light_') or a.get_actor_label().endswith('_night')):
  state['lights'].append({'label':a.get_actor_label(),'hidden':a.get_editor_property('hidden'),'editor':a.is_temporarily_hidden_in_editor()})
  a.set_actor_hidden_in_game(False);a.set_is_temporarily_hidden_in_editor(False)
mpc=unreal.load_asset('/Game/CoH/Materials/MPC_CoH');state['night']=unreal.MaterialLibrary.get_scalar_parameter_value(w,mpc,'Night');unreal.MaterialLibrary.set_scalar_parameter_value(w,mpc,'Night',.25)
json.dump(state,open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_pass2_daylight.json','w'),indent=2)
print('DUSK preview applied; daylight snapshot recorded')

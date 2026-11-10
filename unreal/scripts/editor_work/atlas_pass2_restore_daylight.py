import unreal,json
s=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_pass2_daylight.json'))
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();actors={a.get_actor_label():a for a in sub.get_all_level_actors()}
a=actors['Sun'];p,y,r=s['sun']['rotation'];a.set_actor_rotation(unreal.Rotator(pitch=p,yaw=y,roll=r),False);a.get_component_by_class(unreal.DirectionalLightComponent).set_intensity(s['sun']['intensity'])
c=actors['HeightFog'].get_component_by_class(unreal.ExponentialHeightFogComponent)
for p,v in s['fog'].items():c.set_editor_property(p,v)
for r in s['pp']:
 a=actors[r['label']];p=a.get_editor_property('settings');p.set_editor_property('auto_exposure_min_brightness',r['min']);p.set_editor_property('auto_exposure_max_brightness',r['max']);a.set_editor_property('settings',p)
 assert a.get_editor_property('settings').get_editor_property('auto_exposure_min_brightness')==r['min']
 assert a.get_editor_property('settings').get_editor_property('auto_exposure_max_brightness')==r['max']
for r in s['lights']:
 a=actors[r['label']];a.set_actor_hidden_in_game(r['hidden']);a.set_is_temporarily_hidden_in_editor(r['editor'])
mpc=unreal.load_asset('/Game/CoH/Materials/MPC_CoH');unreal.MaterialLibrary.set_scalar_parameter_value(w,mpc,'Night',s['night'])
print('DAYLIGHT RESTORED',a.get_actor_label(),'sun lux',s['sun']['intensity'],'night',s['night'])
print('SAVE RESTORED MAP',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

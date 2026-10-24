import unreal,builtins
for obj,prop,value in reversed(builtins.atlas_dusk_restore):
 if prop=='__editor_hidden':obj.set_is_temporarily_hidden_in_editor(value)
 elif prop=='hidden':obj.set_actor_hidden_in_game(value)
 elif prop=='intensity':obj.set_intensity(value)
 else:obj.set_editor_property(prop,value)
builtins.atlas_dusk_sun.set_actor_rotation(builtins.atlas_dusk_sun_rotation,False)
w,mpc,value=builtins.atlas_dusk_mpc
unreal.MaterialLibrary.set_scalar_parameter_value(w,mpc,'Night',value)
errors=[]
for obj,prop,value in builtins.atlas_dusk_restore:
 if prop=='__editor_hidden':current=obj.is_temporarily_hidden_in_editor()
 else:current=obj.get_editor_property(prop)
 if str(current)!=str(value) and prop!='settings':errors.append((obj.get_name(),prop))
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
 if isinstance(a,unreal.PostProcessVolume):
  s=a.get_editor_property('settings')
  print('RESTORED EXPOSURE',s.get_editor_property('auto_exposure_min_brightness'),s.get_editor_property('auto_exposure_max_brightness'))
print('RESTORE errors',errors,'Sun',builtins.atlas_dusk_sun.get_actor_rotation(),'Night',unreal.MaterialLibrary.get_scalar_parameter_value(w,mpc,'Night'))

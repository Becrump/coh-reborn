import unreal
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
for a in actors:
 for cls,props in [(unreal.DirectionalLightComponent,['intensity','light_color','atmosphere_sun_light']), (unreal.SkyLightComponent,['intensity','light_color']), (unreal.ExponentialHeightFogComponent,['fog_density','start_distance','fog_inscattering_luminance']), (unreal.PostProcessComponent,[])]:
  c=a.get_component_by_class(cls)
  if c:
   print(a.get_actor_label(),a.get_actor_rotation(),[(p,str(c.get_editor_property(p))) for p in props])
   if cls==unreal.PostProcessComponent:
    s=c.get_editor_property('settings')
    print([(p,str(s.get_editor_property(p))) for p in ['auto_exposure_min_brightness','auto_exposure_max_brightness','auto_exposure_bias','override_auto_exposure_bias','override_auto_exposure_min_brightness','override_auto_exposure_max_brightness']])
mpc=unreal.load_asset('/Game/CoH/Materials/MPC_CoH')
w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
print('MPC Night',unreal.MaterialLibrary.get_scalar_parameter_value(w,mpc,'Night'))
print('NIGHT ACTORS',[(a.get_actor_label(),a.is_hidden_ed(),a.is_hidden()) for a in actors if a.get_actor_label().endswith('_night') or a.get_actor_label().startswith('Lamp_Light_')][:8])

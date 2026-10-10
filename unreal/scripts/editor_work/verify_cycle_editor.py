import unreal,json
lib=unreal.LevelSequenceEditorBlueprintLibrary
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors(); by={a.get_actor_label():a for a in actors}
cycle=by['DayNightCycle'];seq=cycle.get_sequence()
mpc=unreal.load_asset('/Game/CoH/Materials/MPC_CoH')
print('MPC',mpc)
for frame in [0,21600,0]:
 lib.set_current_time(frame);lib.force_update()
 print('SAMPLE',frame,'SUN',by['Sun'].get_actor_rotation(),'MOON',by['Moon'].get_actor_rotation())
 print('NIGHT',unreal.MaterialLibrary.get_scalar_parameter_value(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(),mpc,'Night'))
print('UNRESOLVED',[(b.get_name(),str(b.get_id())) for b in seq.get_bindings() if not lib.get_bound_objects(seq.get_binding_id(b))][:20])
print('AUTOPLAY',cycle.get_editor_property('playback_settings').auto_play,'RATE',cycle.get_editor_property('playback_settings').play_rate)
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

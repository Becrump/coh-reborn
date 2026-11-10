import unreal
w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
seq=unreal.load_asset('/Game/CoH/DayNight')
for b in seq.get_bindings():
 if any(n in b.get_name().lower() for n in ['sun','moon','sky','fog','directional']):
  print('BIND',b.get_name(),'ID',b.get_id().to_string(),'PARENT',b.get_parent().get_name() if b.get_parent().is_valid() else 'NONE','TRACKS',[(t.get_class().get_name(),len(t.get_sections())) for t in b.get_tracks()])
  o=unreal.SequencerTools.get_bound_objects(w,seq,[b],seq.get_playback_range());print('BOUND',[x.get_path_name() for r in o for x in r.bound_objects])
print('HELP',unreal.LevelSequence.rebind_possessable_objects.__doc__ if hasattr(unreal.LevelSequence,'rebind_possessable_objects') else [n for n in dir(unreal.LevelSequence) if any(s in n for s in ['bind','possess'])])

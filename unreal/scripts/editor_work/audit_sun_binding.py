import unreal
s=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
a=s.get_all_level_actors()
cycle=next(x for x in a if isinstance(x,unreal.LevelSequenceActor) and x.get_actor_label()=='DayNightCycle')
seq=cycle.get_sequence()
for b in seq.get_bindings():
 print('BINDING',b.get_name(),b.get_id(),[(t.get_class().get_name(),len(t.get_sections())) for t in b.get_tracks()])
 try:
  objects=unreal.SequencerTools.get_bound_objects(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(),seq,[b],seq.get_playback_range())
  print('RESOLVED',[(str(o.binding_proxy.get_name()),[x.get_path_name() for x in o.bound_objects]) for o in objects])
 except Exception as e:print('RESOLVE ERROR',str(e))
for x in a:
 if isinstance(x,unreal.DirectionalLight):print('LIGHT',x.get_actor_label(),x.get_path_name(),x.get_actor_rotation())

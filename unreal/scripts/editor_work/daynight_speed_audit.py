import unreal
s=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in s.get_all_level_actors():
 if isinstance(a,unreal.LevelSequenceActor):
  seq=a.get_sequence()
  print('SEQUENCE ACTOR',a.get_actor_label(),'SEQUENCE',seq.get_path_name() if seq else None,'SETTINGS',a.get_editor_property('playback_settings'))
  if seq: print('RANGE',seq.get_playback_start(),seq.get_playback_end(),'RATE',seq.get_display_rate())

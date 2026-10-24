import unreal
s=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
a=next(a for a in s.get_all_level_actors() if isinstance(a,unreal.LevelSequenceActor) and a.get_actor_label()=='DayNightCycle')
print('CURRENT RATE',a.get_editor_property('playback_settings').play_rate)
print('SAVE RESULT',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))
seq=a.get_sequence();r=seq.get_display_rate();seconds=(seq.get_playback_end()-seq.get_playback_start())*r.denominator/r.numerator
print('FULL DAY MINUTES',seconds/a.get_editor_property('playback_settings').play_rate/60)

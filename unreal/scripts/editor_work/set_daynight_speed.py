import unreal
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors=[a for a in sub.get_all_level_actors() if isinstance(a,unreal.LevelSequenceActor) and a.get_actor_label()=='DayNightCycle']
assert len(actors)==1
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
a=actors[0];a.modify();ps=a.get_editor_property('playback_settings');old=ps.play_rate;ps.play_rate=1.0;a.set_editor_property('playback_settings',ps)
assert a.get_editor_property('playback_settings').play_rate==1.0
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
seq=a.get_sequence();rate=seq.get_display_rate();seconds=(seq.get_playback_end()-seq.get_playback_start())*rate.denominator/rate.numerator
print('BEFORE full-day minutes',seconds/old/60,'AFTER full-day minutes',seconds/60,'game-hour seconds',seconds/24)

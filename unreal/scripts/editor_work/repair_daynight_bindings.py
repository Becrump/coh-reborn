import unreal
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);actors=sub.get_all_level_actors()
cycle=next(a for a in actors if isinstance(a,unreal.LevelSequenceActor) and a.get_actor_label()=='DayNightCycle')
seq=cycle.get_sequence();assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
cycle.modify();bylabel={a.get_actor_label():a for a in actors};count=0
for b in seq.get_bindings():
 if not b.get_parent().is_valid() and b.get_name() in bylabel:
  cycle.set_binding(seq.get_binding_id(b),[bylabel[b.get_name()]],False);count+=1
print('ROOT BINDINGS RECONNECTED',count)
print('OVERRIDES API',[n for n in dir(cycle.get_editor_property('binding_overrides')) if 'bind' in n])
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))
print('PLAYER API',[n for n in dir(cycle.get_editor_property('sequence_player')) if any(s in n for s in ['bound','playback_position','initialize'])])

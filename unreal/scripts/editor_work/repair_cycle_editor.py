import unreal,json
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors=sub.get_all_level_actors(); bylabel={a.get_actor_label():a for a in actors}
cycle=bylabel['DayNightCycle']; source=cycle.get_sequence()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
path='/Game/CoH/DayNight_AtlasPark_DressingStudy'
seq=unreal.load_asset(path)
if not seq:
 seq=unreal.EditorAssetLibrary.duplicate_asset(source.get_path_name(),path)
assert seq
unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(seq)
editor=unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
count=0;missing=[]
for b in list(seq.get_bindings()):
 if not b.get_parent().is_valid():
  a=bylabel.get(b.get_name())
  if a:
   editor.replace_binding_with_actors([a],b);count+=1
  else: missing.append(b.get_name())
print('REPAIRED ROOTS',count,'MISSING',missing)
cycle.modify();cycle.set_sequence(seq)
print('ASSET SAVE',unreal.EditorAssetLibrary.save_loaded_asset(seq,False))
print('LEVEL SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))
for b in seq.get_bindings():
 if b.get_name() in ['Sun','Moon','SkyLight','HeightFog','SkyLightComponent0','HeightFogComponent0']:
  print('BOUND',b.get_name(),[x.get_path_name() for x in unreal.LevelSequenceEditorBlueprintLibrary.get_bound_objects(seq.get_binding_id(b))])
print('TIME',unreal.LevelSequenceEditorBlueprintLibrary.get_current_time())

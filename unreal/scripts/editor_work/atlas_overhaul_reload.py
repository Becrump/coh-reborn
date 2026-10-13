import unreal
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
for name in ['actors','tile_actors','world','w','a','c','old','sun','sky','v','pp','buildings']:
    globals().pop(name,None)
assert 'save_existing_map' in unreal.EditorLoadingAndSavingUtils.new_blank_map.__doc__
unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
assert unreal.EditorLoadingAndSavingUtils.load_map('/Game/AtlasPark4/AtlasPark_Upgraded')
unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in unreal.WorldPartitionBlueprintLibrary.get_actor_descs()])
print('RELOADED',sum(a.get_actor_label().startswith('AtlasUpgrade_') for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()))

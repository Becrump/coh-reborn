import unreal,json,itertools
u=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
w=u.get_editor_world();assert 'AtlasPark_Upgraded' in w.get_path_name(),w.get_path_name()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
assert not unreal.EditorAssetLibrary.does_asset_exist('/Game/AtlasPark4/AtlasPark_SecondPass')
assert unreal.EditorLoadingAndSavingUtils.save_map(w,'/Game/AtlasPark4/AtlasPark_SecondPass')
assert unreal.EditorLoadingAndSavingUtils.load_map('/Game/AtlasPark4/AtlasPark_SecondPass')
unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in unreal.WorldPartitionBlueprintLibrary.get_actor_descs()])
print('RECOVERY preserved Upgraded; WORKING',u.get_editor_world().get_path_name())

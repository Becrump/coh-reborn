import unreal,json
ROOT='/Game/AtlasUpgraded/Geometry'
w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert 'AtlasPark_Upgraded' in w.get_path_name()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
task=unreal.AssetImportTask();task.filename='C:/Users/rtcru/CoHReborn/out/atlas_upgraded/atlas_upgraded.gltf'
task.destination_path=ROOT;task.automated=True;task.save=True;task.replace_existing=False
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
assert task.imported_object_paths,'No imported objects'
print('IMPORTED',len(task.imported_object_paths))
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

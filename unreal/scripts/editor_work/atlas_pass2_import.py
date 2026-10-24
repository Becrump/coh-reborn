import unreal,json
w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_SecondPass' in w.get_path_name()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
task=unreal.AssetImportTask();task.filename='C:/Users/rtcru/CoHReborn/out/atlas_secondpass/atlas_secondpass.gltf';task.destination_path='/Game/AtlasSecondPass/Geometry';task.automated=True;task.save=True;task.replace_existing=False
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task]);assert task.imported_object_paths
print('PERIMETER IMPORT',len(task.imported_object_paths))

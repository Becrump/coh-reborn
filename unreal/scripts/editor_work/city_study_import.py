import unreal
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert 'AtlasPark_CitySampleStudy' in unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name()
for a in sub.get_all_level_actors():
    if a.get_actor_label().startswith('STUDY_Catalog_'): sub.destroy_actor(a)
task=unreal.AssetImportTask()
task.filename='C:/Users/rtcru/CoHReborn/out/atlas_rebuilt_block/rebuilt.gltf'
task.destination_path='/Game/AtlasRebuiltStudy/Infrastructure'
task.automated=True
task.save=True
task.replace_existing=False
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
print('imported',list(task.imported_object_paths))

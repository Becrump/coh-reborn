import unreal,json
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
task=unreal.AssetImportTask();task.filename='C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_modern_bench.glb';task.destination_path='/Game/AtlasDressingStudy/Props';task.automated=True;task.save=True;task.replace_existing=False
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task]);assert task.imported_object_paths
reg=unreal.AssetRegistryHelpers.get_asset_registry();meshes=[d.get_asset() for d in reg.get_assets_by_path('/Game/AtlasDressingStudy/Props',True) if str(d.asset_class_path.asset_name)=='StaticMesh'];assert len(meshes)==1
m=meshes[0]
for i,s in enumerate(m.static_materials):
 name=str(s.material_slot_name);mat=unreal.load_asset('/Game/AtlasDressingStudy/Materials/MI_'+('Seat' if 'Seat' in name else 'Metal'));assert mat;m.set_material(i,mat)
bs=m.get_editor_property('body_setup');bs.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE);assert unreal.EditorAssetLibrary.save_loaded_asset(m,False)
json.dump({'mesh':m.get_path_name()},open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_core_bench_asset.json','w'))
print('BENCH',m.get_path_name(),'BOUNDS',m.get_bounding_box(),'SLOTS',[str(s.material_slot_name) for s in m.static_materials])

"""Import the exported original enemy library without reimporting the city."""
import json
import pathlib
import time
import unreal

BASE = pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
SOURCE = pathlib.Path(r'C:\Users\rtcru\CoHReborn\out\characters')
ROOT = '/Game/Characters/OriginalEnemies'
reg = unreal.AssetRegistryHelpers.get_asset_registry()
el = unreal.EditorAssetLibrary
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
index = json.loads((SOURCE / 'index.json').read_text())
selected = globals().get('ENEMY_IMPORT_COSTUMES')
if selected is not None:
    index = [e for e in index if e['costume'] in selected]
limit = int(globals().get('ENEMY_IMPORT_LIMIT', 0))
report_path = BASE / 'atlas_enemy_import_report.json'
report = json.loads(report_path.read_text()) if report_path.exists() else {}
manager = unreal.InterchangeManager.get_interchange_manager_scripted()
new_count = 0
for n, entry in enumerate(index):
    costume = entry['costume']
    dest = ROOT + '/' + (entry.get('group') or 'Misc') + '/' + costume
    known = report.get(costume)
    if known and el.does_asset_exist(known.get('mesh', '')):
        continue
    if limit and new_count >= limit:
        break
    pipe = unreal.InterchangeGenericAssetsPipeline()
    pipe.set_editor_property('scene_name_sub_folder', False)
    pipe.set_editor_property('asset_type_sub_folders', True)
    meshpipe = pipe.get_editor_property('mesh_pipeline')
    meshpipe.set_editor_property('combine_skeletal_meshes_behavior', unreal.InterchangeCombineSkeletalMeshesBehavior.BY_SKELETON)
    meshpipe.set_editor_property('create_physics_asset', False)
    asset_type = entry.get('asset_type', 'SkeletalMesh')
    meshpipe.set_editor_property('import_static_meshes', asset_type == 'StaticMesh')
    meshpipe.set_editor_property('import_skeletal_meshes', asset_type == 'SkeletalMesh')
    params = unreal.ImportAssetParameters()
    params.set_editor_property('is_automated', True)
    params.set_editor_property('replace_existing', False)
    params.set_editor_property('override_pipelines', [unreal.SoftObjectPath(pipe.get_path_name())])
    ok = manager.import_asset(dest, unreal.InterchangeManager.create_source_data(str(SOURCE / entry['gltf'])), params)
    assets = reg.get_assets_by_path(dest, True)
    meshes = [d.get_asset() for d in assets if str(d.asset_class_path.asset_name) == asset_type]
    clips = [d.get_asset() for d in assets if str(d.asset_class_path.asset_name) == 'AnimSequence']
    if not ok or len(meshes) != 1:
        report[costume] = {'error': 'Expected one combined ' + asset_type, 'meshes': [m.get_path_name() for m in meshes], 'import_success': bool(ok)}
        report_path.write_text(json.dumps(report, indent=2))
        raise RuntimeError(str(report[costume]))
    mesh = meshes[0]
    for d in assets:
        el.save_loaded_asset(d.get_asset(), False)
    bounds = mesh.get_bounds()
    report[costume] = {'mesh': mesh.get_path_name(), 'group': entry.get('group'), 'asset_type': asset_type,
                       'clips': {c.get_name(): c.get_path_name() for c in clips},
                       'height_cm': bounds.box_extent.z * 2,
                       'source': entry['gltf'], 'materials': len(mesh.get_editor_property('materials' if asset_type == 'SkeletalMesh' else 'static_materials'))}
    report_path.write_text(json.dumps(report, indent=2))
    new_count += 1
    print('IMPORTED', n + 1, '/', len(index), costume, 'height', round(bounds.box_extent.z * 2), 'clips', len(clips))
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
print('ENEMY LIBRARY', len([r for r in report.values() if 'mesh' in r]))

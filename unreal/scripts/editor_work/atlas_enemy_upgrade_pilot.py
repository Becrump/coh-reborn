"""Apply an initial, bounded Hellion model upgrade after original placement."""
import hashlib
import json
import pathlib
import unreal
BASE = pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert 'AtlasPark_DressingStudy' in world.get_path_name()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()
camera, _ = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_level_viewport_camera_info()
variants = {}
for name in ['hellion_biker', 'hellion_hood', 'hellion_punk', 'hellion_lieutenant']:
    folder = '/Game/Characters/Enemies/Hellions/' + name
    assets = reg.get_assets_by_path(folder, True)
    meshes = [d.get_asset() for d in assets if str(d.asset_class_path.asset_name) == 'SkeletalMesh']
    idles = [d.get_asset() for d in assets if str(d.asset_class_path.asset_name) == 'AnimSequence' and str(d.asset_name) == 'Idle_3']
    assert len(meshes) == 1 and len(idles) == 1, (name, len(meshes), len(idles))
    assert meshes[0].get_editor_property('skeleton') == idles[0].get_editor_property('skeleton'), name
    variants[name] = meshes[0], idles[0]
plan = json.loads((BASE / 'atlas_enemy_plan.json').read_text())
rows = {r['id']: r for r in plan['population']}
actors = []
for actor in sub.get_all_level_actors():
    label = actor.get_actor_label()
    if not label.startswith('CoHOriginal_Hellions_'):
        continue
    row = rows.get(label.removeprefix('CoHOriginal_Hellions_'))
    if not row or row['costume'] not in ['Thug_Hellion_%02d' % n for n in range(1,7)] + ['Thug_Hellion_Boss_%02d' % n for n in range(1,4)]:
        continue
    if ((row.get('exclusive_vision_phase') or '').lower() not in ('','all','prime','default','none') or
        any(p.lower() not in ('all','prime','default','none') for p in row.get('vision_phases', []))):
        continue
    actors.append(((actor.get_actor_location() - camera).length(), actor, row))
actors.sort(key=lambda a: a[0])
changes = []
for _, actor, row in actors[:12]:
    component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    old_mesh = component.get_skeletal_mesh_asset()
    if '/OriginalEnemies/' not in old_mesh.get_path_name():
        continue
    name = 'hellion_lieutenant' if row['rank'] in ('Lieutenant','Boss') else ['hellion_biker','hellion_hood','hellion_punk'][int(hashlib.sha256(row['id'].encode()).hexdigest()[:8],16)%3]
    mesh, idle = variants[name]
    old_bounds, new_bounds = old_mesh.get_bounds(), mesh.get_bounds()
    ratio = old_bounds.box_extent.z / new_bounds.box_extent.z
    assert 0.5 < ratio < 2.0, (name, ratio)
    old_scale = actor.get_actor_scale3d()
    rel = component.get_editor_property('relative_location')
    changes.append({'actor': actor.get_path_name(), 'label': actor.get_actor_label(), 'id': row['id'],
                    'source_mesh': old_mesh.get_path_name(), 'upgraded_mesh': mesh.get_path_name(),
                    'variant': name, 'old_scale': [old_scale.x,old_scale.y,old_scale.z],
                    'old_relative_location': [rel.x,rel.y,rel.z], 'scale_ratio': ratio})
    actor.modify()
    component.modify()
    component.set_skeletal_mesh_asset(mesh)
    actor.set_actor_scale3d(unreal.Vector(old_scale.x*ratio,old_scale.y*ratio,old_scale.z*ratio))
    feet = (old_bounds.origin.z-old_bounds.box_extent.z)/ratio - (new_bounds.origin.z-new_bounds.box_extent.z)
    component.set_relative_location(unreal.Vector(rel.x,rel.y,rel.z+feet), False, False)
    component.override_animation_data(idle, True, False, 0.0, 0.0)
    component.set_component_tick_enabled(False)
    actor.set_folder_path('CoH/OriginalEncounters/ModelUpgradePilot/Hellions')
assert changes, 'No eligible original Hellions for upgrade pilot'
(BASE / 'atlas_enemy_upgrade_pilot_report.json').write_text(json.dumps({'map':world.get_path_name(),'changes':changes},indent=2))
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
print('HELLION MODEL UPGRADE PILOT', len(changes))

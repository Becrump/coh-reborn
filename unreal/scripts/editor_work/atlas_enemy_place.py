"""Place original skeletal enemy previews at original encounter positions.

The manifest keeps selection rules and phases. These previews are not combat AI.
Rerunning adds newly imported costumes without duplicating existing actors.
"""
import collections
import json
import pathlib
import unreal

BASE = pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
plan = json.loads((BASE / 'atlas_enemy_plan.json').read_text())
library = json.loads((BASE / 'atlas_enemy_import_report.json').read_text())
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert world.get_path_name().startswith('/Game/AtlasPark4/AtlasPark_DressingStudy.'), world.get_path_name()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
existing = {a.get_actor_label(): a for a in sub.get_all_level_actors()}
limit = int(globals().get('ENEMY_PLACE_LIMIT', 0))
created, unavailable, placed = [], [], []
assets = {}
for row in plan['population']:
    label = 'CoHOriginal_' + row['group'] + '_' + row['id']
    record = library.get(row['costume'], {})
    if 'mesh' not in record:
        unavailable.append({'id': row['id'], 'costume': row['costume']})
        continue
    if row['costume'] not in assets:
        mesh = unreal.load_asset(record['mesh'])
        assert mesh
        idle_paths = [v for k, v in record['clips'].items() if k.lower().endswith('idle')]
        idle = unreal.load_asset(idle_paths[0]) if idle_paths else None
        assets[row['costume']] = mesh, idle
    mesh, idle = assets[row['costume']]
    actor = existing.get(label)
    if actor is None:
        if limit and len(created) >= limit:
            break
        pitch, yaw, roll = row['rotation']
        is_static = record.get('asset_type') == 'StaticMesh'
        # Character export deliberately turns native CoH facing by 180 degrees
        # for glTF's forward convention; undo that for original encounter yaw.
        if not is_static:
            yaw += 180.0
        actor_class = unreal.StaticMeshActor if is_static else unreal.SkeletalMeshActor
        location = list(row['location'])
        no_snap = row.get('actor_properties', {}).get('NoGroundSnap', ['0'])[0] != '0'
        if not no_snap:
            start = unreal.Vector(location[0], location[1], location[2] + 250)
            end = unreal.Vector(location[0], location[1], location[2] - 600)
            hit = unreal.SystemLibrary.line_trace_single(world, start, end,
                unreal.TraceTypeQuery.ECC_VISIBILITY, True, [], unreal.DrawDebugTrace.NONE, True)
            if hit and hit.to_tuple()[0]:
                point = hit.to_tuple()[4]
                normal = hit.to_tuple()[5]
                if normal.z > 0.7:
                    location[2] = point.z
        actor = sub.spawn_actor_from_class(actor_class, unreal.Vector(*location),
                                          unreal.Rotator(pitch=pitch, yaw=yaw, roll=roll))
        assert actor
        actor.modify()
        actor.set_actor_label(label)
        actor.set_actor_scale3d(unreal.Vector(*row['scale']))
        component = actor.get_component_by_class(unreal.StaticMeshComponent if is_static else unreal.SkeletalMeshComponent)
        if is_static:
            component.set_static_mesh(mesh)
        else:
            component.set_skeletal_mesh_asset(mesh)
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        if idle:
            # Serializes the pose and evaluates bones immediately, even with tick disabled.
            component.override_animation_data(idle, True, False, 0.0, 0.0)
        # Thousands of layout previews must not run animation/AI every frame.
        component.set_component_tick_enabled(False)
        phased = bool((row.get('exclusive_vision_phase') or '').lower() not in ('','all','prime','default','none') or
                      any(p.lower() not in ('all', 'prime', 'default', 'none') for p in row.get('vision_phases', [])))
        actor.set_actor_hidden_in_game(phased)
        actor.set_folder_path('CoH/OriginalEncounters/' + ('StoryPhases/' if phased else 'Normal/') + row['group'])
        actor.set_editor_property('tags', [unreal.Name('CoHOriginalEnemyPreview'),
            unreal.Name('Encounter_' + row['encounter_id']), unreal.Name('Costume_' + row['costume']),
            unreal.Name('Faction_' + row['group']), unreal.Name('Rank_' + (row.get('rank') or 'Explicit')),
            unreal.Name('PhaseControlled' if phased else 'NormalEncounter'),
            unreal.Name('Allied' if (row.get('ally') or '').lower() == 'hero' else 'SourceAlliance')])
        created.append(label)
    placed.append({'id': row['id'], 'label': label, 'actor': actor.get_path_name(),
                   'costume': row['costume'], 'mesh': record['mesh'], 'source_location': row['location'],
                   'location': [actor.get_actor_location().x, actor.get_actor_location().y, actor.get_actor_location().z]})
    if len(created) and len(created) % 100 == 0:
        print('PLACED', len(created))
report = {'map': world.get_path_name(), 'created': len(created), 'placed': placed,
          'unavailable': unavailable, 'source_errors': plan['errors'],
          'note': 'Skeletal layout previews; original phases and encounter rules retained in plan; combat and runtime selection not implemented.'}
(BASE / 'atlas_enemy_placement_report.json').write_text(json.dumps(report, indent=2))
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
print('ENEMY PLACEMENT', json.dumps({'created': len(created), 'placed': len(placed), 'unavailable': len(unavailable)}))

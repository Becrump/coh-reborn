"""Persist tile bindings, actual fitted transforms, and component edits on external actors."""
import unreal,json
el=unreal.EditorAssetLibrary;sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_Upgraded' in w.get_path_name()
m=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_manifest.json'));actors={a.get_actor_label():a for a in sub.get_all_level_actors()}
tiles=0;wrong=0
for label,status in m['tiles']:
    if status!='updated':continue
    a=actors.get(label);assert isinstance(a,unreal.StaticMeshActor),label
    c=a.static_mesh_component;mesh=el.load_asset('/Game/AtlasUpgraded/Geometry/atlas_upgraded/StaticMeshes/'+label);assert mesh,label
    wrong+=int(c.static_mesh!=mesh);a.modify();c.modify();c.set_static_mesh(mesh);c.set_editor_property('override_materials',[])
    c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS);tiles+=1
for r in m['buildings']:
    a=actors[r['label']];a.modify();sc=r['final_scale'];a.set_actor_scale3d(unreal.Vector(sc,sc,sc));a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=r['yaw'],roll=0),False);a.set_actor_location(unreal.Vector(*r['location']),False,True)
    for c in a.get_components_by_class(unreal.StaticMeshComponent):c.modify();c.set_relative_transform(c.get_relative_transform(),False,True)
print('TILE_BINDINGS',tiles,'reverted',wrong,'BUILDINGS',len(m['buildings']))
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

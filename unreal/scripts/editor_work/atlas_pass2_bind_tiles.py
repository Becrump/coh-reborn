import unreal,builtins
for key in list(vars(builtins)):
    if key.startswith('atlas_dusk_'):delattr(builtins,key)
for key in ['meshes','targets','classes','actors','tile_actors','w','world','a','c','bp','cache','original','packages','mats','pts']:
    globals().pop(key,None)
unreal.SystemLibrary.collect_garbage()
"""Apply only to the saved upgrade map; preserve original maps and shared assets."""
import unreal,json,itertools,math
el=unreal.EditorAssetLibrary;reg=unreal.AssetRegistryHelpers.get_asset_registry()
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert 'AtlasPark_SecondPass' in w.get_path_name()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
ROOT='/Game/AtlasSecondPass/Geometry'
meshes={str(d.asset_name):d.get_asset() for d in reg.get_assets_by_path(ROOT,True) if str(d.asset_class_path.asset_name)=='StaticMesh'}
assert meshes,'Imported geometry missing'
tuned={str(d.asset_name).lower():d for d in reg.get_assets_by_path('/Game/atlas_park/Materials',True) if str(d.asset_class_path.asset_name)=='MaterialInstanceConstant'}
# Preserve current per-actor civic refresh and invisible material overrides by source slot name.
overrides={};tile_actors=[]
for a in sub.get_all_level_actors():
    if not isinstance(a,unreal.StaticMeshActor) or not a.get_actor_label().startswith('tile_'):continue
    c=a.static_mesh_component;local={}
    for i in range(c.get_num_materials()):
        original=c.static_mesh.get_material(i);current=c.get_material(i)
        if original and current:local[original.get_name().lower()]=current
    overrides[a.get_actor_label()]=local;tile_actors.append(a)
hide={'x_archent_int_window_cube','portal_door1_tga'}
for s in json.load(open('C:/Users/rtcru/CoHReborn/out/atlas_park_v5/statues.json'))['statues']:hide.update(m.lower() for m in s.get('hide_materials',[]))
hide.update(m.lower() for m in json.load(open('C:/Users/rtcru/CoHReborn/out/atlas_park_v5/atlas_park_trees.json'))['materials'])
inv=el.load_asset('/Game/CoH/Materials/M_Invisible');sms=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
affected={tuple(x) for x in json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_pass2_export_manifest.json'))['tiles']}
updated=[]
for a in tile_actors:
    label=a.get_actor_label();parts=label.split('_')
    try:xy=tuple(map(int,parts[1:3]))
    except ValueError:continue
    if xy not in affected:continue
    if label not in meshes:sub.destroy_actor(a);updated.append([label,'removed']);continue
    a.modify();a.static_mesh_component.modify()
    mesh=meshes[label];mats=mesh.get_editor_property('static_materials')
    for i,slot in enumerate(mats):
        mat=slot.material_interface
        if not mat:continue
        name=mat.get_name().lower();target=overrides.get(label,{}).get(name)
        if not target and name in tuned:target=tuned[name].get_asset()
        if name in hide:target=inv
        if target:slot.material_interface=target;mats[i]=slot
    mesh.set_editor_property('static_materials',mats)
    bs=mesh.get_editor_property('body_setup');bs.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    ag=bs.get_editor_property('agg_geom');ag.set_editor_property('convex_elems',[]);bs.set_editor_property('agg_geom',ag);mesh.set_editor_property('body_setup',bs)
    for s in range(mesh.get_num_sections(0)):
        mat=mesh.get_material(sms.get_lod_material_slot(mesh,0,s))
        if mat and mat.get_name()=='M_Invisible':sms.enable_section_collision(mesh,False,0,s)
    el.save_loaded_asset(mesh,False)
    c=a.static_mesh_component;c.set_static_mesh(mesh);c.set_editor_property('override_materials',[]);c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
    updated.append([label,'updated'])
print('TILES',len(updated),flush=True)

json.dump(updated,open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_pass2_tiles.json','w'),indent=2)
print('PERIMETER TILES SAVED',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

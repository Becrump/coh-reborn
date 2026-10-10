"""Apply only to the saved upgrade map; preserve original maps and shared assets."""
import unreal,json,itertools,math
el=unreal.EditorAssetLibrary;reg=unreal.AssetRegistryHelpers.get_asset_registry()
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert 'AtlasPark_Upgraded' in w.get_path_name()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
ROOT='/Game/AtlasUpgraded/Geometry'
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
affected={tuple(map(int,n.split('_')[1:3])) for n in meshes if n.startswith('tile_')}
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
    c=a.static_mesh_component;c.set_static_mesh(mesh);c.set_editor_property('override_materials',[]);c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
    updated.append([label,'updated'])
print('TILES',len(updated),flush=True)
for a in sub.get_all_level_actors():
    if a.get_actor_label().startswith('AtlasUpgrade_'):sub.destroy_actor(a)
def refresh(a):
    for c in a.get_components_by_class(unreal.StaticMeshComponent):c.set_relative_transform(c.get_relative_transform(),False,True)
def bounds(a):
    pts=[]
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        if not c.static_mesh:continue
        box=c.static_mesh.get_bounding_box();lo=box.min;hi=box.max
        ts=[c.get_instance_transform(i,True) for i in range(c.get_instance_count())] if isinstance(c,unreal.InstancedStaticMeshComponent) else [c.get_world_transform()]
        for t in ts:
            for v in itertools.product([lo.x,hi.x],[lo.y,hi.y],[lo.z,hi.z]):
                p=unreal.MathLibrary.transform_location(t,unreal.Vector(*v));pts.append((p.x,p.y,p.z))
    assert pts,a.get_actor_label()
    return [min(p[j] for p in pts) for j in range(3)],[max(p[j] for p in pts) for j in range(3)]
plan=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_layout.json'));report=[]
for p in plan:
    # Trace the empty plot before spawning; source building origins often sit above/below pavement.
    hit=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(p['x'],p['y'],10000),unreal.Vector(p['x'],p['y'],-5000),unreal.TraceTypeQuery.ECC_VISIBILITY,False,[],unreal.DrawDebugTrace.NONE,True)
    ground=hit.to_tuple()[4].z if hit else p['ground_hint']
    a=sub.spawn_actor_from_class(el.load_blueprint_class(p['path']),unreal.Vector(0,0,0));assert a,p['path']
    a.set_actor_label(p['label']);a.set_folder_path('Atlas25/Upgrades/'+('Skyline' if p['tower'] else 'Neighborhoods'))
    scale=p['scale'];a.set_actor_scale3d(unreal.Vector(scale,scale,scale));a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=p['yaw'],roll=0),False);refresh(a)
    lo,hi=bounds(a)
    fit=min(p['plot'][0]*.92/(hi[0]-lo[0]),p['plot'][1]*.92/(hi[1]-lo[1]),1)
    if fit<.995:
        scale*=fit;a.set_actor_scale3d(unreal.Vector(scale,scale,scale));refresh(a);lo,hi=bounds(a)
    loc=unreal.Vector(p['x']-(lo[0]+hi[0])/2,p['y']-(lo[1]+hi[1])/2,ground+5-lo[2])
    a.set_actor_location(loc,False,True);refresh(a);lo,hi=bounds(a)
    report.append(dict(p,final_scale=scale,location=[loc.x,loc.y,loc.z],bounds=[lo,hi],ground=ground,ground_hit=bool(hit)))
    print('BUILD',len(report),p['label'],'height_m',round((hi[2]-lo[2])/100),'ground',round(ground),flush=True)
json.dump({'map':w.get_path_name(),'tiles':updated,'buildings':report},open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_manifest.json','w'),indent=2)
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

"""Atlas Park +25 reconstruction study; only edits the dedicated study map."""
import unreal, json, math, importlib.util
ROOT='/Game/AtlasRebuiltStudy'
BASE='C:/Users/rtcru/CoHReborn/out/'
el=unreal.EditorAssetLibrary
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg=unreal.AssetRegistryHelpers.get_asset_registry()
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert world.get_path_name().startswith('/Game/AtlasPark4/AtlasPark_CitySampleStudy.')
unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in unreal.WorldPartitionBlueprintLibrary.get_actor_descs()])
for a in sub.get_all_level_actors():
    if a.get_actor_label().startswith(('STUDY_Catalog_','Atlas25_')): sub.destroy_actor(a)

task=unreal.AssetImportTask()
task.filename=BASE+'atlas_rebuilt_avenue/avenue.gltf'
task.destination_path=ROOT+'/Avenue'
task.automated=True; task.save=True; task.replace_existing=True
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
assert len(task.imported_object_paths)>0,'Avenue import failed'

tuned={str(d.asset_name).lower():d for d in reg.get_assets_by_path('/Game/atlas_park/Materials',True) if str(d.asset_class_path.asset_name)=='MaterialInstanceConstant'}
for d in reg.get_assets_by_path('/Game/AtlasExpansionTest/Block/expansion/Materials',True):
    if str(d.asset_class_path.asset_name)=='MaterialInstanceConstant':tuned.setdefault(str(d.asset_name).lower(),d)
for d in reg.get_assets_by_path(ROOT,True):
    if str(d.asset_class_path.asset_name)!='StaticMesh': continue
    mesh=d.get_asset(); mats=mesh.get_editor_property('static_materials')
    for i,sm in enumerate(mats):
        mat=sm.get_editor_property('material_interface')
        if mat and mat.get_name().lower() in tuned:
            sm.set_editor_property('material_interface',tuned[mat.get_name().lower()].get_asset()); mats[i]=sm
    mesh.set_editor_property('static_materials',mats)
    bs=mesh.get_editor_property('body_setup')
    bs.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    ag=bs.get_editor_property('agg_geom'); ag.set_editor_property('convex_elems',[]); bs.set_editor_property('agg_geom',ag)
    mesh.set_editor_property('body_setup',bs)
    el.save_loaded_asset(mesh,False)

avenue={str(d.asset_name):d.get_asset() for d in reg.get_assets_by_path(ROOT+'/Avenue',True) if str(d.asset_class_path.asset_name)=='StaticMesh'}
assert 'tile_2_-2' in avenue and 'tile_2_-3' in avenue
affected={(int(name.split('_')[1]),int(name.split('_')[2])) for name in avenue}
affected.add((3,-4))
hide={'x_archent_int_window_cube','portal_door1_tga'}
for s in json.load(open(BASE+'atlas_park_v5/statues.json'))['statues']:hide.update(m.lower() for m in s.get('hide_materials',[]))
hide.update(m.lower() for m in json.load(open(BASE+'atlas_park_v5/atlas_park_trees.json'))['materials'])
inv=el.load_asset('/Game/CoH/Materials/M_Invisible')
sms=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
changed=[]
for a in sub.get_all_level_actors():
    label=a.get_actor_label()
    if not isinstance(a,unreal.StaticMeshActor) or not label.startswith('tile_'):continue
    parts=label.split('_')
    try: xy=(int(parts[1]),int(parts[2]))
    except ValueError:continue
    if xy not in affected:continue
    if label not in avenue:
        sub.destroy_actor(a);changed.append([label,'removed']);continue
    c=a.static_mesh_component; a.modify(); c.modify()
    c.set_static_mesh(avenue[label]); c.set_editor_property('override_materials',[])
    hidden_slots=[]
    for i in range(c.get_num_materials()):
        mat=c.get_material(i)
        if mat and mat.get_name().lower() in hide:c.set_material(i,inv);hidden_slots.append(i)
    for s in range(c.static_mesh.get_num_sections(0)):
        if sms.get_lod_material_slot(c.static_mesh,0,s) in hidden_slots:sms.enable_section_collision(c.static_mesh,False,0,s)
    c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
    changed.append([label,'updated'])
for d in reg.get_assets_by_path(ROOT+'/Infrastructure',True):
    if str(d.asset_class_path.asset_name)!='StaticMesh':continue
    a=sub.spawn_actor_from_object(d.get_asset(),unreal.Vector(0,0,0))
    a.set_actor_label('Atlas25_Infrastructure_'+str(d.asset_name)); a.set_folder_path('Atlas25/Infrastructure')
    a.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)

kit='/Game/CitySampleBuildings/Building/Library/Kit_Ref_Bldg/LevelInstance/'
# Labels describe proposed uses, not functional interiors. Uniform scaling preserves proportions.
placements=[
 ('Gateway_Restored_Office','BPP_CHB_Ref_A1_N1',940,1110,0,.68),
 ('Gateway_Rebuilt_Office','BPP_CHD_Ref_A1_N1',1275,1190,0,.7),
 ('West_Civic_Annex','BPP_Bldg_Hero_CHA_A01_N1',880,1315,0,.9),
 ('West_Residential','BPP_Bldg_Hero_Mid_NYG_Modern_A01_N1',935,1550,0,.8),
 ('East_Research_Office','BPP_Bldg_Hero_Mid_NYG_Modern_A01_N1',1248,1450,0,.7),
 ('East_New_Residential','BPP_CHF_Ref_A1_N1',1280,1630,0,.63),
 ('West_Shopfronts','BPP_NYAA_Ref_N1',1000,1240,90,1.0),
 ('East_Shopfronts','BPP_NYAB_Ref_N1',1176,1370,-90,1.0),
 ('North_Retail','BPP_NYAA_Ref_N1',930,1620,0,1.0),
 ('Back_Restored_Tower','BPP_CHB_Ref_A1_N1',735,1465,90,.85),
 ('Back_New_Tower','BPP_Bldg_Hero_Tower_CHE_B01_N1',1510,1260,0,.65),
 ('Avenue_Retail_South','BPP_NYAA_Ref_N1',978,798,90,.8),
 ('Avenue_Retail_Middle','BPP_NYAB_Ref_N1',997,875,90,.8),
 ('Avenue_Retail_North','BPP_NYAA_Ref_N1',978,947,90,.8),
]
report=[]
for name,bp,x,z,yaw,scale in placements:
    bp_path=(kit.replace('Kit_Ref_Bldg','Kit_Hero_Bldg') if bp.startswith('BPP_Bldg_Hero_') else kit)+bp
    cls=el.load_blueprint_class(bp_path); assert cls, bp
    a=sub.spawn_actor_from_class(cls,unreal.Vector(0,0,0))
    a.set_actor_label('Atlas25_'+name); a.set_folder_path('Atlas25/Buildings')
    # Spawn at identity then move: packed components otherwise retain stale initial bounds.
    a.set_actor_scale3d(unreal.Vector(scale,scale,scale))
    a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=yaw,roll=0),False)
    a.set_actor_location(unreal.Vector(x*30.48,-z*30.48,12),False,True)
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        c.set_relative_transform(c.get_relative_transform(),False,True)
    report.append({'label':a.get_actor_label(),'asset':bp_path,'location':[x*30.48,-z*30.48,12],'yaw':yaw,'scale':scale})

lamp_paths={k:'/Game/CoH/Props/modern_'+k+'light/modern_'+k+'light/StaticMeshes/modern_'+k+'light' for k in ['street','parking']}
props=json.load(open(BASE+'atlas_rebuilt_block/rebuilt_props.json'))
for i,p in enumerate(props):
    if p['keep_pole']:continue
    bx,by,bz=p['base'];fx,fz=p['facing'];yaw=math.degrees(math.atan2(fz,fx))
    mesh=el.load_asset(lamp_paths[p['kind']]); assert mesh,p['kind']
    a=sub.spawn_actor_from_object(mesh,unreal.Vector(bx*100,bz*100,by*100),unreal.Rotator(pitch=0,yaw=yaw,roll=0))
    a.set_actor_label('Atlas25_Lamp_'+str(i));a.set_folder_path('Atlas25/StreetLights')
    headx=124 if p['kind']=='street' else 0
    height=655 if p['kind']=='street' else 745
    r=math.radians(yaw)
    lt=sub.spawn_actor_from_class(unreal.SpotLight,unreal.Vector(bx*100+headx*math.cos(r),bz*100+headx*math.sin(r),by*100+height-8),unreal.Rotator(pitch=-90,yaw=yaw,roll=0))
    lt.set_actor_label('Atlas25_LampLight_'+str(i));lt.set_folder_path('Atlas25/StreetLights')
    c=lt.get_component_by_class(unreal.SpotLightComponent);c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property('intensity_units',unreal.LightUnits.CANDELAS);c.set_intensity(2500 if p['kind']=='street' else 4000)
    c.set_editor_property('use_temperature',True);c.set_editor_property('temperature',3800)
    c.set_outer_cone_angle(65);c.set_inner_cone_angle(35);c.set_attenuation_radius(2000);c.set_cast_shadows(False)

json.dump({'map':world.get_path_name(),'tile_changes':changed,'buildings':report},open('C:/Users/rtcru/ClaudeProjects/COHReborn/city_study_manifest.json','w'),indent=2)
print('BUILDING_PASS',len(report),'buildings;',len(changed),'tile updates;',len(props),'lamp entries')
print('save',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

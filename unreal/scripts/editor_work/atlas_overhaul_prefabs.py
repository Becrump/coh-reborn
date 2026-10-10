"""Store softer component materials in dedicated packed prefab copies."""
import unreal,json
base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_Upgraded' in w.get_path_name()
el=unreal.EditorAssetLibrary;ss=unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem);lib=unreal.SubobjectDataBlueprintFunctionLibrary
state=json.load(open(base+'atlas_overhaul_materials.json'));targets={s:el.load_asset(t) for s,t in state['targets'].items()}
m=json.load(open(base+'atlas_overhaul_manifest.json'));root='/Game/AtlasUpgraded/Buildings';el.make_directory(root)
classes={};template_slots=0
for path in sorted({r['path'] for r in m['buildings']}):
    original=el.load_asset(path);name='BPP_Comic_'+original.get_name();dest=root+'/'+name
    bp=el.load_asset(dest) if el.does_asset_exist(dest) else unreal.AssetToolsHelpers.get_asset_tools().duplicate_asset(name,root,original)
    assert bp,dest;bp.modify();components=0;changed=0
    for h in ss.k2_gather_subobject_data_for_blueprint(bp):
        c=lib.get_object_for_blueprint(lib.get_data(h),bp)
        if not isinstance(c,unreal.StaticMeshComponent):continue
        components+=1;c.modify();mats=[c.get_material(i) for i in range(c.get_num_materials())]
        for i,src in enumerate(mats):
            if src and src.get_path_name() in targets:mats[i]=targets[src.get_path_name()];changed+=1
        c.set_editor_property('override_materials',mats)
    assert components,(dest,'No editable component templates')
    assert unreal.BlueprintEditorLibrary.compile_blueprint(bp),dest
    assert el.save_loaded_asset(bp,False),dest
    classes[path]=el.load_blueprint_class(dest);assert classes[path],dest
    template_slots+=changed;print('PREFAB',name,components,'components',changed,'slots',flush=True)
actors={a.get_actor_label():a for a in sub.get_all_level_actors()}
for r in m['buildings']:
    old=actors[r['label']];old.modify();assert sub.destroy_actor(old),r['label']
    a=sub.spawn_actor_from_class(classes[r['path']],unreal.Vector(0,0,0));assert a,r['label']
    a.set_actor_label(r['label']);a.set_folder_path('Atlas25/Upgrades/'+('Skyline' if r['tower'] else 'Neighborhoods'))
    sc=r['final_scale'];a.set_actor_scale3d(unreal.Vector(sc,sc,sc));a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=r['yaw'],roll=0),False);a.set_actor_location(unreal.Vector(*r['location']),False,True)
    for c in a.get_components_by_class(unreal.StaticMeshComponent):c.set_relative_transform(c.get_relative_transform(),False,True)
    r['upgraded_prefab']=root+'/BPP_Comic_'+r['path'].rsplit('/',1)[1]
m['prefab_template_slots']=template_slots;json.dump(m,open(base+'atlas_overhaul_manifest.json','w'),indent=2)
print('REPLACED_ACTORS',len(m['buildings']),'PREFABS',len(classes))
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

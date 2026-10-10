import unreal,json,itertools
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert 'AtlasPark_Upgraded' in w.get_path_name()
manifest=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_manifest.json'))
baseline=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_baseline.json'))
selected=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_selected.json'))
actors={a.get_actor_label():a for a in sub.get_all_level_actors()}
report={'map':w.get_path_name(),'buildings':[],'streets':[],'overlaps':[]}
for r in manifest['buildings']:
    a=actors.get(r['label']);assert a,r['label']
    pts=[]
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        if not c.static_mesh:continue
        box=c.static_mesh.get_bounding_box()
        ts=[c.get_instance_transform(i,True) for i in range(c.get_instance_count())] if isinstance(c,unreal.InstancedStaticMeshComponent) else [c.get_world_transform()]
        for t in ts:
            for v in itertools.product([box.min.x,box.max.x],[box.min.y,box.max.y],[box.min.z,box.max.z]):
                p=unreal.MathLibrary.transform_location(t,unreal.Vector(*v));pts.append((p.x,p.y,p.z))
    lo=[min(p[j] for p in pts) for j in range(3)];hi=[max(p[j] for p in pts) for j in range(3)]
    r['bounds']=[lo,hi];plotlo,plothi=r['source_bounds']
    inside=lo[0]>=plotlo[0]*30.48-2 and hi[0]<=plothi[0]*30.48+2 and lo[1]>=-plothi[2]*30.48-2 and hi[1]<=-plotlo[2]*30.48+2
    grounded=abs(lo[2]-r['ground']-5)<1
    report['buildings'].append({'label':r['label'],'inside_original_plot':inside,'grounded':grounded,'ground_hit':r['ground_hit'],'height_m':(hi[2]-lo[2])/100})
for i,r in enumerate(manifest['buildings']):
    lo,hi=r['bounds']
    for s in manifest['buildings'][i+1:]:
        sl,sh=s['bounds']
        if min(hi[0],sh[0])-max(lo[0],sl[0])>30 and min(hi[1],sh[1])-max(lo[1],sl[1])>30:report['overlaps'].append([r['label'],s['label']])
samples=[]
for p in baseline['ground_samples']:
    if any(r['min'][0]-2<=p['x']<=r['max'][0]+2 and r['min'][2]-2<=p['z']<=r['max'][2]+2 for r in selected):continue
    samples.append(dict(p,kind='baseline'))
samples += [{'x':1088,'z':z,'height':None,'kind':'avenue'} for z in range(1000,1641,40)]
for p in samples:
    h=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(p['x']*30.48,-p['z']*30.48,4000),unreal.Vector(p['x']*30.48,-p['z']*30.48,-3000),unreal.TraceTypeQuery.ECC_VISIBILITY,False,[],unreal.DrawDebugTrace.NONE,True)
    height=h.to_tuple()[4].z if h else None
    # Rebuilt complex collision can differ from the old tile's simple hull/layer by a curb height.
    # Bound that change to 30 cm and report the actual delta; missing support still fails.
    ok=height is not None and (abs(height-p['height'])<=30 if p['height'] is not None else -20<=height<=10)
    exact=None
    actor=h.to_tuple()[9] if h else None
    if isinstance(actor,unreal.StaticMeshActor) and '/AtlasUpgraded/Geometry/' in actor.static_mesh_component.static_mesh.get_path_name():
        hc=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(p['x']*30.48,-p['z']*30.48,4000),unreal.Vector(p['x']*30.48,-p['z']*30.48,-3000),unreal.TraceTypeQuery.ECC_VISIBILITY,True,[],unreal.DrawDebugTrace.NONE,True)
        exact=bool(hc and abs(hc.to_tuple()[4].z-height)<2)
        ok=ok and exact
    report['streets'].append(dict(p,final_height=height,passed=ok,simple_complex_match=exact))
report['comic_filter']=any(b.object and 'MI_CoH_Comic' in b.object.get_path_name() and b.weight>0 for a in actors.values() if isinstance(a,unreal.PostProcessVolume) for b in a.settings.weighted_blendables.array)
before_civic={m for r in baseline['tiles'] for m in r['materials'] if m and '/CivicMaterials/' in m}
after_civic={c.get_material(i).get_path_name() for a in actors.values() if isinstance(a,unreal.StaticMeshActor) and a.get_actor_label().startswith('tile_') for c in [a.static_mesh_component] for i in range(c.get_num_materials()) if c.get_material(i) and '/CivicMaterials/' in c.get_material(i).get_path_name()}
report['civic_materials_retained']=before_civic<=after_civic
report['civic_missing']=sorted(before_civic-after_civic)
style=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_materials.json'))
targetpaths=set(style['targets'].values())
report['style_slots']=sum(c.get_material(i) is not None and c.get_material(i).get_path_name() in targetpaths for a in actors.values() if a.get_actor_label().startswith('AtlasUpgrade_') for c in a.get_components_by_class(unreal.StaticMeshComponent) for i in range(c.get_num_materials()))
report['style_bindings_retained']=report['style_slots']==style['slots']
report['tile_bindings_retained']=all(label in actors and '/AtlasUpgraded/Geometry/' in actors[label].static_mesh_component.static_mesh.get_path_name() for label,status in manifest['tiles'] if status=='updated')
json.dump(report,open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_validation.json','w'),indent=2)
print('BUILDINGS',len(report['buildings']),'OUTSIDE',sum(not r['inside_original_plot'] for r in report['buildings']),'UNGROUNDED',sum(not r['grounded'] for r in report['buildings']),'NO_GROUND_HIT',sum(not r['ground_hit'] for r in report['buildings']))
print('OVERLAPS',report['overlaps'])
print('STREETS',len(report['streets']),'FAILED',[r for r in report['streets'] if not r['passed']])
print('COMIC',report['comic_filter'])
print('CIVIC',report['civic_materials_retained'],report['civic_missing'])
print('STYLE',report['style_bindings_retained'],report['style_slots'],'TILES',report['tile_bindings_retained'])
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

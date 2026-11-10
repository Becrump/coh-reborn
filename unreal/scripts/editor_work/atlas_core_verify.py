import unreal,json
base='C:/Users/rtcru/ClaudeProjects/COHReborn/';data=json.load(open(base+'atlas_core_refresh_manifest.json'));u=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
assert unreal.EditorLoadingAndSavingUtils.load_map('/Game/AtlasPark4/AtlasPark_SecondPass')
unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in unreal.WorldPartitionBlueprintLibrary.get_actor_descs()])
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);orig={a.get_actor_label():a for a in sub.get_all_level_actors()}
assert not any(k.startswith('AtlasCore_') for k in orig)
for r in data['tile_changes']:assert orig[r['label']].static_mesh_component.static_mesh.get_path_name()==r['original_mesh']
assert unreal.EditorLoadingAndSavingUtils.load_map('/Game/AtlasPark4/AtlasPark_DressingStudy')
unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in unreal.WorldPartitionBlueprintLibrary.get_actor_descs()]);w=u.get_editor_world();actors={a.get_actor_label():a for a in sub.get_all_level_actors()};sms=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
assert not any(k.startswith('AtlasCore_Sign_') for k in actors)
for r in data['tile_changes']:
 c=actors[r['label']].static_mesh_component;m=c.static_mesh;assert m.get_path_name()==r['new_mesh']
 for i in r['hidden_slots']:assert c.get_material(i).get_name()=='M_Invisible'
for r in data['benches']+data['new_furniture']:
 a=actors[r['label']];p=a.get_actor_location();assert max(abs(v-q) for v,q in zip([p.x,p.y,p.z],r['location']))<.1,r['label']
 assert a.static_mesh_component.static_mesh.get_path_name()==r['mesh'],r['label']
 if r['label'].startswith('AtlasCore_Bench'):assert a.static_mesh_component.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION
 else:assert a.static_mesh_component.get_collision_enabled()==unreal.CollisionEnabled.NO_COLLISION
benches=[actors[r['label']] for r in data['benches']];support=[]
for r in data['benches']:
 x,y,z=r['location'];h=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(x,y,z+180),unreal.Vector(x,y,z-200),unreal.TraceTypeQuery.ECC_VISIBILITY,False,benches,unreal.DrawDebugTrace.NONE,True)
 hz=h.to_tuple()[4].z if h and h.to_tuple()[0] else None;support.append({'label':r['label'],'ground':hz,'expected':z,'passed':hz is not None and abs(hz-z)<30})
streets=[]
for p in json.load(open(base+'atlas_overhaul_validation.json'))['streets']:
 x=p['x']*30.48;y=-p['z']*30.48;h=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(x,y,4000),unreal.Vector(x,y,-3000),unreal.TraceTypeQuery.ECC_VISIBILITY,False,[],unreal.DrawDebugTrace.NONE,True);hz=h.to_tuple()[4].z if h and h.to_tuple()[0] else None
 streets.append({'x':x,'y':y,'passed':hz is not None and abs(hz-p['final_height'])<=30})
report={'bench_count':len(benches),'furniture_count':len(data['new_furniture']),'tile_copies':len(data['tile_changes']),'saved_bindings':'passed','baseline_unchanged':True,'bench_ground':support,'streets':streets}
json.dump(report,open(base+'atlas_core_refresh_validation.json','w'),indent=2)
print('BENCH GROUND FAILURES',[r for r in support if not r['passed']]);print('STREET FAILURES',[r for r in streets if not r['passed']]);print('REOPENED BINDINGS PASSED',len(benches)+len(data['new_furniture']))

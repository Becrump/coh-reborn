import unreal,json
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert 'AtlasPark_Upgraded' in w.get_path_name()
rows=[]
for a in sub.get_all_level_actors():
    if isinstance(a,unreal.StaticMeshActor) and a.get_actor_label().startswith('tile_'):
        c=a.static_mesh_component
        rows.append({'label':a.get_actor_label(),'mesh':c.static_mesh.get_path_name(),'materials':[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())]})
traces=[]
for x in [-1792,-1216,-768,-384,0,384,768,1088,1600,2048]:
    for z in [-2304,-1920,-1536,-1152,-768,-384,0,384,768,1100,1400]:
        h=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(x*30.48,-z*30.48,4000),unreal.Vector(x*30.48,-z*30.48,-3000),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
        if h:
            t=h.to_tuple();p=t[4]
            if -2000<p.z<1900:traces.append({'x':x,'z':z,'height':p.z})
json.dump({'tiles':rows,'ground_samples':traces},open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_baseline.json','w'),indent=2)
print('BASELINE',len(rows),'tiles;',len(traces),'low ground samples')

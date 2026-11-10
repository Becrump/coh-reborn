import unreal,json
w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();old=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_validation.json'))
for x,y in [(-54620.16,-23408.64),(-23408.64,-23408.64)]:
 print('EXPECTED',[p for p in old['streets'] if abs(p['x']*30.48-x)<1 and abs(-p['z']*30.48-y)<1])
 for complex in [False,True]:
  h=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(x,y,4000),unreal.Vector(x,y,-3000),unreal.TraceTypeQuery.ECC_VISIBILITY,complex,[],unreal.DrawDebugTrace.NONE,True)
  if h:
   t=h.to_tuple();print('HIT',complex,'height',t[4].z,'actor',t[9].get_actor_label(),'component',t[10].get_name(),'mesh',t[10].static_mesh.get_path_name() if isinstance(t[10],unreal.StaticMeshComponent) else '?')

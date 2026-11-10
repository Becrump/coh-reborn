"""Resolve shared/interlocking old plot bounds and ignore overhead surfaces while grounding."""
import unreal,json,itertools,math
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_Upgraded' in w.get_path_name()
path='C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_manifest.json';m=json.load(open(path));rows=m['buildings']
actors={a.get_actor_label():a for a in sub.get_all_level_actors()}
ignore=[a for a in actors.values() if a.get_actor_label().startswith(('AtlasUpgrade_','Atlas25_'))]
def overlap(a,b):return min(a[2],b[2])-max(a[0],b[0])>10 and min(a[3],b[3])-max(a[1],b[1])>10
def rect(r):lo,hi=r['bounds'];return [lo[0],lo[1],hi[0],hi[1]]
graph={i:set() for i in range(len(rows))}
for i,r in enumerate(rows):
    for j in range(i+1,len(rows)):
        if overlap(rect(r),rect(rows[j])):graph[i].add(j);graph[j].add(i)
clusters=[];seen=set()
for i in graph:
    if not graph[i] or i in seen:continue
    todo=[i];group=set()
    while todo:
        q=todo.pop()
        if q in group:continue
        group.add(q);todo+=list(graph[q]-group)
    seen|=group;clusters.append(group)
placed={i:rect(r) for i,r in enumerate(rows) if i not in seen};choices={}
for group in clusters:
    order=sorted(group,key=lambda i:rows[i]['plot'][0]*rows[i]['plot'][1])
    for i in order:
        r=rows[i];lo,hi=r['bounds'];width=hi[0]-lo[0];depth=hi[1]-lo[1];pl,ph=r['source_bounds']
        px0,px1=pl[0]*30.48,ph[0]*30.48;py0,py1=-ph[2]*30.48,-pl[2]*30.48
        options=[]
        for ratio in [1,.95,.9,.85,.8,.75,.7,.65,.6,.55,.5,.45,.4,.35,.3]:
            ww=width*ratio;dd=depth*ratio
            if px1-px0<ww+10 or py1-py0<dd+10:continue
            for fx,fy in itertools.product([.5,0,1,.25,.75],repeat=2):
                cx=px0+ww/2+5+fx*(px1-px0-ww-10);cy=py0+dd/2+5+fy*(py1-py0-dd-10)
                box=[cx-ww/2,cy-dd/2,cx+ww/2,cy+dd/2]
                if any(overlap(box,b) for b in placed.values()):continue
                score=(1-ratio)*5+math.hypot(cx-r['x'],cy-r['y'])/max(width,depth)
                options.append((score,ratio,cx,cy,box))
        assert options,('No safe placement',r['label'])
        _,ratio,cx,cy,box=min(options);placed[i]=box;choices[i]=(ratio,cx,cy)
        print('REFIT',r['label'],ratio,round((cx-r['x'])/30.48),round((cy-r['y'])/30.48))
for i,r in enumerate(rows):
    a=actors[r['label']];a.modify();ratio,cx,cy=choices.get(i,(1,r['x'],r['y']))
    lo,hi=r['bounds'];oldloc=r['location']
    # Start close to the original ground, below legacy overhead surfaces and neighboring roofs.
    hint=r['ground_hint']
    hit=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(cx,cy,hint+150),unreal.Vector(cx,cy,hint-3000),unreal.TraceTypeQuery.ECC_VISIBILITY,False,ignore,unreal.DrawDebugTrace.NONE,True)
    ground=hit.to_tuple()[4].z if hit else hint
    newlo=[oldloc[j]+(lo[j]-oldloc[j])*ratio for j in range(3)];newhi=[oldloc[j]+(hi[j]-oldloc[j])*ratio for j in range(3)]
    dx=cx-(newlo[0]+newhi[0])/2;dy=cy-(newlo[1]+newhi[1])/2;dz=ground+5-newlo[2]
    loc=unreal.Vector(oldloc[0]+dx,oldloc[1]+dy,oldloc[2]+dz)
    scale=r['final_scale']*ratio;a.set_actor_scale3d(unreal.Vector(scale,scale,scale));a.set_actor_location(loc,False,True)
    for c in a.get_components_by_class(unreal.StaticMeshComponent):c.modify();c.set_relative_transform(c.get_relative_transform(),False,True)
    delta=[dx,dy,dz];r['bounds']=[[newlo[j]+delta[j] for j in range(3)],[newhi[j]+delta[j] for j in range(3)]]
    r.update(final_scale=scale,location=[loc.x,loc.y,loc.z],ground=ground,ground_hit=bool(hit),x=cx,y=cy)
    if abs(ground-(lo[2]-5))>100:print('LOWERED',r['label'],round((lo[2]-5-ground)/100,1),'m')
m['refit_clusters']=len(clusters);m['refit_buildings']=len(choices)
json.dump(m,open(path,'w'),indent=2)
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

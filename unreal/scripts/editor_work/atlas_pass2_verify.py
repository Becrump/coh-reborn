import unreal,json,itertools
base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_SecondPass' in w.get_path_name()
m=json.load(open(base+'atlas_overhaul_manifest.json'));changes=json.load(open(base+'atlas_pass2_manifest.json'));actors={a.get_actor_label():a for a in sub.get_all_level_actors()}
def bounds(a):
 pts=[]
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  if not c.static_mesh:continue
  b=c.static_mesh.get_bounding_box();ts=[c.get_instance_transform(i,True) for i in range(c.get_instance_count())] if isinstance(c,unreal.InstancedStaticMeshComponent) else [c.get_world_transform()]
  for t in ts:
   for v in itertools.product([b.min.x,b.max.x],[b.min.y,b.max.y],[b.min.z,b.max.z]):
    p=unreal.MathLibrary.transform_location(t,unreal.Vector(*v));pts.append((p.x,p.y,p.z))
 return [[min(p[j] for p in pts) for j in range(3)],[max(p[j] for p in pts) for j in range(3)]]
new={r['label']:r for r in changes['swaps']};report={'map':w.get_path_name(),'street_buildings':[],'overlaps':[],'perimeter':[],'streets':[],'palette_bindings':[]};actual=[]
for old in m['buildings']:
 r=new.get(old['label'],old);a=actors[r['label']];lo,hi=bounds(a);pl,ph=r['source_bounds']
 inside=lo[0]>=pl[0]*30.48-2 and hi[0]<=ph[0]*30.48+2 and lo[1]>=-ph[2]*30.48-2 and hi[1]<=-pl[2]*30.48+2
 grounded=abs(lo[2]-r['ground']-5)<1;report['street_buildings'].append({'label':r['label'],'inside':inside,'grounded':grounded});actual.append((r['label'],lo,hi))
for r in changes['backdrop']:
 a=actors[r['label']];lo,hi=bounds(a)
 report['perimeter'].append({'label':r['label'],'bounds_match':all(abs([lo,hi][i][j]-r['bounds'][i][j])<2 for i in range(2) for j in range(3)),'prefab_match':a.get_class().get_path_name().startswith(r['prefab']+'.')});actual.append((r['label'],lo,hi))
for i,(label,lo,hi) in enumerate(actual):
 for other,sl,sh in actual[i+1:]:
  if min(hi[0],sh[0])-max(lo[0],sl[0])>30 and min(hi[1],sh[1])-max(lo[1],sl[1])>30:report['overlaps'].append([label,other])
for r in changes['palettes']:
 a=actors[r['label']];count=sum(1 for c in a.get_components_by_class(unreal.StaticMeshComponent) for i in range(c.get_num_materials()) if c.get_material(i) and '/AtlasSecondPass/PaletteMaterials/' in c.get_material(i).get_path_name())
 report['palette_bindings'].append({'label':r['label'],'slots':count,'prefab_match':a.get_class().get_path_name().startswith(r['prefab']+'.')})
validation=json.load(open(base+'atlas_overhaul_validation.json'))
for p in validation['streets']:
 x=p['x']*30.48;y=-p['z']*30.48
 h=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(x,y,4000),unreal.Vector(x,y,-3000),unreal.TraceTypeQuery.ECC_VISIBILITY,False,[],unreal.DrawDebugTrace.NONE,True)
 z=h.to_tuple()[4].z if h else None
 report['streets'].append({'x':x,'y':y,'passed':z is not None and abs(z-p['final_height'])<=30,'height':z})
report['comic_filter']=any(b.object and 'MI_CoH_Comic' in b.object.get_path_name() and b.weight>0 for a in actors.values() if isinstance(a,unreal.PostProcessVolume) for b in a.settings.weighted_blendables.array)
report['prototypes_remaining']=[a.get_actor_label() for a in actors.values() if 'Prototype' in a.get_actor_label()]
report['tile_bindings']=all(label not in actors if status=='removed' else label in actors and '/AtlasSecondPass/Geometry/' in actors[label].static_mesh_component.static_mesh.get_path_name() for label,status in json.load(open(base+'atlas_pass2_tiles.json')))
json.dump(report,open(base+'atlas_pass2_validation.json','w'),indent=2)
print('BUILDINGS',len(report['street_buildings']),'outside',sum(not r['inside'] for r in report['street_buildings']),'ungrounded',sum(not r['grounded'] for r in report['street_buildings']))
print('PERIMETER',len(report['perimeter']),'bad',sum(not r['bounds_match'] or not r['prefab_match'] for r in report['perimeter']))
print('OVERLAPS',report['overlaps'],'STREETS',len(report['streets']),'failed',[r for r in report['streets'] if not r['passed']])
print('PALETTES',report['palette_bindings'],'COMIC',report['comic_filter'],'TILES',report['tile_bindings'],'PROTOTYPES',report['prototypes_remaining'])

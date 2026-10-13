import unreal,json,itertools
base='C:/Users/rtcru/ClaudeProjects/COHReborn/';sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
manifest=json.load(open(base+'atlas_overhaul_manifest.json'));state=json.load(open(base+'atlas_pass2_prefab_state.json'));used={r['name']:r for r in manifest['buildings']}
def bounds(a):
 pts=[]
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  if not c.static_mesh:continue
  b=c.static_mesh.get_bounding_box();ts=[c.get_instance_transform(i,True) for i in range(c.get_instance_count())] if isinstance(c,unreal.InstancedStaticMeshComponent) else [c.get_world_transform()]
  for t in ts:
   for v in itertools.product([b.min.x,b.max.x],[b.min.y,b.max.y],[b.min.z,b.max.z]):
    p=unreal.MathLibrary.transform_location(t,unreal.Vector(*v));pts.append((p.x,p.y,p.z))
 return [[min(p[j] for p in pts) for j in range(3)],[max(p[j] for p in pts) for j in range(3)]]
def refresh(a):
 for c in a.get_components_by_class(unreal.StaticMeshComponent):c.set_relative_transform(c.get_relative_transform(),False,True)
paths=[state['palette_prefabs'][c] for c in ['Brown','WarmRed','Tan','Charcoal']]+[used[n]['upgraded_prefab'] for n in ['BPP_NYAE_Ref_N1','BPP_NYAF_Ref_N1']]
slots=[]
for y in range(-34000,81001,5500):slots.extend([('West',-63000,y,True),('East',94300,y,True)])
for x in range(-53000,85001,5500):slots.append(('Top',x,87500,False))
for x in range(-53000,85001,5500):
 if x<=9000 or x>=59000:slots.append(('Bottom',x,-41500,False))
report=json.load(open(base+'atlas_pass2_manifest.json'))
assert not any(a.get_actor_label().startswith('AtlasPass2_Frontage_') for a in sub.get_all_level_actors())
for i,(side,x,y,vertical) in enumerate(slots):
 path=paths[(i+i//6)%len(paths)];a=sub.spawn_actor_from_class(unreal.EditorAssetLibrary.load_blueprint_class(path),unreal.Vector(0,0,0));options=[]
 for yaw in [0,90]:
  a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=yaw,roll=0),False);refresh(a);lo,hi=bounds(a);w,d=hi[0]-lo[0],hi[1]-lo[1]
  scale=min((2600 if vertical else 4800)/w,(4800 if vertical else 2600)/d,5500/(hi[2]-lo[2]),1.1);options.append((scale,yaw))
 scale,yaw=max(options);a.set_actor_scale3d(unreal.Vector(scale,scale,scale));a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=yaw,roll=0),False);refresh(a);lo,hi=bounds(a)
 loc=unreal.Vector(x-(lo[0]+hi[0])/2,y-(lo[1]+hi[1])/2,2100-lo[2]);a.set_actor_location(loc,False,True);refresh(a);label='AtlasPass2_Frontage_%03d_%s'%(i,side);a.set_actor_label(label);a.set_folder_path('Atlas25/SecondPass/PerimeterFrontage');a.modify()
 for c in a.get_components_by_class(unreal.StaticMeshComponent):c.modify();c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
 report['backdrop'].append({'label':label,'prefab':path,'name':path.rsplit('/',1)[1],'location':[loc.x,loc.y,loc.z],'bounds':bounds(a),'scale':scale,'yaw':yaw,'base':2100,'side':side,'role':'frontage'})
json.dump(report,open(base+'atlas_pass2_manifest.json','w'),indent=2)
print('NEW STREET FRONTAGE',len(slots),'TOTAL PERIMETER BUILDINGS',len(report['backdrop']))
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

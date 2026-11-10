import unreal,json,itertools
base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_SecondPass' in w.get_path_name()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
def refresh(a):
 for c in a.get_components_by_class(unreal.StaticMeshComponent):c.set_relative_transform(c.get_relative_transform(),False,True)
def bounds(a):
 pts=[]
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  if not c.static_mesh:continue
  b=c.static_mesh.get_bounding_box();ts=[c.get_instance_transform(i,True) for i in range(c.get_instance_count())] if isinstance(c,unreal.InstancedStaticMeshComponent) else [c.get_world_transform()]
  for t in ts:
   for v in itertools.product([b.min.x,b.max.x],[b.min.y,b.max.y],[b.min.z,b.max.z]):
    p=unreal.MathLibrary.transform_location(t,unreal.Vector(*v));pts.append((p.x,p.y,p.z))
 return [[min(p[j] for p in pts) for j in range(3)],[max(p[j] for p in pts) for j in range(3)]]
state=json.load(open(base+'atlas_pass2_prefab_state.json'));actors={a.get_actor_label():a for a in sub.get_all_level_actors()}
report={'map':w.get_path_name(),'swaps':[],'palettes':[],'backdrop':[]}
for r in json.load(open(base+'atlas_pass2_changes.json')):
 old=actors[r['label']];old.modify();oldlo,oldhi=bounds(old);cx=(oldlo[0]+oldhi[0])/2;cy=(oldlo[1]+oldhi[1])/2
 dest=state['prefabs'][r['new_path']];a=sub.spawn_actor_from_class(unreal.EditorAssetLibrary.load_blueprint_class(dest),unreal.Vector(0,0,0));assert a
 options=[]
 for yaw in [0,90]:
  a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=yaw,roll=0),False);refresh(a);lo,hi=bounds(a)
  s=min((oldhi[0]-oldlo[0])*.98/(hi[0]-lo[0]),(oldhi[1]-oldlo[1])*.98/(hi[1]-lo[1]),(oldhi[2]-oldlo[2])*(1.15 if r['tower'] else 1.6)/(hi[2]-lo[2]),1.35)
  options.append((s,yaw))
 scale,yaw=max(options);a.set_actor_scale3d(unreal.Vector(scale,scale,scale));a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=yaw,roll=0),False);refresh(a);lo,hi=bounds(a)
 loc=unreal.Vector(cx-(lo[0]+hi[0])/2,cy-(lo[1]+hi[1])/2,r['ground']+5-lo[2]);a.set_actor_location(loc,False,True);refresh(a)
 assert sub.destroy_actor(old);a.set_actor_label(r['label']);a.set_folder_path('Atlas25/SecondPass/Streets');a.modify()
 for c in a.get_components_by_class(unreal.StaticMeshComponent):c.modify();c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
 record=dict(r,new_prefab=dest,final_scale=scale,yaw=yaw,location=[loc.x,loc.y,loc.z],bounds=bounds(a));report['swaps'].append(record);actors[r['label']]=a
 print('SWAP',r['label'],dest.rsplit('/',1)[-1],flush=True)
palettes={9:'Brown',21:'Brown',120:'Brown',13:'WarmRed',25:'WarmRed',93:'WarmRed',16:'Tan',24:'Tan',95:'Tan',20:'Charcoal',84:'Charcoal',124:'Charcoal'}
manifest=json.load(open(base+'atlas_overhaul_manifest.json'))
for r in manifest['buildings']:
 if r['source_id'] not in palettes:continue
 old=actors[r['label']];color=palettes[r['source_id']];dest=state['palette_prefabs'][color];old.modify()
 tr=old.get_actor_transform();a=sub.spawn_actor_from_class(unreal.EditorAssetLibrary.load_blueprint_class(dest),old.get_actor_location());a.set_actor_transform(tr,False,True);refresh(a)
 assert sub.destroy_actor(old);a.set_actor_label(r['label']);a.set_folder_path('Atlas25/SecondPass/BrickVariants');a.modify()
 for c in a.get_components_by_class(unreal.StaticMeshComponent):c.modify()
 report['palettes'].append({'label':r['label'],'palette':color,'prefab':dest,'bounds':bounds(a)});actors[r['label']]=a
for r in json.load(open(base+'atlas_pass2_backdrop_plan.json')):
 dest=state['prefabs'].get(r['path'],r['path']);a=sub.spawn_actor_from_class(unreal.EditorAssetLibrary.load_blueprint_class(dest),unreal.Vector(0,0,0));assert a
 s=r['scale'];a.set_actor_scale3d(unreal.Vector(s,s,s));a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=r['yaw'],roll=0),False);refresh(a);lo,hi=bounds(a)
 loc=unreal.Vector(r['x']-(lo[0]+hi[0])/2,r['y']-(lo[1]+hi[1])/2,r['base']-lo[2]);a.set_actor_location(loc,False,True);refresh(a);a.set_actor_label(r['label']);a.set_folder_path('Atlas25/SecondPass/Perimeter');a.modify()
 for c in a.get_components_by_class(unreal.StaticMeshComponent):c.modify();c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
 report['backdrop'].append(dict(r,prefab=dest,location=[loc.x,loc.y,loc.z],bounds=bounds(a)))
json.dump(report,open(base+'atlas_pass2_manifest.json','w'),indent=2)
print('PLACED',len(report['swaps']),len(report['palettes']),len(report['backdrop']))
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

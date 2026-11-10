import unreal,json,itertools
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_SecondPass' in w.get_path_name()
def bounds(a):
 pts=[]
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  if not c.static_mesh:continue
  box=c.static_mesh.get_bounding_box()
  ts=[c.get_instance_transform(i,True) for i in range(c.get_instance_count())] if isinstance(c,unreal.InstancedStaticMeshComponent) else [c.get_world_transform()]
  for t in ts:
   for v in itertools.product([box.min.x,box.max.x],[box.min.y,box.max.y],[box.min.z,box.max.z]):
    p=unreal.MathLibrary.transform_location(t,unreal.Vector(*v));pts.append((p.x,p.y,p.z))
 assert pts,a.get_actor_label()
 return [[min(p[j] for p in pts) for j in range(3)],[max(p[j] for p in pts) for j in range(3)]]
names=['BPP_Bldg_Hero_CHC_BlockThreeBuilding_A01_N1','BPP_Bldg_Hero_Mid_NYG_Triangle_B01_N1','BPP_Bldg_Hero_Mid_SFA_Triangle_N1','BPP_Bldg_Hero_Tower_CHC_A01_N1','BPP_SFD_RoundSplitTower_N1','BPP_CHD_Ref_A1_N1','BPP_SFB_Ref_N1','BPP_CHH_Ref_A1_N1']
rows=[]
for i,name in enumerate(names):
 folder='Kit_Hero_Bldg' if name.startswith('BPP_Bldg_') or name.startswith('BPP_SFD_Round') else 'Kit_Ref_Bldg'
 path='/Game/CitySampleBuildings/Building/Library/'+folder+'/LevelInstance/'+name
 a=sub.spawn_actor_from_class(unreal.EditorAssetLibrary.load_blueprint_class(path),unreal.Vector(200000+i*50000,200000,0));assert a,path
 a.set_actor_label('AtlasPass2_Prototype_'+str(i));lo,hi=bounds(a)
 rows.append({'name':name,'path':path,'label':a.get_actor_label(),'bounds':[lo,hi],'dimensions':[hi[j]-lo[j] for j in range(3)],'center':[(lo[j]+hi[j])/2 for j in range(3)]})
 print('CANDIDATE',i,name,[round((hi[j]-lo[j])/100,1) for j in range(3)],flush=True)
json.dump(rows,open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_pass2_catalog.json','w'),indent=2)
print('CATALOG READY')

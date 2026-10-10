"""Use a narrow storefront in the constrained corner bay instead of shrinking a mid-rise."""
import unreal,json,itertools
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_Upgraded' in w.get_path_name()
path='C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_manifest.json';m=json.load(open(path))
r=next(r for r in m['buildings'] if r['source_id']==84)
old=next(a for a in sub.get_all_level_actors() if a.get_actor_label()==r['label']);sub.destroy_actor(old)
bp='/Game/CitySampleBuildings/Building/Library/Kit_Ref_Bldg/LevelInstance/BPP_NYAD_Ref_N1'
a=sub.spawn_actor_from_class(unreal.EditorAssetLibrary.load_blueprint_class(bp),unreal.Vector(0,0,0));a.set_actor_label(r['label']);a.set_folder_path('Atlas25/Upgrades/Neighborhoods')
scale=.8;a.set_actor_scale3d(unreal.Vector(scale,scale,scale))
pts=[]
for c in a.get_components_by_class(unreal.StaticMeshComponent):
    if not c.static_mesh:continue
    c.set_relative_transform(c.get_relative_transform(),False,True)
    b=c.static_mesh.get_bounding_box();ts=[c.get_instance_transform(i,True) for i in range(c.get_instance_count())] if isinstance(c,unreal.InstancedStaticMeshComponent) else [c.get_world_transform()]
    for t in ts:
        for v in itertools.product([b.min.x,b.max.x],[b.min.y,b.max.y],[b.min.z,b.max.z]):
            p=unreal.MathLibrary.transform_location(t,unreal.Vector(*v));pts.append((p.x,p.y,p.z))
lo=[min(p[j] for p in pts) for j in range(3)];hi=[max(p[j] for p in pts) for j in range(3)]
loc=unreal.Vector(r['x']-(lo[0]+hi[0])/2,r['y']-(lo[1]+hi[1])/2,r['ground']+5-lo[2])
a.set_actor_location(loc,False,True)
for c in a.get_components_by_class(unreal.StaticMeshComponent):c.set_relative_transform(c.get_relative_transform(),False,True)
r.update(path=bp,name='BPP_NYAD_Ref_N1',yaw=0,final_scale=scale,location=[loc.x,loc.y,loc.z],bounds=[[lo[j]+[loc.x,loc.y,loc.z][j] for j in range(3)],[hi[j]+[loc.x,loc.y,loc.z][j] for j in range(3)]])
json.dump(m,open(path,'w'),indent=2);print('CORNER',r['label'],r['bounds'])
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

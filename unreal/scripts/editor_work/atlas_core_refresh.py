import unreal,json,math,sys
sys.path.insert(0,'C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/coh2unreal')
from coh2unreal.export import ue_transform
base='C:/Users/rtcru/ClaudeProjects/COHReborn/';sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);el=unreal.EditorAssetLibrary;sms=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_DressingStudy' in w.get_path_name()
assert not any(a.get_actor_label().startswith('AtlasCore_Bench_') for a in sub.get_all_level_actors())
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
inv=unreal.load_asset('/Game/CoH/Materials/M_Invisible');assert inv
bench=unreal.load_asset(json.load(open(base+'atlas_core_bench_asset.json'))['mesh']);assert bench
root='/Game/AtlasDressingStudy/CoreTiles';el.make_directory(root);changed=[];tiles={}
for a in sub.get_all_level_actors():
 if not a.get_actor_label().startswith('tile_') or not isinstance(a,unreal.StaticMeshActor):continue
 c=a.static_mesh_component;old=c.static_mesh
 if not old:continue
 slots=[i for i in range(len(old.static_materials)) if old.get_material(i) and old.get_material(i).get_name().lower() in ['prk_bench01_tga','prk_bench02_tga']]
 if not slots:continue
 name=a.get_actor_label();p=root+'/'+name;assert not el.does_asset_exist(p)
 mesh=el.duplicate_asset(old.get_path_name(),p);assert mesh
 for s in range(mesh.get_num_sections(0)):
  if sms.get_lod_material_slot(mesh,0,s) in slots:sms.enable_section_collision(mesh,False,0,s)
 assert el.save_loaded_asset(mesh,False)
 previous=[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())]
 a.modify();c.modify();c.set_static_mesh(mesh)
 for i,p in enumerate(previous):
  if p:c.set_material(i,unreal.load_asset(p))
 for i in slots:c.set_material(i,inv)
 c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
 changed.append({'label':name,'original_mesh':old.get_path_name(),'new_mesh':mesh.get_path_name(),'hidden_slots':slots,'previous_materials':previous});tiles[name]=a
assert changed,'No bench-only sections found'
rows=json.load(open(base+'atlas_core_bench_selected.json'));placed=[]
for i,r in enumerate(rows):
 loc,rot,scale=ue_transform(r['matrix']);a=sub.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*loc),unreal.Rotator(pitch=rot[0],yaw=rot[1],roll=rot[2]));c=a.static_mesh_component;a.modify();c.modify();c.set_static_mesh(bench);c.set_collision_profile_name('BlockAll');a.set_actor_scale3d(unreal.Vector(*scale));a.set_actor_label('AtlasCore_Bench_%03d'%i);a.set_folder_path('Atlas25/DressingStudy/OriginalPark/Benches')
 placed.append({'label':a.get_actor_label(),'location':loc,'rotation':rot,'scale':scale,'source_model':r['model'],'mesh':bench.get_path_name()})
json.dump({'map':w.get_path_name(),'tile_changes':changed,'benches':placed},open(base+'atlas_core_refresh_manifest.json','w'),indent=2)
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
print('CORE REFRESH',len(placed),'BENCHES',len(changed),'TILE COPIES SAVED')

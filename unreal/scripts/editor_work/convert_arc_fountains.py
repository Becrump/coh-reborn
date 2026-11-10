import unreal,json,pathlib
base=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors=sub.get_all_level_actors()
jets=[]
for a in actors:
 c=a.get_component_by_class(unreal.StaticMeshComponent)
 if not isinstance(a,unreal.StaticMeshActor) or not c:continue
 mesh=c.get_editor_property('static_mesh')
 if mesh and '/ArcJet/' in mesh.get_path_name():jets.append((a,c))
backups=[]
for a,c in jets:
 t=a.get_actor_transform();backups.append({'label':a.get_actor_label(),'path':a.get_path_name(),'location':list(t.translation.to_tuple()),'rotation':list(a.get_actor_rotation().to_tuple()),'scale':list(t.scale3d.to_tuple()),'mesh':c.get_editor_property('static_mesh').get_path_name()})
(base/'fountain_bundle_originals.json').write_text(json.dumps(backups,indent=2))
cls=unreal.EditorAssetLibrary.load_blueprint_class('/Game/CoH/FX/BP_CoH_ArcFountain')
assert cls
converted=[]
with unreal.ScopedEditorTransaction('Package water streams and splashes'):
 for a,c in jets:
  label=a.get_actor_label();t=a.get_actor_transform()
  new=sub.spawn_actor_from_class(cls,a.get_actor_location(),a.get_actor_rotation())
  assert new
  new.set_actor_transform(t,False,False)
  new.set_actor_label(label+'_Fountain');new.set_folder_path(a.get_folder_path())
  comps=new.get_components_by_class(unreal.StaticMeshComponent)
  splash=next(x for x in comps if x.get_name().startswith('Splash'))
  stream=next(x for x in comps if x.get_name().startswith('Stream'))
  for i in range(c.get_num_materials()):stream.set_material(i,c.get_material(i))
  endpoint=unreal.MathLibrary.transform_location(t,unreal.Vector(600,0,0))
  assert (splash.get_world_location()-endpoint).length()<0.01
  assert (stream.get_world_location()-a.get_actor_location()).length()<0.01
  converted.append({'label':new.get_actor_label(),'path':new.get_path_name(),'landing':list(endpoint.to_tuple()),'scale':list(new.get_actor_scale3d().to_tuple())})
  old_splash=next((x for x in actors if x.get_actor_label()==label+'_Splash'),None)
  if old_splash:sub.destroy_actor(old_splash)
  sub.destroy_actor(a)
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
(base/'fountain_bundle_report.json').write_text(json.dumps(converted,indent=2))
print('PACKAGED',len(converted),'fountains; user transforms preserved')

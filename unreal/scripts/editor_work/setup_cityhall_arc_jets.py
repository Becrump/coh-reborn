import unreal,json,pathlib
base=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
el=unreal.EditorAssetLibrary; reg=unreal.AssetRegistryHelpers.get_asset_registry()
folder='/Game/CoH/FX/ArcJet'
found=[d.get_asset() for d in reg.get_assets_by_path(folder,True) if str(d.asset_class_path.asset_name)=='StaticMesh']
if not found:
 task=unreal.AssetImportTask();task.filename=str(base/'fountain_arc/arc.gltf');task.destination_path=folder;task.automated=True;task.save=True
 unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
 found=[d.get_asset() for d in reg.get_assets_by_path(folder,True) if str(d.asset_class_path.asset_name)=='StaticMesh']
assert len(found)==1
mesh=found[0]
matpath='/Game/CoH/Materials/MI_CoH_ArcJet'
mat=unreal.load_asset(matpath) if el.does_asset_exist(matpath) else unreal.AssetToolsHelpers.get_asset_tools().create_asset('MI_CoH_ArcJet','/Game/CoH/Materials',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
unreal.MaterialEditingLibrary.set_material_instance_parent(mat,unreal.load_asset('/Game/CoH/Materials/M_CoH_WaterJet'))
for k,v in [('Opacity',0.28),('Streaks',0.1),('Glow',0.03)]:unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mat,k,v)
unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(mat,'WaterColor',unreal.LinearColor(0.65,0.85,0.92,1))
mesh.set_material(0,mat); ns=mesh.get_editor_property('nanite_settings');ns.enabled=False;mesh.set_editor_property('nanite_settings',ns)
el.save_loaded_asset(mesh,False);el.save_loaded_asset(mat,False)
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
existing={a.get_actor_label():a for a in sub.get_all_level_actors()}
placed=[]
for side,x in [('West',-5800),('East',13000)]:
 for i,y in enumerate([27000,28500,30000]):
  label='CityHall_ArcJet_'+side+'_'+str(i)
  a=existing.get(label) or sub.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(x,y,965),unreal.Rotator(yaw=90))
  a.set_actor_label(label);a.set_folder_path('CoH/Fountains/CityHallArcJets');c=a.static_mesh_component;c.set_static_mesh(mesh);c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
  placed.append({'label':label,'location':[x,y,965],'landing':[x,y+600,965]})
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
(base/'cityhall_arc_jets.json').write_text(json.dumps({'placed':placed,'mesh':mesh.get_path_name(),'material':mat.get_path_name(),'note':'Animated material on a parabolic water stream; no fluid simulation'},indent=2))
print('ARC JETS',len(placed))

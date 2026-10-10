import unreal
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
path='/Game/CoH/FX/BP_CoH_ArcFountain'
el=unreal.EditorAssetLibrary
if el.does_asset_exist(path):
 bp=unreal.load_asset(path)
else:
 f=unreal.BlueprintFactory();f.set_editor_property('parent_class',unreal.Actor)
 bp=unreal.AssetToolsHelpers.get_asset_tools().create_asset('BP_CoH_ArcFountain','/Game/CoH/FX',unreal.Blueprint,f)
s=unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem);lib=unreal.SubobjectDataBlueprintFunctionLibrary
handles=s.k2_gather_subobject_data_for_blueprint(bp)
objects=[(h,lib.get_object(lib.get_data(h))) for h in handles]
print('ROOTS',[(o.get_name(),o.get_class().get_name()) for h,o in objects])
root=next(h for h,o in objects if isinstance(o,unreal.SceneComponent))
for name,meshpath,location in [('Stream','/Game/CoH/FX/ArcJet/arc/StaticMeshes/SM_CoH_ArcJet',unreal.Vector(0,0,0)),('Splash','/Game/CoH/FX/Jets/jet_crown/jet_crown/StaticMeshes/jet_crown',unreal.Vector(600,0,0))]:
 mesh=unreal.load_asset(meshpath)
 if not mesh and name=='Stream':
  assets=unreal.AssetRegistryHelpers.get_asset_registry().get_assets_by_path('/Game/CoH/FX/ArcJet',True)
  mesh=next(d.get_asset() for d in assets if str(d.asset_class_path.asset_name)=='StaticMesh')
 assert mesh
 existing=next((o for h,o in objects if o.get_name().startswith(name)),None)
 if existing:c=existing
 else:
  h,reason=s.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=root,new_class=unreal.StaticMeshComponent,blueprint_context=bp))
  assert not str(reason),str(reason)
  assert s.rename_subobject(h,unreal.Text(name))
  c=lib.get_object(lib.get_data(h))
 c.set_static_mesh(mesh);c.set_editor_property('relative_location',location)
 c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_cast_shadow(False)
 if name=='Stream':c.set_material(0,unreal.load_asset('/Game/CoH/Materials/MI_CoH_ArcJet'))
 else:
  b=mesh.get_bounds().box_extent;c.set_editor_property('relative_scale3d',unreal.Vector(22/max(b.x,1),22/max(b.y,1),5/max(b.z,1)))
unreal.BlueprintEditorLibrary.compile_blueprint(bp)
assert el.save_loaded_asset(bp,False)
print('FOUNTAIN BLUEPRINT',bp.get_path_name())

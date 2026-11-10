import unreal,json
el=unreal.EditorAssetLibrary;bp=unreal.load_asset('/Game/CoH/FX/BP_CoH_ArcFountain')
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
backup='/Game/CoH/FX/BP_CoH_ArcFountain_BeforeRipples'
if not el.does_asset_exist(backup):assert el.duplicate_asset(bp.get_path_name(),backup)
sub=unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem);lib=unreal.SubobjectDataBlueprintFunctionLibrary
pairs=[(h,lib.get_object(lib.get_data(h))) for h in sub.k2_gather_subobject_data_for_blueprint(bp)]
root=next(h for h,o in pairs if isinstance(o,unreal.SceneComponent) and not isinstance(o,unreal.StaticMeshComponent))
spray=unreal.load_asset('/Game/CoH/FX/Spray/spray/StaticMeshes/spray')
mat=unreal.load_asset('/Game/CoH/Materials/M_CoH_SplashDroplets');ring=unreal.load_asset('/Game/CoH/Materials/M_CoH_ImpactRipples')
splash=next(o for h,o in pairs if o.get_name().startswith('Splash'))
splash.set_static_mesh(spray);splash.set_material(0,mat);splash.set_editor_property('relative_scale3d',unreal.Vector(1,1,1));splash.set_editor_property('bounds_scale',100.0)
ripple=next((o for h,o in pairs if o.get_name().startswith('Ripples')),None)
if not ripple:
 h,reason=sub.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=root,new_class=unreal.StaticMeshComponent,blueprint_context=bp));assert not str(reason)
 assert sub.rename_subobject(h,unreal.Text('Ripples'));ripple=lib.get_object(lib.get_data(h))
ripple.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Plane'));ripple.set_material(0,ring)
ripple.set_editor_property('relative_location',unreal.Vector(600,0,1));ripple.set_editor_property('relative_scale3d',unreal.Vector(1.2,1.2,1))
for c in [splash,ripple]:c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_cast_shadow(False);c.set_editor_property('disallow_nanite',True)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
before={a.get_path_name():str(a.get_actor_transform()) for a in actors if a.get_class().get_name().startswith('BP_CoH_ArcFountain')}
unreal.BlueprintEditorLibrary.compile_blueprint(bp)
assert el.save_loaded_asset(bp,False)
count=0
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
 if a.get_path_name() in before:
  assert str(a.get_actor_transform())==before[a.get_path_name()]
  a.modify()
  for c in a.get_components_by_class(unreal.StaticMeshComponent):
   if c.get_name()=='Ripples':c.set_editor_property('disallow_nanite',True)
   if c.get_name()=='Splash':c.set_editor_property('disallow_nanite',True);c.set_static_mesh(spray);c.set_material(0,mat);c.set_editor_property('relative_scale3d',unreal.Vector(1,1,1));c.set_editor_property('bounds_scale',100.0)
  print('UPDATED',a.get_actor_label(),[c.get_name() for c in a.get_components_by_class(unreal.StaticMeshComponent)])
  count+=1
print('FOUNTAINS UPDATED',count,'TRANSFORMS PRESERVED')
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

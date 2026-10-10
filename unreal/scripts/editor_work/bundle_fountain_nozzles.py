import unreal,math
el=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary;tools=unreal.AssetToolsHelpers.get_asset_tools()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
def mat(name,color,metal,rough):
 m=unreal.load_asset('/Game/CoH/Materials/'+name)
 if m:
  assert el.save_loaded_asset(m,False)
  return m
 m=tools.create_asset(name,'/Game/CoH/Materials',unreal.Material,unreal.MaterialFactoryNew())
 c=mel.create_material_expression(m,unreal.MaterialExpressionConstant3Vector);c.set_editor_property('constant',unreal.LinearColor(*color,1));assert mel.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
 for value,prop in [(metal,unreal.MaterialProperty.MP_METALLIC),(rough,unreal.MaterialProperty.MP_ROUGHNESS)]:
  c=mel.create_material_expression(m,unreal.MaterialExpressionConstant);c.set_editor_property('r',value);assert mel.connect_material_property(c,'',prop)
 mel.recompile_material(m);assert el.save_loaded_asset(m,False)
 return m
steel=mat('M_CoH_FountainSteel',(.22,.25,.27),.9,.25);dark=mat('M_CoH_NozzleBore',(.005,.007,.008),.2,.7)
bp=unreal.load_asset('/Game/CoH/FX/BP_CoH_ArcFountain');sub=unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem);lib=unreal.SubobjectDataBlueprintFunctionLibrary
pairs=[(h,lib.get_object(lib.get_data(h))) for h in sub.k2_gather_subobject_data_for_blueprint(bp)]
root=next(h for h,o in pairs if isinstance(o,unreal.SceneComponent) and not isinstance(o,unreal.StaticMeshComponent))
settings=[('NozzleTube',(-6,0,-8),(.14,.14,.28),-36.8699,steel),('NozzleBore',(2.5,0,3.3),(.105,.105,.008),-36.8699,dark),('NozzleBase',(-14.4,0,-20.7),(.25,.25,.05),0,steel)]
for name,loc,scale,pitch,m in settings:
 c=next((o for h,o in pairs if o.get_name().startswith(name)),None)
 if not c:
  h,reason=sub.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=root,new_class=unreal.StaticMeshComponent,blueprint_context=bp));assert not str(reason)
  assert sub.rename_subobject(h,unreal.Text(name));c=lib.get_object(lib.get_data(h))
 c.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cylinder'));c.set_material(0,m);c.set_editor_property('relative_location',unreal.Vector(*loc));c.set_editor_property('relative_scale3d',unreal.Vector(*scale));c.set_editor_property('relative_rotation',unreal.Rotator(pitch,0,0));c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
unreal.BlueprintEditorLibrary.compile_blueprint(bp);assert el.save_loaded_asset(bp,False)
count=0
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
 if a.get_class().get_name()!='BP_CoH_ArcFountain_C':continue
 a.modify();s=a.get_actor_scale3d();pitch=math.degrees(math.atan2(8*s.z,6*s.x));yaw=math.radians(a.get_actor_rotation().yaw);pr=math.radians(pitch);direction=unreal.Vector(math.cos(pr)*math.cos(yaw),math.cos(pr)*math.sin(yaw),math.sin(pr));origin=a.get_actor_location()
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  name=c.get_name()
  if name not in {x[0] for x in settings}:continue
  entry=next(x for x in settings if x[0]==name)
  c.set_editor_property('absolute_scale',True);c.set_world_scale3d(unreal.Vector(*entry[2]))
  if name!='NozzleBase':c.set_editor_property('absolute_rotation',False);c.set_relative_rotation(unreal.Rotator(pitch-90,0,0),False,False)
  target=origin-direction*10 if name=='NozzleTube' else origin+direction*4 if name=='NozzleBore' else origin-direction*24-unreal.Vector(0,0,2)
  c.set_world_location(target,False,False)
 count+=1
print('NOZZLES',count,'ACTOR PLACEMENTS UNCHANGED')
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

import unreal,json
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);el=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary;root='/Game/AtlasSecondPass/Scenery';el.make_directory(root)
cube=unreal.load_asset('/Engine/BasicShapes/Cube');parent=unreal.load_asset('/Engine/BasicShapes/BasicShapeMaterial');mats={}
for name,color in [('Pavement',[.075,.082,.087]),('Road',[.034,.039,.044]),('Lane',[.5,.5,.44])]:
 path=root+'/MI_'+name;mat=el.load_asset(path) if el.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset('MI_'+name,root,unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
 mel.set_material_instance_parent(mat,parent);mel.set_material_instance_vector_parameter_value(mat,'Color',unreal.LinearColor(*color,1));assert el.save_loaded_asset(mat,False);mats[name]=mat
for a in sub.get_all_level_actors():
 if a.get_actor_label().startswith('AtlasPass2_Apron_'):sub.destroy_actor(a)
records=[]
def box(name,lo,hi,z,height,mat):
 a=sub.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector((lo[0]+hi[0])/2,(lo[1]+hi[1])/2,z-height/2));c=a.static_mesh_component;c.set_static_mesh(cube);c.set_material(0,mats[mat]);a.set_actor_scale3d(unreal.Vector((hi[0]-lo[0])/100,(hi[1]-lo[1])/100,height/100));c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);a.set_actor_label('AtlasPass2_Apron_'+name);a.set_folder_path('Atlas25/SecondPass/PerimeterGround');a.modify();c.modify();records.append({'label':a.get_actor_label(),'lo':lo,'hi':hi,'top':z,'material':mat})
for name,lo,hi in [('West',[-88000,-65000],[-56000,112000]),('East',[90000,-65000],[122000,112000]),('Top',[-56000,82000],[90000,112000]),('BottomLeft',[-56000,-65000],[12000,-36500]),('BottomRight',[55000,-65000],[90000,-36500])]:box(name,lo,hi,2100,2600,'Pavement')
roads=[('West',[-61400,-43000],[-60600,82000],True),('East',[91600,-43000],[92400,82000],True),('Top',[-60000,84600],[105000,85400],False),('BottomLeft',[-60000,-39400],[12000,-38600],False),('BottomRight',[55000,-39400],[105000,-38600],False)]
for name,lo,hi,vertical in roads:
 box(name+'Road',lo,hi,2110,10,'Road')
 for i,v in enumerate(range(int(lo[1] if vertical else lo[0]),int(hi[1] if vertical else hi[0]),2200)):
  if vertical:
   x=(lo[0]+hi[0])/2;bl=[x-8,v];bh=[x+8,v+650]
  else:
   y=(lo[1]+hi[1])/2;bl=[v,y-8];bh=[v+650,y+8]
  box(name+'Lane_%03d'%i,bl,bh,2114,4,'Lane')
json.dump(records,open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_pass2_ground.json','w'),indent=2)
# Return the rebuilt tile to its original Nanite rendering settings; retain the verified street-support collision proxy.
sms=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem);m=el.load_asset('/Game/AtlasSecondPass/Geometry/atlas_secondpass/StaticMeshes/tile_-4_-3');old=el.load_asset('/Game/AtlasUpgraded/Geometry/atlas_upgraded/StaticMeshes/tile_-4_-3');sms.set_nanite_settings(m,old.get_editor_property('nanite_settings'),True);assert el.save_loaded_asset(m,False)
print('PERIMETER GROUND pieces',len(records),'SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

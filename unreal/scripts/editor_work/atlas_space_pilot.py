import unreal,json
base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
u=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);el=unreal.EditorAssetLibrary
source='/Game/AtlasPark4/AtlasPark_SecondPass';dest='/Game/AtlasPark4/AtlasPark_DressingStudy'
assert source in u.get_editor_world().get_path_name()
assert not el.does_asset_exist(dest),'Study already exists; inspect before replacing'
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
assert unreal.EditorLoadingAndSavingUtils.save_map(u.get_editor_world(),dest)
assert unreal.EditorLoadingAndSavingUtils.load_map(dest)
unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in unreal.WorldPartitionBlueprintLibrary.get_actor_descs()])
root='/Game/AtlasDressingStudy/Materials';el.make_directory(root);mats={}
for name,col in [('Sidewalk',(.18,.18,.165)),('Stone',(.10,.115,.12)),('Soil',(.025,.032,.019)),('Seat',(.13,.085,.052)),('Metal',(.018,.024,.025))]:
 p=root+'/MI_'+name
 m=unreal.AssetToolsHelpers.get_asset_tools().create_asset('MI_'+name,root,unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
 assert m
 unreal.MaterialEditingLibrary.set_material_instance_parent(m,unreal.load_asset('/Engine/BasicShapes/BasicShapeMaterial'))
 unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(m,'Color',unreal.LinearColor(*col,1))
 assert el.save_loaded_asset(m,False);mats[name]=m
cube=unreal.load_asset('/Engine/BasicShapes/Cube');records=[]
def mesh(name,m,x,y,z,scale=(1,1,1),yaw=0,mat=None):
 a=sub.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(x,y,z),unreal.Rotator(pitch=0,yaw=yaw,roll=0));c=a.static_mesh_component;c.set_static_mesh(m)
 a.set_actor_scale3d(unreal.Vector(*scale));a.set_actor_label('AtlasDressing_'+name);a.set_folder_path('Atlas25/DressingStudy/WestStreet');c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
 if mat:c.set_material(0,mats[mat])
 a.modify();c.modify();records.append({'label':a.get_actor_label(),'mesh':m.get_path_name(),'location':[x,y,z],'scale':list(scale),'yaw':yaw});return a
def box(name,x,y,z,w,d,h,mat):return mesh(name,cube,x,y,z,(w/100,d/100,h/100),mat=mat)
# A continuous 4m sidewalk and a shallow curb, with no raised pieces over the road.
box('Sidewalk',-61600,56000,2114,400,27000,28,'Sidewalk')
box('Curb',-61412,56000,2117,24,27000,34,'Stone')
data=json.load(open(base+'atlas_pass2_manifest.json'))
rows=sorted([r for r in data['backdrop'] if r.get('role')=='frontage' and r['side']=='West' and 40000<r['bounds'][0][1]<78000],key=lambda r:r['bounds'][0][1])
allbounds=[r['bounds'] for r in data['backdrop']]
def clear(lo,hi):
 return not any(lo[0]<b[1][0] and hi[0]>b[0][0] and lo[1]<b[1][1] and hi[1]>b[0][1] for b in allbounds)
shrub=unreal.load_asset('/Game/GV_FreeShrubsPack/Meshes/Shrubs/Wind/Shrub_B/GV_Vol7_Shrub_B_full_type1')
assert isinstance(shrub,unreal.StaticMesh)
sign=unreal.load_asset('/Game/Deko_MatrixDemo/City/Meshes/SM_StandingSignAd_A01_N1')
assert isinstance(sign,unreal.StaticMesh)
for i,(left,right) in enumerate(zip(rows,rows[1:])):
 y=(left['bounds'][1][1]+right['bounds'][0][1])/2
 if y>69000:continue
 # Each pocket occupies a verified gap, keeping the four-metre sidewalk open.
 lo=[-63800,y-600];hi=[-62050,y+600];assert clear(lo,hi),(i,lo,hi)
 box('Pocket_%02d'%i,-62925,y,2112,1750,1200,24,'Sidewalk')
 box('BedBase_%02d'%i,-63350,y,2124,700,1000,48,'Stone')
 box('BedSoil_%02d'%i,-63350,y,2148,630,930,8,'Soil')
 for j,dy in enumerate([-300,0,300]):mesh('Shrub_%02d_%d'%(i,j),shrub,-63350,y+dy,2152,(.5,.5,.5),yaw=i*43+j*97)
 # Simple modern seating for the study; not a claimed City Sample bench asset.
 for j,dy in enumerate([-340,340]):
  by=y+dy
  box('Seat_%02d_%d'%(i,j),-62300,by,2170,65,200,12,'Seat')
  box('SeatBack_%02d_%d'%(i,j),-62328,by,2203,10,200,60,'Seat')
  for k,ly in enumerate([-70,70]):box('SeatLeg_%02d_%d_%d'%(i,j,k),-62300,by+ly,2145,45,10,40,'Metal')
 if i in [1,3]:mesh('AdSign_%02d'%i,sign,-62050,y+120,2128,yaw=90)
for i,r in enumerate(rows):
 lo,hi=r['bounds'];y=(lo[1]+hi[1])/2
 if y>69000:continue
 # Short approach pavement fills the setback without shifting the buildings.
 x0=hi[0]+35;x1=-61800
 assert x1>x0
 box('Approach_%02d'%i,(x0+x1)/2,y,2104,x1-x0,800,8,'Sidewalk')
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
json.dump({'map':dest,'source':source,'actors':records,'scope':'West outer street visual dressing pilot; no gameplay collision'},open(base+'atlas_space_pilot.json','w'),indent=2)
print('DRESSING STUDY',dest,'NEW ACTORS',len(records),'SAVED',True)

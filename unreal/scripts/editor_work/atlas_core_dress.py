import unreal,json,math
base='C:/Users/rtcru/ClaudeProjects/COHReborn/';sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();el=unreal.EditorAssetLibrary
assert 'AtlasPark_DressingStudy' in w.get_path_name();assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
assert not any(a.get_actor_label().startswith('AtlasCore_Planter_') for a in sub.get_all_level_actors())
data=json.load(open(base+'atlas_core_refresh_manifest.json'));mats={k:unreal.load_asset('/Game/AtlasDressingStudy/Materials/MI_'+k) for k in ['Stone','Soil']};cube=unreal.load_asset('/Engine/BasicShapes/Cube');shrub=unreal.load_asset('/Game/GV_FreeShrubsPack/Meshes/Shrubs/Wind/Shrub_B/GV_Vol7_Shrub_B_full_type1');sign=unreal.load_asset('/Game/Deko_MatrixDemo/City/Meshes/SM_StandingSignAd_A01_N1');records=[];benches=[a for a in sub.get_all_level_actors() if a.get_actor_label().startswith('AtlasCore_Bench_')]
def ground(x,y,hint):
 h=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(x,y,hint+180),unreal.Vector(x,y,hint-200),unreal.TraceTypeQuery.ECC_VISIBILITY,False,benches,unreal.DrawDebugTrace.NONE,True)
 if not h or not h.to_tuple()[0]:return None
 return h.to_tuple()[4].z
def spawn(label,m,loc,scale,yaw=0,material=None):
 a=sub.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*loc),unreal.Rotator(pitch=0,yaw=yaw,roll=0));c=a.static_mesh_component;a.modify();c.modify();c.set_static_mesh(m);a.set_actor_scale3d(unreal.Vector(*scale));c.set_collision_profile_name('NoCollision');a.set_actor_label(label);a.set_folder_path('Atlas25/DressingStudy/OriginalPark/StreetFurniture')
 if material:c.set_material(0,mats[material])
 records.append({'label':label,'mesh':m.get_path_name(),'location':loc,'scale':scale,'yaw':yaw})
# Select separated, existing seating locations within the original park streets.
selected=[]
for r in data['benches']:
 x,y,z=r['location']
 if not (-15000<x<15000 and -21000<y<20000):continue
 if any(math.hypot(x-s['location'][0],y-s['location'][1])<2500 for s in selected):continue
 selected.append(r)
 if len(selected)==8:break
for i,r in enumerate(selected):
 x,y,z=r['location'];rad=math.radians(r['rotation'][1]);co,si=math.cos(rad),math.sin(rad)
 for j,dx in enumerate([-180,180]):
  # Small planters beside the seat, leaving its front approach clear.
  px=x+dx*co-60*si;py=y+dx*si+60*co;gz=ground(px,py,z)
  if gz is None or abs(gz-z)>25:continue
  corner=[ground(px+sx,py+sy,z) for sx in [-40,40] for sy in [-40,40]]
  if any(v is None or abs(v-gz)>10 for v in corner):continue
  spawn('AtlasCore_Planter_%02d_%d'%(i,j),cube,[px,py,gz+24],[.8,.8,.48],material='Stone')
  spawn('AtlasCore_Soil_%02d_%d'%(i,j),cube,[px,py,gz+48],[.68,.68,.04],material='Soil')
  spawn('AtlasCore_Shrub_%02d_%d'%(i,j),shrub,[px,py,gz+50],[.23,.23,.23],yaw=i*57+j*89)
 # A few signs by the seating, rather than beside every bench.
 if i in [1,5]:
  px=x+330*co;py=y+330*si;gz=ground(px,py,z)
  if gz is not None and abs(gz-z)<20:spawn('AtlasCore_Sign_%02d'%i,sign,[px,py,gz],[.8,.8,.8],yaw=r['rotation'][1]+90)
data['new_furniture']=records;data['seating_locations']=selected;json.dump(data,open(base+'atlas_core_refresh_manifest.json','w'),indent=2)
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
print('PARK DRESSING',len(selected),'SEATING LOCATIONS',len(records),'ADDITIONS',[(k,sum(r['label'].startswith(k) for r in records)) for k in ['AtlasCore_Planter','AtlasCore_Sign']])

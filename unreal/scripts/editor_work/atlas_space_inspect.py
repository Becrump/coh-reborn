import unreal,json
u=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
print('MAP',u.get_editor_world().get_path_name())
paths=['/Game/Deko_MatrixDemo/City/Meshes/SM_CTY_StreetSign_A01_N1','/Game/Deko_MatrixDemo/City/Meshes/SM_StandingSignAd_A01_N1','/Game/GV_FreeShrubsPack/Meshes/Shrubs/Wind/Shrub_B/GV_Vol7_Shrub_B_full_type1']
for p in paths:
 m=unreal.load_asset(p)
 if isinstance(m,unreal.StaticMesh):
  b=m.get_bounding_box();print(p,'BOUNDS',b.min,b.max,'MATERIALS',[str(x.material_interface) for x in m.static_materials])
 else:print('UNUSABLE',p,str(m))
data=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_pass2_manifest.json'))
for r in data['backdrop']:
 if r.get('role')=='frontage' and r['side']=='West' and 40000<r['bounds'][0][1]<78000:print(r['label'],r['bounds'])

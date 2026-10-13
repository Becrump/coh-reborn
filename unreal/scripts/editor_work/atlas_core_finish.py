import unreal,json
base='C:/Users/rtcru/ClaudeProjects/COHReborn/';sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);data=json.load(open(base+'atlas_core_refresh_manifest.json'))
removed=[]
for a in sub.get_all_level_actors():
 if a.get_actor_label().startswith('AtlasCore_Sign_'):removed.append(a.get_actor_label());assert sub.destroy_actor(a)
data['new_furniture']=[r for r in data['new_furniture'] if r['label'] not in removed];data['removed_after_visual_review']=removed
json.dump(data,open(base+'atlas_core_refresh_manifest.json','w'),indent=2)
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
print('FINAL PARK',len(data['benches']),'BENCHES',len(data['new_furniture']),'PLANTER PARTS; REMOVED SIGNS',removed)

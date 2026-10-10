import unreal,json,math
base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
u=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
manifest=json.load(open(base+'atlas_space_pilot.json'))
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
assert unreal.EditorLoadingAndSavingUtils.load_map('/Game/AtlasPark4/AtlasPark_SecondPass')
assert unreal.EditorLoadingAndSavingUtils.load_map(manifest['map'])
unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in unreal.WorldPartitionBlueprintLibrary.get_actor_descs()])
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);actors={a.get_actor_label():a for a in sub.get_all_level_actors()}
for r in manifest['actors']:
 a=actors[r['label']];p=a.get_actor_location();s=a.get_actor_scale3d();c=a.static_mesh_component
 assert max(abs(v-w) for v,w in zip([p.x,p.y,p.z],r['location']))<.1,r['label']
 assert max(abs(v-w) for v,w in zip([s.x,s.y,s.z],r['scale']))<.001,r['label']
 assert c.static_mesh.get_path_name()==r['mesh'],r['label']
 assert c.get_collision_enabled()==unreal.CollisionEnabled.NO_COLLISION,r['label']
report={'map':manifest['map'],'saved_reload_actor_checks':len(manifest['actors']),'result':'passed','scope':'visual dressing; new sidewalk and props have no gameplay collision'}
json.dump(report,open(base+'atlas_space_validation.json','w'),indent=2)
print('SAVED MAP REOPEN CHECK',report)

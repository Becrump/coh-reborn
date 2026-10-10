import unreal,json,pathlib
base=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
r=json.load(open(base/'atlas_enemy_upgrade_pilot_report.json'))
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
actors={a.get_actor_label():a for a in sub.get_all_level_actors()}
reg=unreal.AssetRegistryHelpers.get_asset_registry()
for row in r['changes']:
 a=actors[row['label']]; c=a.get_component_by_class(unreal.SkeletalMeshComponent)
 assets=reg.get_assets_by_path('/Game/Characters/Enemies/Hellions/'+row['variant'],True)
 stance=next(d.get_asset() for d in assets if str(d.asset_name)=='Combat_Stance' and str(d.asset_class_path.asset_name)=='AnimSequence')
 c.override_animation_data(stance,True,False,0.5,0.0)
 pos=a.get_actor_location()
 hit=unreal.SystemLibrary.line_trace_single(world,unreal.Vector(pos.x,pos.y,pos.z+200),unreal.Vector(pos.x,pos.y,pos.z-600),unreal.TraceTypeQuery.ECC_VISIBILITY,True,[],unreal.DrawDebugTrace.NONE,True)
 if hit and hit.to_tuple()[0] and hit.to_tuple()[5].z>0.7:
  ground=hit.to_tuple()[4].z
  feet=min(c.get_socket_location(n).z for n in ['LeftFoot','RightFoot','LeftToeBase','RightToeBase'])
  delta=ground+6.0-feet
  a.set_actor_location(unreal.Vector(pos.x,pos.y,pos.z+delta),False,False)
  row['ground_adjust_cm']=delta
 row['preview_animation']=stance.get_path_name()
 row['preview_time']=0.5
 c.set_component_tick_enabled(False)
(base/'atlas_enemy_upgrade_pilot_report.json').write_text(json.dumps(r,indent=2))
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
print('CORRECTED UPGRADE POSES',len(r['changes']))

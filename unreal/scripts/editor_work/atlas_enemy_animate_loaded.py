import unreal,json,pathlib,hashlib
base=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
plan=json.load(open(base/'atlas_enemy_plan.json'));library=json.load(open(base/'atlas_enemy_import_report.json'))
rows={r['id']:r for r in plan['population']}
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert 'AtlasPark_DressingStudy' in world.get_path_name()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
reportpath=base/'atlas_enemy_animation_ground_report.json'
report=json.load(open(reportpath)) if reportpath.exists() else {}
for a in sub.get_all_level_actors():
 label=a.get_actor_label()
 if not label.startswith('CoHOriginal_') or label in report:continue
 tags=[str(t) for t in a.tags];costume=next(t[8:] for t in tags if t.startswith('Costume_'))
 row=next((r for r in plan['population'] if label=='CoHOriginal_'+r['group']+'_'+r['id']),None)
 assert row
 c=a.get_component_by_class(unreal.SkeletalMeshComponent)
 result={'costume':costume,'original_location':list(a.get_actor_location().to_tuple()),'animated':False,'phase':'PhaseControlled' in tags}
 if not c:
  result['status']='static_object';report[label]=result;continue
 mesh=c.get_skeletal_mesh_asset();original='/OriginalEnemies/' in mesh.get_path_name()
 paths=[v for k,v in library[costume]['clips'].items() if k.lower().endswith('idle')]
 if costume == 'Rikti_Pylon':
  paths=list(library[costume]['clips'].values())
 if not original:
  folder='/Game/Characters/Enemies/Hellions/'+mesh.get_name()
  found=[d.get_asset() for d in unreal.AssetRegistryHelpers.get_asset_registry().get_assets_by_path(folder,True) if str(d.asset_name)=='Combat_Stance' and str(d.asset_class_path.asset_name)=='AnimSequence']
  paths=[found[0].get_path_name()] if found else []
 if not paths:
  result['status']='missing_idle';report[label]=result;continue
 idle=unreal.load_asset(paths[0]);assert mesh.get_editor_property('skeleton')==idle.get_editor_property('skeleton')
 a.modify();c.modify()
 t=(int(hashlib.sha256(label.encode()).hexdigest()[:8],16)%10000)/10000*idle.get_play_length()
 c.override_animation_data(idle,True,True,t,1.0)
 c.set_component_tick_enabled(True)
 c.set_component_tick_interval(0.05)
 c.set_editor_property('visibility_based_anim_tick_option',unreal.VisibilityBasedAnimTickOption.ONLY_TICK_POSE_WHEN_RENDERED)
 c.set_editor_property('enable_update_rate_optimizations',True)
 c.set_update_animation_in_editor(True)
 result.update(animated=True,animation=idle.get_path_name(),start_time=t,status='configured')
 no_snap=row.get('actor_properties',{}).get('NoGroundSnap',['0'])[0]!='0'
 if not no_snap:
  p=a.get_actor_location();hit=unreal.SystemLibrary.line_trace_single(world,unreal.Vector(p.x,p.y,p.z+120),unreal.Vector(p.x,p.y,p.z-400),unreal.TraceTypeQuery.ECC_VISIBILITY,True,[],unreal.DrawDebugTrace.NONE,True)
  names={str(n) for n in c.get_all_socket_names()};feet=[n for n in ['FOOTL','FOOTR','TOEL','TOER','LeftFoot','RightFoot','LeftToeBase','RightToeBase'] if n in names]
  if hit and hit.to_tuple()[0] and hit.to_tuple()[5].z>0.7 and feet:
   delta=hit.to_tuple()[4].z+6-min(c.get_socket_location(n).z for n in feet)
   result['ground_delta_cm']=delta
   if abs(delta)<=75:
    if abs(delta)>1:a.set_actor_location(unreal.Vector(p.x,p.y,p.z+delta),False,False)
   else:result['placement_review']='height_difference_over_75cm'
  elif not(hit and hit.to_tuple()[0]):result['placement_review']='no_ground_below'
 if 'PhaseControlled' in tags:a.set_is_temporarily_hidden_in_editor(True)
 report[label]=result
reportpath.write_text(json.dumps(report,indent=2))
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
print('ANIMATION CHECKPOINT',len(report),'animated',sum(r['animated'] for r in report.values()),'placement_flags',sum('placement_review' in r for r in report.values()))

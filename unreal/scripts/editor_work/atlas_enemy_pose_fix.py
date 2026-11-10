import json,unreal
r=json.load(open(r'C:\Users\rtcru\ClaudeProjects\COHReborn\atlas_enemy_import_report.json'))
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
 if not a.get_actor_label().startswith('CoHOriginal_'): continue
 c=a.get_component_by_class(unreal.SkeletalMeshComponent)
 if not c: continue
 key=next(str(t)[8:] for t in a.tags if str(t).startswith('Costume_'))
 paths=[v for k,v in r[key]['clips'].items() if k.lower().endswith('idle')]
 if paths:
  c.override_animation_data(unreal.load_asset(paths[0]),True,False,0.0,0.0)
  c.set_component_tick_enabled(False)
  print('POSE',key)
unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)

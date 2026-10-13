import unreal,json,collections,pathlib
base=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
plan=json.load(open(base/'atlas_enemy_plan.json'))
actors=[a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors() if a.get_actor_label().startswith('CoHOriginal_')]
labels=[a.get_actor_label() for a in actors]
expected={'CoHOriginal_'+r['group']+'_'+r['id'] for r in plan['population']}
assert len(labels)==len(set(labels))==len(expected)==4659
assert set(labels)==expected
phased=sum(any(str(t)=='PhaseControlled' for t in a.tags) for a in actors)
upgrade=sum('/OriginalEnemies/' not in a.get_component_by_class(unreal.SkeletalMeshComponent).get_skeletal_mesh_asset().get_path_name() for a in actors if a.get_component_by_class(unreal.SkeletalMeshComponent))
assert upgrade==12
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
r={'map':unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name(),'placed':len(actors),'duplicates':0,'missing':0,'story_phase_previews':phased,'upgraded_hellions':upgrade,'source_effect_markers':len(plan['effects']),'combat_ai':False,'selection':'One deterministic spawn alternative per original encounter, one-player preview; all sites shown. Seasonal layers excluded.'}
(base/'atlas_enemy_verification.json').write_text(json.dumps(r,indent=2))
print(json.dumps(r))

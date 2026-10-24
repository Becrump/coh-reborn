import unreal,json,pathlib
base=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
report=json.load(open(base/'atlas_enemy_animation_ground_report.json'))
descs=unreal.WorldPartitionBlueprintLibrary.get_actor_descs()
selected=[d for d in descs if str(d.label).startswith('CoHOriginal_') and str(d.label) not in report][:120]
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
loaded={a.get_actor_label() for a in sub.get_all_level_actors()}
new=[d.guid for d in selected if str(d.label) not in loaded]
unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in selected])
exec(compile((base/'atlas_enemy_animate_loaded.py').read_text(),'atlas_enemy_animate_loaded.py','exec'),{'__name__':'__main__'})
unreal.WorldPartitionBlueprintLibrary.unload_actors(new)
print('BATCH FINISHED',len(selected))

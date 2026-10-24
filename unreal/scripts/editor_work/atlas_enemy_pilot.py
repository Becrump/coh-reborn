import unreal
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level('/Game/AtlasPark4/AtlasPark_DressingStudy')
descs=unreal.WorldPartitionBlueprintLibrary.get_actor_descs()
unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in descs])
print('LOADED WORLD ACTORS',len(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()))
ENEMY_PLACE_LIMIT=20
exec(compile(open(r'C:\Users\rtcru\ClaudeProjects\COHReborn\atlas_enemy_place.py').read(),'atlas_enemy_place.py','exec'))

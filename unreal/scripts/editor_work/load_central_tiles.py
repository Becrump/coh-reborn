import unreal
w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();print('WORLD',w.get_path_name())
d=unreal.WorldPartitionBlueprintLibrary.get_actor_descs()
selected=[x for x in d if str(x.label) in ['tile_0_1','tile_0_2','tile_-1_1','Sun','Moon','DayNightCycle']]
print('CENTRAL DESCS',[(str(x.label),str(x.bounds)) for x in selected])
unreal.WorldPartitionBlueprintLibrary.load_actors([x.guid for x in selected])
a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tiles=[x for x in a.get_all_level_actors() if x.get_actor_label() in ['tile_0_1','tile_0_2','tile_-1_1']]
a.set_selected_level_actors(tiles)
print('SELECTED CENTRAL TILES',len(tiles))

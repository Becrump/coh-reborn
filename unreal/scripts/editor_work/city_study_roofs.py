import unreal
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert 'AtlasPark_CitySampleStudy' in unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name()
n=0
for a in sub.get_all_level_actors():
    if str(a.get_folder_path())!='Atlas25/Buildings':continue
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        if c.static_mesh and c.static_mesh.get_name() in ('Plane','SM_Plane_NN_A'):
            c.set_visibility(True);c.set_hidden_in_game(False);c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS);n+=1
print('ROOF_PLANES',n)
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

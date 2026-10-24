import unreal,json
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_Upgraded' in w.get_path_name()
m=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_manifest.json'));labels={r[0] for r in m['tiles'] if r[1]=='updated'}
n=0
for a in sub.get_all_level_actors():
    if isinstance(a,unreal.StaticMeshActor) and a.get_actor_label() in labels:
        c=a.static_mesh_component;c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS);n+=1
print('PHYSICS_REFRESH',n)
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))

import unreal,json,pathlib
base=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
mesh=unreal.load_asset('/Game/CoH/FX/Jets/jet_crown/jet_crown/StaticMeshes/jet_crown')
assert mesh
b=mesh.get_bounds().box_extent
actors={a.get_actor_label():a for a in sub.get_all_level_actors()}
jets=json.load(open(base/'cityhall_arc_jets.json'))
for row in jets['placed']:
 label=row['label']+'_Splash';a=actors.get(label) or sub.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*row['landing']))
 a.set_actor_label(label);a.set_folder_path('CoH/Fountains/CityHallArcJets')
 c=a.static_mesh_component;c.set_static_mesh(mesh);c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_cast_shadow(False)
 a.set_actor_scale3d(unreal.Vector(22/max(b.x,1),22/max(b.y,1),5/max(b.z,1)))
 actors[row['label']].static_mesh_component.set_cast_shadow(False)
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
print('SPLASH RINGS',len(jets['placed']))

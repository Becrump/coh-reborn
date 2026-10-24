import unreal
m=unreal.load_asset('/Game/AtlasSecondPass/Geometry/atlas_secondpass/StaticMeshes/tile_-4_-3');old=unreal.load_asset('/Game/AtlasUpgraded/Geometry/atlas_upgraded/StaticMeshes/tile_-4_-3')
print('Custom collision before',m.get_editor_property('complex_collision_mesh'))
m.modify();m.set_editor_property('complex_collision_mesh',old);assert unreal.EditorAssetLibrary.save_loaded_asset(m,False)
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
 if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh==m:
  c=a.static_mesh_component;a.modify();c.modify();c.set_static_mesh(None);c.set_static_mesh(m);c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
print('Preserved original support collision')
print('Basic shape params',[str(p) for p in unreal.MaterialEditingLibrary.get_vector_parameter_names(unreal.load_asset('/Engine/BasicShapes/BasicShapeMaterial'))])

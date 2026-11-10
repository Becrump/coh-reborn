import unreal
sms=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem);m=unreal.load_asset('/Game/AtlasSecondPass/Geometry/atlas_secondpass/StaticMeshes/tile_-4_-3');s=m.get_editor_property('nanite_settings');s.set_editor_property('enabled',False);sms.set_nanite_settings(m,s,True);assert unreal.EditorAssetLibrary.save_loaded_asset(m,False)
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
 if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh==m:
  c=a.static_mesh_component;a.modify();c.modify();c.set_static_mesh(None);c.set_static_mesh(m);c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
print('Exact legacy render mesh enabled')

import unreal
sms=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
print('SET NANITE API',sms.set_nanite_settings.__doc__)
m=unreal.load_asset('/Game/AtlasSecondPass/Geometry/atlas_secondpass/StaticMeshes/tile_-4_-3')
s=m.get_editor_property('nanite_settings');s.set_editor_property('fallback_relative_error',0.0)
sms.set_nanite_settings(m,s,True)
unreal.EditorAssetLibrary.save_loaded_asset(m,False)
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
 if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh==m:
  a.modify();c=a.static_mesh_component;c.modify();c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION);c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
print('Exact fallback repaired')

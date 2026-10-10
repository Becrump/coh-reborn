import unreal
for path in ['/Game/AtlasSecondPass/Geometry/atlas_secondpass/StaticMeshes/tile_-4_-3','/Game/AtlasUpgraded/Geometry/atlas_upgraded/StaticMeshes/tile_-4_-3']:
 m=unreal.load_asset(path);print('MESH',path,m)
 if m:print('NANITE',m.get_editor_property('nanite_settings'),'BOX',m.get_bounding_box())
print('API',[p for p in dir(unreal.StaticMeshEditorSubsystem) if any(k in p for k in ['nanite','lod','build'])])

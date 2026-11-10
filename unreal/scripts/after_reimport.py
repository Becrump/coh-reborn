import unreal, sys
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()
meshes = {str(d.asset_name): d for d in reg.get_assets_by_path("/Game/atlas_park/StaticMeshes", True)
          if str(d.asset_class_path.asset_name) == "StaticMesh"}
tiles = {a.get_actor_label(): a for a in asub.get_all_level_actors()
         if isinstance(a, unreal.StaticMeshActor) and a.get_actor_label().startswith("tile_")}
ref = next(iter(tiles.values()))
folder = ref.get_folder_path()
print("tile folder:", folder, "transform", ref.get_actor_location(), ref.get_actor_scale3d())
added = 0
for name, d in sorted(meshes.items()):
    if name in tiles or not name.startswith("tile_"):
        continue
    a = asub.spawn_actor_from_object(d.get_asset(), ref.get_actor_location(), ref.get_actor_rotation())
    a.set_actor_scale3d(ref.get_actor_scale3d())
    a.set_actor_label(name)
    a.set_folder_path(folder)
    added += 1
print("new tile actors:", added)
# clear per-slot overrides (slot order may have changed), then reapply
cleared = 0
for a in tiles.values():
    c = a.static_mesh_component
    for i in range(c.get_num_materials()):
        if c.get_material(i) != c.static_mesh.get_material(i):
            c.set_material(i, c.static_mesh.get_material(i)); cleared += 1
print("cleared overrides:", cleared)
gone = [l for l in tiles if l not in meshes]
print("tile actors with no mesh any more:", gone)

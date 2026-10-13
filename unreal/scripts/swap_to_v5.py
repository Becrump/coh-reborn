import sys, unreal
sys.path.insert(0, r"C:/Users/rtcru/ClaudeProjects/coh-reborn/coh2unreal/unreal")
import importlib, coh_materials as cm
importlib.reload(cm)
NEW = "/Game/atlas_park/atlas_park"
TUNED = "/Game/atlas_park/Materials"
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()
el = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tuned = {str(d.asset_name).lower(): d for d in reg.get_assets_by_path(TUNED, True)
         if str(d.asset_class_path.asset_name) == "MaterialInstanceConstant"}
meshes = {str(d.asset_name): d for d in reg.get_assets_by_path(NEW + "/StaticMeshes", True)
          if str(d.asset_class_path.asset_name) == "StaticMesh"}
water = unreal.load_asset("/Game/CoH/Materials/M_CoH_Water")
linked = kept = 0
new_mats = set()
with unreal.ScopedSlowTask(len(meshes), "Linking v5 tiles to tuned materials") as task:
    task.make_dialog(False)
    for name, d in sorted(meshes.items()):
        task.enter_progress_frame(1, name)
        mesh = d.get_asset()
        mats = mesh.get_editor_property("static_materials")
        changed = False
        for i, sm in enumerate(mats):
            mi = sm.get_editor_property("material_interface")
            if mi is None:
                continue
            t = tuned.get(mi.get_name().lower())
            if t is not None:
                sm.set_editor_property("material_interface", t.get_asset())
                mats[i] = sm; changed = True; linked += 1
            else:
                kept += 1; new_mats.add(mi.get_path_name())
        if changed:
            mesh.set_editor_property("static_materials", mats)
            el.save_loaded_asset(mesh, False)
# new-only materials: water tops onto the water master
for p in new_mats:
    mi = unreal.load_asset(p)
    if mi and mi.get_name().lower().endswith("__watertop") and water and mi.parent != water:
        cm.reparent(mi, water)
        mel.set_material_instance_vector_parameter_value(mi, "DeepColor", unreal.LinearColor(0.03, 0.12, 0.14, 1))
        mel.set_material_instance_scalar_parameter_value(mi, "TextureMix", 0.3)
        mel.update_material_instance(mi); el.save_loaded_asset(mi, False)
print("slots linked to tuned:", linked, "| new-only slots:", kept, sorted(n.rsplit(".", 1)[-1] for n in new_mats)[:12], len(new_mats))
# swap level actors
tiles = {a.get_actor_label(): a for a in asub.get_all_level_actors()
         if isinstance(a, unreal.StaticMeshActor) and a.get_actor_label().startswith("tile_")}
ref = next(iter(tiles.values()))
folder = ref.get_folder_path()
swapped = added = 0
for name, d in sorted(meshes.items()):
    mesh = d.get_asset()
    a = tiles.get(name)
    if a is None:
        a = asub.spawn_actor_from_object(mesh, ref.get_actor_location(), ref.get_actor_rotation())
        a.set_actor_scale3d(ref.get_actor_scale3d()); a.set_actor_label(name); a.set_folder_path(folder)
        added += 1
    else:
        c = a.static_mesh_component
        c.set_static_mesh(mesh)
        c.set_editor_property("override_materials", [])
        swapped += 1
gone = [n for n in tiles if n not in meshes]
for n in gone:
    asub.destroy_actor(tiles[n])
print("swapped", swapped, "added", added, "removed (no longer in export):", gone)

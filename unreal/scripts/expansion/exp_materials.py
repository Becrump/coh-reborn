"""Expansion test, step 4a: material setup for the re-exported wall tiles and
the new block, all inside /Game/AtlasExpansionTest.
Slots whose material already exists in the tuned Atlas Park set
(/Game/atlas_park/Materials) are pointed at it, as swap_to_v5.py did. The
rest (textures Atlas Park never used) get apply_tuning.tune_materials()
from the block's export folder. Only assets under ROOT are changed."""
import importlib.util, unreal
ROOT = "/Game/AtlasExpansionTest"
TUNED = "/Game/atlas_park/Materials"
OUT_BLOCK = r"C:/Users/rtcru/CoHReborn/out/atlas_expansion_block"
reg = unreal.AssetRegistryHelpers.get_asset_registry()
el = unreal.EditorAssetLibrary
tuned = {str(d.asset_name).lower(): d for d in reg.get_assets_by_path(TUNED, True)
         if str(d.asset_class_path.asset_name) == "MaterialInstanceConstant"}
meshes = [d for d in reg.get_assets_by_path(ROOT, True) if str(d.asset_class_path.asset_name) == "StaticMesh"]
linked = kept = 0
new_folders = set()
for d in meshes:
    mesh = d.get_asset()
    assert mesh.get_path_name().startswith(ROOT + "/")
    mats = mesh.get_editor_property("static_materials")
    changed = False
    for i, sm in enumerate(mats):
        mi = sm.get_editor_property("material_interface")
        if mi is None or not mi.get_path_name().startswith(ROOT + "/"):
            continue
        t = tuned.get(mi.get_name().lower())
        if t is not None:
            sm.set_editor_property("material_interface", t.get_asset())
            mats[i] = sm; changed = True; linked += 1
        else:
            kept += 1; new_folders.add(mi.get_path_name().rsplit("/", 1)[0])
    if changed:
        mesh.set_editor_property("static_materials", mats)
        el.save_loaded_asset(mesh, False)
print("slots linked to tuned Atlas materials:", linked, "| new-only slots:", kept, sorted(new_folders))
spec = importlib.util.spec_from_file_location("exp_apply_tuning", OUT_BLOCK + "/apply_tuning.py")
at = importlib.util.module_from_spec(spec); spec.loader.exec_module(at)
for f in sorted(new_folders):
    assert f.startswith(ROOT + "/")
    at.tune_materials(f)
    print("tuned", f)

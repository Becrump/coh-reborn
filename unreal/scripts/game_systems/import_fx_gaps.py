"""Fills the effect assets still missing from the project: every texture of
the player and enemy effect libraries not yet in /Game/CoH/FX/Textures, and
every visible effect model not yet in /Game/CoH/FX/Geoms.

Textures are imported from a staging folder of PIL-checked RGBA PNGs
(out/fx_stage/textures, prepared outside the editor), in batches of 100 with
a save after each. Plain AssetImportTask only (never an export task).
Only the packages this script creates are saved.
"""
import json
import os
import re
import unreal

OUT = r"C:\Users\rtcru\CoHReborn\out"
STAGE = os.path.join(OUT, "fx_stage", "textures")
TEX, GEO = "/Game/CoH/FX/Textures", "/Game/CoH/FX/Geoms"
el = unreal.EditorAssetLibrary


def an(f):
    return re.sub(r"[^a-z0-9_]", "_", os.path.splitext(os.path.basename(f))[0].lower())


tools = unreal.AssetToolsHelpers.get_asset_tools()
pngs = sorted(f for f in os.listdir(STAGE) if f.endswith(".png")) if os.path.isdir(STAGE) else []
done = 0
for b in range(0, len(pngs), 100):
    tasks = []
    for f in pngs[b:b + 100]:
        n = an(f)
        if el.does_asset_exist(TEX + "/" + n):
            continue
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", os.path.join(STAGE, f))
        t.set_editor_property("destination_path", TEX)
        t.set_editor_property("destination_name", n)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", False)
        t.set_editor_property("save", True)
        tasks.append(t)
    if tasks:
        tools.import_asset_tasks(tasks)
        done += len(tasks)
    print("textures batch %d: %d imported" % (b // 100 + 1, done))

mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
models = 0
for lib_dir in (os.path.join(OUT, "fx"), os.path.join(OUT, "enemies", "fx")):
    lib = json.load(open(os.path.join(lib_dir, "fx_library.json")))
    for g in lib["geoms"].values():
        if not g.get("mesh") or el.does_asset_exist(GEO + "/" + an(g["mesh"])):
            continue
        pipe = unreal.InterchangeGenericAssetsPipeline()
        pipe.set_editor_property("scene_name_sub_folder", False)
        pipe.set_editor_property("asset_type_sub_folders", False)
        mesh = pipe.get_editor_property("mesh_pipeline")
        mesh.set_editor_property("import_skeletal_meshes", False)
        mesh.set_editor_property("import_static_meshes", True)
        params = unreal.ImportAssetParameters()
        params.set_editor_property("is_automated", True)
        params.set_editor_property("replace_existing", False)
        params.set_editor_property("override_pipelines", [unreal.SoftObjectPath(pipe.get_path_name())])
        try:
            mgr.import_asset(GEO, unreal.InterchangeManager.create_source_data(os.path.join(lib_dir, g["mesh"])), params)
            models += 1
        except Exception as e:
            print("  warn", g["mesh"], str(e)[:160])
# Interchange finishes asynchronously: save what landed
el.save_directory(GEO, only_if_is_dirty=True, recursive=True)
print("models requested", models)

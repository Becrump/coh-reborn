"""Step 6 (docs/enemy-setup.md): import the villain models of the kit
(out/enemies/models/<costume>.gltf, each clip named after its move) into
/Game/CoH/Enemies/<costume>/, clips renamed to the move names
(Brawl_R, Spray_A, idle, run ...) so the game finds them by name.

Globals: GS_GROUPS (list of villain groups, None = all), GS_LIMIT.
Only the packages this script creates are saved.
"""
import json
import os
import unreal

OUT = r"C:\Users\rtcru\CoHReborn\out\enemies"
ROOT = "/Game/CoH/Enemies"
el = unreal.EditorAssetLibrary
reg = unreal.AssetRegistryHelpers.get_asset_registry()
mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
groups = globals().get("GS_GROUPS")
limit = int(globals().get("GS_LIMIT") or 0)


def assets_in(path, cls=None):
    reg.scan_paths_synchronous([path], True)
    return [d for d in reg.get_assets_by_path(path, True)
            if cls is None or str(d.asset_class_path.asset_name) == cls]


kit = json.load(open(os.path.join(OUT, "kit.json")))
models = {}
for name, v in kit.items():
    if groups and v.get("group") not in groups:
        continue
    for m in v.get("models", []):
        c = os.path.splitext(os.path.basename(m))[0]
        models.setdefault(c, set()).update(v.get("clips", []))
done = 0
for costume, clips in sorted(models.items()):
    dest = "%s/%s" % (ROOT, costume)
    if assets_in(dest, "SkeletalMesh"):
        print("have", costume)
        continue
    if limit and done >= limit:
        break
    pipe = unreal.InterchangeGenericAssetsPipeline()
    pipe.set_editor_property("scene_name_sub_folder", False)
    pipe.set_editor_property("asset_type_sub_folders", False)
    mesh = pipe.get_editor_property("mesh_pipeline")
    mesh.set_editor_property("combine_skeletal_meshes_behavior",
                             unreal.InterchangeCombineSkeletalMeshesBehavior.BY_SKELETON)
    mesh.set_editor_property("create_physics_asset", True)
    mesh.set_editor_property("import_static_meshes", False)
    pipe.get_editor_property("animation_pipeline").set_editor_property("import_animations", True)
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    params.set_editor_property("replace_existing", False)
    params.set_editor_property("override_pipelines", [unreal.SoftObjectPath(pipe.get_path_name())])
    src = os.path.join(OUT, "models", costume + ".gltf")
    try:
        mgr.import_asset(dest, unreal.InterchangeManager.create_source_data(src), params)
    except Exception as e:  # Interchange logs non-fatal errors as exceptions
        print("  warn", costume, str(e)[:200])
    want = sorted(set(clips) | {"idle", "run", "attack", "hit", "death"}, key=len, reverse=True)
    renamed = 0
    for d in assets_in(dest, "AnimSequence"):
        n = str(d.asset_name)
        clip = next((c for c in want if n.endswith(c) and n != c), None)
        if clip and not el.does_asset_exist(dest + "/" + clip):
            if el.rename_asset(str(d.package_name), dest + "/" + clip):
                renamed += 1
    for d in assets_in(dest):
        a = d.get_asset()
        if a:
            el.save_loaded_asset(a, False)
    done += 1
    print("ENEMY", costume, "meshes", len(assets_in(dest, "SkeletalMesh")),
          "clips", len(assets_in(dest, "AnimSequence")), "renamed", renamed)
print("ENEMIES", len([c for c in models if assets_in("%s/%s" % (ROOT, c), "SkeletalMesh")]), "/", len(models))

"""Step 1-2 (docs/powers-and-player-models.md): import the original player
bodies and the animation library into the open editor.

Run with ue_exec.py (Python Remote Execution). Settings come from globals
set before the file runs (ue_exec "GS_STEP='anims'; GS_BODY='male'; exec(open(...).read())"):

  GS_STEP   'base'    one preset per body as the skeletal mesh that defines
                      the body's skeleton (SK of Model_Positron, Model_MsLiberty,
                      Model_Back_Alley_Brawler)
            'anims'   every <body>_anims_NN.gltf onto that skeleton as
                      animations only, renamed to the clip names of anims.json
                      (male/energy_rapid -> male__energy_rapid)
            'presets' more presets (GS_PRESETS list) on the same skeletons
  GS_BODY   limit to one body
  GS_FILES  limit 'anims' to these file stems (male_anims_03 ...)

Assets: /Game/CoH/Player/Presets/<body>/<preset>/..., /Game/CoH/Player/Anims/<body>/<clip>.
Only the packages this script creates are saved.
"""
import json
import os
import unreal

OUT = r"C:\Users\rtcru\CoHReborn\out\player"
ROOT = "/Game/CoH/Player"
BASE = {"male": "Model_Positron", "fem": "Model_MsLiberty", "huge": "Model_Back_Alley_Brawler"}

el = unreal.EditorAssetLibrary
reg = unreal.AssetRegistryHelpers.get_asset_registry()
mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
step = globals().get("GS_STEP", "base")
bodies = [globals()["GS_BODY"]] if globals().get("GS_BODY") else list(BASE)


def assets_in(path, cls=None):
    reg.scan_paths_synchronous([path], True)
    out = []
    for d in reg.get_assets_by_path(path, True):
        if cls is None or str(d.asset_class_path.asset_name) == cls:
            out.append(d)
    return out


def pipeline(skeleton=None, anims_only=False):
    pipe = unreal.InterchangeGenericAssetsPipeline()
    pipe.set_editor_property("scene_name_sub_folder", False)
    pipe.set_editor_property("asset_type_sub_folders", False)
    mesh = pipe.get_editor_property("mesh_pipeline")
    mesh.set_editor_property("combine_skeletal_meshes_behavior",
                             unreal.InterchangeCombineSkeletalMeshesBehavior.BY_SKELETON)
    mesh.set_editor_property("create_physics_asset", False)
    mesh.set_editor_property("import_static_meshes", False)
    common = pipe.get_editor_property("common_skeletal_meshes_and_animations_properties")
    if skeleton:
        common.set_editor_property("skeleton", skeleton)
    if anims_only:
        common.set_editor_property("import_only_animations", True)
    pipe.get_editor_property("animation_pipeline").set_editor_property("import_animations", True)
    return pipe


def body_copy(src, body):
    """A copy of the glTF whose scene root node is named after the body.
    The skeletons have two root joints (HIPS, MYSTIC), so Interchange adds a
    proxy root joint named after the scene root: every file of a body must
    use the same name or its tracks do not match the skeleton."""
    g = json.load(open(src))
    for sc in g.get("scenes", []):
        for n in sc.get("nodes", []):
            g["nodes"][n]["name"] = body
    dst = src[:-5] + ".ue.gltf"
    with open(dst, "w") as f:
        json.dump(g, f)
    return dst


def run_import(src, dest, pipe):
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    params.set_editor_property("replace_existing", False)
    params.set_editor_property("override_pipelines", [unreal.SoftObjectPath(pipe.get_path_name())])
    return mgr.import_asset(dest, unreal.InterchangeManager.create_source_data(src), params)


def save(path):
    for d in assets_in(path):
        a = d.get_asset()
        if a:
            el.save_loaded_asset(a, False)


def body_skeleton(body):
    for d in assets_in("%s/Presets/%s/%s" % (ROOT, body, BASE[body]), "Skeleton"):
        return d.get_asset()
    return None


def models():
    return {m["name"]: m for m in json.load(open(os.path.join(OUT, "models.json")))}


CLIPS = ("combat_idle", "idle", "run", "attack", "hit", "death")


def rename_clips(dest):
    """Model_Positron_ueidle -> idle (the hero code looks clips up by name)."""
    for d in assets_in(dest, "AnimSequence"):
        n = str(d.asset_name)
        clip = next((c for c in CLIPS if n.endswith(c)), None)
        if clip and n != clip:
            el.rename_asset(str(d.package_name), dest + "/" + clip)


def import_preset(body, name, skeleton):
    dest = "%s/Presets/%s/%s" % (ROOT, body, name)
    if assets_in(dest, "SkeletalMesh"):
        print("have", dest)
        return
    m = models()[name]
    ok = run_import(body_copy(os.path.join(OUT, m["gltf"]), body), dest, pipeline(skeleton))
    rename_clips(dest)
    save(dest)
    meshes = assets_in(dest, "SkeletalMesh")
    print("PRESET", name, body, "ok" if ok and meshes else "FAILED",
          [d.asset_name for d in assets_in(dest)][:12])


if step == "fixclips":
    for body in bodies:
        rename_clips("%s/Presets/%s/%s" % (ROOT, body, BASE[body]))
        save("%s/Presets/%s/%s" % (ROOT, body, BASE[body]))
        print("CLIPS", body, [str(d.asset_name) for d in assets_in("%s/Presets/%s/%s" % (ROOT, body, BASE[body]), "AnimSequence")])

if step == "base":
    for body in bodies:
        import_preset(body, BASE[body], None)
        print("SKELETON", body, body_skeleton(body))

elif step == "presets":
    ms = models()
    for name in globals().get("GS_PRESETS", []):
        body = ms[name]["body"]
        if body not in bodies:
            continue
        import_preset(body, name, body_skeleton(body))

elif step == "anims":
    lib = {b["body"]: b for b in json.load(open(os.path.join(OUT, "anims.json")))}
    for body in bodies:
        skel = body_skeleton(body)
        if not skel:
            raise RuntimeError("import the %s base preset first" % body)
        files = sorted({c["file"] for c in lib[body]["clips"]})
        if globals().get("GS_FILES"):
            files = [f for f in files if f in globals()["GS_FILES"]]
        dest = "%s/Anims/%s" % (ROOT, body)
        for f in files:
            want = [c["clip"] for c in lib[body]["clips"] if c["file"] == f]
            if all(el.does_asset_exist("%s/%s" % (dest, c)) for c in want):
                print("have", f)
                continue
            tmp = "%s/_import/%s" % (dest, f)
            ok = run_import(body_copy(os.path.join(OUT, "anims", body, f + ".gltf"), body), tmp, pipeline(skel, True))
            seqs = assets_in(tmp, "AnimSequence")
            moved = 0
            for d in seqs:
                n = str(d.asset_name)
                clip = next((c for c in sorted(want, key=len, reverse=True) if n == c or n.endswith(c)), None)
                if not clip:
                    print("  no clip for", n)
                    continue
                target = "%s/%s" % (dest, clip)
                if el.does_asset_exist(target):
                    el.delete_asset(str(d.package_name))
                    continue
                if el.rename_asset(str(d.package_name), target):
                    moved += 1
            save(dest)
            for d in assets_in(tmp):
                el.delete_asset(str(d.package_name))
            print("ANIMS", body, f, "ok" if ok else "FAILED", "%d/%d clips" % (moved, len(want)))
    for body in bodies:
        print("LIBRARY", body, len(assets_in("%s/Anims/%s" % (ROOT, body), "AnimSequence")))

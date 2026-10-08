"""Imports glTF animation clips onto an existing character skeleton.

Run in the Unreal editor (not during Play):
    py "<repo>/coh2unreal/unreal/import_anims.py" <clip folder> <skeleton asset> <dest folder>

Each <clip>.glb (from export_anims.py) is imported with Interchange set to
animations only, onto <skeleton>, so the clips play on the character already
in the project. Prints each AnimSequence created.
"""
import os
import sys

import unreal


def main():
    folder, skel_path, dest = [a for a in sys.argv[1:]
                               if not a.startswith("-")][:3]
    skel = unreal.load_asset(skel_path)
    if not skel:
        raise RuntimeError("no skeleton at " + skel_path)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    made = []
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith(".glb"):
            continue
        pipe = unreal.InterchangeGenericAssetsPipeline()
        common = pipe.get_editor_property(
            "common_skeletal_meshes_and_animations_properties")
        common.set_editor_property("import_only_animations", True)
        common.set_editor_property("skeleton", skel)
        anim = pipe.get_editor_property("animation_pipeline")
        anim.set_editor_property("import_animations", True)
        params = unreal.ImportAssetParameters()
        params.set_editor_property("is_automated", True)
        params.set_editor_property("replace_existing", True)
        # override pipelines are soft paths; the transient pipeline object
        # resolves while it is alive
        params.set_editor_property(
            "override_pipelines", [unreal.SoftObjectPath(pipe.get_path_name())])
        src = unreal.InterchangeManager.create_source_data(
            os.path.join(folder, f))
        mgr.import_asset(dest + "/" + os.path.splitext(f)[0], src, params)
        made.append(f)
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    reg.scan_paths_synchronous([dest], True)
    seqs = [str(d.package_name) for d in reg.get_assets_by_path(dest, True)
            if str(d.asset_class_path.asset_name) == "AnimSequence"]
    unreal.log("[CoH anims] imported %d files -> %d AnimSequences: %s" % (
        len(made), len(seqs), seqs))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


main()

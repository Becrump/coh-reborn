"""Imports a Meshy enemy group (e.g. Hellions) into Unreal.

Run in the Unreal editor (not during Play):
    py "<repo>/coh2unreal/unreal/setup_enemies.py" <meshy folder> <Group> <anim source> <name> [<name> ...]

e.g. setup_enemies.py C:/Users/me/CoHReborn/meshy Hellions hellion_biker
     hellion_biker hellion_hood hellion_punk hellion_lieutenant

For each <name> (from tools/meshy_make.py): imports rig/rigged_character_glb.glb
as a skeletal mesh under /Game/Characters/Enemies/<Group>/<name> and builds
its material from textured/texture_urls_0_*.png. The animation set
(<anim source>/anims/animation_glb.glb, Meshy's merged clips) is imported onto
the anim source's skeleton, then retargeted onto every other variant (FK only:
no root-motion or foot-IK ops, which break Meshy rigs).
"""
import os
import sys

import unreal

el = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
reg = unreal.AssetRegistryHelpers.get_asset_registry()


def log(msg):
    unreal.log("[CoH enemies] " + msg)


def import_file(path, dest, name=None):
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", path)
    t.set_editor_property("destination_path", dest)
    if name:
        t.set_editor_property("destination_name", name)
    for k in ("automated", "replace_existing", "save"):
        t.set_editor_property(k, True)
    tools.import_asset_tasks([t])


def assets(path, cls):
    return [d.get_asset() for d in reg.get_assets_by_path(path, True)
            if str(d.asset_class_path.asset_name) == cls]


def texture(path, dest, name, srgb=True, kind=None):
    import_file(path, dest, name)
    t = unreal.load_asset("%s/%s" % (dest, name))
    t.set_editor_property("srgb", srgb)
    if kind == "normal":
        t.set_editor_property("compression_settings",
                              unreal.TextureCompressionSettings.TC_NORMALMAP)
    elif not srgb:
        t.set_editor_property("compression_settings",
                              unreal.TextureCompressionSettings.TC_MASKS)
    el.save_loaded_asset(t, False)
    return t


def build_material(folder, dest, name):
    tex_dir = os.path.join(folder, "textured")
    maps = {"BaseColor": ("base_color", True, None),
            "Normal": ("normal", False, "normal"),
            "Metallic": ("metallic", False, None),
            "Roughness": ("roughness", False, None)}
    path = "%s/M_%s" % (dest, name)
    if el.does_asset_exist(path):
        m = unreal.load_asset(path)
        mel.delete_all_material_expressions(m)
    else:
        m = tools.create_asset("M_" + name, dest, unreal.Material,
                               unreal.MaterialFactoryNew())
    m.set_editor_property("used_with_skeletal_mesh", True)
    props = {"BaseColor": unreal.MaterialProperty.MP_BASE_COLOR,
             "Normal": unreal.MaterialProperty.MP_NORMAL,
             "Metallic": unreal.MaterialProperty.MP_METALLIC,
             "Roughness": unreal.MaterialProperty.MP_ROUGHNESS}
    for i, (k, (suffix, srgb, kind)) in enumerate(maps.items()):
        png = os.path.join(tex_dir, "texture_urls_0_%s.png" % suffix)
        if not os.path.exists(png):
            continue
        tex = texture(png, dest, "T_%s_%s" % (name, suffix), srgb, kind)
        n = mel.create_material_expression(
            m, unreal.MaterialExpressionTextureSample, -400, i * 250)
        n.set_editor_property("texture", tex)
        n.set_editor_property(
            "sampler_type",
            unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if kind == "normal"
            else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if srgb
            else unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
        mel.connect_material_property(
            n, "RGB" if k in ("BaseColor", "Normal") else "R", props[k])
    mel.recompile_material(m)
    el.save_loaded_asset(m, False)
    return m


def ik_rig(mesh, path):
    folder, name = path.rsplit("/", 1)
    rig = unreal.load_asset(path) if el.does_asset_exist(path) else \
        tools.create_asset(name, folder, unreal.IKRigDefinition,
                           unreal.IKRigDefinitionFactory())
    c = unreal.IKRigController.get_controller(rig)
    c.set_skeletal_mesh(mesh)
    c.apply_auto_generated_retarget_definition()
    el.save_loaded_asset(rig, False)
    return rig


def retargeter(src, dst, path):
    folder, name = path.rsplit("/", 1)
    rt = unreal.load_asset(path) if el.does_asset_exist(path) else \
        tools.create_asset(name, folder, unreal.IKRetargeter,
                           unreal.IKRetargetFactory())
    c = unreal.IKRetargeterController.get_controller(rt)
    c.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, src)
    c.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, dst)
    if c.get_num_retarget_ops() == 0:
        c.add_default_ops()
    for side, rig in ((unreal.RetargetSourceOrTarget.SOURCE, src),
                      (unreal.RetargetSourceOrTarget.TARGET, dst)):
        try:
            c.assign_ik_rig_to_all_ops(side, rig)
        except Exception:
            pass
    c.auto_map_chains(unreal.AutoMapChainType.FUZZY, True)
    for i in range(c.get_num_retarget_ops()):
        if str(c.get_op_name(i)) in ("Root Motion", "Run IK Rig"):
            c.set_retarget_op_enabled(i, False)
    el.save_loaded_asset(rt, False)
    return rt


def import_clips(glb, skeleton, dest):
    pipe = unreal.InterchangeGenericAssetsPipeline()
    common = pipe.get_editor_property(
        "common_skeletal_meshes_and_animations_properties")
    common.set_editor_property("import_only_animations", True)
    common.set_editor_property("skeleton", skeleton)
    pipe.get_editor_property("animation_pipeline").set_editor_property(
        "import_animations", True)
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    params.set_editor_property("replace_existing", True)
    params.set_editor_property(
        "override_pipelines", [unreal.SoftObjectPath(pipe.get_path_name())])
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    mgr.import_asset(dest, unreal.InterchangeManager.create_source_data(glb),
                     params)
    reg.scan_paths_synchronous([dest], True)
    return assets(dest, "AnimSequence")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    root, group, src_name, names = args[0], args[1], args[2], args[3:]
    base = "/Game/Characters/Enemies/" + group
    meshes = {}
    for n in names:
        dest = "%s/%s" % (base, n)
        # baked to Unreal units by fix_rig_scale.py (Meshy API rigs come in
        # at 1/100 scale otherwise)
        import_file(os.path.join(root, n, "ue", n + ".glb"), dest)
        mesh = assets(dest, "SkeletalMesh")[0]
        mat = build_material(os.path.join(root, n), dest, n)
        mats = mesh.get_editor_property("materials")
        for i, sm in enumerate(mats):
            sm.set_editor_property("material_interface", mat)
            mats[i] = sm
        mesh.set_editor_property("materials", mats)
        el.save_loaded_asset(mesh, False)
        meshes[n] = mesh
        log("%s: mesh %.0f cm tall" % (n, mesh.get_bounds().box_extent.z * 2))
    src = meshes[src_name]
    # one glb per clip from export_anims.py
    clip_dir = os.path.join(root, src_name, "ue", "clips")
    for f in sorted(os.listdir(clip_dir)):
        if f.endswith(".glb"):
            import_clips(os.path.join(clip_dir, f),
                         src.get_editor_property("skeleton"),
                         "%s/%s/Anims/%s" % (base, src_name, f[:-4]))
    reg.scan_paths_synchronous(["%s/%s/Anims" % (base, src_name)], True)
    clips = assets("%s/%s/Anims" % (base, src_name), "AnimSequence")
    log("animation clips on %s: %s" % (src_name,
                                       sorted(c.get_name() for c in clips)))
    src_rig = ik_rig(src, "%s/%s/IK_%s" % (base, src_name, src_name))
    for n, mesh in meshes.items():
        if n == src_name:
            continue
        dst_rig = ik_rig(mesh, "%s/%s/IK_%s" % (base, n, n))
        rt = retargeter(src_rig, dst_rig, "%s/%s/RTG_%s" % (base, n, n))
        out = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
            [unreal.AssetRegistryHelpers.create_asset_data(c) for c in clips],
            src, mesh, rt, search="", replace="", prefix="", suffix="",
            target_path="%s/%s/Anims" % (base, n), use_source_path=False,
            include_referenced_assets=False, overwrite_existing_files=True)
        log("%s: %d clips retargeted" % (n, len(out)))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    log("done")


main()

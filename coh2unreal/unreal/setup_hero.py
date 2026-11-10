"""Imports a rigged Meshy hero and makes it animatable with the UE mannequin set.

Run in the Unreal editor:
    py "<repo>/coh2unreal/unreal/setup_hero.py" <character.fbx> <Name>

1. Imports the skeletal mesh (own skeleton) into /Game/Characters/<Name>
   and builds its material from Meshy's colour/normal/metallic/roughness maps.
2. IK Rigs for it and for the mannequin (auto-generated retarget chains and
   full-body IK), and an IK Retargeter mannequin -> hero.
3. Duplicates and retargets ABP_Unarmed (idle/walk/run blend, jump, fall,
   land, dash, wall jump, punches) and all its animations onto the hero.
4. Writes attach_points.json: CoH's FX attach points (WepR, Chest, Head, ...)
   mapped to this skeleton's bones, so power effects find the same body
   places on every character.
"""
import os
import sys

import unreal

el = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MANNY = "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple"
ABP = "/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed"

# CoH FX attach point -> (bone, offset cm in bone space)
SOCKETS = {
    "WepR": ("RightHand", (8, 0, 0)), "WepL": ("LeftHand", (8, 0, 0)),
    "HandR": ("RightHand", (0, 0, 0)), "HandL": ("LeftHand", (0, 0, 0)),
    "Chest": ("Spine", (0, 0, 0)), "Head": ("Head", (0, 0, 0)),
    "Hips": ("Hips", (0, 0, 0)), "Origin": ("Hips", (0, 0, 0)),
    "Eyes": ("headfront", (0, 0, 0)), "EyeAnchor": ("headfront", (0, 0, 0)),
    "Hair": ("head_end", (0, 0, 0)), "Back": ("Spine", (0, -15, 0)),
    "UArmL": ("LeftArm", (0, 0, 0)), "UArmR": ("RightArm", (0, 0, 0)),
    "LArmL": ("LeftForeArm", (0, 0, 0)), "LArmR": ("RightForeArm", (0, 0, 0)),
    "ULegL": ("LeftUpLeg", (0, 0, 0)), "ULegR": ("RightUpLeg", (0, 0, 0)),
    "LLegL": ("LeftLeg", (0, 0, 0)), "LLegR": ("RightLeg", (0, 0, 0)),
    "FootL": ("LeftFoot", (0, 0, 0)), "FootR": ("RightFoot", (0, 0, 0)),
}


def log(msg):
    unreal.log("[CoH hero] " + msg)


def import_mesh(fbx, dest):
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", fbx)
    t.set_editor_property("destination_path", dest)
    for k in ("automated", "replace_existing", "save"):
        t.set_editor_property(k, True)
    tools.import_asset_tasks([t])
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    found = [d.get_asset() for d in reg.get_assets_by_path(dest, True)
             if str(d.asset_class_path.asset_name) == "SkeletalMesh"]
    if not found:
        raise RuntimeError("no skeletal mesh imported from " + fbx)
    return found[0]


def import_texture(path, dest, name, srgb=True, normal=False):
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", path)
    t.set_editor_property("destination_path", dest)
    t.set_editor_property("destination_name", name)
    for k in ("automated", "replace_existing", "save"):
        t.set_editor_property(k, True)
    tools.import_asset_tasks([t])
    tex = unreal.load_asset("%s/%s" % (dest, name))
    tex.set_editor_property("srgb", srgb)
    if normal:
        tex.set_editor_property("compression_settings",
                                unreal.TextureCompressionSettings.TC_NORMALMAP)
    elif not srgb:
        tex.set_editor_property("compression_settings",
                                unreal.TextureCompressionSettings.TC_MASKS)
    el.save_loaded_asset(tex, False)
    return tex


def build_material(dest, name, folder, stem):
    texs = {
        "BaseColor": import_texture(os.path.join(folder, stem + ".png"),
                                    dest, "T_%s_D" % name),
        "Normal": import_texture(os.path.join(folder, stem + "_normal.png"),
                                 dest, "T_%s_N" % name, srgb=False,
                                 normal=True),
        "Metallic": import_texture(
            os.path.join(folder, stem + "_metallic.png"), dest,
            "T_%s_M" % name, srgb=False),
        "Roughness": import_texture(
            os.path.join(folder, stem + "_roughness.png"), dest,
            "T_%s_R" % name, srgb=False),
    }
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
    for i, (k, tex) in enumerate(texs.items()):
        n = mel.create_material_expression(
            m, unreal.MaterialExpressionTextureSample, -400, i * 250)
        n.set_editor_property("texture", tex)
        n.set_editor_property(
            "sampler_type",
            unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if k == "Normal"
            else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if k ==
            "BaseColor" else unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
        mel.connect_material_property(n, "RGB" if k in ("BaseColor",
                                                         "Normal") else "R",
                                      props[k])
    mel.recompile_material(m)
    el.save_loaded_asset(m, False)
    return m


def ik_rig(mesh, path):
    folder, name = path.rsplit("/", 1)
    if el.does_asset_exist(path):
        rig = unreal.load_asset(path)
    else:
        rig = tools.create_asset(name, folder, unreal.IKRigDefinition,
                                 unreal.IKRigDefinitionFactory())
    c = unreal.IKRigController.get_controller(rig)
    c.set_skeletal_mesh(mesh)
    c.apply_auto_generated_retarget_definition()
    try:
        c.apply_auto_fbik()
    except Exception as e:
        unreal.log_warning("[CoH hero] auto FBIK: %s" % e)
    el.save_loaded_asset(rig, False)
    chains = [str(ch.get_editor_property("chain_name"))
              for ch in c.get_retarget_chains()]
    log("IK rig %s: %d chains %s" % (name, len(chains), chains))
    return rig


def retargeter(src_rig, dst_rig, path):
    folder, name = path.rsplit("/", 1)
    if el.does_asset_exist(path):
        rt = unreal.load_asset(path)
    else:
        rt = tools.create_asset(name, folder, unreal.IKRetargeter,
                                unreal.IKRetargetFactory())
    c = unreal.IKRetargeterController.get_controller(rt)
    c.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, src_rig)
    c.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, dst_rig)
    # UE 5.6+: a new retargeter has an empty op stack and transfers no
    # motion; add the default ops (pelvis motion, FK chains, IK, ...)
    if c.get_num_retarget_ops() == 0:
        c.add_default_ops()
    for side, rig in ((unreal.RetargetSourceOrTarget.SOURCE, src_rig),
                      (unreal.RetargetSourceOrTarget.TARGET, dst_rig)):
        try:
            c.assign_ik_rig_to_all_ops(side, rig)
        except Exception as e:
            unreal.log_warning("[CoH hero] assign rig to ops: %s" % e)
    c.auto_map_chains(unreal.AutoMapChainType.FUZZY, True)
    for i in range(c.get_num_retarget_ops()):
        if str(c.get_op_name(i)) in ("Root Motion", "Run IK Rig"):
            c.set_retarget_op_enabled(i, False)
    log("retarget ops: %s" % [str(c.get_op_name(i))
                              for i in range(c.get_num_retarget_ops())])
    # line the hero's A-pose up with the mannequin's before retargeting
    try:
        c.auto_align_all_bones(unreal.RetargetSourceOrTarget.TARGET)
    except Exception as e:
        unreal.log_warning("[CoH hero] auto align: %s" % e)
    el.save_loaded_asset(rt, False)
    return rt


def write_attach_points(mesh, folder):
    """CoH FX attach point -> bone + offset, next to the character's source
    (sockets can't be named from Python; the FX player reads this map)."""
    import json
    out = {"mesh": mesh.get_path_name(),
           "points": {k: {"bone": b, "offset": list(o)}
                      for k, (b, o) in SOCKETS.items()}}
    path = os.path.join(folder, "attach_points.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    log("attach points: %d CoH FX points -> %s" % (len(SOCKETS), path))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    fbx, name = args[0], args[1]
    folder = os.path.dirname(fbx)
    stems = [f[:-4] for f in os.listdir(folder)
             if f.endswith("_texture_0.png")]
    dest = "/Game/Characters/" + name
    mesh = import_mesh(fbx, dest)
    if stems:
        mat = build_material(dest, name, folder, stems[0])
        mats = mesh.get_editor_property("materials")
        for i, sm in enumerate(mats):
            sm.set_editor_property("material_interface", mat)
            mats[i] = sm
        mesh.set_editor_property("materials", mats)
        el.save_loaded_asset(mesh, False)
    b = mesh.get_bounds()
    log("mesh %s height %.0f cm" % (mesh.get_name(), b.box_extent.z * 2))
    manny = unreal.load_asset(MANNY)
    src = ik_rig(manny, "/Game/Characters/Retarget/IK_Manny")
    dst = ik_rig(mesh, "%s/IK_%s" % (dest, name))
    rt = retargeter(src, dst, "%s/RTG_Manny_to_%s" % (dest, name))
    write_attach_points(mesh, folder)
    abp = unreal.load_asset(ABP)
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    anims = [d for d in reg.get_assets_by_path(
        "/Game/Characters/Mannequins/Anims/Unarmed", True)
        if str(d.asset_class_path.asset_name) in (
            "AnimSequence", "BlendSpace", "AnimMontage", "AnimBlueprint")]
    out = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
        anims, manny, mesh, rt, search="", replace="", prefix="",
        suffix="_" + name, target_path=dest + "/Anims",
        use_source_path=False, include_referenced_assets=True,
        overwrite_existing_files=True)
    log("retargeted %d animation assets (ABP_Unarmed set) onto %s" % (
        len(out), name))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


main()

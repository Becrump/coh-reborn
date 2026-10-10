"""Retargets the Meshy Hellion clips onto an assembled MetaHuman.

Run in the Unreal editor (not during Play):
    py "<repo>/coh2unreal/unreal/setup_metahuman_anims.py" [<MetaHuman name>] [<actor label>]

defaults: MH_Hellion_Biker, HellionCompare_MetaHuman

Source: the hellion_biker clips and IK rig made by setup_enemies.py.
Target: a copy of Epic's IK_MH_IKRig (metahuman_base_skel) with leg chains
split to match the Meshy rig; chains map by exact name, and the finger and
root chains (no Meshy equivalent) stay unmapped. The Meshy rig
binds in a T-pose and MetaHumans in an A-pose, so the retargeter's target
pose is auto-aligned to the source before the batch. FK only, as for the
Meshy variants (root motion / IK ops off).
The clips land in /Game/Characters/MetaHumans/Unpacked/<name>/Anims, and the
level actor's body plays the idle so the face, outfit and grooms follow.
"""
import sys

import unreal

el = unreal.EditorAssetLibrary
reg = unreal.AssetRegistryHelpers.get_asset_registry()
tools = unreal.AssetToolsHelpers.get_asset_tools()

SRC = "/Game/Characters/Enemies/Hellions/hellion_biker"
MH_RIG = "/MetaHumanCharacter/Animation/Retargeting/IK_MH_IKRig"
IDLE = "Idle_3"


def log(msg):
    unreal.log("[CoH MH anims] " + msg)


def assets(path, cls):
    return [d.get_asset() for d in reg.get_assets_by_path(path, True)
            if str(d.asset_class_path.asset_name) == cls]


def mh_rig(path):
    """Project copy of Epic's MetaHuman IK rig, with the leg chains split
    like the Meshy rig's (thigh..foot + a ball chain). Epic's leg chain runs
    thigh..ball, which against the Meshy UpLeg..Foot chain bends the toes
    into the ground."""
    if not el.does_asset_exist(path):
        el.duplicate_asset(MH_RIG, path)
    rig = unreal.load_asset(path)
    c = unreal.IKRigController.get_controller(rig)
    names = [str(ch.get_editor_property("chain_name"))
             for ch in c.get_retarget_chains()]
    for side in ("l", "r"):
        leg = "LeftLeg" if side == "l" else "RightLeg"
        foot = "LeftFoot" if side == "l" else "RightFoot"
        c.set_retarget_chain_end_bone(leg, "foot_" + side)
        if foot not in names:
            c.add_retarget_chain(foot, "ball_" + side, "ball_" + side, "None")
    el.save_loaded_asset(rig, False)
    return rig


# Meshy rigs have no finger or root chains: those MetaHuman chains stay
# unmapped (rest pose) instead of whatever a fuzzy name match picks
MAPPED = ("Spine", "Neck", "Head", "LeftClavicle", "LeftArm", "RightClavicle",
          "RightArm", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot")


def retargeter(src_rig, dst_rig, path):
    folder, name = path.rsplit("/", 1)
    rt = unreal.load_asset(path) if el.does_asset_exist(path) else \
        tools.create_asset(name, folder, unreal.IKRetargeter,
                           unreal.IKRetargetFactory())
    c = unreal.IKRetargeterController.get_controller(rt)
    c.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, src_rig)
    c.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, dst_rig)
    if c.get_num_retarget_ops() == 0:
        c.add_default_ops()
    for side, rig in ((unreal.RetargetSourceOrTarget.SOURCE, src_rig),
                      (unreal.RetargetSourceOrTarget.TARGET, dst_rig)):
        try:
            c.assign_ik_rig_to_all_ops(side, rig)
        except Exception:
            pass
    c.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    for ch in unreal.IKRigController.get_controller(dst_rig).get_retarget_chains():
        n = str(ch.get_editor_property("chain_name"))
        c.set_source_chain(n if n in MAPPED else "None", n)
    log("chains: %s" % ", ".join(
        "%s<-%s" % (n, c.get_source_chain(n)) for n in MAPPED))
    for i in range(c.get_num_retarget_ops()):
        if str(c.get_op_name(i)) in ("Root Motion", "Run IK Rig"):
            c.set_retarget_op_enabled(i, False)
    # A-pose MetaHuman -> match the Meshy T-pose
    try:
        c.auto_align_all_bones(unreal.RetargetSourceOrTarget.TARGET)
    except Exception as e:
        log("auto-align skipped: %s" % e)
    el.save_loaded_asset(rt, False)
    return rt


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    name = args[0] if args else "MH_Hellion_Biker"
    label = args[1] if len(args) > 1 else "HellionCompare_MetaHuman"
    base = "/Game/Characters/MetaHumans/Unpacked/" + name
    body = unreal.load_asset("%s/Body/SKM_%s_BodyMesh" % (base, name))
    src_mesh = assets(SRC, "SkeletalMesh")[0]
    src_rig = unreal.load_asset(SRC + "/IK_hellion_biker")
    rt = retargeter(src_rig, mh_rig("%s/IK_%s" % (base, name)),
                    "%s/RTG_hellion_to_%s" % (base, name))
    clips = assets(SRC + "/Anims", "AnimSequence")
    out = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
        [unreal.AssetRegistryHelpers.create_asset_data(c) for c in clips],
        src_mesh, body, rt, search="", replace="", prefix="", suffix="",
        target_path=base + "/Anims", use_source_path=False,
        include_referenced_assets=False, overwrite_existing_files=True)
    log("%d clips retargeted onto %s" % (len(out), name))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)

    idle = unreal.load_asset("%s/Anims/%s" % (base, IDLE))
    es = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in es.get_all_level_actors():
        if a.get_actor_label() != label:
            continue
        a.modify()
        for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
            if c.get_name() == "Body" and idle:
                c.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
                c.set_editor_property("animation_data", unreal.SingleAnimationPlayData(
                    anim_to_play=idle, saved_looping=True, saved_playing=True))
                log("%s plays %s" % (label, IDLE))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    log("done")


main()

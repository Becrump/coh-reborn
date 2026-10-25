"""Editor step: the Meshy climbing clips onto the CoH hero bodies (male, fem, huge).

    python unreal/scripts/ue_exec.py - < tools/anim/climb_clips_unreal.py       (editor open, no Play)

Globals (set before running, all optional):
    CLIMB_STEP   'import' (clips onto the Hellion biker's skeleton), 'rigs' (IK rigs of the CoH bodies,
                 reports their chains), 'retarget' (clips onto each body), 'all' (default)
    CLIMB_DIR    folder of per-clip glTF from tools/anim/export_climb_clips.py

Result: /Game/CoH/Player/Anims/<body>/<body>__<clip>, the naming of the power moves, for every clip.
"""
import os

import unreal

el = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
reg = unreal.AssetRegistryHelpers.get_asset_registry()
step = globals().get("CLIMB_STEP", "all")
CLIPS = globals().get("CLIMB_DIR", r"C:\Users\rtcru\CoHReborn\characters\climb_set\clips")

BIKER = "/Game/Characters/Enemies/Hellions/hellion_biker/hellion_biker/SkeletalMeshes/hellion_biker"
BIKER_ANIMS = "/Game/Characters/Enemies/Hellions/hellion_biker/Anims"
VALOR = "/Game/Characters/CaptainValor/CaptainValor_ue/SkeletalMeshes/CaptainValor_ue"
VALOR_CLIPS = ["climbing_up_wall", "climbing_down_wall", "Climb_Left_with_Both_Limbs", "Climb_Right_with_Both_Limbs"]
BODIES = {"male": "/Game/CoH/Player/Presets/male/Model_Positron/Model_Positron_ue",
          "fem": "/Game/CoH/Player/Presets/fem/Model_MsLiberty/Model_MsLiberty_ue",
          "huge": "/Game/CoH/Player/Presets/huge/Model_Back_Alley_Brawler/Model_Back_Alley_Brawler_ue"}
RIGS = "/Game/CoH/Player/Retarget"
CLIP_NAMES = {"Climb_Up_Rope", "Fast_Ladder_Climb", "Grab_Wall_Midair_Idle", "Hang_and_Climb_Left", "Hang_and_Climb_Rght", "Jump_and_Grab_Wall",
              "Ladder_Climb_Finish", "Ladder_Climb_Loop", "Ladder_Mount_Start", "Slow_Ladder_Climb", "Wall_Support_to_Step_Down", "diagonal_wall_run"}


def log(msg):
    unreal.log("[CoH climb] " + msg)


def assets(path, cls):
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", cls)], package_paths=[path], recursive_paths=True)
    return reg.get_assets(flt)


def import_clip(glb, skeleton, dest):
    pipe = unreal.InterchangeGenericAssetsPipeline()
    common = pipe.get_editor_property("common_skeletal_meshes_and_animations_properties")
    common.set_editor_property("import_only_animations", True)
    common.set_editor_property("skeleton", skeleton)
    pipe.get_editor_property("animation_pipeline").set_editor_property("import_animations", True)
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    params.set_editor_property("replace_existing", True)
    params.set_editor_property("override_pipelines", [unreal.SoftObjectPath(pipe.get_path_name())])
    unreal.InterchangeManager.get_interchange_manager_scripted().import_asset(dest, unreal.InterchangeManager.create_source_data(glb), params)
    reg.scan_paths_synchronous([dest], True)


def do_import():
    mesh = el.load_asset(BIKER)
    skel = mesh.get_editor_property("skeleton")
    for f in sorted(os.listdir(CLIPS)):
        if f.endswith(".glb") and not el.does_asset_exist("%s/%s/%s" % (BIKER_ANIMS, f[:-4], f[:-4])):
            import_clip(os.path.join(CLIPS, f), skel, "%s/%s" % (BIKER_ANIMS, f[:-4]))
    clips = [a for a in assets(BIKER_ANIMS, "AnimSequence")]
    log("clips on the biker skeleton: %s" % sorted(str(a.asset_name) for a in clips))


# the CoH skeleton (HIPS > WAIST > CHEST > NECK > HEAD, COL_x > UARMx > LARMx > HANDx, ULEGx > LLEGx > FOOTx > TOEx)
# the same chain names as the Meshy rigs, so the retargeter pairs them
COH_CHAINS = {"Spine": ("WAIST", "CHEST"), "Neck": ("NECK", "NECK"), "Head": ("HEAD", "HEAD"),
              "LeftClavicle": ("COL_L", "COL_L"), "LeftArm": ("UARML", "HANDL"), "RightClavicle": ("COL_R", "COL_R"), "RightArm": ("UARMR", "HANDR"),
              "LeftLeg": ("ULEGL", "FOOTL"), "LeftFoot": ("TOEL", "TOEL"), "RightLeg": ("ULEGR", "FOOTR"), "RightFoot": ("TOER", "TOER")}


def ik_rig(mesh, path, chains=None):
    folder, name = path.rsplit("/", 1)
    rig = el.load_asset(path) if el.does_asset_exist(path) else tools.create_asset(name, folder, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
    c = unreal.IKRigController.get_controller(rig)
    c.set_skeletal_mesh(mesh)
    if chains:
        # our own chains: drop whatever the auto detection made, then set the root and the chains
        for ch in list(c.get_retarget_chains()):
            c.remove_retarget_chain(ch.get_editor_property("chain_name"))
        c.set_retarget_root("HIPS")
        for chain, (start, end) in chains.items():
            c.add_retarget_chain(chain, start, end, "None")
    else:
        c.apply_auto_generated_retarget_definition()
    el.save_loaded_asset(rig, False)
    return rig


def describe(rig):
    c = unreal.IKRigController.get_controller(rig)
    out = {}
    for ch in c.get_retarget_chains():
        n = ch.get_editor_property("chain_name")
        out[str(n)] = "%s -> %s" % (c.get_retarget_chain_start_bone(n), c.get_retarget_chain_end_bone(n))
    return out, str(c.get_retarget_root())


def body_rig(body):
    return ik_rig(el.load_asset(BODIES[body]), "%s/IK_%s" % (RIGS, body), COH_CHAINS)


def do_rigs():
    for body in BODIES:
        chains, root = describe(body_rig(body))
        log("%s: root %s, chains %s" % (body, root, chains))


def retargeter(src, dst, path):
    folder, name = path.rsplit("/", 1)
    rt = el.load_asset(path) if el.does_asset_exist(path) else tools.create_asset(name, folder, unreal.IKRetargeter, unreal.IKRetargetFactory())
    c = unreal.IKRetargeterController.get_controller(rt)
    c.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, src)
    c.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, dst)
    if c.get_num_retarget_ops() == 0:
        c.add_default_ops()
    for side, rig in ((unreal.RetargetSourceOrTarget.SOURCE, src), (unreal.RetargetSourceOrTarget.TARGET, dst)):
        try:
            c.assign_ik_rig_to_all_ops(side, rig)
        except Exception:
            pass
    c.auto_map_chains(unreal.AutoMapChainType.FUZZY, True)
    for i in range(c.get_num_retarget_ops()):
        if str(c.get_op_name(i)) in ("Root Motion", "Run IK Rig"):
            c.set_retarget_op_enabled(i, False)      # FK only: these break the Meshy rigs
    el.save_loaded_asset(rt, False)
    return rt


def do_retarget():
    sources = [("biker", el.load_asset(BIKER), el.load_asset("/Game/Characters/Enemies/Hellions/hellion_biker/IK_hellion_biker"),
                [str(a.asset_name) for a in assets(BIKER_ANIMS, "AnimSequence")
                 if str(a.asset_name) in CLIP_NAMES], BIKER_ANIMS),
               ("valor", el.load_asset(VALOR), el.load_asset("/Game/Characters/CaptainValor/IK_CaptainValor"), VALOR_CLIPS, "/Game/Characters/CaptainValor/Meshy")]
    for body in BODIES:
        dst_mesh, dst_rig = el.load_asset(BODIES[body]), body_rig(body)
        dest = "/Game/CoH/Player/Anims/" + body
        for tag, src_mesh, src_rig, names, root in sources:
            rt = retargeter(src_rig, dst_rig, "%s/RTG_%s_to_%s" % (RIGS, tag, body))
            todo = []
            for n in names:
                p = "%s/%s/%s" % (root, n, n) if tag == "valor" else "%s/%s/%s" % (root, n, n)
                if not el.does_asset_exist(p):
                    p = "%s/%s" % (root, n)
                if el.does_asset_exist(p) and not el.does_asset_exist("%s/%s__%s" % (dest, body, n)):
                    todo.append(unreal.AssetRegistryHelpers.create_asset_data(el.load_asset(p)))
            if todo:
                out = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
                    todo, src_mesh, dst_mesh, rt, search="", replace="", prefix=body + "__", suffix="", target_path=dest,
                    use_source_path=False, include_referenced_assets=False, overwrite_existing_files=True)
                log("%s from %s: %d clips" % (body, tag, len(out)))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


if step in ("import", "all"):
    do_import()
if step in ("rigs", "all"):
    do_rigs()
if step in ("retarget", "all"):
    do_retarget()

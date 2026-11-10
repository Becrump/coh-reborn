"""Editor step: bring an animation pack onto the hero (UE mannequin skeleton).

    (echo "import os; os.environ['PACK_SRC']='/Game/GameAnimationSample'; os.environ['PACK_NAME']='GASP'"; \
     cat tools/anim/retarget_pack.py) | python unreal/scripts/ue_exec.py -

PACK_SRC   content folder with the pack's animation sequences (searched recursively)
PACK_NAME  short name; retargeted copies go to /Game/AnimBench/<PACK_NAME>
PACK_MESH  (optional) a skeletal mesh of the pack's skeleton; found from the
           first clip's skeleton when left out

Clips already on the mannequin skeleton (SK_Mannequin, e.g. Epic's Game
Animation Sample and most UE5 packs) need no retarget: they show up in the
animation test bench (F8) as they are, and the script only lists them.
For any other skeleton it makes an IK Rig for the pack (auto-generated
retarget chains and full-body IK), an IK Retargeter to IK_Manny, and
duplicates and retargets every clip. Then open the test bench in Play mode.
"""
import os

import unreal

el = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
SRC = os.environ["PACK_SRC"]
NAME = os.environ.get("PACK_NAME", SRC.rstrip("/").split("/")[-1])
DEST = "/Game/AnimBench/" + NAME
MANNY = el.load_asset("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple")
MANNY_SKEL = MANNY.get_editor_property("skeleton")

clips = []
for path in el.list_assets(SRC, recursive=True):
    a = el.find_asset_data(path)
    if a.asset_class_path.asset_name == "AnimSequence":
        clips.append(a)
print("pack", NAME, "clips", len(clips))
if not clips:
    raise SystemExit

first = clips[0].get_asset()
skel = first.get_editor_property("skeleton")
if skel == MANNY_SKEL:
    names = sorted(str(c.asset_name) for c in clips)
    print("already on the mannequin skeleton: no retarget needed;", len(names), "clips appear in the test bench")
    for word in ("attack", "punch", "kick", "taunt", "emote", "idle", "dance", "wave", "cheer", "throw", "cast"):
        hits = [n for n in names if word in n.lower()]
        print("  %-7s %3d  %s" % (word, len(hits), ", ".join(hits[:8])))
    raise SystemExit

# source mesh for the pack skeleton
mesh_path = os.environ.get("PACK_MESH")
src_mesh = el.load_asset(mesh_path) if mesh_path else None
if not src_mesh:
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    for m in reg.get_assets_by_class(unreal.TopLevelAssetPath("/Script/Engine", "SkeletalMesh"), True):
        mesh = m.get_asset()
        if mesh and mesh.get_editor_property("skeleton") == skel:
            src_mesh = mesh
            break
assert src_mesh, "no skeletal mesh found for the pack skeleton; set PACK_MESH"

# IK rig for the pack skeleton (auto chains + full body IK)
RIG = DEST + "/IK_" + NAME
if not el.does_asset_exist(RIG):
    rig = tools.create_asset("IK_" + NAME, DEST, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
    rc = unreal.IKRigController.get_controller(rig)
    rc.set_skeletal_mesh(src_mesh)
    rc.apply_auto_generated_retarget_definition()
    rc.apply_auto_fbik()
    el.save_loaded_asset(rig)
rig = el.load_asset(RIG)

RTG = DEST + "/RTG_" + NAME + "_to_Manny"
if not el.does_asset_exist(RTG):
    rtg = tools.create_asset("RTG_" + NAME + "_to_Manny", DEST, unreal.IKRetargeter, unreal.IKRetargetFactory())
    ctrl = unreal.IKRetargeterController.get_controller(rtg)
    ctrl.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, rig)
    ctrl.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, el.load_asset("/Game/Characters/Retarget/IK_Manny"))
    ctrl.auto_map_chains(unreal.AutoMapChainType.FUZZY, True)
    el.save_loaded_asset(rtg)
rtg = el.load_asset(RTG)

done = 0
for i in range(0, len(clips), 50):            # in batches: the editor runs out of memory on big packs
    out = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
        clips[i:i + 50], src_mesh, MANNY, rtg, suffix="_Manny", target_path=DEST,
        use_source_path=False, include_referenced_assets=False, overwrite_existing_files=True)
    done += len([a for a in out if str(a.asset_class_path.asset_name) == "AnimSequence"])
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(False, True)
    unreal.SystemLibrary.collect_garbage()
print("retargeted", done, "clips to", DEST)

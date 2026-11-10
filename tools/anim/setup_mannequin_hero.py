"""Editor step: the test hero becomes the UE mannequin (Manny).

    python unreal/scripts/ue_exec.py - < tools/anim/setup_mannequin_hero.py

1. Adds the power emitter sockets to the mannequin skeleton (SK_Mannequin):
   emit_eyes, emit_mouth, emit_chest, emit_hand_l, emit_hand_r,
   emit_palm_l, emit_palm_r, emit_palms, emit_back, emit_feet,
   emit_overhead. Offsets are measured on a posed preview of SKM_Manny so
   each point sits where it should in the world (forward = the way the
   mannequin faces), whatever the bone axes are.
2. Retargets the climbing clips (made on the Captain Valor rig) to Manny
   through a new IK Retargeter RTG_CaptainValor_to_Manny, into
   /Game/CoH/Hero/Anims/Climb.
The hero's mesh, anim blueprint and clips are set in Config/DefaultGame.ini
([/Script/COHREBORN.CoHHeroCharacter]); the Captain Valor assets stay as
they were, only unused.
"""
import unreal

el = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

MANNY = el.load_asset("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple")
skeleton = MANNY.get_editor_property("skeleton")

# ------------------------------------------------------------- 1. sockets
# (socket, bone, offset in cm: x right, y forward, z up, for an unrotated mannequin facing +Y)
SOCKETS = [
    ("emit_eyes", "head", (0, 12, 8)),
    ("emit_mouth", "head", (0, 12, -3)),
    ("emit_chest", "spine_05", (0, 16, 0)),
    ("emit_back", "spine_05", (0, -20, 0)),
    ("emit_hand_l", "hand_l", (0, 0, 0)),
    ("emit_hand_r", "hand_r", (0, 0, 0)),
    ("emit_palm_l", "middle_metacarpal_l", (0, 0, 0)),
    ("emit_palm_r", "middle_metacarpal_r", (0, 0, 0)),
    ("emit_palms", "spine_05", (0, 45, -10)),
    ("emit_feet", "root", (0, 35, 3)),
    ("emit_overhead", "head", (0, 0, 38)),
]
for a in actors.get_all_level_actors():          # leftovers of an interrupted run
    if isinstance(a, unreal.SkeletalMeshActor) and a.get_actor_location().z > 90000:
        actors.destroy_actor(a)
probe = actors.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 100000))
comp = probe.skeletal_mesh_component
comp.set_skinned_asset_and_update(MANNY) if hasattr(comp, "set_skinned_asset_and_update") else comp.set_skeletal_mesh(MANNY)
probe.set_actor_rotation(unreal.Rotator(0, 0, 0), False)
existing = {n for n, _, _ in SOCKETS if MANNY.find_socket(n)}
made = 0
for name, bone, (dx, dy, dz) in SOCKETS:
    bone_world = comp.get_socket_transform(bone, unreal.RelativeTransformSpace.RTS_WORLD)
    want = bone_world.translation + unreal.Vector(dx, dy, dz)
    local = bone_world.inverse_transform_location(want)
    if not unreal.CoHHeroCharacter.add_skeleton_socket(skeleton, name, bone, local):
        print("could not add", name, "to", bone)
    elif name not in existing:
        made += 1
actors.destroy_actor(probe)
el.save_loaded_asset(MANNY)
el.save_loaded_asset(skeleton)
print("sockets added", made, "of", len(SOCKETS))

# ------------------------------------------------------------- 2. climb clips
SRC = ["/Game/Characters/CaptainValor/Meshy/climbing_up_wall/climbing_up_wall",
       "/Game/Characters/CaptainValor/Meshy/climbing_down_wall/climbing_down_wall",
       "/Game/Characters/CaptainValor/Meshy/Climb_Left_with_Both_Limbs/Climb_Left_with_Both_Limbs",
       "/Game/Characters/CaptainValor/Meshy/Climb_Right_with_Both_Limbs/Climb_Right_with_Both_Limbs"]
DEST = "/Game/CoH/Hero/Anims/Climb"
RTG = "/Game/CoH/Hero/Retarget/RTG_CaptainValor_to_Manny"
if not el.does_asset_exist(RTG):
    rtg = tools.create_asset("RTG_CaptainValor_to_Manny", "/Game/CoH/Hero/Retarget", unreal.IKRetargeter, unreal.IKRetargetFactory())
    ctrl = unreal.IKRetargeterController.get_controller(rtg)
    ctrl.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, el.load_asset("/Game/Characters/CaptainValor/IK_CaptainValor"))
    ctrl.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, el.load_asset("/Game/Characters/Retarget/IK_Manny"))
    ctrl.auto_map_chains(unreal.AutoMapChainType.FUZZY, True)
    el.save_loaded_asset(rtg)
rtg = el.load_asset(RTG)
src_mesh = el.load_asset("/Game/Characters/CaptainValor/CaptainValor_ue/SkeletalMeshes/CaptainValor_ue")
clips = [el.load_asset(p) for p in SRC if el.does_asset_exist(p)]
todo = [c for c in clips if not el.does_asset_exist(DEST + "/" + c.get_name())]
if todo:
    unreal.IKRetargetBatchOperation.duplicate_and_retarget(
        [el.find_asset_data(c.get_path_name().split(".")[0]) for c in todo], src_mesh, MANNY, rtg,
        target_path=DEST, use_source_path=False, include_referenced_assets=False, overwrite_existing_files=True)
unreal.EditorLoadingAndSavingUtils.save_dirty_packages(False, True)
print("climb clips on Manny:", [n for n in el.list_assets(DEST, recursive=False)])

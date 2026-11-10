"""Exports a Meshy merged-animations FBX as one glTF per clip (run with Blender).

    blender -b --factory-startup -P export_anims.py -- <merged.fbx> <out folder>

Each action becomes <out>/<clip>.glb (armature + skin + that one animation),
in metres like the character glb from fix_rig_scale.py, so Unreal can import
the clips onto the character's existing skeleton.
"""
import os
import re
import sys

import bpy

src, out = sys.argv[sys.argv.index("--") + 1:][:2]
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=src, automatic_bone_orientation=False)
arm = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
actions = list(bpy.data.actions)

# Meshy's animation export uses Mixamo bone names; its character export uses
# its own. Rename to the character's names so the clips land on its skeleton.
MIXAMO_TO_MESHY = {"Spine": "Spine02", "Spine1": "Spine01", "Spine2": "Spine",
                   "Neck": "neck", "HeadTop_End": "head_end",
                   "LeftHandMiddle4": "LeftHand_End",
                   "RightHandMiddle4": "RightHand_End",
                   "LeftToe_End": "LeftToe_end", "RightToe_End": "RightToe_end"}
renamed = {}
for b in arm.data.bones:
    if b.name.startswith("mixamorig:"):
        short = b.name[len("mixamorig:"):]
        renamed[b.name] = MIXAMO_TO_MESHY.get(short, short)
for old, new in renamed.items():
    arm.data.bones[old].name = new          # updates groups and anim paths


def fcurves(act):
    if hasattr(act, "fcurves") and act.fcurves:
        return act.fcurves
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


# keep bone translation only on the hips: the rigs' rest offsets differ a
# little and would otherwise shift the spine
for act in actions:
    for fc in list(fcurves(act)):
        p = fc.data_path
        for old, new in renamed.items():
            p = p.replace('"%s"' % old, '"%s"' % new)
        if p != fc.data_path:
            fc.data_path = p
        if p.startswith('pose.bones["') and p.endswith(".location")                 and not p.startswith('pose.bones["Hips"]'):
            for kp in fc.keyframe_points:
                kp.co[1] = 0.0
                kp.handle_left[1] = kp.handle_right[1] = 0.0
print("renamed bones:", len(renamed))

# climbing clips travel up/down/sideways inside the animation; the game
# moves the character itself, so remove the hips' net drift over each loop
for act in actions:
    if "climb" not in act.name.lower():
        continue
    for fc in fcurves(act):
        if fc.data_path != 'pose.bones["Hips"].location' or                 len(fc.keyframe_points) < 2:
            continue
        k = fc.keyframe_points
        t0, t1 = k[0].co[0], k[-1].co[0]
        v0, v1 = k[0].co[1], k[-1].co[1]
        for kp in k:
            d = (v1 - v0) * (kp.co[0] - t0) / max(t1 - t0, 1e-6)
            kp.co[1] -= d
            kp.handle_left[1] -= d
            kp.handle_right[1] -= d
scene = bpy.context.scene
# climbing clips: same average hanging height (hips) for all of them, so
# switching direction on the wall doesn't make the body jump
CLIMB_HIPS_M = 0.94
for act in actions:
    if "climb" not in act.name.lower():
        continue
    arm.animation_data_create()
    arm.animation_data.action = act
    s, e = (int(v) for v in act.frame_range)
    hb = arm.pose.bones["Hips"]
    zs = []
    for f in range(s, e + 1):
        bpy.context.scene.frame_set(f)
        zs.append((arm.matrix_world @ hb.head).z)
    dz = CLIMB_HIPS_M - sum(zs) / len(zs)
    # world up -> the hips bone's local location axes
    rest = (arm.matrix_world @ hb.bone.matrix_local).to_3x3().inverted()
    from mathutils import Vector
    dl = rest @ Vector((0, 0, dz))
    for fc in fcurves(act):
        if fc.data_path == 'pose.bones["Hips"].location':
            for kp in fc.keyframe_points:
                kp.co[1] += dl[fc.array_index]
                kp.handle_left[1] += dl[fc.array_index]
                kp.handle_right[1] += dl[fc.array_index]
    print("climb", act.name, "hips shift (m)", round(dz, 3))

for act in actions:
    name = re.sub(r"[^A-Za-z0-9_]", "_", act.name.split("|")[-1])
    arm.animation_data_create()
    arm.animation_data.action = act
    s, e = (int(v) for v in act.frame_range)
    scene.frame_start, scene.frame_end = s, e
    bpy.ops.object.select_all(action="DESELECT")
    for o in [arm] + meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(
        filepath=os.path.join(out, name + ".glb"), export_format="GLB",
        use_selection=True, export_yup=True, export_skins=True,
        export_animations=True, export_animation_mode="ACTIVE_ACTIONS",
        export_force_sampling=True, export_def_bones=True,
        export_frame_range=True)
    print("clip", name, s, e)

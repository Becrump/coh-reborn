"""Meshy climbing clips (one FBX per action, tools/meshy_anims.py) -> one glTF per clip for Unreal.

    blender -b --factory-startup -P export_climb_clips.py -- <in folder with the .fbx files> <out folder>

Like coh2unreal/unreal/export_anims.py (the clip lands on the character's skeleton in metres), but
each file is named after its source and the climb fixes depend on what the clip is:
  LOOP    a climb that travels inside the clip: the hips' net drift over the loop is removed (the game
          moves the character) and the average hang height is the same as every other climb
  STATIC  a hold (the wall idle): same hang height only
  ONESHOT mount, finish, step down: left as the animator made them
"""
import os
import sys

import bpy
from mathutils import Vector

src, out = sys.argv[sys.argv.index("--") + 1:][:2]
os.makedirs(out, exist_ok=True)
LOOP = {"Fast_Ladder_Climb", "Slow_Ladder_Climb", "Ladder_Climb_Loop", "Climb_Up_Rope", "Hang_and_Climb_Left", "Hang_and_Climb_Rght", "diagonal_wall_run"}
STATIC = {"Grab_Wall_Midair_Idle"}
HIPS_M = 0.94            # the hang height of the other climb clips (hips, metres)


def fcurves(act):
    if hasattr(act, "fcurves") and act.fcurves:
        return act.fcurves
    res = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                res.extend(bag.fcurves)
    return res


for f in sorted(os.listdir(src)):
    if not f.lower().endswith(".fbx"):
        continue
    name = f[:-4]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=os.path.join(src, f), automatic_bone_orientation=False)
    arm = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    act = list(bpy.data.actions)[0]
    # bone translation only on the hips: the rigs' rest offsets differ a little
    for fc in fcurves(act):
        p = fc.data_path
        if p.startswith('pose.bones["') and p.endswith(".location") and not p.startswith('pose.bones["Hips"]'):
            for kp in fc.keyframe_points:
                kp.co[1] = 0.0
                kp.handle_left[1] = kp.handle_right[1] = 0.0
    if name in LOOP:
        for fc in fcurves(act):
            if fc.data_path != 'pose.bones["Hips"].location' or len(fc.keyframe_points) < 2:
                continue
            k = fc.keyframe_points
            t0, t1 = k[0].co[0], k[-1].co[0]
            v0, v1 = k[0].co[1], k[-1].co[1]
            for kp in k:
                d = (v1 - v0) * (kp.co[0] - t0) / max(t1 - t0, 1e-6)
                kp.co[1] -= d
                kp.handle_left[1] -= d
                kp.handle_right[1] -= d
    arm.animation_data_create()
    arm.animation_data.action = act
    s, e = (int(v) for v in act.frame_range)
    if name in LOOP or name in STATIC:
        hb = arm.pose.bones["Hips"]
        zs = []
        for fr in range(s, e + 1):
            bpy.context.scene.frame_set(fr)
            zs.append((arm.matrix_world @ hb.head).z)
        dz = HIPS_M - sum(zs) / len(zs)
        rest = (arm.matrix_world @ hb.bone.matrix_local).to_3x3().inverted()
        dl = rest @ Vector((0, 0, dz))
        for fc in fcurves(act):
            if fc.data_path == 'pose.bones["Hips"].location':
                for kp in fc.keyframe_points:
                    kp.co[1] += dl[fc.array_index]
                    kp.handle_left[1] += dl[fc.array_index]
                    kp.handle_right[1] += dl[fc.array_index]
        print("hips shift (m)", name, round(dz, 3))
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = s, e
    bpy.ops.object.select_all(action="DESELECT")
    for o in [arm] + meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, name + ".glb"), export_format="GLB", use_selection=True, export_yup=True,
                              export_skins=True, export_animations=True, export_animation_mode="ACTIVE_ACTIONS",
                              export_force_sampling=True, export_def_bones=True, export_frame_range=True)
    print("clip", name, s, e)

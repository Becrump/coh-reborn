"""Assemble a robot / construct from separately exported Tripo parts onto the shared humanoid skeleton (Blender).

    blender -b --factory-startup -P bl_robot_assemble.py -- <rigged_template.glb> <parts.json> <out.glb> [--height 1.82]

Tripo part exports are each normalised to 1 unit, so their original placement is lost. This rebuilds it
from the template skeleton (any charpipe rig; only its bones are used, the body mesh is dropped).
parts.json: {"<file>": "role", ...} with roles
  head, torso (chest + belly), pelvis, arm_l, arm_r, leg_l, leg_r, back (key, pipe, pack: on the back),
  top (dome / antenna: on top of the head)
Placement: each limb's long axis is laid from its root joint (shoulder / hip) to its end joint (wrist / ankle)
and scaled to that length (the thicker end is the root); head / torso / pelvis are scaled to their bone span and
centred on it; back items sit behind the torso, top items on the head.
Rigging: robot parts are rigid. Arms are split along their length into Arm / ForeArm / Hand (40 / 40 / 20 %),
legs into UpLeg / Leg / Foot (45 / 45 / 10 %), with a 3 cm blend at each joint; the rest is 100 % on one bone.
No finger animation (the hands are rigid). Output: armature + one mesh per part, Unreal-ready via bl_export.py.
"""
import json
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
TPL, PJ, OUT = a[0], a[1], a[2]
parts = json.load(open(PJ))
base_dir = os.path.dirname(os.path.abspath(PJ))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=TPL)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere") or o.type == "MESH":
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
W = arm.matrix_world
J = lambda n, tail=False: np.array((W @ (arm.data.bones[n].tail_local if tail else arm.data.bones[n].head_local))[:])  # noqa: E731
LIMB = {"arm_l": ("Left", ["LeftArm", "LeftForeArm", "LeftHand"], (0.4, 0.4, 0.2)),
        "arm_r": ("Right", ["RightArm", "RightForeArm", "RightHand"], (0.4, 0.4, 0.2)),
        "leg_l": ("Left", ["LeftUpLeg", "LeftLeg", "LeftFoot"], (0.45, 0.45, 0.1)),
        "leg_r": ("Right", ["RightUpLeg", "RightLeg", "RightFoot"], (0.45, 0.45, 0.1))}
rep = {}


def imp(path):
    before = set(bpy.data.objects)
    if path.lower().endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    ms = [o for o in new if o.type == "MESH" and not o.name.startswith("Icosphere")]
    for o in new:
        if o not in ms:
            bpy.data.objects.remove(o, do_unlink=True)
    for o in ms:
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw)
        o.matrix_world = Matrix.Identity(4)
    for x in bpy.data.objects:
        if x.name in bpy.context.view_layer.objects:
            x.select_set(False)
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


objs = []
for f, role in parts.items():
    P = imp(f if os.path.isabs(f) else os.path.join(base_dir, f))
    P.name = "%s_%s" % (role, os.path.splitext(os.path.basename(f))[0].replace("#", "").replace(" ", ""))
    co = np.array([v.co[:] for v in P.data.vertices])
    c = co.mean(0)
    if role in LIMB:
        side, bones, frac = LIMB[role]
        root = J(bones[0])
        end = J(bones[2], tail=True) if role.startswith("arm") else J(bones[2])
        U, s, Vt = np.linalg.svd(co - c, full_matrices=False)
        ax = Vt[0]
        t = (co - c) @ ax
        lo_end, hi_end = co[t < np.percentile(t, 12)], co[t > np.percentile(t, 88)]
        r_lo = np.linalg.norm(lo_end - lo_end.mean(0), axis=1).mean()
        r_hi = np.linalg.norm(hi_end - hi_end.mean(0), axis=1).mean()
        if r_hi > r_lo:  # the thicker end is the shoulder / hip
            ax = -ax
            t = -t
        p0 = c + ax * t.min()
        Lp = np.ptp(t)
        Lb = np.linalg.norm(end - root)
        k = Lb / max(Lp, 1e-6)
        d = (end - root) / Lb
        R = Vector(ax).rotation_difference(Vector(d)).to_matrix().to_4x4()
        M = Matrix.Translation(Vector(root)) @ R @ Matrix.Scale(k, 4) @ Matrix.Translation(Vector(-p0))
        P.data.transform(M)
        co2 = np.array([v.co[:] for v in P.data.vertices])
        u = ((co2 - root) @ d) / Lb
        g = [P.vertex_groups.new(name=b) for b in bones]
        c1, c2 = frac[0], frac[0] + frac[1]
        bl = 0.03 / Lb
        for i, ui in enumerate(u):
            w1 = np.clip((ui - (c1 - bl)) / (2 * bl), 0, 1)
            w2 = np.clip((ui - (c2 - bl)) / (2 * bl), 0, 1)
            ws = (1 - w1, w1 * (1 - w2), w2)
            for gi, wv in zip(g, ws):
                if wv > 0.001:
                    gi.add([i], float(wv), "REPLACE")
    else:
        if role == "head":
            z0, z1, bone = J("neck")[2] + 0.01, J("head_end", tail=True)[2] if "head_end" in arm.data.bones else J("Head")[2] + 0.25, "Head"
            ctr = J("Head")
        elif role == "torso":
            no_pelvis = "pelvis" not in parts.values()
            z0 = (J("LeftUpLeg")[2] - 0.04) if no_pelvis else J("Spine02")[2] - 0.02  # torso fills the hips if no pelvis part
            z1, bone = J("neck")[2] + 0.02, "Spine"
            ctr = (J("Spine02") + J("neck")) / 2
        elif role == "pelvis":
            z0, z1, bone = J("LeftUpLeg")[2] - 0.06, J("Spine02")[2], "Hips"
            ctr = J("Hips")
        elif role == "top":
            z0 = (J("head_end", tail=True)[2] if "head_end" in arm.data.bones else J("Head")[2] + 0.25) - 0.04
            z1, bone, ctr = z0 + 0.14, "Head", J("Head")
        else:  # back
            z0, z1, bone = J("Spine01")[2], J("Spine")[2] + 0.1, "Spine"
            ctr = J("Spine")
        lo, hi = co.min(0), co.max(0)
        k = (z1 - z0) / max(hi[2] - lo[2], 1e-6)
        if role == "back":
            k = min(k, 0.45 / max(np.ptp(co, 0)))
        off = np.array([ctr[0], ctr[1], z0]) - np.array([c[0] * k, c[1] * k, lo[2] * k])
        if role == "back":
            off[1] += 0.16  # behind the torso (characters face -Y)
        P.data.transform(Matrix.Translation(Vector(off)) @ Matrix.Scale(k, 4))
        P.vertex_groups.new(name=bone).add(list(range(len(P.data.vertices))), 1.0, "REPLACE")
    P.parent = arm
    P.modifiers.new("Armature", "ARMATURE").object = arm
    objs.append(P)
    rep[P.name] = {"role": role, "scale": round(float(k), 3)}
for x in bpy.data.objects:
    x.select_set(x is arm or x in objs)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
print("ROBOT_OK", json.dumps(rep))

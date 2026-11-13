"""Auto-rig a generated character mesh onto the shared 24-bone skeleton (Blender).

    blender -b --factory-startup -P bl_autorig.py -- <in.glb> <out.glb> [--height 1.8] [--face-plus-y] [--report r.json]

The skeleton uses the Meshy biped bone names (Hips, Spine02, Spine01, Spine, neck, Head,
head_end, headfront, Left/Right Shoulder/Arm/ForeArm/Hand/UpLeg/Leg/Foot/ToeBase), so
rig_cleanup.py and retarget2.py (family "meshy") work unchanged and CoH clips retarget onto it.
Joints are fitted to the mesh: torso joints at fixed height fractions centred on the body's
cross-section, hands at the farthest arm point (T-pose or arms-down), knees/ankles at the leg
cross-section centroids, toes at the most forward foot point. Then Blender automatic (heat)
weights; on failure, envelope weights. The mesh is scaled to --height, grounded and centred
first; generated meshes face -Y (use --face-plus-y if a model comes out backwards).
"""
import json
import math
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
src, dst = args[0], args[1]
H = float(args[args.index("--height") + 1]) if "--height" in args else 1.8
rep_path = args[args.index("--report") + 1] if "--report" in args else None
rep = {"source": src, "height": H}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.type != "MESH" or o.name.startswith("Icosphere"):
        if o.type == "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
for o in list(bpy.data.objects):
    if o.type not in ("MESH",):
        bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.object.select_all(action="DESELECT")
for m in meshes:
    m.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
body = bpy.context.view_layer.objects.active
body.name = "Body"
body.parent = None
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
if "--face-plus-y" in args:
    body.rotation_euler = (0, 0, math.pi)
    bpy.ops.object.transform_apply(rotation=True)


def verts():
    n = len(body.data.vertices)
    a = np.empty(n * 3, np.float32)
    body.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


P = verts()
lo, hi = P.min(0), P.max(0)
k = H / (hi[2] - lo[2])
body.scale = (k, k, k)
bpy.ops.object.transform_apply(scale=True)
P = verts()
lo, hi = P.min(0), P.max(0)
off = Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
body.location = off
bpy.ops.object.transform_apply(location=True)
P = verts()
rep["scale_factor"] = round(float(k), 4)


def slab(z, dz=0.025, side=0, xmax=None, xmin=None):
    m = np.abs(P[:, 2] - z * H) < dz * H
    if side:
        m &= (P[:, 0] * side) > 0
    if xmax is not None:
        m &= np.abs(P[:, 0]) < xmax * H
    if xmin is not None:
        m &= np.abs(P[:, 0]) > xmin * H
    return P[m]


def centre(z, **kw):
    s = slab(z, **kw)
    if len(s) == 0:
        return Vector((0, 0, z * H))
    c = (s.min(0) + s.max(0)) / 2
    return Vector((float(c[0]), float(c[1]), z * H))


J = {}
for name, z in (("hips", .557), ("spine02", .622), ("spine01", .688), ("spine", .741), ("neck", .841), ("head", .865),
                ("head_end", .93)):
    c = centre(z, xmax=.12)
    J[name] = Vector((0.0, c.y, z * H))
J["top"] = Vector((0.0, J["head_end"].y, H))
J["headfront"] = J["head"] + Vector((0, -0.10 * H, 0))
chest = slab(.74, xmax=.2)
half_w = float(np.abs(chest[:, 0]).max()) if len(chest) else 0.1 * H
arm_pose = {}
for s, S in ((1, "Left"), (-1, "Right")):
    root = Vector((s * max(0.085 * H, 0.8 * half_w), J["spine"].y, 0.80 * H))
    clav = Vector((s * 0.025 * H, J["spine"].y, 0.765 * H))
    m = ((P[:, 0] * s) > root.x * s + 0.04 * H) & (P[:, 2] > 0.42 * H)
    arm = P[m]
    if len(arm):
        d = np.linalg.norm(arm - np.array(root), axis=1)
        tip = Vector(arm[int(d.argmax())].tolist())
    else:
        tip = root + Vector((s * 0.39 * H, 0, 0))
    v = tip - root
    arm_pose[S] = "arms-down" if v.normalized().z < -0.6 else "T/A-pose"
    wrist = root + v * 0.80
    elbow = root + v * 0.44 + Vector((0, 0.012 * H, 0))
    J[S + "clav"], J[S + "root"], J[S + "elbow"], J[S + "wrist"], J[S + "tip"] = clav, root, elbow, wrist, tip
    hipj = Vector((s * 0.053 * H, J["hips"].y, 0.507 * H))
    knee = centre(.30, side=s, xmax=.16)
    ankle = centre(.095, side=s, xmax=.16)
    foot = slab(.03, dz=.03, side=s, xmax=.18)
    if len(foot):
        fwd = foot[int(foot[:, 1].argmin())]
        toe = Vector((float(fwd[0]) * 0.6 + ankle.x * 0.4, ankle.y + (float(fwd[1]) - ankle.y) * 0.7, 0.025 * H))
    else:
        toe = ankle + Vector((0, -0.07 * H, -0.07 * H))
    J[S + "hip"], J[S + "knee"], J[S + "ankle"], J[S + "toe"] = hipj, knee, ankle, toe
    J[S + "toe_end"] = toe + Vector((0, -0.035 * H, 0))
rep["arm_pose"] = arm_pose
rep["joints"] = {k_: [round(c, 3) for c in v] for k_, v in J.items()}

arm_data = bpy.data.armatures.new("Armature")
arm = bpy.data.objects.new("Armature", arm_data)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
EB = arm_data.edit_bones


def bone(name, h, t, parent=None, deform=True):
    b = EB.new(name)
    b.head, b.tail = J[h] if isinstance(h, str) else h, J[t] if isinstance(t, str) else t
    if (b.tail - b.head).length < 1e-3:
        b.tail = b.head + Vector((0, 0, 0.02 * H))
    if parent:
        b.parent = EB[parent]
    b.use_deform = deform
    return b


bone("Hips", "hips", "spine02")
bone("Spine02", "spine02", "spine01", "Hips")
bone("Spine01", "spine01", "spine", "Spine02")
bone("Spine", "spine", "neck", "Spine01")
bone("neck", "neck", "head", "Spine")
bone("Head", "head", "head_end", "neck")
bone("head_end", "head_end", "top", "Head", deform=False)
bone("headfront", "headfront", J["headfront"] + Vector((0, -0.03 * H, 0)), "Head", deform=False)
for S in ("Left", "Right"):
    bone(S + "Shoulder", S + "clav", S + "root", "Spine")
    bone(S + "Arm", S + "root", S + "elbow", S + "Shoulder")
    bone(S + "ForeArm", S + "elbow", S + "wrist", S + "Arm")
    bone(S + "Hand", S + "wrist", S + "tip", S + "ForeArm")
    bone(S + "UpLeg", S + "hip", S + "knee", "Hips")
    bone(S + "Leg", S + "knee", S + "ankle", S + "UpLeg")
    bone(S + "Foot", S + "ankle", S + "toe", S + "Leg")
    bone(S + "ToeBase", S + "toe", S + "toe_end", S + "Foot")
bpy.ops.object.mode_set(mode="OBJECT")

bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
rep["weights"] = "heat"
try:
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    if len(body.vertex_groups) < 10:
        raise RuntimeError("heat weighting produced too few groups")
except Exception as e:  # noqa: BLE001
    rep["weights"] = "envelope (heat failed: %s)" % str(e)[:100]
    for md in list(body.modifiers):
        body.modifiers.remove(md)
    body.vertex_groups.clear()
    bpy.ops.object.parent_set(type="ARMATURE_ENVELOPE")
rep["vertex_groups"] = len(body.vertex_groups)
rep["vertices"] = len(body.data.vertices)
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
arm.select_set(True)
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_skins=True,
                          export_animations=False)
print("AUTORIG", json.dumps({k_: v for k_, v in rep.items() if k_ != "joints"}))
if rep_path:
    json.dump(rep, open(rep_path, "w"), indent=1)

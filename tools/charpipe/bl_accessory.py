"""Attach generated props to a rigged character as rigid, bone-bound accessories (Blender).

    blender -b --factory-startup -P bl_accessory.py -- <rigged.glb> <out.glb> <slot>=<prop.glb> [...] [--report r.json]

Slots (sockets on the Meshy-family skeleton; each prop is skinned 100% to ONE bone, so it moves
rigidly, like an Unreal socket attachment):
  head     headwear (cap, bandana, helmet): scaled to the head's width x 1.08 and set on the crown.
  hand_r   one-handed weapon (bat, pipe, chain): long axis along the right hand's grip direction
           (forearm -> hand), 0.85 m long, gripped 12 cm from its end.
  belt     belt item (wallet chain, pouch): 0.22 m, on the right hip, in front of the pelvis.
The props come from charpipe's concept "prop" view + Hunyuan3D, so their long axis is found with a
bounding-box test (the longest side), not trusted from the image.
"""
import json
import sys

import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
body_p, dst = args[0], args[1]
items = dict(a.split("=", 1) for a in args[2:] if "=" in a and not a.startswith("--"))
rep_path = args[args.index("--report") + 1] if "--report" in args else None
rep = {}


def imp(p):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=p)
    for o in [o for o in bpy.data.objects if o not in before and o.name.startswith("Icosphere")]:
        bpy.data.objects.remove(o, do_unlink=True)
    return [o for o in bpy.data.objects if o not in before]


bpy.ops.wm.read_factory_settings(use_empty=True)
bnew = imp(body_p)
arm = next(o for o in bnew if o.type == "ARMATURE")
meshes = [o for o in bnew if o.type == "MESH"]
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
AW = arm.matrix_world
B = arm.data.bones


def jpos(n, tail=False):
    return AW @ (B[n].tail_local if tail else B[n].head_local)


def body_pts(bones):
    out = []
    for m in meshes:
        gn = {g.index: g.name for g in m.vertex_groups}
        for v in m.data.vertices:
            tot = sum(g.weight for g in v.groups)
            w = sum(g.weight for g in v.groups if gn[g.group] in bones)
            if tot > 0 and w / tot > 0.5:
                out.append(m.matrix_world @ v.co)
    return out


new = []
for slot, path in items.items():
    ms = [o for o in imp(path) if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    p = bpy.context.view_layer.objects.active
    p.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    vs = [v.co.copy() for v in p.data.vertices]
    lo = Vector([min(q[i] for q in vs) for i in range(3)])
    hi = Vector([max(q[i] for q in vs) for i in range(3)])
    size = hi - lo
    ctr = (lo + hi) / 2
    if slot == "head":
        hp = body_pts({"Head", "head_end", "headfront"})
        hlo = Vector([min(q[i] for q in hp) for i in range(3)])
        hhi = Vector([max(q[i] for q in hp) for i in range(3)])
        k = (hhi.x - hlo.x) * 1.08 / size.x
        M = Matrix.Translation(Vector(((hlo.x + hhi.x) / 2, (hlo.y + hhi.y) / 2, hhi.z - 0.55 * size.z * k))) @ Matrix.Scale(k, 4) @ Matrix.Translation(-ctr)
        bone = "Head"
    elif slot == "hand_r":
        ax = max(range(3), key=lambda i: size[i])
        grip = (jpos("RightHand") - jpos("RightForeArm")).normalized()
        k = 0.85 / size[ax]
        local_axis = Vector([1.0 if i == ax else 0.0 for i in range(3)])
        R = local_axis.rotation_difference(grip).to_matrix().to_4x4()
        start = ctr - local_axis * size[ax] / 2
        hand = jpos("RightHand") + grip * 0.07
        M = Matrix.Translation(hand - grip * 0.12) @ R @ Matrix.Scale(k, 4) @ Matrix.Translation(-start)
        bone = "RightHand"
    else:  # belt
        k = 0.22 / max(size)
        hip = jpos("RightUpLeg")
        M = Matrix.Translation(hip + Vector((0.02, -0.09, 0.06))) @ Matrix.Scale(k, 4) @ Matrix.Translation(-ctr)
        bone = "Hips"
    p.data.transform(M)
    vg = p.vertex_groups.new(name=bone)
    vg.add(list(range(len(p.data.vertices))), 1.0, "REPLACE")
    p.parent = arm
    md = p.modifiers.new("Armature", "ARMATURE")
    md.object = arm
    p.name = "acc_" + slot
    rep[slot] = {"bone": bone, "scale": round(k, 4), "vertices": len(p.data.vertices)}
    new.append(p)

bpy.ops.object.select_all(action="DESELECT")
for o in [arm] + meshes + new:
    o.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
print("ACCESSORY", json.dumps(rep))
if rep_path:
    json.dump(rep, open(rep_path, "w"), indent=1)

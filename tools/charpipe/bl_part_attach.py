"""Swap a body region of a rigged character for a separately generated, higher-detail part (Blender).

    blender -b --factory-startup -P bl_part_attach.py -- <rigged.glb> <out.glb> <slot>=<part.glb> [<slot>=<part.glb> ...] [--report r.json]

Slots (Meshy-family bone names):
  head    neck/Head bones. Part = head-and-neck portrait mesh, upright, facing -Y.
  arms    Left/Right Arm+ForeArm+Hand. Part = ONE right arm hanging straight down (shoulder at the top,
          fist at the bottom), facing -Y; it is mirrored for the left arm.
  legs    Left/Right UpLeg+Leg+Foot+ToeBase. Part = lower body from the hips down, legs slightly apart,
          front view.
For every slot the body faces dominated by the slot's bones are removed. The removed region gives the
target frame: for head/legs its bounding box (part scaled per axis to match, base kept at the seam);
for each arm its shoulder->fingertip axis (part's top->bottom axis is rotated onto it and scaled to the
same length, thickness scaled to the removed sleeve). Part vertices beyond the seam (more than 1 cm
inside the remaining body) are trimmed. Weights: head = Head rigid with an 8 cm blend into neck;
arms/legs = transferred from the ORIGINAL (uncut) body, nearest face, so elbows, knees and the
shoulder/hip seams bend exactly like the original skin.
"""
import json
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
body_p, dst = args[0], args[1]
parts = dict(a.split("=", 1) for a in args[2:] if "=" in a and not a.startswith("--"))
rep_path = args[args.index("--report") + 1] if "--report" in args else None
rep = {"parts": {}}
SLOTS = {
    "head": {"neck", "Head", "head_end", "headfront"},
    "arm_L": {"LeftArm", "LeftForeArm", "LeftHand"},
    "arm_R": {"RightArm", "RightForeArm", "RightHand"},
    "legs": {"LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase", "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"},
}


def imp(p):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=p)
    for o in [o for o in bpy.data.objects if o not in before and o.name.startswith("Icosphere")]:
        bpy.data.objects.remove(o, do_unlink=True)
    return [o for o in bpy.data.objects if o not in before]


def single_mesh(objs):
    ms = [o for o in objs if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    m = bpy.context.view_layer.objects.active
    m.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for a in [o for o in objs if o.type != "MESH" and o.name in bpy.data.objects]:
        bpy.data.objects.remove(a, do_unlink=True)
    return m


bpy.ops.wm.read_factory_settings(use_empty=True)
bnew = imp(body_p)
arm = next(o for o in bnew if o.type == "ARMATURE")
body = next(o for o in bnew if o.type == "MESH")
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
orig = body.copy()
orig.data = body.data.copy()
bpy.context.scene.collection.objects.link(orig)
orig.hide_render = True
gname = {g.index: g.name for g in body.vertex_groups}
MW = body.matrix_world
B = arm.data.bones
AW = arm.matrix_world


def region(bones):
    out = set()
    for v in body.data.vertices:
        tot = sum(g.weight for g in v.groups)
        w = sum(g.weight for g in v.groups if gname[g.group] in bones)
        if tot > 0 and w / tot > 0.5:
            out.add(v.index)
    return out


def bbox(pts):
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


todo = []
if "head" in parts:
    todo.append(("head", parts["head"], False))
if "arms" in parts:
    todo += [("arm_R", parts["arms"], False), ("arm_L", parts["arms"], True)]
if "legs" in parts:
    todo.append(("legs", parts["legs"], False))
cut = {}
for slot, _, _ in todo:
    rv = region(SLOTS[slot])
    cut[slot] = [MW @ body.data.vertices[i].co for i in rv]
    cut[slot + "_idx"] = rv
allcut = set().union(*[cut[s + "_idx"] for s, _, _ in todo]) if todo else set()
bm = bmesh.new()
bm.from_mesh(body.data)
kill = [f for f in bm.faces if sum(1 for v in f.verts if v.index in allcut) >= 2]
bmesh.ops.delete(bm, geom=kill, context="FACES")
bm.to_mesh(body.data)
bm.free()
rep["body_faces_removed"] = len(kill)

new_parts = []
for slot, path, mirror in todo:
    p = single_mesh(imp(path))
    p.name = "part_" + slot
    pts = [v.co.copy() for v in p.data.vertices]
    plo, phi = bbox(pts)
    tgt = cut[slot]
    tlo, thi = bbox(tgt)
    if slot in ("head", "legs"):
        if slot == "head":  # uniform scale by height, base on the seam
            k = (thi.z - tlo.z + 0.02) / (phi.z - plo.z)
            S = Vector((k, k, k))
            base = Vector(((tlo.x + thi.x) / 2, (tlo.y + thi.y) / 2, tlo.z - 0.02))
        else:  # legs: per-axis fit, top at the hip seam
            S = Vector(((thi.x - tlo.x) / (phi.x - plo.x), (thi.y - tlo.y) / max(phi.y - plo.y, 1e-4), (thi.z - tlo.z + 0.03) / (phi.z - plo.z)))
            base = Vector(((tlo.x + thi.x) / 2, (tlo.y + thi.y) / 2, tlo.z))
        pc = Vector(((plo.x + phi.x) / 2, (plo.y + phi.y) / 2, plo.z))
        for v in p.data.vertices:
            d = v.co - pc
            v.co = Vector((d.x * S.x, d.y * S.y, d.z * S.z)) + base
        seam_z = thi.z if slot == "legs" else tlo.z
        rep["parts"][slot] = {"scale": [round(c, 3) for c in S]}
    else:  # arm: part top->bottom axis onto shoulder->fingertip axis of this side
        side = "Left" if slot == "arm_L" else "Right"
        sh = AW @ B[side + "Arm"].head_local
        far = max(tgt, key=lambda q: (q - sh).length)
        axis_t = (far - sh).normalized()
        L_t = (far - sh).length
        if mirror:
            for v in p.data.vertices:
                v.co.x = -v.co.x
            p.data.flip_normals()
            pts = [v.co.copy() for v in p.data.vertices]
            plo, phi = bbox(pts)
        top = Vector(((plo.x + phi.x) / 2, (plo.y + phi.y) / 2, phi.z))
        k = (L_t + 0.02) / (phi.z - plo.z)
        thick_t = sorted(((q - sh) - axis_t * (q - sh).dot(axis_t)).length for q in tgt)
        thick_t = thick_t[int(len(thick_t) * 0.9)]
        thick_p = sorted(((v.co - top) - Vector((0, 0, (v.co - top).z))).length for v in p.data.vertices)
        thick_p = thick_p[int(len(thick_p) * 0.9)] * k
        kr = thick_t / max(thick_p, 1e-4)
        R = Vector((0, 0, -1)).rotation_difference(axis_t).to_matrix()
        for v in p.data.vertices:
            d = (v.co - top) * k
            d = Vector((d.x * kr, d.y * kr, d.z))
            v.co = R @ d + sh - axis_t * 0.01
        seam_z = None
        rep["parts"][slot] = {"length_m": round(L_t, 3), "radius_scale": round(kr, 3)}
    # trim part geometry reaching into the remaining body
    bm = bmesh.new()
    bm.from_mesh(p.data)
    if slot == "head":
        bad = [v for v in bm.verts if v.co.z < seam_z - 0.01]
    elif slot == "legs":
        bad = [v for v in bm.verts if v.co.z > seam_z + 0.01]
    else:
        bad = [v for v in bm.verts if (v.co - sh).dot(axis_t) < -0.015]
    bmesh.ops.delete(bm, geom=bad, context="VERTS")
    bm.to_mesh(p.data)
    bm.free()
    # weights
    if slot == "head":
        vh, vn = p.vertex_groups.new(name="Head"), p.vertex_groups.new(name="neck")
        for v in p.data.vertices:
            t = min(max((v.co.z - seam_z) / 0.08, 0.0), 1.0)
            vh.add([v.index], t, "REPLACE")
            if t < 1:
                vn.add([v.index], 1 - t, "REPLACE")
    else:
        for g in orig.vertex_groups:
            p.vertex_groups.new(name=g.name)
        dt = p.modifiers.new("wt", "DATA_TRANSFER")
        dt.object = orig
        dt.use_vert_data = True
        dt.data_types_verts = {"VGROUP_WEIGHTS"}
        dt.vert_mapping = "POLYINTERP_NEAREST"
        dt.layers_vgroup_select_src = "ALL"
        dt.layers_vgroup_select_dst = "NAME"
        bpy.ops.object.select_all(action="DESELECT")
        p.select_set(True)
        bpy.context.view_layer.objects.active = p
        bpy.ops.object.modifier_apply(modifier="wt")
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    p.parent = arm
    md = p.modifiers.new("Armature", "ARMATURE")
    md.object = arm
    rep["parts"][slot]["vertices"] = len(p.data.vertices)
    new_parts.append(p)

bpy.data.objects.remove(orig, do_unlink=True)
bpy.ops.object.select_all(action="DESELECT")
for o in [arm, body] + new_parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
print("PARTATTACH", json.dumps(rep))
if rep_path:
    json.dump(rep, open(rep_path, "w"), indent=1)

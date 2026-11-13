"""Dress a MetaHuman base body in a generated character's outfit (Blender).

    blender -b --factory-startup -P bl_mh_dress.py -- <mh_base.glb> <outfit_rigged.glb> <out.glb> [--skin r,g,b] [--report r.json]

<outfit_rigged.glb> is any 24-bone (Meshy-family) rig: a cleaned Meshy character or a charpipe
output. Steps:
 1. pose the outfit rig onto the MetaHuman rest pose (A-pose) with retarget2 (mh -> meshy) and stretch
    every limb/spine bone to the MetaHuman bone length, then bake that pose into the outfit mesh;
 2. drop the outfit's own head and hands (faces dominated by neck/Head/hand bones);
 3. transfer skin weights from the MetaHuman body (nearest face, all 341 bone groups), 4 influences;
 4. keep only the MetaHuman head, neck and hands visible (the rest of the body is under the clothes),
    tinted with --skin.
Result: one armature (MetaHuman skeleton incl. fingers) with body + head + outfit.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retarget2 as R  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
mh_path, outfit_path, dst = args[0], args[1], args[2]
skin = tuple(float(v) for v in (args[args.index("--skin") + 1] if "--skin" in args else "0.72,0.56,0.47").split(","))
rep_path = args[args.index("--report") + 1] if "--report" in args else None
rep = {}

bpy.ops.wm.read_factory_settings(use_empty=True)


def imp(p):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=p)
    new = [o for o in bpy.data.objects if o not in before]
    for o in list(new):
        if o.name.startswith("Icosphere"):
            bpy.data.objects.remove(o, do_unlink=True)
    new = [o for o in bpy.data.objects if o not in before]
    return next(o for o in new if o.type == "ARMATURE"), [o for o in new if o.type == "MESH"]


mh, mh_meshes = imp(mh_path)
oa, om = imp(outfit_path)
for a in (mh, oa):
    if a.animation_data:
        a.animation_data.action = None
    for pb in a.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.matrix_basis.identity()
bpy.context.view_layer.update()

# 1. outfit rig -> MetaHuman rest pose
act = bpy.data.actions.new("mh_rest")
mh.animation_data_create()
mh.animation_data.action = act
for f in (0, 1):
    mh.pose.bones["pelvis"].keyframe_insert("location", frame=f)
_, rlog = R.retarget(mh, "mh", oa, "meshy", "to_mh_rest", frames=[0], bend_fix=True, ground=False, in_place=False,
                     scale_hips=False)
bpy.context.scene.frame_set(0)
oa.animation_data.action.fcurves if hasattr(oa.animation_data.action, "fcurves") else None
bpy.context.view_layer.update()
pose = {pb.name: pb.matrix_basis.copy() for pb in oa.pose.bones}
oa.animation_data.action = None
for pb in oa.pose.bones:
    pb.matrix_basis = pose[pb.name]
# hips onto MetaHuman pelvis
S, T = R.Rig(mh, "mh"), R.Rig(oa, "meshy")
d = S.rest_pos("hips") - (oa.matrix_world @ oa.pose.bones["Hips"].head)
oa.location += d
bpy.context.view_layer.update()
# stretch bones to MetaHuman lengths (child joint distance), parents first
for b in oa.data.bones:
    b.inherit_scale = "NONE"
pairs = []
for j in ("spine1", "spine2", "chest", "neck"):
    pass
LMAP = [("clav", "uarm"), ("uarm", "larm"), ("larm", "hand"), ("uleg", "lleg"), ("lleg", "foot")]
stretch = {}
for s in "lr":
    for a, b in LMAP:
        ja, jb = a + "_" + s, b + "_" + s
        mh_len = (S.rest_pos(jb) - S.rest_pos(ja)).length
        pa, pb_ = oa.pose.bones[T.name(ja)], oa.pose.bones[T.name(jb)]
        cur = (pb_.head - pa.head).length * oa.matrix_world.to_scale()[0]
        if cur > 1e-4:
            k = mh_len / cur
            if 0.6 < k < 1.6:
                pa.scale = (1.0, k, 1.0)
                stretch[T.name(ja)] = round(k, 3)
                bpy.context.view_layer.update()
rep["stretch"] = stretch
for m in om:
    bpy.context.view_layer.objects.active = m
    mod = next((md for md in m.modifiers if md.type == "ARMATURE"), None)
    if mod:
        mod.object = oa
        bpy.ops.object.modifier_apply(modifier=mod.name)
    mw = m.matrix_world.copy()
    m.parent = None
    m.matrix_world = mw
    bpy.ops.object.select_all(action="DESELECT")
    m.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# 2. drop outfit head + hands
DROP = {"neck", "Head", "head_end", "headfront", "LeftHand", "RightHand"}
outfit = om[0]
gname = {g.index: g.name for g in outfit.vertex_groups}
drop_v = set()
for v in outfit.data.vertices:
    acc_drop = sum(g.weight for g in v.groups if gname[g.group] in DROP)
    acc = sum(g.weight for g in v.groups)
    if acc > 0 and acc_drop / acc > 0.5:
        drop_v.add(v.index)
bm = bmesh.new()
bm.from_mesh(outfit.data)
bm.verts.ensure_lookup_table()
kill = [f for f in bm.faces if sum(1 for v in f.verts if v.index in drop_v) >= 2]
bmesh.ops.delete(bm, geom=kill, context="FACES")
bm.to_mesh(outfit.data)
bm.free()
rep["outfit_faces_dropped"] = len(kill)
bpy.data.objects.remove(oa, do_unlink=True)

# 3. weights from the MetaHuman body
body = max((m for m in mh_meshes if "Body" in m.name or "body" in m.name), key=lambda m: len(m.data.vertices), default=mh_meshes[0])
head = next((m for m in mh_meshes if m is not body), None)
outfit.vertex_groups.clear()
for g in body.vertex_groups:
    outfit.vertex_groups.new(name=g.name)
dt = outfit.modifiers.new("wt", "DATA_TRANSFER")
dt.object = body
dt.use_vert_data = True
dt.data_types_verts = {"VGROUP_WEIGHTS"}
dt.vert_mapping = "POLYINTERP_NEAREST"
dt.layers_vgroup_select_src = "ALL"
dt.layers_vgroup_select_dst = "NAME"
bpy.context.view_layer.objects.active = outfit
bpy.ops.object.datalayer_transfer(data_type="VGROUP_WEIGHTS") if False else None
bpy.ops.object.modifier_apply(modifier="wt")
bpy.ops.object.select_all(action="DESELECT")
outfit.select_set(True)
bpy.context.view_layer.objects.active = outfit
bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
bpy.ops.object.vertex_group_normalize_all(lock_active=False)
outfit.parent = mh
outfit.matrix_parent_inverse = mh.matrix_world.inverted()
am = outfit.modifiers.new("Armature", "ARMATURE")
am.object = mh

# 4. keep MetaHuman hands / neck visible, hide the rest of the body
KEEP = ("hand_", "thumb_", "index_", "middle_", "ring_", "pinky_", "neck_", "head", "lowerarm_twist_02", "wrist")
bg = {g.index: g.name for g in body.vertex_groups}
keep_v = set()
for v in body.data.vertices:
    acc = {}
    for g in v.groups:
        acc[bg[g.group]] = acc.get(bg[g.group], 0) + g.weight
    if acc:
        top = max(acc, key=acc.get)
        if top.startswith(KEEP) or top in ("head",):
            keep_v.add(v.index)
bm = bmesh.new()
bm.from_mesh(body.data)
kill = [f for f in bm.faces if not all(v.index in keep_v for v in f.verts)]
bmesh.ops.delete(bm, geom=kill, context="FACES")
bm.to_mesh(body.data)
bm.free()
for m in (body, head):
    if m is None:
        continue
    for slot in m.material_slots:
        if slot.material and slot.material.use_nodes:
            p = next((n for n in slot.material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if p:
                p.inputs["Base Color"].default_value = (*skin, 1)
rep["body_faces_kept"] = len(body.data.polygons)
bpy.ops.object.select_all(action="DESELECT")
for o in [mh, body, outfit] + ([head] if head else []):
    o.select_set(True)
bpy.context.view_layer.objects.active = mh
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
print("MHDRESS", json.dumps(rep))
if rep_path:
    json.dump(rep, open(rep_path, "w"), indent=1)

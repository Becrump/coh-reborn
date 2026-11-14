"""Replace a rigged character's head with a separately generated, higher-detail head (Blender).

    blender -b --factory-startup -P bl_head_attach.py -- <rigged.glb> <head.glb> <out.glb> [--report r.json]

<rigged.glb>: charpipe/Meshy-family rig (bones neck, Head). <head.glb>: a textured head-and-neck
mesh generated on its own (e.g. Hunyuan3D from a portrait concept), facing -Y.
Steps:
 1. neck seam: the body's faces dominated by neck/Head/head_end are removed; the seam height is the
    lowest removed vertex ring (z_seam), its centre and radius come from the removed region's base.
 2. the new head is scaled so its height above its own neck base matches the removed head region
    (seam -> top of head), centred on the seam and dropped so its base overlaps the seam by 2 cm.
 3. head vertices below the seam + 1 cm are trimmed; weights: Head bone 1.0 above seam + 8 cm,
    blending linearly to neck at the seam, so the jaw/skull are rigid and the neck bends.
 4. exported with the same armature (eyes/jaw are static).
"""
import json
import sys

import bmesh
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
body_p, head_p, dst = args[0], args[1], args[2]
rep_path = args[args.index("--report") + 1] if "--report" in args else None
rep = {}


def imp(p):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=p)
    new = [o for o in bpy.data.objects if o not in before]
    for o in list(new):
        if o.name.startswith("Icosphere"):
            bpy.data.objects.remove(o, do_unlink=True)
    return [o for o in bpy.data.objects if o not in before]


bpy.ops.wm.read_factory_settings(use_empty=True)
bnew = imp(body_p)
arm = next(o for o in bnew if o.type == "ARMATURE")
body = next(o for o in bnew if o.type == "MESH")
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()

# 1. cut the old head
HEAD = {"neck", "Head", "head_end", "headfront"}
gname = {g.index: g.name for g in body.vertex_groups}
mw = body.matrix_world
head_v = set()
for v in body.data.vertices:
    tot = sum(g.weight for g in v.groups)
    hw = sum(g.weight for g in v.groups if gname[g.group] in HEAD)
    if tot > 0 and hw / tot > 0.5:
        head_v.add(v.index)
pts = [mw @ body.data.vertices[i].co for i in head_v]
z_seam = min(p.z for p in pts)
z_top = max(p.z for p in pts)
base = [p for p in pts if p.z < z_seam + 0.03]
c = sum(base, Vector()) / len(base)
r = max(((p.x - c.x) ** 2 + (p.y - c.y) ** 2) ** 0.5 for p in base)
bm = bmesh.new()
bm.from_mesh(body.data)
kill = [f for f in bm.faces if sum(1 for v in f.verts if v.index in head_v) >= 2]
bmesh.ops.delete(bm, geom=kill, context="FACES")
bm.to_mesh(body.data)
bm.free()
rep.update(seam_z=round(z_seam, 3), head_top=round(z_top, 3), seam_radius=round(r, 3), body_faces_removed=len(kill))

# 2. place the new head
hnew = [o for o in imp(head_p) if o.type == "MESH"]
bpy.ops.object.select_all(action="DESELECT")
for o in hnew:
    o.select_set(True)
bpy.context.view_layer.objects.active = hnew[0]
if len(hnew) > 1:
    bpy.ops.object.join()
head = bpy.context.view_layer.objects.active
head.parent = None
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
hp = [v.co.copy() for v in head.data.vertices]
lo = Vector([min(p[i] for p in hp) for i in range(3)])
hi = Vector([max(p[i] for p in hp) for i in range(3)])
k = (z_top - z_seam + 0.02) / (hi.z - lo.z)
for v in head.data.vertices:
    v.co = (v.co - Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))) * k + Vector((c.x, c.y, z_seam - 0.02))
rep["head_scale"] = round(k, 4)

# 3. trim + weights
bm = bmesh.new()
bm.from_mesh(head.data)
low = [v for v in bm.verts if v.co.z < z_seam - 0.01]
bmesh.ops.delete(bm, geom=low, context="VERTS")
bm.to_mesh(head.data)
bm.free()
vg_h = head.vertex_groups.new(name="Head")
vg_n = head.vertex_groups.new(name="neck")
for v in head.data.vertices:
    t = min(max((v.co.z - z_seam) / 0.08, 0.0), 1.0)
    vg_h.add([v.index], t, "REPLACE")
    if t < 1:
        vg_n.add([v.index], 1 - t, "REPLACE")
head.parent = arm
md = head.modifiers.new("Armature", "ARMATURE")
md.object = arm
rep["head_vertices"] = len(head.data.vertices)

bpy.ops.object.select_all(action="DESELECT")
for o in (arm, body, head):
    o.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
print("HEADATTACH", json.dumps(rep))
if rep_path:
    json.dump(rep, open(rep_path, "w"), indent=1)

"""Put a head from the head library on a rigged HEADLESS body (Blender).

    blender -b --factory-startup -P bl_head_swap.py -- <headless_rigged.glb> <head.glb> <out.glb> [--height 1.82] [--report r.json]

<head.glb>: a head + neck mesh (static or skinned; only meshes are used), facing -Y, any scale.
 * the stump: the ring of body vertices in the top 2.5 cm near the centre line (centre + width)
 * the head is scaled so that its neck base sits 3 cm inside the collar and its crown reaches the
   body's full height (--height, default: the rig's head_end tail / top joint), centred on the ring
 * head vertices more than 4 cm below the stump top are trimmed (hidden inside the collar anyway)
 * weights: neck at the stump, blending to 100 % Head 3 cm above the Head joint, so the jaw and
   skull are rigid and the neck bends; the head is its own mesh (material and SkinTone separate)
Output: armature + body + head ("head" mesh). Report: scale, neck/collar width ratio.
"""
import json
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
body_p, head_p, dst = a[0], a[1], a[2]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
rep = {"head_source": head_p}


def imp(p):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=p)
    new = [o for o in bpy.data.objects if o not in before]
    for o in list(new):
        if o.name.startswith("Icosphere"):
            bpy.data.objects.remove(o, do_unlink=True)
            new.remove(o)
    return new


bpy.ops.wm.read_factory_settings(use_empty=True)
bn = imp(body_p)
arm = next(o for o in bn if o.type == "ARMATURE")
body = max((o for o in bn if o.type == "MESH"), key=lambda o: len(o.data.vertices))
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
W = arm.matrix_world
nb = W @ arm.data.bones["neck"].head_local
hb = W @ arm.data.bones["Head"].head_local
he = arm.data.bones.get("head_end")
H = float(opt("--height", (W @ he.tail_local).z if he else hb.z + 0.24))
bv = [body.matrix_world @ v.co for v in body.data.vertices]
top = max(p.z for p in bv if abs(p.x - nb.x) < 0.12)
ring = [p for p in bv if p.z > top - 0.025 and abs(p.x - nb.x) < 0.12]
c = sum(ring, Vector()) / len(ring)
ring_w = max(p.x for p in ring) - min(p.x for p in ring)
rep.update(stump_top=round(top, 3), ring_width=round(ring_w, 3), target_top=round(H, 3))

hn = [o for o in imp(head_p) if o.type == "MESH"]
for o in [o for o in bpy.data.objects if o.type == "ARMATURE" and o is not arm]:
    bpy.data.objects.remove(o, do_unlink=True)
for o in hn:
    mw = o.matrix_world.copy()
    o.parent = None
    o.modifiers.clear()
    o.vertex_groups.clear()
    o.data.transform(mw)
    o.matrix_world = Matrix.Identity(4)
for x in bpy.data.objects:
    if x.name in bpy.context.view_layer.objects:
        x.select_set(False)
for o in hn:
    o.select_set(True)
bpy.context.view_layer.objects.active = hn[0]
if len(hn) > 1:
    bpy.ops.object.join()
head = bpy.context.view_layer.objects.active
head.name = "head"
hp = [v.co.copy() for v in head.data.vertices]
lo = Vector([min(p[i] for p in hp) for i in range(3)])
hi = Vector([max(p[i] for p in hp) for i in range(3)])
# the neck = the narrowest horizontal slab in the lower 45 % (busts carry shoulders below it)
hh = hi.z - lo.z
best = None
for i in range(2, 45, 2):
    z = lo.z + hh * i / 100.0
    sl = [p for p in hp if abs(p.z - z) < hh * 0.015]
    if len(sl) < 8:
        continue
    w = max(p.x for p in sl) - min(p.x for p in sl)
    if best is None or w < best[0]:
        best = (w, z, sl)
neck_z = best[1] if best else lo.z
if neck_z > lo.z + 0.05 * hh:  # cut away shoulders/chest below the neck
    bm = bmesh.new()
    bm.from_mesh(head.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < neck_z - 0.02 * hh], context="VERTS")
    bm.to_mesh(head.data)
    bm.free()
    hp = [v.co.copy() for v in head.data.vertices]
    lo = Vector([min(p[i] for p in hp) for i in range(3)])
neck = [p for p in hp if p.z < lo.z + 0.12 * (hi.z - lo.z)]
nc = sum(neck, Vector()) / len(neck)
base_z = top - 0.03
k = (H - base_z) / (hi.z - lo.z)
T = Matrix.Translation(Vector((c.x, c.y, base_z))) @ Matrix.Scale(k, 4) @ Matrix.Translation(-Vector((nc.x, nc.y, lo.z)))
head.data.transform(T)
neck_w = (max(p.x for p in neck) - min(p.x for p in neck)) * k
rep.update(head_scale=round(k, 4), neck_width=round(neck_w, 3), neck_to_collar=round(neck_w / max(ring_w, 1e-6), 2))
bm = bmesh.new()
bm.from_mesh(head.data)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < top - 0.04], context="VERTS")
bm.to_mesh(head.data)
bm.free()
vh, vn = head.vertex_groups.new(name="Head"), head.vertex_groups.new(name="neck")
z0, z1 = top - 0.01, hb.z + 0.03
for v in head.data.vertices:
    t = min(max((v.co.z - z0) / max(z1 - z0, 1e-4), 0.0), 1.0)
    if t > 0:
        vh.add([v.index], t, "REPLACE")
    if t < 1:
        vn.add([v.index], 1 - t, "REPLACE")
head.parent = arm
head.modifiers.new("Armature", "ARMATURE").object = arm
for x in bpy.data.objects:
    if x.name in bpy.context.view_layer.objects:
        x.select_set(False)
for o in (arm, body, head):
    o.select_set(True)
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
print("HEADSWAP_OK", json.dumps(rep))
if opt("--report"):
    json.dump(rep, open(opt("--report"), "w"), indent=1)

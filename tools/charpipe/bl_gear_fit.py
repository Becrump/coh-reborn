"""Fit a generated gear piece to a rigged character as its own skinned piece on the same skeleton (Blender).

    blender -b --factory-startup -P bl_gear_fit.py -- <rigged.glb> <gear.glb|fbx> <out.glb> neck|head [--report r.json]

neck : neckerchief / bandana worn around the neck. The ring at the top of the piece is scaled to
       1.15 x the neck width (clamped 17-24 cm) and set just under the jaw; the hanging tip is
       turned to the front. Weights: 50 % neck at the top blending to 85 % Spine at the tip (it follows
       the chest, the neck turn only moves the top a little); untextured pieces get a flat Hellion red, so it never pierces the collar when bending.
head : rigid headwear on the Head bone (cap / beanie / mask): scaled to 1.08 x head width.
Output: armature + the gear mesh only. In Unreal import it as a skeletal mesh on the SAME
skeleton and attach it with Leader Pose (Set Leader Pose Component) or as a modular part.
"""
import json
import math
import sys

import bpy
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
rig_p, gear_p, dst, slot = a[0], a[1], a[2], a[3]
rep = {"slot": slot}
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=rig_p)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
W = arm.matrix_world
bone = lambda n: W @ arm.data.bones[n].head_local  # noqa: E731
before = set(bpy.data.objects)
if gear_p.lower().endswith(".fbx"):
    bpy.ops.import_scene.fbx(filepath=gear_p)
else:
    bpy.ops.import_scene.gltf(filepath=gear_p)
G = next(o for o in bpy.data.objects if o not in before and o.type == "MESH")
for o in [o for o in bpy.data.objects if o not in before and o is not G]:
    bpy.data.objects.remove(o, do_unlink=True)
mw = G.matrix_world.copy()
G.parent = None
G.data.transform(mw)
G.matrix_world = Matrix.Identity(4)
gv = [v.co for v in G.data.vertices]
lo = Vector((min(p.x for p in gv), min(p.y for p in gv), min(p.z for p in gv)))
hi = Vector((max(p.x for p in gv), max(p.y for p in gv), max(p.z for p in gv)))
bv = [body.matrix_world @ v.co for v in body.data.vertices]
nb, hb = bone("neck"), bone("Head")


def width_at(z0, z1):
    s = [p for p in bv if z0 < p.z < z1 and abs(p.x - nb.x) < 0.15]
    if not s:
        return 0.14, nb.y
    return max(p.x for p in s) - min(p.x for p in s), sum(p.y for p in s) / len(s)


if slot == "neck":
    nw, ny = width_at(nb.z - 0.01, nb.z + 0.03)
    top = [p for p in gv if p.z > hi.z - 0.10 * (hi.z - lo.z)]
    ring_w = max(p.x for p in top) - min(p.x for p in top)
    ring_c = Vector(((max(p.x for p in top) + min(p.x for p in top)) / 2, (max(p.y for p in top) + min(p.y for p in top)) / 2, hi.z))
    s = min(0.24, max(0.17, nw * 1.15)) / ring_w
    tgt = Vector((nb.x, ny, min(hb.z + 0.015, max(p.z for p in bv) + 0.02)))
    G.data.transform(Matrix.Translation(tgt) @ Matrix.Scale(s, 4) @ Matrix.Translation(-ring_c))
    tip = min(G.data.vertices, key=lambda v: v.co.z).co
    if tip.y > tgt.y:
        G.data.transform(Matrix.Translation(tgt) @ Matrix.Rotation(math.pi, 4, "Z") @ Matrix.Translation(-tgt))
    zs = [v.co.z for v in G.data.vertices]
    z0, z1 = min(zs), max(zs)
    for n in ("neck", "Spine"):
        G.vertex_groups.new(name=n)
    for v in G.data.vertices:
        t = (v.co.z - z0) / max(1e-4, z1 - z0)
        wn = 0.15 + 0.35 * t  # follows the chest; the neck turn only moves the top a little
        G.vertex_groups["neck"].add([v.index], wn, "REPLACE")
        G.vertex_groups["Spine"].add([v.index], 1 - wn, "REPLACE")
    rep.update(neck_width=nw, scale=s)
    if not any(m and m.use_nodes and any(n.type == "TEX_IMAGE" for n in m.node_tree.nodes) for m in G.data.materials):
        mat = bpy.data.materials.new("gear_cloth_red")  # untextured Tripo piece: flat Hellion red until it is textured
        mat.use_nodes = True
        mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.04, 0.04, 1)
        mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.85
        G.data.materials.clear()
        G.data.materials.append(mat)
elif slot == "head":
    hw, hy = width_at(hb.z + 0.05, hb.z + 0.12)
    s = hw * 1.08 / (hi.x - lo.x)
    G.data.transform(Matrix.Translation(Vector((hb.x, hy, max(p.z for p in bv) - 0.06 * (hi.z - lo.z) * s)))
                     @ Matrix.Scale(s, 4) @ Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))))
    G.vertex_groups.new(name="Head").add(list(range(len(G.data.vertices))), 1.0, "REPLACE")
    rep.update(head_width=hw, scale=s)
G.parent = arm
m = G.modifiers.new("Armature", "ARMATURE")
m.object = arm
bpy.data.objects.remove(body, do_unlink=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
print("GEAR_OK", json.dumps(rep))
if "--report" in a:
    json.dump(rep, open(a[a.index("--report") + 1], "w"), indent=1)

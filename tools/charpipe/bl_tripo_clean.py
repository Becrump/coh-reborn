"""Clean a Tripo download into a game-ready, correctly sized mesh before rigging (Blender).

    blender -b --factory-startup -P bl_tripo_clean.py -- <in.glb|fbx|obj> <out.glb> [--height-cm N] [--tris 50000]
                                                        [--tex 2048] [--headless] [--interior] [--report r.json]

Steps:
 1. import, join all meshes, apply transforms
 2. weld split vertices (UV seams survive: UVs live per face corner)
 3. remove floaters: loose parts with < 0.3 % of the vertices
 4. (--interior, off by default: it can punch holes in thin low-poly shells) remove hidden interior faces: faces whose centre is enclosed (rays along +-X, +-Y, +Z all hit the
    mesh within the body's size) and that face away from all six probe directions' first hit
 5. recalculate normals outward
 6. decimate to the triangle budget (default 50k)
 7. textures resized to 2K (base colour, normal, roughness/metal)
 8. size: --height-cm (else the build in the file name: kid/lean 172, veteran 178, average 180,
    heavy/brawler 183, big/biker 193; default 182); headless bodies (--headless or "headless" in the
    name) put the neck stump at 0.87 x height; feet at origin, centred, facing -Y (glTF metres)
"""
import json
import os
import re
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

a = sys.argv[sys.argv.index("--") + 1:]
src, dst = a[0], a[1]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
TRIS = int(opt("--tris", 50000))
TEX = int(opt("--tex", 2048))
low = os.path.basename(src).lower()
HEADLESS = "--headless" in a or "headless" in low
BUILDS = [(r"kid|lean", 172), (r"veteran", 178), (r"average", 180), (r"heavy|brawler", 183), (r"big|biker", 193)]
H_CM = float(opt("--height-cm", next((h for p, h in BUILDS if re.search(p, low)), 182)))
rep = {"source": src, "headless": HEADLESS, "height_cm": H_CM}

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = src.lower().rsplit(".", 1)[-1]
if ext == "fbx":
    bpy.ops.import_scene.fbx(filepath=src)
elif ext == "obj":
    bpy.ops.wm.obj_import(filepath=src)
else:
    bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.type != "MESH" or o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
ms = list(bpy.data.objects)
for o in ms:
    mw = o.matrix_world.copy()
    o.parent = None
    o.data.transform(mw)
    o.matrix_world = Matrix.Identity(4)
bpy.ops.object.select_all(action="DESELECT")
for o in ms:
    o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
if len(ms) > 1:
    bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
ob.name = os.path.splitext(os.path.basename(dst))[0]
me = ob.data
rep["in_verts"], rep["in_tris"] = len(me.vertices), sum(len(p.vertices) - 2 for p in me.polygons)

bm = bmesh.new()
bm.from_mesh(me)
n0 = len(bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
rep["welded"] = n0 - len(bm.verts)
# floaters
bm.verts.ensure_lookup_table()
seen, parts = set(), []
for v in bm.verts:
    if v in seen:
        continue
    st, comp = [v], []
    seen.add(v)
    while st:
        x = st.pop()
        comp.append(x)
        for e in x.link_edges:
            y = e.other_vert(x)
            if y not in seen:
                seen.add(y)
                st.append(y)
    parts.append(comp)
lim = 0.003 * len(bm.verts)
fl = [v for p in parts if len(p) < lim for v in p]
rep["loose_parts"], rep["floater_verts_removed"] = len(parts), len(fl)
bmesh.ops.delete(bm, geom=fl, context="VERTS")
# interior faces: enclosed in every direction, never seen from outside
bm.faces.ensure_lookup_table()
tree = BVHTree.FromBMesh(bm)
lo = Vector((min(v.co.x for v in bm.verts), min(v.co.y for v in bm.verts), min(v.co.z for v in bm.verts)))
hi = Vector((max(v.co.x for v in bm.verts), max(v.co.y for v in bm.verts), max(v.co.z for v in bm.verts)))
size = (hi - lo).length
dirs = [Vector(d) for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1))]
inner = []
for f in (bm.faces if "--interior" in a else []):
    c = f.calc_center_median()
    nrm = f.normal
    eps = c + nrm * 1e-4
    enclosed = True
    for d in dirs:
        hit = tree.ray_cast(eps, d, size)
        if hit[0] is None:
            enclosed = False
            break
    if not enclosed:
        continue
    # outward-facing side blocked very close (< 4 mm): the face is buried under another surface
    hit = tree.ray_cast(eps, nrm, size)
    if hit[0] is not None and hit[3] < 0.004 * size / 1.8:
        inner.append(f)
rep["interior_faces_removed"] = len(inner)
bmesh.ops.delete(bm, geom=inner, context="FACES")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(me)
bm.free()
me.update()

tris = sum(len(p.vertices) - 2 for p in me.polygons)
if tris > TRIS:
    d = ob.modifiers.new("dec", "DECIMATE")
    d.ratio = TRIS / tris
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="dec")
rep["out_tris"] = sum(len(p.vertices) - 2 for p in me.polygons)
rep["out_verts"] = len(me.vertices)

# textures to 2K, packed so the GLB carries them
done = set()
for mat in me.materials:
    if not (mat and mat.use_nodes):
        continue
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image and n.image.name not in done:
            im = n.image
            done.add(im.name)
            if max(im.size) > TEX:
                im.scale(TEX, TEX)
            im.pack()
rep["textures"] = sorted(done)

# size + placement
vs = [v.co for v in me.vertices]
lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
target = (H_CM * (0.87 if HEADLESS else 1.0)) / 100.0
s = target / (hi.z - lo.z)
me.transform(Matrix.Scale(s, 4) @ Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))))
me.update()
rep["scale"] = s
rep["out_height_m"] = target
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True)
print("CLEAN_OK", json.dumps(rep))
if opt("--report"):
    json.dump(rep, open(opt("--report"), "w"), indent=1)

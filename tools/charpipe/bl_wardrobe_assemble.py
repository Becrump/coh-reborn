"""Assemble a character from wardrobe items on a body build (Blender).

    blender -b --factory-startup -P bl_wardrobe_assemble.py -- <wardrobe_dir> <out_dir> --build base|heavy|big
            --items tee,jeans,boots[,...] [--tint item=hue_deg:sat_mul:val_mul[,...]]

* build: the base body deformed along its own bones (girth only, same skeleton and topology):
  heavy = belly/hips/thighs/neck thicker; big = shoulders/arms/chest/legs thicker.
* fit-to-build: every piece vertex is bound to its nearest point on the base body (face +
  barycentric coordinates) and moves with that point when the body is deformed (surface deform),
  so cloth thickness and layering are kept.
* body hide: faces whose vertices are all covered by worn pieces (wardrobe.json hides_body_verts)
  are deleted from the body, so skin can never poke through.
* tint: optional hue / saturation / value change of a piece's base-colour texture (palette swaps).
Writes <out_dir>/body.glb (armature + body) and <out_dir>/<item>.glb for each item (same armature),
and assembly.json.
"""
import colorsys  # noqa: F401  (documented dependency; numpy path below)
import json
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform  # noqa: F401

a = sys.argv[sys.argv.index("--") + 1:]
WDIR, OUT = a[0], a[1]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
BUILD = opt("--build", "base")
ITEMS = [x for x in opt("--items", "").split(",") if x]
TINT = {}
for kv in filter(None, (opt("--tint", "") or "").split(",")):
    k, v = kv.split("=")
    TINT[k] = [float(x) for x in v.split(":")]
os.makedirs(OUT, exist_ok=True)
wd = json.load(open(os.path.join(WDIR, "wardrobe.json")))
FACT = {
    "base": {},
    "heavy": {"Spine02": 1.28, "Spine01": 1.24, "Spine": 1.12, "Hips": 1.2, "UpLeg": 1.14, "Leg": 1.06, "neck": 1.15,
              "Arm": 1.1, "ForeArm": 1.05, "Shoulder": 1.08},
    "big": {"Spine02": 1.08, "Spine01": 1.12, "Spine": 1.16, "Hips": 1.08, "UpLeg": 1.12, "Leg": 1.1, "neck": 1.18,
            "Arm": 1.2, "ForeArm": 1.16, "Shoulder": 1.18},
}[BUILD]


def factor(bone):
    for k in sorted(FACT, key=len, reverse=True):
        if bone.endswith(k) or bone == k:
            return FACT[k]
    return 1.0


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(WDIR, wd["body"]["base"]["file"]))
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
body.name = "body"
me = body.data
M = body.matrix_world
co0 = np.array([(M @ v.co)[:] for v in me.vertices])
tris0 = [tuple(p.vertices) for p in me.polygons]
tree0 = BVHTree.FromPolygons([Vector(c) for c in co0], tris0)

# build deformation: weighted radial push away from each bone's axis
names = [g.name for g in body.vertex_groups]
W = np.zeros((len(co0), len(names)))
for v in me.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
disp = np.zeros_like(co0)
for j, n in enumerate(names):
    f = factor(n)
    b = arm.data.bones.get(n)
    if f == 1.0 or b is None:
        continue
    h = np.array((arm.matrix_world @ b.head_local)[:])
    t = np.array((arm.matrix_world @ b.tail_local)[:])
    d = t - h
    u = np.clip(((co0 - h) @ d) / max(d @ d, 1e-9), 0, 1)
    c = h + u[:, None] * d
    disp += W[:, j:j + 1] * (co0 - c) * (f - 1.0)
co1 = co0 + disp
Mi = M.inverted()
for v, p in zip(me.vertices, co1):
    v.co = Mi @ Vector(p)
me.update()


def surface_point(cos, fi, bc):
    return sum(cos[i] * w for i, w in zip(tris0[fi], bc))


def bary(p, fi):
    idx = tris0[fi]
    P = [Vector(co0[i]) for i in idx]
    if len(P) == 3:
        A, B, C = P
        v0, v1, v2 = B - A, C - A, Vector(p) - A
        d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
        den = d00 * d11 - d01 * d01 or 1e-12
        vv = (d11 * d20 - d01 * d21) / den
        ww = (d00 * d21 - d01 * d20) / den
        return (1 - vv - ww, vv, ww)
    dist = np.array([(Vector(p) - q).length for q in P]) + 1e-9
    w = 1 / dist
    return tuple(w / w.sum())


hidden = set()
rep = {"build": BUILD, "items": {}}
for it in ITEMS:
    info = wd["items"][it]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(WDIR, info["file"]))
    new = [o for o in bpy.data.objects if o not in before]
    piece = max((o for o in new if o.type == "MESH" and not o.name.startswith("Icosphere")), key=lambda o: len(o.data.vertices))
    for o in new:
        if o is not piece:
            bpy.data.objects.remove(o, do_unlink=True)
    pm = piece.matrix_world.copy()
    piece.parent = arm
    piece.matrix_world = pm
    for m in piece.modifiers:
        if m.type == "ARMATURE":
            m.object = arm
    if not any(m.type == "ARMATURE" for m in piece.modifiers):
        piece.modifiers.new("Armature", "ARMATURE").object = arm
    piece.name = it
    # fit to build (skip for rigid socket items: they follow their bone, the head does not change)
    if BUILD != "base" and not info.get("socket"):
        PM, PMi = piece.matrix_world, piece.matrix_world.inverted()
        for v in piece.data.vertices:
            p = PM @ v.co
            loc, nrm, fi, dist = tree0.find_nearest(p)
            if fi is None:
                continue
            bc = bary(loc, fi)
            s0 = surface_point(co0, fi, bc)
            s1 = surface_point(co1, fi, bc)
            v.co = PMi @ (p + Vector(s1 - s0))
        piece.data.update()
    # palette swap
    if it in TINT:
        hd, sm, vm = TINT[it]
        for mat in piece.data.materials:
            for n in (mat.node_tree.nodes if mat and mat.use_nodes else []):
                if n.type == "TEX_IMAGE" and n.image and "normal" not in n.image.name.lower():
                    im = n.image
                    if max(im.size) > 2048:
                        im.scale(2048, 2048)
                    px = np.empty(im.size[0] * im.size[1] * im.channels, np.float32)
                    im.pixels.foreach_get(px)
                    P = px.reshape(-1, im.channels)
                    rgb = P[:, :3]
                    mx, mn = rgb.max(1), rgb.min(1)
                    v_ = mx
                    s_ = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)
                    rc, gc, bcn = [(mx - rgb[:, i]) / np.maximum(mx - mn, 1e-9) for i in range(3)]
                    h_ = np.select([mx == rgb[:, 0], mx == rgb[:, 1]], [bcn - gc, 2 + rc - bcn], 4 + gc - rc) / 6.0 % 1.0
                    h_ = (h_ + hd / 360.0) % 1.0
                    s_ = np.clip(s_ * sm, 0, 1)
                    v_ = np.clip(v_ * vm, 0, 1)
                    i_ = (h_ * 6).astype(int) % 6
                    f_ = h_ * 6 - np.floor(h_ * 6)
                    p_, q_, t_ = v_ * (1 - s_), v_ * (1 - f_ * s_), v_ * (1 - (1 - f_) * s_)
                    out = np.choose(i_[:, None].repeat(3, 1), [np.stack(x, 1) for x in (
                        (v_, t_, p_), (q_, v_, p_), (p_, v_, t_), (p_, q_, v_), (t_, p_, v_), (v_, p_, q_))])
                    P[:, :3] = out
                    im.pixels.foreach_set(P.ravel())
                    im.pack()
    hidden |= set(info.get("hides_body_verts", []))
    rep["items"][it] = {"slot": info["slot"], "tint": TINT.get(it)}

# hide body faces fully covered by the worn pieces
bm = bmesh.new()
bm.from_mesh(me)
kill = [f for f in bm.faces if all(v.index in hidden for v in f.verts)]
rep["body_faces_hidden"] = len(kill)
bmesh.ops.delete(bm, geom=kill, context="FACES")
bm.to_mesh(me)
bm.free()


def export(objs, path):
    for x in bpy.data.objects:
        if x is not None and x.name in bpy.context.view_layer.objects:
            x.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)


export([arm, body], os.path.join(OUT, "body.glb"))
for it in ITEMS:
    export([arm, bpy.data.objects[it]], os.path.join(OUT, it + ".glb"))
json.dump(rep, open(os.path.join(OUT, "assembly.json"), "w"), indent=1)
print("ASSEMBLE_OK", json.dumps(rep))

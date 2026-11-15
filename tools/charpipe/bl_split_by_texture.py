"""Split a one-piece rigged character (Tripo / charpipe) into outfit slots (Blender, prototype).

    blender -b --factory-startup -P bl_split_by_texture.py -- <rigged.glb> <out_dir> <name> [--render] [--mesh NAME] [--subdiv N]

Slots: head (head, hair, bandana: kept fused to the face), vest, shirt, skin (arms, hands, chest),
gloves, pants, boots.
How: every face gets
  * a body region from its vertices' dominant bone (head/torso/hips/arm/hand/upleg/lowleg/foot),
  * a colour sampled from the base-colour texture at its UVs (CIE Lab).
Each slot gets a small palette (k-means centres) learned from faces where it is certain
(head: Head bone; skin: forearms; gloves: hand faces unlike skin; vest: back of the torso;
shirt: front torso centre unlike the vest; pants: thighs; boots: feet). Every face then takes
the nearest palette among the slots its region allows, followed by a neighbour majority filter
and small-island cleanup. Each slot becomes its own mesh with the same armature and weights.
Outputs <name>_split.glb (armature + slot meshes), <name>_split.json (face counts) and,
with --render, <name>_slots.png (slot colours) and <name>_exploded.png (textured, pulled apart).
Limits: open seams where slots meet; no base body is generated under the clothes yet.
"""
import json
import math
import os
import sys
from collections import Counter

import bmesh
import bpy
import numpy as np
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
src, out, name = args[0], args[1], args[2]
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
_cands = [o for o in bpy.data.objects if o.type == "MESH" and o.vertex_groups]
_want = args[args.index("--mesh") + 1] if "--mesh" in args else None
body = next((o for o in _cands if o.name == _want), None) or max(_cands, key=lambda o: len(o.data.polygons))
for o in [o for o in bpy.data.objects if o.type == "MESH" and o is not body]:
    bpy.data.objects.remove(o, do_unlink=True)  # split the main body only (separate heads/props are dropped)
me = body.data
_sub = int(args[args.index("--subdiv") + 1]) if "--subdiv" in args else (2 if len(me.polygons) < 40000 else 0)
if _sub:  # low-poly meshes: big faces straddle texture borders, so cut them finer first (weights/UVs interpolate)
    sm_ = body.modifiers.new("sub", "SUBSURF")
    sm_.subdivision_type = "SIMPLE"
    sm_.levels = _sub
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.modifier_move_to_index(modifier="sub", index=0)
    bpy.ops.object.modifier_apply(modifier="sub")
    me = body.data
print("BODY_MW", [list(r) for r in body.matrix_world], "ARM_MW", [list(r) for r in arm.matrix_world])

SLOTS = ["head", "vest", "shirt", "skin", "gloves", "pants", "boots"]
COLORS = {"head": (0.9, 0.75, 0.2), "vest": (0.85, 0.45, 0.1), "shirt": (0.95, 0.95, 0.95), "skin": (0.9, 0.6, 0.5),
          "gloves": (0.2, 0.2, 0.25), "pants": (0.7, 0.1, 0.15), "boots": (0.3, 0.35, 0.2)}
ALLOWED = {"head": ["head"], "torso": ["vest", "shirt", "skin"], "hips": ["pants", "vest", "shirt"],
           "uparm": ["skin", "vest"], "forearm": ["skin", "gloves"], "hand": ["skin", "gloves"], "upleg": ["pants"],
           "lowleg": ["pants", "boots"], "foot": ["boots"]}


def region_of(bone):
    b = bone.lower()
    if b in ("head", "head_end", "headfront", "neck"):
        return "head"
    if any(k in b for k in ("index", "middle", "ring", "pinky", "thumb")) or b.endswith("hand"):
        return "hand"
    if b.endswith("forearm"):
        return "forearm"
    if b.endswith("arm"):
        return "uparm"
    if b.endswith("upleg"):
        return "upleg"
    if b.endswith("leg"):
        return "lowleg"
    if "foot" in b or "toe" in b:
        return "foot"
    if b == "hips":
        return "hips"
    return "torso"


gname = {g.index: g.name for g in body.vertex_groups}
vreg, vbone = [], []
for v in me.vertices:
    best = max(v.groups, key=lambda g: g.weight, default=None)
    bn = gname[best.group] if best else "Spine"
    vbone.append(bn)
    vreg.append(region_of(bn))

# base-colour texture as an array
img = None
for n in me.materials[0].node_tree.nodes:
    if n.type == "TEX_IMAGE" and n.image and ("basecolor" in n.image.name.lower() or img is None):
        img = n.image
W_, H_ = img.size
px = np.empty(W_ * H_ * 4, dtype=np.float32)
img.pixels.foreach_get(px)
px = px.reshape(H_, W_, 4)[:, :, :3]


def srgb_to_lab(rgb):
    # img.pixels are linear for sRGB images in Blender
    c = np.asarray(rgb, dtype=np.float64)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


uv = me.uv_layers.active.data
nf = len(me.polygons)
fcol = np.zeros((nf, 3))
freg = []
fcen = np.zeros((nf, 3))
fnor = np.zeros((nf, 3))
fbone = []
for p in me.polygons:
    samples = [uv[li].uv for li in p.loop_indices]
    cu = sum((s for s in samples), Vector((0, 0))) / len(samples)
    samples.append(cu)
    acc = np.zeros(3)
    for s in samples:
        x = min(W_ - 1, max(0, int((s.x % 1.0) * W_)))
        y = min(H_ - 1, max(0, int((s.y % 1.0) * H_)))
        acc += px[y, x]
    fcol[p.index] = acc / len(samples)
    regs = Counter(vreg[i] for i in p.vertices)
    freg.append(regs.most_common(1)[0][0])
    fbone.append(Counter(vbone[i] for i in p.vertices).most_common(1)[0][0])
    fcen[p.index] = p.center
    fnor[p.index] = p.normal
lab = srgb_to_lab(fcol)
freg = np.array(freg)
fbone = np.array(fbone)


def kmeans(X, k, it=20, seed=0):
    rng = np.random.default_rng(seed)
    k = max(1, min(k, len(X)))
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(it):
        lab_ = np.argmin(((X[:, None] - C[None]) ** 2).sum(-1), 1)
        C = np.array([X[lab_ == j].mean(0) if (lab_ == j).any() else C[j] for j in range(k)])
    sizes = np.bincount(np.argmin(((X[:, None] - C[None]) ** 2).sum(-1), 1), minlength=k)
    return C, sizes


def dist(X, C):
    return np.sqrt(((X[:, None] - C[None]) ** 2).sum(-1)).min(1)


# palettes from faces where the slot is certain (the CoH-style outfit: open vest over a shirt)
pal = {}
if (freg == "head").sum() > 20:  # headless bodies have no head slot
    pal["head"], _ = kmeans(lab[freg == "head"], 4)
chroma = np.hypot(lab[:, 1], lab[:, 2])
fa = (freg == "forearm") & (chroma > 14)
pal["skin"], _ = kmeans(lab[fa if fa.sum() > 50 else (freg == "forearm")], 3)
hand = freg == "hand"
gl = hand & (chroma < 10)
if gl.sum() > 50:
    pal["gloves"], _ = kmeans(lab[gl], 2)
else:
    dh = dist(lab[hand], pal["skin"])
    pal["gloves"], _ = kmeans(lab[hand][dh > np.percentile(dh, 60)], 2)
torso = freg == "torso"
back = torso & (fnor[:, 1] > 0.5)
pal["vest"], _ = kmeans(lab[back], 3)
cx = np.median(fcen[torso, 0])
front_mid = torso & (fnor[:, 1] < -0.5) & (np.abs(fcen[:, 0] - cx) < 0.06)
fm = lab[front_mid]
fm = fm[dist(fm, pal["vest"]) > 18]
pal["shirt"], _ = kmeans(fm if len(fm) > 20 else lab[front_mid], 3)
pal["pants"], _ = kmeans(lab[freg == "upleg"], 3)
pal["boots"], _ = kmeans(lab[freg == "foot"], 3)

label = np.empty(nf, dtype=object)
for r, allowed in ALLOWED.items():
    m = freg == r
    if not m.any():
        continue
    allowed = [s_ for s_ in allowed if s_ in pal] or [s_ for s_ in ALLOWED["torso"] if s_ in pal]
    D = np.stack([dist(lab[m], pal[s_]) for s_ in allowed], 1)
    label[m] = np.array(allowed, dtype=object)[np.argmin(D, 1)]
label[label == None] = "skin"  # noqa: E711
# a sleeveless vest only reaches the armhole: upper-arm faces past the top 20% of the bone are skin
for i in np.where((freg == "uparm") & (label == "vest"))[0]:
    b = arm.data.bones.get(fbone[i])
    if b is None:
        continue
    h, t = np.array(b.head_local), np.array(b.tail_local)
    d = t - h
    if np.dot(fcen[i] - h, d) / np.dot(d, d) > 0.2:
        label[i] = "skin"
# deltoids sit on the shoulder bones: above the armpit and outside the vest's shoulder line they are skin
ua = [arm.data.bones[b].head_local for b in ("LeftArm", "RightArm") if b in arm.data.bones]
if ua:
    sh_x = min(abs(v.x - cx) for v in ua) * 0.77
    pit_z = min(v.z for v in ua) - 0.08
    dl = (label == "vest") & (freg == "torso") & (np.abs(fcen[:, 0] - cx) > sh_x) & (fcen[:, 2] > pit_z)
    label[dl] = "skin"
# the shirt only shows in the vest opening: shirt faces far from the torso centre go to vest/skin
far = (label == "shirt") & (freg == "torso") & (np.abs(fcen[:, 0] - cx) > 0.13)
if far.any():
    D = np.stack([dist(lab[far], pal["vest"]), dist(lab[far], pal["skin"])], 1)
    label[far] = np.array(["vest", "skin"], dtype=object)[np.argmin(D, 1)]

# face adjacency (shared edges) for smoothing
bm = bmesh.new()
bm.from_mesh(me)
bm.faces.ensure_lookup_table()
nbr = [[f2.index for e in f.edges for f2 in e.link_faces if f2.index != f.index] for f in bm.faces]
bm.free()
for _ in range(3):
    new = label.copy()
    for i in range(nf):
        c = Counter(label[j] for j in nbr[i])
        if c:
            top, cnt = c.most_common(1)[0]
            if top != label[i] and cnt >= 2 and top in ALLOWED[freg[i]] + ["head"] * (freg[i] == "head"):
                new[i] = top
    label = new
# small islands -> neighbouring majority
seen = np.zeros(nf, bool)
for i in range(nf):
    if seen[i]:
        continue
    comp, stack = [], [i]
    seen[i] = True
    while stack:
        f = stack.pop()
        comp.append(f)
        for j in nbr[f]:
            if not seen[j] and label[j] == label[i]:
                seen[j] = True
                stack.append(j)
    if len(comp) < max(40, nf // 1200):
        cs = set(comp)
        c = Counter(label[j] for f in comp for j in nbr[f] if j not in cs)
        if c:
            label[comp] = c.most_common(1)[0][0]


def components(lbl):
    seen_ = np.zeros(nf, bool)
    comps = []
    for i in range(nf):
        if seen_[i] or label[i] != lbl:
            continue
        comp, stack = [], [i]
        seen_[i] = True
        while stack:
            f = stack.pop()
            comp.append(f)
            for j in nbr[f]:
                if not seen_[j] and label[j] == lbl:
                    seen_[j] = True
                    stack.append(j)
        comps.append(comp)
    return comps


# one-piece garments keep only their main pieces; stray islands join their neighbours
for lbl in ("vest", "shirt", "pants", "head"):
    comps = sorted(components(lbl), key=len, reverse=True)
    if not comps:
        continue
    keep = len(comps[0]) * 0.15
    for comp in comps[1:]:
        if len(comp) < keep:
            cs = set(comp)
            c = Counter(label[j] for f in comp for j in nbr[f] if j not in cs and label[j] != lbl)
            if c:
                label[comp] = c.most_common(1)[0][0]
counts = {s_: int((label == s_).sum()) for s_ in SLOTS}
print("SLOT_FACES", counts)

# one mesh per slot (copies keep the armature modifier, parent and weights)
parts = {}
for s_ in SLOTS:
    if counts[s_] == 0:
        continue
    o = body.copy()
    o.data = body.data.copy()
    o.name = "%s_%s" % (name, s_)
    o.data.name = o.name
    bpy.context.scene.collection.objects.link(o)
    bmx = bmesh.new()
    bmx.from_mesh(o.data)
    bmx.faces.ensure_lookup_table()
    bmesh.ops.delete(bmx, geom=[f for f in bmx.faces if label[f.index] != s_], context="FACES")
    bmx.to_mesh(o.data)
    bmx.free()
    parts[s_] = o
bpy.data.objects.remove(body, do_unlink=True)

bpy.ops.object.select_all(action="DESELECT")
arm.select_set(True)
for o in parts.values():
    o.select_set(True)
bpy.ops.export_scene.gltf(filepath=os.path.join(out, name + "_split.glb"), use_selection=True, export_format="GLB")
json.dump({"faces": counts, "palettes": {k: v.round(1).tolist() for k, v in pal.items()}},
          open(os.path.join(out, name + "_split.json"), "w"), indent=1)

if "--render" in args:
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 900, 1200
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.2158, 0.2158, 0.2158, 1)
    for nm, rot, e in (("K", (50, 0, -35), 3.0), ("F", (60, 0, 50), 1.5), ("B", (60, 0, 170), 1.5)):
        ld = bpy.data.lights.new(nm, "SUN")
        ld.energy = e
        lo_ = bpy.data.objects.new(nm, ld)
        sc.collection.objects.link(lo_)
        lo_.rotation_euler = [math.radians(a) for a in rot]
    cd = bpy.data.cameras.new("C")
    cd.type = "ORTHO"
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    ang = math.radians(25)

    def shoot(path, scale, zc):
        cd.ortho_scale = scale
        cam.location = (math.sin(ang) * 6, -math.cos(ang) * 6, zc)
        cam.rotation_euler = (math.pi / 2, 0, ang)
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)

    mats = {}
    for s_, o in parts.items():
        m = bpy.data.materials.new("slot_" + s_)
        m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = COLORS[s_] + (1,)
        mats[s_] = m
        o["tex_mats"] = 0
    orig = {s_: [ms for ms in o.data.materials] for s_, o in parts.items()}
    for s_, o in parts.items():
        o.data.materials.clear()
        o.data.materials.append(mats[s_])
    shoot(os.path.join(out, name + "_slots.png"), 2.1, 0.92)
    for s_, o in parts.items():
        o.data.materials.clear()
        for ms in orig[s_]:
            o.data.materials.append(ms)
    # exploded: move each slot (and each side of paired slots) away from the body
    base = {"head": (0, 0, 0.32), "vest": (0, 0.0, 0.12), "shirt": (0, -0.45, 0.08), "skin": (0, 0, 0.0),
            "gloves": (0, 0, -0.05), "pants": (0, 0, -0.18), "boots": (0, 0, -0.38)}
    lateral = {"skin": 0.32, "gloves": 0.55, "boots": 0.12, "pants": 0.0, "vest": 0.0, "shirt": 0.0, "head": 0.0}
    for s_, o in parts.items():
        bx = bmesh.new()
        bx.from_mesh(o.data)
        islands, seenv = [], set()
        for v in bx.verts:
            if v in seenv:
                continue
            isl, st = [], [v]
            seenv.add(v)
            while st:
                a = st.pop()
                isl.append(a)
                for e in a.link_edges:
                    b = e.other_vert(a)
                    if b not in seenv:
                        seenv.add(b)
                        st.append(b)
            islands.append(isl)
        for isl in islands:
            cxi = sum(v.co.x for v in isl) / len(isl)
            off = Vector(base[s_]) + Vector((math.copysign(lateral[s_], cxi) if abs(cxi) > 0.05 else 0, 0, 0))
            for v in isl:
                v.co += off
        bx.to_mesh(o.data)
        bx.free()
    shoot(os.path.join(out, name + "_exploded.png"), 2.9, 0.85)
print("SPLIT_OK", json.dumps(counts))

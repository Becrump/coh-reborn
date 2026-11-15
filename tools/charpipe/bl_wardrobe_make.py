"""Turn kitbash clothing pieces into reusable wardrobe items on the shared skeleton (Blender).

    blender -b --factory-startup -P bl_wardrobe_make.py -- <rigged_body.glb> <pieces_dir> <wardrobe_dir> <group>
            --pieces name:slot[:socket][,...] [--source "<text>"] [--shift-y 0.0015]

<pieces_dir>/<name>.glb are the clothing meshes, already in the rigged body's space (bl_kitbash_export.py).
Per piece:
  * gloves (slot "hands"): a flat pair is split into left/right and each glove is fitted onto its
    hand (centroid + principal axes + scale, best of the 4 proper axis flips by chamfer distance)
  * socket pieces (e.g. head gear): skinned 100 % to the socket bone (rigid, like an Unreal socket)
  * other pieces: skin weights copied from the body (nearest surface, interpolated), then smoothed
  * body-hide mask: body vertices the piece covers (the cloth lies within 4 cm along the skin normal,
    or the skin is inside the cloth); stored as vertex indices of the base body and as covered bones
  * writes <wardrobe_dir>/<slot>/<name>.glb (armature + piece) and updates <wardrobe_dir>/wardrobe.json
The base body itself is saved as <wardrobe_dir>/body/base.glb with the same skeleton.
"""
import json
import math
import os
import sys
from itertools import product

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

a = sys.argv[sys.argv.index("--") + 1:]
BODY, PDIR, WDIR, GROUP = a[:4]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
PIECES = [p.split(":") for p in opt("--pieces").split(",")]
SOURCE = opt("--source", "Tripo part export")
SHIFT = Vector((0, float(opt("--shift-y", 0)), 0))
os.makedirs(WDIR, exist_ok=True)


def load_body():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=BODY)
    for o in list(bpy.data.objects):
        if o.name.startswith("Icosphere"):
            bpy.data.objects.remove(o, do_unlink=True)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    body = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    return arm, body


def import_piece(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    ms = [o for o in new if o.type == "MESH"]
    for o in new:
        if o not in ms:
            bpy.data.objects.remove(o, do_unlink=True)
    for o in ms:
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(Matrix.Translation(SHIFT) @ mw)
        o.matrix_world = Matrix.Identity(4)
    if len(ms) > 1:
        for x in bpy.context.view_layer.objects:
            x.select_set(False)
        for o in ms:
            o.select_set(True)
        bpy.context.view_layer.objects.active = ms[0]
        bpy.ops.object.join()
    return ms[0]


def wcols(obj):
    names = [g.name for g in obj.vertex_groups]
    W = np.zeros((len(obj.data.vertices), len(names)))
    for v in obj.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    return names, W


def pca_frame(P):
    c = P.mean(0)
    U, s, Vt = np.linalg.svd(P - c, full_matrices=False)
    return c, Vt, s


def fit_gloves(piece, body, arm):
    """Split the pair into two loose parts and fit each onto a hand."""
    bm = bmesh.new()
    bm.from_mesh(piece.data)
    bm.verts.ensure_lookup_table()
    seen, parts = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        st, comp = [v], []
        seen.add(v.index)
        while st:
            x = st.pop()
            comp.append(x.index)
            for e in x.link_edges:
                y = e.other_vert(x)
                if y.index not in seen:
                    seen.add(y.index)
                    st.append(y)
        parts.append(comp)
    bm.free()
    parts.sort(key=len, reverse=True)
    co = np.array([v.co[:] for v in piece.data.vertices])
    # whole loose parts go to one of two gloves: 2-means on the part centroids (size-weighted)
    cents = np.array([co[c].mean(0) for c in parts])
    sizes = np.array([len(c) for c in parts], float)
    ax = int(np.argmax(np.ptp(cents if len(cents) > 1 else co, 0)))
    ka, kb = cents[0], cents[np.argmax(np.linalg.norm(cents - cents[0], axis=1))]
    for _ in range(20):
        lab = np.linalg.norm(cents - ka, axis=1) > np.linalg.norm(cents - kb, axis=1)
        if lab.all() or (~lab).all():
            break
        ka = np.average(cents[~lab], 0, sizes[~lab])
        kb = np.average(cents[lab], 0, sizes[lab])
    if lab.all() or (~lab).all():  # one connected piece: fall back to a split along the widest axis
        mid = np.median(co[:, ax])
        groups = {"A": np.nonzero(co[:, ax] < mid)[0], "B": np.nonzero(co[:, ax] >= mid)[0]}
    else:
        groups = {"A": np.array([i for c, l in zip(parts, lab) if not l for i in c]),
                  "B": np.array([i for c, l in zip(parts, lab) if l for i in c])}
    names, W = wcols(body)
    bco = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices])
    rep = {}
    hands = {}
    for S in ("Left", "Right"):
        cols = [i for i, n in enumerate(names) if n.startswith(S) and (n.endswith("Hand") or any(f in n for f in ("Thumb", "Index", "Middle", "Ring", "Pinky")))]
        hw = W[:, cols].sum(1)
        wrist = np.array((arm.matrix_world @ arm.data.bones[S + "Hand"].head_local)[:])
        fa = names.index(S + "ForeArm") if S + "ForeArm" in names else None
        cuff = (W[:, fa] > 0.3) & (np.linalg.norm(bco - wrist, axis=1) < 0.08) if fa is not None else np.zeros(len(bco), bool)
        hands[S] = bco[(hw > 0.5) | cuff]
    # assign glove groups to hands by x side
    gA, gB = groups["A"], groups["B"]
    # the glove whose thumb side... unknown for a flat pair: try both assignments, keep the better fit
    def kdt(P):
        k = KDTree(len(P))
        for i, p in enumerate(P):
            k.insert(p, i)
        k.balance()
        return k

    def fit(G, H, kdH):
        cg, Vg, sg = pca_frame(G)
        ch, Vh, sh = pca_frame(H)
        scale = (np.ptp((H - ch) @ Vh[0]) / max(np.ptp((G - cg) @ Vg[0]), 1e-6)) * 1.08
        best = None
        Hs = H[:: max(1, len(H) // 250)]
        for sx, sy in product((1, -1), (1, -1)):
            Rg = Vg.copy()
            Rg[0] *= sx
            Rg[1] *= sy
            Rg[2] = np.cross(Rg[0], Rg[1])
            R = Vh.T @ Rg  # glove frame -> hand frame
            P = (G - cg) @ R.T * scale + ch
            kdP = kdt(P[:: max(1, len(P) // 1500)])
            d = 0.5 * (np.mean([kdP.find(p)[2] for p in Hs]) + np.mean([kdH.find(p)[2] for p in P[:: max(1, len(P) // 250)]]))
            if best is None or d < best[0]:
                best = (d, P, scale)
        return best

    kds = {S: kdt(hands[S]) for S in hands}
    tries = []
    for order in ({"Left": gA, "Right": gB}, {"Left": gB, "Right": gA}):
        res = {S: fit(co[idx], hands[S], kds[S]) for S, idx in order.items()}
        tries.append((sum(r[0] for r in res.values()), order, res))
    tot, order, res = min(tries, key=lambda t: t[0])
    newco = co.copy()
    for S, idx in order.items():
        d, P, scale = res[S]
        newco[idx] = P
        rep[S] = {"verts": int(len(idx)), "scale": round(float(scale), 3), "chamfer_cm": round(d * 100, 2)}
    for v, p in zip(piece.data.vertices, newco):
        v.co = Vector(p)
    piece.data.update()
    return rep


def transfer_weights(piece, body):
    for g in body.vertex_groups:
        piece.vertex_groups.new(name=g.name)
    dt = piece.modifiers.new("dt", "DATA_TRANSFER")
    dt.object = body
    dt.use_vert_data = True
    dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src = "ALL"
    dt.layers_vgroup_select_dst = "NAME"
    bpy.context.view_layer.objects.active = piece
    bpy.ops.object.modifier_apply(modifier="dt")
    # smooth + max 4 influences
    names, W = wcols(piece)
    E = np.array([e.vertices[:] for e in piece.data.edges]) if len(piece.data.edges) else np.zeros((0, 2), int)
    for _ in range(2):
        S = np.zeros_like(W)
        C = np.zeros(len(W))
        np.add.at(S, E[:, 0], W[E[:, 1]])
        np.add.at(S, E[:, 1], W[E[:, 0]])
        np.add.at(C, E[:, 0], 1)
        np.add.at(C, E[:, 1], 1)
        W = 0.5 * W + 0.5 * S / np.maximum(C, 1)[:, None]
    order = np.argsort(-W, 1)
    keep = np.zeros_like(W, bool)
    np.put_along_axis(keep, order[:, :4], True, 1)
    W[~keep] = 0
    W[W < 0.01] = 0
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    for g in piece.vertex_groups:
        g.remove(list(range(len(W))))
    for j, n in enumerate(names):
        g = piece.vertex_groups[n]
        for i in np.nonzero(W[:, j])[0]:
            g.add([int(i)], float(W[i, j]), "REPLACE")


def rigid(piece, bone):
    piece.vertex_groups.clear()
    piece.vertex_groups.new(name=bone).add(list(range(len(piece.data.vertices))), 1.0, "REPLACE")


def hide_mask(piece, body):
    verts = [piece.matrix_world @ v.co for v in piece.data.vertices]
    tree = BVHTree.FromPolygons(verts, [tuple(p.vertices) for p in piece.data.polygons])
    M = body.matrix_world
    N3 = M.to_3x3().inverted().transposed()
    names, W = wcols(body)
    covered = []
    for v in body.data.vertices:
        p = M @ v.co
        n = (N3 @ v.normal).normalized()
        hit = tree.ray_cast(p + n * 0.0005, n, 0.04)
        if hit[0] is not None:
            covered.append(v.index)
    covered = np.array(covered, int)
    bones = {}
    if len(covered):
        dom = W[covered].argmax(1)
        tot = np.bincount(W.argmax(1), minlength=len(names))
        cnt = np.bincount(dom, minlength=len(names))
        bones = {names[i]: round(float(cnt[i] / tot[i]), 2) for i in range(len(names)) if cnt[i] and cnt[i] / max(tot[i], 1) > 0.3}
    return covered.tolist(), bones


def save(arm, piece, path):
    piece.parent = arm
    m = piece.modifiers.new("Armature", "ARMATURE")
    m.object = arm
    for x in bpy.context.view_layer.objects:
        x.select_set(False)
    arm.select_set(True)
    piece.select_set(True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)


jp = os.path.join(WDIR, "wardrobe.json")
wd = json.load(open(jp)) if os.path.exists(jp) else {"group": GROUP, "skeleton": "charpipe 24-bone + 30 fingers", "body": {}, "items": {}}
arm, body = load_body()
for x in bpy.context.view_layer.objects:
    x.select_set(False)
arm.select_set(True)
body.select_set(True)
os.makedirs(os.path.join(WDIR, "body"), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=os.path.join(WDIR, "body", "base.glb"), export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
wd["body"]["base"] = {"file": "body/base.glb", "verts": len(body.data.vertices), "source": BODY}
for spec in PIECES:
    name, slot = spec[0], spec[1]
    socket = spec[2] if len(spec) > 2 else None
    arm, body = load_body()
    piece = import_piece(os.path.join(PDIR, name + ".glb"))
    piece.name = name
    info = {"slot": slot, "socket": socket, "source": SOURCE, "file": "%s/%s.glb" % (slot, name)}
    if slot == "hands":
        info["fit"] = fit_gloves(piece, body, arm)
    if socket:
        rigid(piece, socket)
    else:
        transfer_weights(piece, body)
    cov, bones = hide_mask(piece, body)
    info["hides_body_verts"] = cov
    info["covers_bones"] = bones
    save(arm, piece, os.path.join(WDIR, slot, name + ".glb"))
    wd["items"][name] = info
    print("WARDROBE_ITEM", name, slot, socket or "", "covers", len(cov), "verts", bones)
json.dump(wd, open(jp, "w"), indent=1)
print("WARDROBE_OK", len(PIECES))

"""Polish the skin weights of a charpipe rig for game use (Blender).

    blender -b --factory-startup -P bl_weight_polish.py -- <rigged.glb> <out.glb> [--cut-above Z] [--report r.json]

 * --cut-above Z: delete vertices above Z (the temporary proxy head of a headless body); their
   Head weights are folded into neck so the stump follows the neck.
 * fingers/knuckles: 3 Laplacian smoothing passes of the hand + finger weights over the mesh
   edges (hand vertices only), so the knuckles fold round instead of blocky.
 * wrist twist: the distal 45 % of each forearm blends up to 35 % into the hand, so a twisted
   wrist spreads over the forearm instead of pinching (no extra twist bones: the skeleton stays
   the shared one).
 * shoulders: one smoothing pass over Shoulder/Arm/Spine weights on the shoulder vertices.
 * every vertex keeps at most 4 influences, normalised (Unreal default).
"""
import json
import sys

import bmesh
import bpy
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
src, dst = a[0], a[1]
CUT = float(a[a.index("--cut-above") + 1]) if "--cut-above" in a else None
rep = {}
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = max((o for o in bpy.data.objects if o.type == "MESH" and o.vertex_groups), key=lambda o: len(o.data.vertices))
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
me = body.data
names = [g.name for g in body.vertex_groups]
gi = {n: i for i, n in enumerate(names)}

if CUT is not None:
    bm = bmesh.new()
    bm.from_mesh(me)
    kill = [v for v in bm.verts if (body.matrix_world @ v.co).z > CUT]
    rep["proxy_verts_removed"] = len(kill)
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()

nv = len(me.vertices)
W = np.zeros((nv, len(names)))
for v in me.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
if CUT is not None and "Head" in gi and "neck" in gi:
    for n in ("Head", "head_end", "headfront"):
        if n in gi:
            W[:, gi["neck"]] += W[:, gi[n]]
            W[:, gi[n]] = 0
if CUT is not None and "neck" in gi and "Spine" in gi:
    # headless stump: the proxy head pulled the collar onto neck/Head; keep the collar on the chest,
    # with at most 50 % neck at the very top fading to 0 % 10 cm below the cut
    zc = np.array([(body.matrix_world @ v.co).z for v in me.vertices])
    band = zc > CUT - 0.10
    cap = 0.5 * np.clip((zc - (CUT - 0.10)) / 0.10, 0, 1)
    nk = W[:, gi["neck"]]
    over = band & (nk > cap)
    W[over, gi["Spine"]] += nk[over] - cap[over]
    W[over, gi["neck"]] = cap[over]
    rep["stump_collar_verts"] = int(over.sum())
E = np.array([e.vertices[:] for e in me.edges])
co = np.array([(body.matrix_world @ v.co)[:] for v in me.vertices])
# vertices the autorig left unweighted come back from glTF bound to "neutral_bone" (never moves):
# give each the weights of its nearest properly weighted vertex
if "neutral_bone" in gi:
    W[:, gi["neutral_bone"]] = 0
orph = W.sum(1) < 1e-6
rep["orphans_fixed"] = int(orph.sum())
if orph.any() and (~orph).any():
    from mathutils.kdtree import KDTree
    good = np.nonzero(~orph)[0]
    kd = KDTree(len(good))
    for k, i in enumerate(good):
        kd.insert(co[i], k)
    kd.balance()
    for i in np.nonzero(orph)[0]:
        _, k, _ = kd.find(co[i])
        W[i] = W[good[k]]


def smooth(cols, mask, passes):
    """Laplacian smoothing of weight columns `cols`, only for vertices in mask (others fixed)."""
    cols = [c for c in cols if c is not None]
    if not cols or not mask.any():
        return
    for _ in range(passes):
        S = np.zeros((nv, len(cols)))
        C = np.zeros(nv)
        np.add.at(S, E[:, 0], W[E[:, 1]][:, cols])
        np.add.at(S, E[:, 1], W[E[:, 0]][:, cols])
        np.add.at(C, E[:, 0], 1)
        np.add.at(C, E[:, 1], 1)
        avg = S / np.maximum(C, 1)[:, None]
        tot_before = W[mask][:, cols].sum(1, keepdims=True)
        new = 0.5 * W[mask][:, cols] + 0.5 * avg[mask]
        # keep the hand+finger share of each vertex the same (only redistribute between them)
        new *= tot_before / np.maximum(new.sum(1, keepdims=True), 1e-9)
        sub = W[mask]
        sub[:, cols] = new
        W[mask] = sub


FING = ("Thumb", "Index", "Middle", "Ring", "Pinky")
for S in ("Left", "Right"):
    hand = [gi.get(S + "Hand")] + [gi[n] for n in names if n.startswith(S) and any(f in n for f in FING)]
    hand = [c for c in hand if c is not None]
    if len(hand) > 1:
        mask = W[:, hand].sum(1) > 0.05
        smooth(hand, mask, 3)
        rep[S + "_hand_verts_smoothed"] = int(mask.sum())
    # wrist twist spread
    fa, hd = gi.get(S + "ForeArm"), gi.get(S + "Hand")
    if fa is not None and hd is not None:
        b = arm.data.bones[S + "ForeArm"]
        h = np.array((arm.matrix_world @ b.head_local)[:])
        t = np.array((arm.matrix_world @ b.tail_local)[:])
        d = t - h
        u = ((co - h) @ d) / (d @ d)
        m = (W[:, fa] > 0.5) & (u > 0.55) & (u <= 1.05)
        share = 0.35 * np.clip((u[m] - 0.55) / 0.45, 0, 1)
        moved = W[m, fa] * share
        W[m, fa] -= moved
        W[m, hd] += moved
        rep[S + "_twist_verts"] = int(m.sum())
    sh = [gi.get(n) for n in (S + "Shoulder", S + "Arm", "Spine")]
    sh = [c for c in sh if c is not None]
    if len(sh) > 1:
        mask = W[:, sh].sum(1) > 0.3
        if S + "Shoulder" in gi:
            mask &= W[:, gi[S + "Shoulder"]] > 0.05
        smooth(sh, mask, 1)

# max 4 influences, normalised
order = np.argsort(-W, 1)
keep = np.zeros_like(W, dtype=bool)
np.put_along_axis(keep, order[:, :4], True, 1)
W[~keep] = 0
W[W < 0.01] = 0
W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
for g in body.vertex_groups:
    g.remove(list(range(nv)))
for j, n in enumerate(names):
    idx = np.nonzero(W[:, j])[0]
    g = body.vertex_groups[n]
    for i in idx:
        g.add([int(i)], float(W[i, j]), "REPLACE")
rep["max_influences"] = int((W > 0).sum(1).max())
if "neutral_bone" in arm.data.bones:
    if "neutral_bone" in body.vertex_groups:
        body.vertex_groups.remove(body.vertex_groups["neutral_bone"])
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    arm.data.edit_bones.remove(arm.data.edit_bones["neutral_bone"])
    bpy.ops.object.mode_set(mode="OBJECT")
for o in [o for o in bpy.data.objects if o.type == "MESH" and o is not body]:
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
print("POLISH_OK", json.dumps(rep))
if "--report" in a:
    json.dump(rep, open(a[a.index("--report") + 1], "w"), indent=1)

"""Add finger bones + skin weights to a 24-bone (Meshy-family) rig (Blender).

    blender -b --factory-startup -P bl_fingers.py -- <rigged.glb> <out.glb> [--report r.json]

Meshy and charpipe rigs stop at the hand, so fists can't close. Per hand this adds a thumb and
four fingers, 3 bones each: Left/Right{Thumb,Index,Middle,Ring,Pinky}{1,2,3}, parented to the
hand. They are fitted to the hand mesh: the hand's long axis, width and palm direction come from
a PCA of the vertices skinned to the hand bone; knuckles sit at 48% of the hand length; the thumb
starts near the wrist on the thumb side (forward). Every finger bone's local Z points the way the
palm faces, so a positive rotation about local X curls the finger into a fist; retarget2.py uses
that to play CoH finger curls (RING/F2/F1, T3/T2/T1) or a constant fist.
Weights: each hand vertex past the palm goes to its nearest finger segment, blended with the hand
over the first part of the finger, so even fused "mitten" fingers fold into a fist.
"""
import json
import sys

import bpy
import numpy as np
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
src, dst = args[0], args[1]
rep_path = args[args.index("--report") + 1] if "--report" in args else None
rep = {"source": src, "hands": {}}
FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = next(o for o in bpy.data.objects if o.type == "MESH" and o.vertex_groups)
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
AW = arm.matrix_world
BW = body.matrix_world
co = np.array([tuple(BW @ v.co) for v in body.data.vertices], np.float64)
gidx = {g.name: g.index for g in body.vertex_groups}
center = Vector(co.mean(0).tolist())


def weights_of(name):
    gi = gidx.get(name)
    w = np.zeros(len(co))
    if gi is None:
        return w
    for v in body.data.vertices:
        for g in v.groups:
            if g.group == gi:
                w[v.index] = g.weight
    return w


plan = {}
for S in ("Left", "Right"):
    hb = arm.data.bones.get(S + "Hand")
    if hb is None:
        continue
    wh = weights_of(S + "Hand")
    sel = wh > 0.35
    if sel.sum() < 30:
        rep["hands"][S] = "too few hand vertices (%d), skipped" % int(sel.sum())
        continue
    P = co[sel]
    wrist = np.array(tuple(AW @ hb.head_local))
    fore = np.array(tuple(AW @ hb.parent.head_local)) if hb.parent else wrist - np.array([0, 0, 0.2])
    m = P.mean(0)
    U, s_, Vt = np.linalg.svd(P - m, full_matrices=False)
    ax = Vt[0] if np.dot(Vt[0], wrist - fore) > 0 else -Vt[0]
    proj = (P - wrist) @ ax
    L = float(np.percentile(proj, 99))
    tip_c = wrist + ax * L
    # width / palm axes from the remaining two principal axes (width = larger extent)
    a1, a2 = Vt[1], Vt[2]
    e1 = np.ptp((P - m) @ a1)
    e2 = np.ptp((P - m) @ a2)
    wid, nrm = (a1, a2) if e1 >= e2 else (a2, a1)
    wid = wid - ax * np.dot(wid, ax)
    wid /= np.linalg.norm(wid)
    nrm = np.cross(ax, wid)
    # palm faces down in a T-pose, toward the body when arms hang down
    pref = np.array([0, 0, -1.0]) if abs(ax[2]) < 0.6 else np.array(tuple(center)) - wrist
    pref[2] = pref[2] if abs(ax[2]) < 0.6 else 0
    if np.dot(nrm, pref) < 0:
        nrm = -nrm
    # thumb side points forward (-Y)
    if np.dot(wid, [0, -1, 0]) < 0:
        wid = -wid
    W = float(np.percentile((P - wrist) @ wid, 95) - np.percentile((P - wrist) @ wid, 5))
    T = float(np.percentile((P - wrist) @ nrm, 95) - np.percentile((P - wrist) @ nrm, 5))
    plan[S] = dict(wrist=wrist, ax=ax, wid=wid, nrm=nrm, L=L, W=W, T=T, sel=sel, wh=wh)
    rep["hands"][S] = {"verts": int(sel.sum()), "length_cm": round(L * 100, 1), "width_cm": round(W * 100, 1)}

bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
EB = arm.data.edit_bones
inv = AW.inverted()
segs = {}
for S, p in plan.items():
    wrist, ax, wid, nrm, L, W = p["wrist"], p["ax"], p["wid"], p["nrm"], p["L"], p["W"]
    knuck = wrist + ax * L * 0.48
    for fi, F in enumerate(FINGERS):
        if F == "Thumb":
            root = wrist + ax * L * 0.18 + wid * W * 0.38 + p["nrm"] * p["T"] * 0.15
            d = ax * 0.55 + wid * 0.75
            d /= np.linalg.norm(d)
            flen = L * 0.48
            parts = (0.38, 0.32, 0.30)
        else:
            k = fi - 1  # index .. pinky across the width, thumb side first
            root = knuck + wid * W * (0.33 - 0.22 * k)
            d = ax
            flen = L * 0.52 * (1.0, 1.06, 1.0, 0.82)[k]
            parts = (0.45, 0.30, 0.25)
        prev = None
        h = root.copy()
        for j in range(3):
            t = h + d * flen * parts[j]
            name = "%s%s%d" % (S, F, j + 1)
            b = EB.new(name)
            b.head, b.tail = inv @ Vector(h.tolist()), inv @ Vector(t.tolist())
            b.parent = prev or EB[S + "Hand"]
            b.use_deform = True
            b.align_roll(inv.to_3x3() @ Vector(nrm.tolist()))
            segs[name] = (h.copy(), t.copy(), S, F, j)
            prev = b
            h = t
bpy.ops.object.mode_set(mode="OBJECT")


def segdist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(np.dot(ab, ab), 1e-9), 0, 1)
    return np.linalg.norm(P - (a + np.outer(t, ab)), axis=1), t


for S, p in plan.items():
    idx = np.nonzero(p["wh"] > 0.0)[0]
    P = co[idx]
    names = [n for n, s in segs.items() if s[2] == S]
    D = np.stack([segdist(P, segs[n][0], segs[n][1])[0] for n in names], 1)
    # palm pseudo-segment: wrist -> knuckle centre, keeps the palm on the hand bone
    palm_d, _ = segdist(P, p["wrist"], p["wrist"] + p["ax"] * p["L"] * 0.45)
    best = D.argmin(1)
    bestd = D[np.arange(len(P)), best]
    moved = 0
    for g in names:
        if g not in gidx:
            gidx[g] = body.vertex_groups.new(name=g).index
    hand_vg = body.vertex_groups[S + "Hand"]
    for r, vi in enumerate(idx):
        if palm_d[r] < bestd[r] * 0.9:
            continue
        n = names[best[r]]
        h, t, _, F, j = segs[n]
        if j == 0:  # blend into the hand over the first 40% of the base segment
            _, tt = segdist(P[r:r + 1], h, t)
            s = float(np.clip(tt[0] / 0.4, 0, 1))
        else:
            s = 1.0
        if s <= 0:
            continue
        wh = p["wh"][vi]
        body.vertex_groups[n].add([int(vi)], wh * s, "REPLACE")
        hand_vg.add([int(vi)], wh * (1 - s), "REPLACE")
        moved += 1
    rep["hands"][S]["finger_weighted_verts"] = moved

bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
rep["bones_added"] = len(segs)
print("FINGERS", json.dumps(rep))
if rep_path:
    json.dump(rep, open(rep_path, "w"), indent=1)

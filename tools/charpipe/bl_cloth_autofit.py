"""Fit separately generated (each normalised to 1 unit) Tripo clothing pieces onto a rigged base body (Blender).

    blender -b --factory-startup -P bl_cloth_autofit.py -- <rigged_body.glb> <out_dir> name=<file>[:slot] [...] [--gap 0.006]

Slot from the name unless given: legs (jeans, cargo, pants, trousers, shorts), torso (shirt, tshirt, tee,
undershirt, tank, vest), outer (jacket, longjacket, hoody, hoodie, coat, trench), feet (boots, shoes, sneakers).
Fit (all uniform scales, so garment proportions survive):
  legs   : waist width (top 8 % slab) -> body hip width at the waist, top at the waist (Hips + 6 cm);
           then the height is set waist -> ankle (only z re-scaled) so hems end at the ankle
  torso  : chest width at 70 % of its height -> body chest width there, collar at the neck base
  outer  : same as torso, sleeves included (best when the piece was generated in the body's pose)
  feet   : the pair is split into two boots (2-means on loose parts), each scaled by length to its foot,
           sole on the ground, centred on the foot
Then cloth vertices that end up inside the body are pushed out to --gap above the skin.
Writes <out_dir>/<name>.glb (in the body's space, ready for bl_wardrobe_make.py) and autofit.json.
"""
import json
import os
import re
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

a = sys.argv[sys.argv.index("--") + 1:]
BODY, OUT = a[0], a[1]
GAP = float(a[a.index("--gap") + 1]) if "--gap" in a else 0.006
ITEMS = [x for x in a[2:] if "=" in x and not x.startswith("--")]
os.makedirs(OUT, exist_ok=True)
RULES = [("outer", r"longjacket|jacket|hood|coat|trench"), ("legs", r"jean|cargo|pant|trouser|short"),
         ("feet", r"boot|shoe|sneaker"), ("torso", r"shirt|tee|tank|vest")]


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


def imp(path):
    before = set(bpy.data.objects)
    if path.lower().endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    ms = [o for o in new if o.type == "MESH" and not o.name.startswith("Icosphere")]
    for o in new:
        if o not in ms:
            bpy.data.objects.remove(o, do_unlink=True)
    for o in ms:
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw)
        o.matrix_world = Matrix.Identity(4)
    for x in bpy.data.objects:
        if x.name in bpy.context.view_layer.objects:
            x.select_set(False)
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def slab_width(P, z, dz, xmax=None, cx=0.0):
    s = P[np.abs(P[:, 2] - z) < dz]
    if xmax is not None:
        s = s[np.abs(s[:, 0] - cx) < xmax]
    if len(s) < 5:
        return None, None
    return np.ptp(s[:, 0]), s.mean(0)


rep = {}
for spec in ITEMS:
    name, rest = spec.split("=", 1)
    path, _, slot = rest.partition("|")
    slot = slot or next((s for s, rx in RULES if re.search(rx, name.lower())), "torso")
    arm, body = load_body()
    W = arm.matrix_world
    J = lambda n: np.array((W @ arm.data.bones[n].head_local)[:])  # noqa: E731
    BV = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices])
    gname = [g.name for g in body.vertex_groups]
    dom = np.array([gname[max(v.groups, key=lambda g: g.weight).group] if v.groups else "" for v in body.data.vertices])
    torso_m = np.array([d in ("Hips", "Spine02", "Spine01", "Spine", "neck", "LeftShoulder", "RightShoulder") for d in dom])
    P = imp(path)
    P.name = name
    co = np.array([v.co[:] for v in P.data.vertices])
    lo, hi = co.min(0), co.max(0)
    h = hi[2] - lo[2]
    cx = (lo[0] + hi[0]) / 2
    if slot == "legs":
        wz = J("Hips")[2] + 0.06
        az = J("LeftFoot")[2] + 0.02
        bw, bc = slab_width(BV[torso_m | np.char.endswith(dom.astype(str), "UpLeg")], wz, 0.025)
        pw, pc = slab_width(co, hi[2] - 0.04 * h, 0.04 * h)
        k = bw * 1.04 / pw
        kz = (wz - az) / h
        M = Matrix.Translation(Vector((bc[0], bc[1], az))) @ Matrix.Diagonal((k, k, kz, 1)) @ Matrix.Translation(Vector((-pc[0], -pc[1], -lo[2])))
    elif slot in ("torso", "outer"):
        # uniform scale from the garment length: collar at the neck base, hem at the hips (shirts, jackets,
        # hoodies) or at the knees (long coats / trench), centred on the torso
        nz = J("neck")[2] + (0.04 if slot == "outer" else 0.015)
        longc = re.search(r"long|trench|coat|duster", name.lower()) is not None
        hem = J("LeftLeg")[2] + 0.02 if longc else J("Hips")[2] - 0.05
        k = (nz - hem) / h
        bc = BV[torso_m].mean(0)
        top = co[co[:, 2] > hi[2] - 0.1 * h]
        tc = top.mean(0)
        # width: the torso part of the chest slab (the x-cluster around the centre, sleeves excluded) must
        # wrap the body's chest; never narrower than the body
        cz_b = J("Spine")[2]
        bw = np.ptp(BV[torso_m & (np.abs(BV[:, 2] - cz_b) < 0.03)][:, 0])
        cz_p = hi[2] - (nz - cz_b) / k
        sl = np.sort(co[np.abs(co[:, 2] - cz_p) < 0.02 * h][:, 0])
        kx = k
        if len(sl) > 10:
            gaps = np.nonzero(np.diff(sl) > 0.01 * h)[0]
            edges = np.concatenate([[0], gaps + 1, [len(sl)]])
            for e0, e1 in zip(edges[:-1], edges[1:]):
                w_c = sl[e1 - 1] - sl[e0]
                if sl[e0] <= cx <= sl[e1 - 1] and w_c > 0.25 * (hi[0] - lo[0]):  # ignore a lone zipper strip
                    kx = max(k, bw * (1.08 if slot == "torso" else 1.16) / max(w_c, 1e-6))
        kx = min(kx, 1.6 * k)
        M = Matrix.Translation(Vector((bc[0], bc[1], nz))) @ Matrix.Diagonal((kx, kx, k, 1)) @ Matrix.Translation(Vector((-tc[0], -tc[1], -hi[2])))
        P.data.transform(M)
        M = Matrix.Identity(4)
        if slot == "outer":  # swing each sleeve from the jacket's own shoulder onto the body's arm
            co2 = np.array([v.co[:] for v in P.data.vertices])
            chest = co2[np.abs(co2[:, 2] - cz_b) < 0.03]
            ccx = bc[0]
            half = np.percentile(np.abs(chest[:, 0] - ccx), 60) if len(chest) else 0.18  # jacket torso half width
            jtop = co2[:, 2].max()
            for S, sg in (("Left", 1), ("Right", -1)):
                sh = J(S + "Arm")
                wr = J(S + "Hand")
                d_b = (wr - sh) / np.linalg.norm(wr - sh)
                side = (co2[:, 0] - ccx) * sg - half  # distance outside the jacket's torso edge
                sl = side > -0.03
                far = co2[sl & (side > 0.08)]
                if len(far) < 10:
                    continue
                piv = np.array([ccx + sg * half, bc[1], jtop - 0.06])  # the jacket's shoulder seam
                d_s = far.mean(0) - piv
                d_s /= np.linalg.norm(d_s)
                R = np.array(Vector(d_s).rotation_difference(Vector(d_b)).to_matrix())
                rel = co2 - piv
                along = rel @ d_s
                L_s = np.percentile(along[sl], 98)
                L_b = np.linalg.norm(wr - sh) + 0.04
                stretch = np.clip(L_b / max(L_s, 1e-3), 0.7, 2.0)
                t = np.clip((side + 0.03) / 0.09, 0, 1)[:, None]
                moved = (rel + np.outer(along * (stretch - 1), d_s)) @ R.T + sh
                co2 = np.where(sl[:, None], co2 * (1 - t) + moved * t, co2)
            for v, p in zip(P.data.vertices, co2):
                v.co = Vector(p)
    else:  # feet: split the pair, fit each boot to its foot
        bm = bmesh.new()
        bm.from_mesh(P.data)
        bm.verts.ensure_lookup_table()
        seen, parts = set(), []
        for v in bm.verts:
            if v.index in seen:
                continue
            st_, comp = [v], []
            seen.add(v.index)
            while st_:
                x = st_.pop()
                comp.append(x.index)
                for e in x.link_edges:
                    y = e.other_vert(x)
                    if y.index not in seen:
                        seen.add(y.index)
                        st_.append(y)
            parts.append(comp)
        bm.free()
        left = np.array([i for c in parts if co[c, 0].mean() > cx for i in c])
        right = np.array([i for c in parts if co[c, 0].mean() <= cx for i in c])
        new = co.copy()
        for S, idx in (("Left", left), ("Right", right)):
            if len(idx) == 0:
                continue
            fm = np.char.startswith(dom.astype(str), S) & (np.char.endswith(dom.astype(str), "Foot") | np.char.endswith(dom.astype(str), "ToeBase"))
            F = BV[fm]
            G = co[idx]
            k = np.ptp(F[:, 1]) * 1.12 / max(np.ptp(G[:, 1]), 1e-6)
            fc = np.array([F[:, 0].mean(), F[:, 1].mean(), 0.0])
            gc = np.array([G[:, 0].mean(), G[:, 1].mean(), G[:, 2].min()])
            new[idx] = (G - gc) * k + fc
        for v, p in zip(P.data.vertices, new):
            v.co = Vector(p)
        M = Matrix.Identity(4)
        k = None
    P.data.transform(M)
    P.data.update()
    # push cloth out of the body
    bt = BVHTree.FromPolygons([Vector(p) for p in BV], [tuple(p.vertices) for p in body.data.polygons])
    pushed = 0
    for v in P.data.vertices:
        loc, nrm, fi, d = bt.find_nearest(v.co)
        if loc is not None and d < 0.06 and (v.co - loc).dot(nrm) < GAP:
            v.co = loc + nrm * GAP
            pushed += 1
    for x in bpy.data.objects:
        x.select_set(x is P)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, name + ".glb"), export_format="GLB", use_selection=True)
    rep[name] = {"slot": slot, "scale": None if k is None else round(float(k), 3), "pushed_out": pushed, "source": path}
    print("AUTOFIT", name, slot, rep[name]["scale"], "pushed", pushed)
json.dump(rep, open(os.path.join(OUT, "autofit.json"), "w"), indent=1)
print("AUTOFIT_OK", len(rep))

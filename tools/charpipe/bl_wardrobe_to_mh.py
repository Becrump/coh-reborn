"""Transfer wardrobe items from the charpipe skeleton to a MetaHuman body (Blender).

    blender -b --factory-startup -P bl_wardrobe_to_mh.py -- <wardrobe_dir> <mh_base.glb> <out_dir> [--items a,b,c] [--gap 0.006]

<mh_base.glb>: MetaHuman body + head on the UE5/MetaHuman skeleton (bl_mh_extract.py from hero.blend).
Per piece vertex (skeleton-driven fit):
  * for each bone that skins the vertex on the charpipe body, the vertex is written in that bone's
    frame (position along the bone + radial offset in a frame built from the bone direction and
    the forward axis), the radial part scaled by the ratio of the two bodies' thickness at that
    point along the bone, and rebuilt on the matching MetaHuman bone; results blended by the weights
  * pushed out to --gap (6 mm) above the MetaHuman skin wherever it ends up inside the body
  * skinned from the MetaHuman body (nearest surface, interpolated, max 4 influences); socket items
    go 100 % to the mapped socket bone (Head -> head)
  * body-hide list for the MetaHuman body (vertex indices of body+head, as joined in the GLB order)
Writes <out_dir>/<slot>/<name>.glb (MetaHuman armature + piece), <out_dir>/body/mh_base.glb and
<out_dir>/wardrobe_mh.json. Attach in Unreal with Leader Pose on the MetaHuman body.
"""
import json
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retarget2 import SKELETONS as FAMILIES  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
WDIR, MHP, OUT = a[0], a[1], a[2]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
GAP = float(opt("--gap", 0.006))
wd = json.load(open(os.path.join(WDIR, "wardrobe.json")))
ITEMS = [x for x in (opt("--items") or ",".join(wd["items"])).split(",") if x]
MEM, MH = FAMILIES["meshy"], FAMILIES["mh"]
B2MH = {MEM[k]: MH[k] for k in MEM if k in MH and isinstance(MEM[k], str) and ":" not in MEM[k]}
FING = {"Thumb": "thumb", "Index": "index", "Middle": "middle", "Ring": "ring", "Pinky": "pinky"}
for S, s in (("Left", "l"), ("Right", "r")):
    for F, f in FING.items():
        for j in (1, 2, 3):
            B2MH["%s%s%d" % (S, F, j)] = "%s_0%d_%s" % (f, j, s)
os.makedirs(OUT, exist_ok=True)


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in list(new):
        if o.name.startswith("Icosphere"):
            bpy.data.objects.remove(o, do_unlink=True)
            new.remove(o)
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    if arm is not None:
        if arm.animation_data:
            arm.animation_data.action = None
        for pb in arm.pose.bones:
            pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    return arm, [o for o in new if o.type == "MESH"]


def weights(o):
    names = [g.name for g in o.vertex_groups]
    W = np.zeros((len(o.data.vertices), len(names)))
    for v in o.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    return names, W


def bone_seg(arm, n):
    b = arm.data.bones.get(n)
    if b is None:
        return None
    return np.array((arm.matrix_world @ b.head_local)[:]), np.array((arm.matrix_world @ b.tail_local)[:])


def frame(h, t):
    d = t - h
    L = np.linalg.norm(d) + 1e-9
    dn = d / L
    fwd = np.array([0, -1.0, 0]) if abs(dn[1]) < 0.9 else np.array([0, 0, 1.0])
    x = np.cross(dn, fwd)
    x /= np.linalg.norm(x) + 1e-9
    y = np.cross(x, dn)
    return h, dn, L, x, y


def thickness(arm, body_objs, bone):
    """mean radial distance of the body around a bone, in 10 bins along it"""
    seg = bone_seg(arm, bone)
    if seg is None:
        return None
    h, dn, L, x, y = frame(*seg)
    pts = []
    for o in body_objs:
        names, W = weights(o)
        if bone not in names:
            continue
        j = names.index(bone)
        co = np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices])
        pts.append(co[W[:, j] > 0.5])
    if not pts:
        return None
    P = np.concatenate(pts)
    if len(P) < 5:
        return None
    u = ((P - h) @ dn) / L
    r = np.linalg.norm((P - h) - np.outer(u * L, dn), axis=1)
    bins = np.full(10, np.median(r))
    for i in range(10):
        m = (u >= i / 10) & (u < (i + 1) / 10)
        if m.sum() > 3:
            bins[i] = np.median(r[m])
    return bins


bpy.ops.wm.read_factory_settings(use_empty=True)
carm, cbody = imp(os.path.join(WDIR, wd["body"]["base"]["file"]))
marm, mbody = imp(MHP)
cbody = [max(cbody, key=lambda o: len(o.data.vertices))]
# MetaHuman target surface (body + head)
mco = [np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in mbody]
offs = np.cumsum([0] + [len(c) for c in mco])
MCO = np.concatenate(mco)
MT = []
for o, off in zip(mbody, offs[:-1]):
    MT += [tuple(off + i for i in p.vertices) for p in o.data.polygons]
mtree = BVHTree.FromPolygons([Vector(c) for c in MCO], MT)
ratio_cache = {}


def ratio(cb, mb, u):
    key = (cb, mb)
    if key not in ratio_cache:
        rc, rm = thickness(carm, cbody, cb), thickness(marm, mbody, mb)
        ratio_cache[key] = None if rc is None or rm is None else np.clip(rm / np.maximum(rc, 1e-4), 0.6, 1.6)
    r = ratio_cache[key]
    if r is None:
        return 1.0
    return float(r[int(np.clip(u * 10, 0, 9))])


# MetaHuman surface normals: make them point outward (the extracted mesh can come in flipped)
_c = MCO.mean(0)
_votes = 0
for _d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
    _p = Vector(_c) + Vector(_d) * 3.0
    _loc, _n, _fi, _ = mtree.find_nearest(_p)
    _votes += 1 if (_p - _loc).dot(_n) > 0 else -1
NSIGN = 1.0 if _votes >= 0 else -1.0

# pose the charpipe skeleton onto the MetaHuman one (no inherited scale so every bone is set exactly)
bpy.context.view_layer.objects.active = carm
bpy.ops.object.mode_set(mode="EDIT")
for eb in carm.data.edit_bones:
    eb.inherit_scale = "NONE"
bpy.ops.object.mode_set(mode="OBJECT")


def depth(b):
    n = 0
    while b.parent:
        b, n = b.parent, n + 1
    return n


posed = 0
for pb in sorted(carm.pose.bones, key=lambda p: depth(p.bone)):
    mb = B2MH.get(pb.name)
    cs = bone_seg(carm, pb.name)
    ms = bone_seg(marm, mb) if mb else None
    if cs is None or ms is None:
        continue
    d1, d2 = Vector((cs[1] - cs[0])[:]), Vector((ms[1] - ms[0])[:])
    if d1.length < 1e-5 or d2.length < 1e-5:
        continue
    rest = carm.matrix_world @ pb.bone.matrix_local
    rot = d1.normalized().rotation_difference(d2.normalized()).to_matrix().to_4x4()
    r = ratio(pb.name, mb, 0.5)
    S = Matrix.Diagonal((r, d2.length / d1.length, r, 1.0))
    target = Matrix.Translation(Vector(ms[0][:])) @ rot @ Matrix.Translation(-Vector(cs[0][:])) @ rest @ S
    pb.matrix = carm.matrix_world.inverted() @ target
    bpy.context.view_layer.update()
    posed += 1
print("MH_POSED_BONES", posed, "normal_sign", NSIGN)

# export the MetaHuman base once (armature + body + head)
for x in bpy.data.objects:
    if x.name in bpy.context.view_layer.objects:
        x.select_set(False)
for o in [marm] + mbody:
    o.select_set(True)
os.makedirs(os.path.join(OUT, "body"), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "body", "mh_base.glb"), export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
mnames_all = sorted(set(g.name for o in mbody for g in o.vertex_groups))
res = {"skeleton": "MetaHuman / UE5", "body": "body/mh_base.glb", "items": {}}
for it in ITEMS:
    info = wd["items"][it]
    _, ps = imp(os.path.join(WDIR, info["file"]))
    piece = max(ps, key=lambda o: len(o.data.vertices))
    for o in ps:
        if o is not piece:
            bpy.data.objects.remove(o, do_unlink=True)
    mw = piece.matrix_world.copy()
    piece.parent = None
    piece.modifiers.clear()
    piece.data.transform(mw)
    piece.matrix_world = Matrix.Identity(4)
    # skinning-based fit: the charpipe skeleton is posed onto the MetaHuman skeleton (each bone moved,
    # turned and stretched to its MetaHuman bone, thickened/thinned by the body ratio) and the piece
    # follows with its own skin weights, so the cloth deforms smoothly instead of per-vertex mapping
    if info.get("socket"):
        sb = info["socket"]
        cs, ms = bone_seg(carm, sb), bone_seg(marm, B2MH.get(sb, "head"))
        k = np.linalg.norm(ms[1] - ms[0]) / max(np.linalg.norm(cs[1] - cs[0]), 1e-6)
        co = np.array([v.co[:] for v in piece.data.vertices])
        new = ms[0] + (co - cs[0]) * k
    else:
        piece.modifiers.new("Armature", "ARMATURE").object = carm
        dg = bpy.context.evaluated_depsgraph_get()
        ev = piece.evaluated_get(dg)
        tmp = ev.to_mesh()
        new = np.array([v.co[:] for v in tmp.vertices])
        ev.to_mesh_clear()
        piece.modifiers.clear()
    # push out of the MetaHuman skin
    pushed = 0
    for i, p in enumerate(new):
        loc, nrm, fi, d = mtree.find_nearest(Vector(p))
        if loc is None:
            continue
        nrm = nrm * NSIGN
        if (Vector(p) - loc).dot(nrm) < GAP and d < 0.08:
            new[i] = np.array((loc + nrm * GAP)[:])
            pushed += 1
    for v, p in zip(piece.data.vertices, new):
        v.co = Vector(p)
    piece.data.update()
    # skin from the MetaHuman body
    piece.vertex_groups.clear()
    sock = {"Head": "head"}.get(info.get("socket"), info.get("socket"))
    if sock:
        piece.vertex_groups.new(name=sock).add(list(range(len(new))), 1.0, "REPLACE")
    else:
        for g in mnames_all:
            piece.vertex_groups.new(name=g)
        for src in mbody:
            dt = piece.modifiers.new("dt", "DATA_TRANSFER")
            dt.object = src
            dt.use_vert_data = True
            dt.data_types_verts = {"VGROUP_WEIGHTS"}
            dt.vert_mapping = "POLYINTERP_NEAREST"
            dt.layers_vgroup_select_src = "ALL"
            dt.layers_vgroup_select_dst = "NAME"
            dt.mix_mode = "REPLACE" if src is mbody[0] else "ADD"
            if src is not mbody[0]:
                dt.use_max_distance = True
                dt.max_distance = 0.03  # head weights only near the head
            bpy.context.view_layer.objects.active = piece
            bpy.ops.object.modifier_apply(modifier="dt")
        pn, PW = weights(piece)
        order = np.argsort(-PW, 1)
        keep = np.zeros_like(PW, bool)
        np.put_along_axis(keep, order[:, :4], True, 1)
        PW[~keep] = 0
        PW[PW < 0.01] = 0
        PW /= np.maximum(PW.sum(1, keepdims=True), 1e-9)
        used = set(np.nonzero(PW.sum(0))[0])
        for g in list(piece.vertex_groups):
            if g.index not in used:
                continue
        for g in piece.vertex_groups:
            g.remove(list(range(len(PW))))
        for j, n in enumerate(pn):
            if j in used:
                g = piece.vertex_groups[n]
                for i in np.nonzero(PW[:, j])[0]:
                    g.add([int(i)], float(PW[i, j]), "REPLACE")
        for g in [g for g in piece.vertex_groups if g.index not in used]:
            piece.vertex_groups.remove(g)
    # hide list on the MetaHuman body
    ptree = BVHTree.FromPolygons([Vector(p) for p in new], [tuple(p.vertices) for p in piece.data.polygons])
    hide = []
    for o, off in zip(mbody, offs[:-1]):
        N3 = o.matrix_world.to_3x3().inverted().transposed()
        for v in o.data.vertices:
            pv = o.matrix_world @ v.co
            nv = (N3 @ v.normal).normalized()
            if ptree.ray_cast(pv + nv * 0.0005, nv, 0.04)[0] is not None:
                hide.append(int(off + v.index))
    piece.parent = marm
    piece.modifiers.new("Armature", "ARMATURE").object = marm
    for x in bpy.data.objects:
        if x.name in bpy.context.view_layer.objects:
            x.select_set(False)
    marm.select_set(True)
    piece.select_set(True)
    path = os.path.join(OUT, info["slot"], it + ".glb")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
    res["items"][it] = {"slot": info["slot"], "socket": sock, "file": "%s/%s.glb" % (info["slot"], it), "pushed_out": pushed,
                        "hides_body_verts": hide, "source": info.get("source")}
    print("MH_ITEM", it, "pushed", pushed, "hides", len(hide))
    bpy.data.objects.remove(piece, do_unlink=True)
json.dump(res, open(os.path.join(OUT, "wardrobe_mh.json"), "w"), indent=1)
print("MH_WARDROBE_OK", len(res["items"]))

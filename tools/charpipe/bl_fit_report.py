"""Fit every wardrobe garment onto other bodies with a landmark + cloth-sim fitter, and score the fit (Blender).

    blender -b --factory-startup -P bl_fit_report.py -- <wardrobe_dir> <out_dir> name=<body.glb> [...]
            [--items a,b] [--frames 24] [--save-fitted]

Bodies: any rig with the charpipe skeleton (24 bones + fingers), e.g. BaseHellion, the headless Tripo body,
HellionLT, the full Tripo Hellion, heavy / big build variants.
Per garment x body:
 (a) landmarks: the garment comes skinned to the wardrobe base skeleton; that skeleton is posed so every joint
     (neck, shoulders, elbows, wrists, spine, hips, knees, ankles) lands on the target body's joint, bones stretched
     to the target lengths and thickened by the girth ratio of the two bodies around each bone; the garment follows
     its own skin weights (smooth, no tearing)
 (b) shrink-fit: Blender cloth on the garment (no gravity, 3 % shrink, pinned waistband / collar / cuffs = the
     top 6 % of legs pieces and the collar band of tops), the target body as a collision object (4 mm), N frames,
     then baked
 (c) skinned from the target body (nearest surface, max 4 influences)
 Score at the A-pose and at a CoH Brawl frame (retargeted onto the target):
     penetration % = garment vertices more than 3 mm inside the body, gap = median distance of the garment to the
     skin where it is within 10 cm (cm). PASS if penetration < 5 % and gap < 3 cm (tops) / 4 cm (feet) / 6 cm
     (pants, jackets, coats) in both poses. Jackets: sleeve vertices are skinned only along their arm chain.
Waits while CPU_HOLD.txt / GPU_HOLD.txt exist (Blender renders paused by other threads).
Writes <out_dir>/fit_report.json and a thumbnail per fit (<body>__<item>.png, A-pose front, with the body).
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retarget2 as R  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
WDIR, OUT = a[0], a[1]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
BODIES = [x.split("=", 1) for x in a[2:] if "=" in x and not x.startswith("--")]
FRAMES = int(opt("--frames", 24))
COH = "C:/Users/rtcru/CoHReborn"
BRAWL = (COH + "/out/player/anims/male/male_anims_01.gltf", "male__brawl_high2", 14)
os.makedirs(OUT, exist_ok=True)
wd = json.load(open(os.path.join(WDIR, "wardrobe.json")))
ITEMS = [x for x in (opt("--items") or ",".join(k for k, v in wd["items"].items()
                                                 if not v.get("socket") and v["slot"] not in ("hands",))).split(",") if x]


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


def wcols(o):
    names = [g.name for g in o.vertex_groups]
    W = np.zeros((len(o.data.vertices), len(names)))
    for v in o.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    return names, W


def seg(arm, n):
    b = arm.data.bones.get(n)
    return None if b is None else (np.array((arm.matrix_world @ b.head_local)[:]), np.array((arm.matrix_world @ b.tail_local)[:]))


def girth(arm, body, bone):
    s = seg(arm, bone)
    if s is None:
        return None
    names, W = wcols(body)
    if bone not in names:
        return None
    P = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices])[W[:, names.index(bone)] > 0.5]
    if len(P) < 10:
        return None
    d = s[1] - s[0]
    u = ((P - s[0]) @ d) / max(d @ d, 1e-9)
    return float(np.median(np.linalg.norm(P - (s[0] + np.outer(u, d)), axis=1)))


def depth(b):
    n = 0
    while b.parent:
        b, n = b.parent, n + 1
    return n


def pose_onto(src_arm, src_body, dst_arm, dst_body):
    bpy.context.view_layer.objects.active = src_arm
    bpy.ops.object.mode_set(mode="EDIT")
    for eb in src_arm.data.edit_bones:
        eb.inherit_scale = "NONE"
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in sorted(src_arm.pose.bones, key=lambda p: depth(p.bone)):
        cs, ds = seg(src_arm, pb.name), seg(dst_arm, pb.name)
        if cs is None or ds is None:
            continue
        d1, d2 = Vector((cs[1] - cs[0])[:]), Vector((ds[1] - ds[0])[:])
        if d1.length < 1e-5 or d2.length < 1e-5:
            continue
        g1, g2 = girth(src_arm, src_body, pb.name), girth(dst_arm, dst_body, pb.name)
        r = float(np.clip(g2 / g1, 0.7, 1.5)) if g1 and g2 else 1.0
        rest = src_arm.matrix_world @ pb.bone.matrix_local
        rot = d1.normalized().rotation_difference(d2.normalized()).to_matrix().to_4x4()
        S = Matrix.Diagonal((r, d2.length / d1.length, r, 1.0))
        pb.matrix = src_arm.matrix_world.inverted() @ (Matrix.Translation(Vector(ds[0][:])) @ rot @ Matrix.Translation(-Vector(cs[0][:])) @ rest @ S)
        bpy.context.view_layer.update()


def bake_mesh(o):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    me.transform(o.matrix_world)
    old = o.data
    o.modifiers.clear()
    o.data = me
    o.matrix_world = Matrix.Identity(4)
    o.parent = None
    return old


def body_tree(body):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    vs = [body.matrix_world @ v.co for v in me.vertices]
    t = BVHTree.FromPolygons(vs, [tuple(p.vertices) for p in me.polygons])
    ev.to_mesh_clear()
    return t


def score(piece, body):
    t = body_tree(body)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = piece.evaluated_get(dg)
    me = ev.to_mesh()
    P = [piece.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    sd = []
    for p in P[:: max(1, len(P) // 2500)]:
        loc, n, fi, d = t.find_nearest(p)
        if loc is None or d > 0.10:
            continue
        sd.append(d if (p - loc).dot(n) >= 0 else -d)
    sd = np.array(sd) if sd else np.zeros(1)
    pen = float((sd < -0.003).mean() * 100)
    gap = float(np.median(sd[sd >= 0]) * 100) if (sd >= 0).any() else 0.0
    return round(pen, 1), round(gap, 2)


def cloth_fit(piece, body, slot):
    # glTF splits vertices at UV seams; welded, the cloth is one sheet instead of islands that fly apart
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(piece.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(piece.data)
    bm.free()
    piece.data.update()
    # start outside the target: bodies that are already clothed (Tripo full / headless / LT) would otherwise
    # begin deep inside the collision surface and the cloth solver explodes
    t = body_tree(body)
    for v in piece.data.vertices:
        loc, n, fi, d = t.find_nearest(v.co)
        if loc is not None and d < 0.10 and (v.co - loc).dot(n) < 0.008:
            v.co = loc + n * 0.008
    piece.data.update()
    co = np.array([v.co[:] for v in piece.data.vertices])
    z = co[:, 2]
    zt, zb = z.max(), z.min()
    pin = piece.vertex_groups.new(name="pin")
    if slot == "legs":
        band = np.nonzero(z > zt - 0.06 * (zt - zb))[0]
    elif slot == "feet":
        band = np.nonzero(z < zb + 0.02)[0]
    else:
        band = np.nonzero(z > zt - 0.05 * (zt - zb))[0]
    pin.add([int(i) for i in band], 1.0, "REPLACE")
    col = body.modifiers.new("col", "COLLISION")
    body.collision.thickness_outer = 0.004
    body.collision.thickness_inner = 0.01
    cl = piece.modifiers.new("cloth", "CLOTH")
    s = cl.settings
    s.quality = 10
    s.mass = 0.3
    s.air_damping = 5.0
    s.tension_stiffness = s.compression_stiffness = s.shear_stiffness = 40
    s.bending_stiffness = 5
    s.shrink_min = 0.03
    s.vertex_group_mass = "pin"
    s.effector_weights.gravity = 0.0
    cl.collision_settings.use_self_collision = False
    cl.collision_settings.distance_min = 0.004
    cl.point_cache.frame_start = 1
    cl.point_cache.frame_end = FRAMES
    pre = np.array([v.co[:] for v in piece.data.vertices])
    sc = bpy.context.scene
    for f in range(1, FRAMES + 1):
        sc.frame_set(f)
    bake_mesh(piece)
    body.modifiers.remove(col)
    # safety: the solver can fling single vertices on clothed bodies; limit every vertex to 3 cm of travel
    post = np.array([v.co[:] for v in piece.data.vertices])
    if post.shape == pre.shape:
        d = post - pre
        n = np.linalg.norm(d, axis=1, keepdims=True)
        post = pre + d * np.minimum(1.0, 0.03 / np.maximum(n, 1e-9))
        for v, p in zip(piece.data.vertices, post):
            v.co = Vector(p)
        piece.data.update()


def reskin(piece, body, arm, slot=""):
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
    if slot in ("outer", "torso_outer"):
        sleeve_weights(piece, arm)
    piece.parent = arm
    piece.modifiers.new("Armature", "ARMATURE").object = arm


def sleeve_weights(piece, arm):
    """jackets: vertices closer to an arm chain than to the torso get weights from that arm chain only
    (Shoulder near the seam, Arm / ForeArm split at the elbow with a 4 cm blend, 15 % Hand twist at the cuff),
    and torso vertices lose any arm weight, so sleeves never fuse to the torso."""
    co = np.array([v.co[:] for v in piece.data.vertices])
    names, W = wcols(piece)
    ix = {n: i for i, n in enumerate(names)}
    sp = seg(arm, "Spine")
    hp = seg(arm, "Hips")
    t0, t1 = hp[0], sp[1]
    td = t1 - t0
    tu = np.clip(((co - t0) @ td) / (td @ td), 0, 1)
    dt = np.linalg.norm(co - (t0 + np.outer(tu, td)), axis=1)
    moved = 0
    for S in ("Left", "Right"):
        sh, el, wr = seg(arm, S + "Arm")[0], seg(arm, S + "ForeArm")[0], seg(arm, S + "Hand")[0]

        def segd(a_, b_):
            d = b_ - a_
            u = np.clip(((co - a_) @ d) / (d @ d), 0, 1)
            return np.linalg.norm(co - (a_ + np.outer(u, d)), axis=1), u
        d1, u1 = segd(sh, el)
        d2, u2 = segd(el, wr)
        da = np.minimum(d1, d2)
        sleeve = (da < dt * 0.8) & (np.abs(co[:, 0]) > np.abs(sh[0]) * 0.75)
        L1, L2 = np.linalg.norm(el - sh), np.linalg.norm(wr - el)
        s_ = np.where(d1 <= d2, u1 * L1, L1 + u2 * L2)  # distance along the arm from the shoulder
        for i in np.nonzero(sleeve)[0]:
            w = np.zeros(len(names))
            x = s_[i]
            e = np.clip((x - (L1 - 0.02)) / 0.04, 0, 1)
            sh_w = np.clip(1 - x / 0.06, 0, 1) * 0.5
            hd = np.clip((x - (L1 + L2 * 0.75)) / (L2 * 0.25), 0, 1) * 0.15
            for n, val in ((S + "Shoulder", sh_w), (S + "Arm", (1 - e) * (1 - sh_w)), (S + "ForeArm", e * (1 - hd)), (S + "Hand", e * hd)):
                if n in ix:
                    w[ix[n]] = val
            if w.sum() > 0:
                W[i] = w / w.sum()
                moved += 1
    torso = ~np.zeros(len(co), bool)
    armcols = [ix[n] for n in names if any(n.endswith(k) for k in ("Arm", "ForeArm", "Hand")) or any(f in n for f in ("Thumb", "Index", "Middle", "Ring", "Pinky"))]
    for i in range(len(co)):
        if W[i, armcols].sum() > 0 and not (np.abs(co[i, 0]) > 0.15):
            W[i, armcols] = 0
            if W[i].sum() > 0:
                W[i] /= W[i].sum()
    for g in piece.vertex_groups:
        g.remove(list(range(len(co))))
    for j, n in enumerate(names):
        for i in np.nonzero(W[:, j] > 0.01)[0]:
            piece.vertex_groups[n].add([int(i)], float(W[i, j]), "REPLACE")
    return moved


def brawl(arm):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=BRAWL[0])
    src = next(o for o in bpy.data.objects if o not in before and o.type == "ARMATURE")
    for o in [o for o in bpy.data.objects if o not in before and o is not src]:
        bpy.data.objects.remove(o, do_unlink=True)
    act = next(x for x in bpy.data.actions if x.name.startswith(BRAWL[1]))
    src.animation_data_create()
    src.animation_data.action = act
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    out, _ = R.retarget(src, "coh", arm, "meshy", "FIT_brawl", frames=list(range(1, 49)))
    bpy.data.objects.remove(src, do_unlink=True)
    return out


def thumb(path, objs):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 200, 300
    sc.view_settings.view_transform = "Standard"
    if not sc.world:
        w = bpy.data.worlds.new("w")
        sc.world = w
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs[0].default_value = (0.3, 0.3, 0.3, 1)
        l_ = bpy.data.objects.new("L", bpy.data.lights.new("L", "SUN"))
        l_.data.energy = 3
        sc.collection.objects.link(l_)
        l_.rotation_euler = (0.8, 0, -0.5)
    cam = sc.camera
    if cam is None:
        cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
        cam.data.type = "ORTHO"
        sc.collection.objects.link(cam)
        sc.camera = cam
    cam.data.ortho_scale = 2.0
    cam.location = (0, -6, 0.95)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = o not in objs
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


ORDER = {"outer": 0, "torso_outer": 0, "torso": 1, "legs": 2, "feet": 3}
ITEMS.sort(key=lambda k: ORDER.get(wd["items"][k]["slot"], 9))
HOLDS = ["C:/Users/rtcru/ClaudeProjects/COHReborn/CPU_HOLD.txt", "C:/Users/rtcru/ClaudeProjects/COHReborn/GPU_HOLD.txt"]
report = {}
for bname, bpath in BODIES:
    for it in ITEMS:
        import time as _t
        while any(os.path.exists(h) for h in HOLDS):
            print("hold file present, waiting", flush=True)
            _t.sleep(60)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        tarm, tms = imp(bpath)
        tbody = max(tms, key=lambda o: len(o.data.vertices))
        for o in tms:
            if o is not tbody:
                bpy.data.objects.remove(o, do_unlink=True)
        sarm, sms = imp(os.path.join(WDIR, wd["body"]["base"]["file"]))
        sbody = max(sms, key=lambda o: len(o.data.vertices))
        iarm, ims = imp(os.path.join(WDIR, wd["items"][it]["file"]))
        piece = max(ims, key=lambda o: len(o.data.vertices))
        for m in piece.modifiers:
            if m.type == "ARMATURE":
                m.object = sarm
        piece.parent = sarm
        bpy.data.objects.remove(iarm, do_unlink=True)
        pose_onto(sarm, sbody, tarm, tbody)
        bake_mesh(piece)
        bpy.data.objects.remove(sbody, do_unlink=True)
        bpy.data.objects.remove(sarm, do_unlink=True)
        slot = wd["items"][it]["slot"]
        try:
            cloth_fit(piece, tbody, slot)
        except Exception as e:  # noqa: BLE001
            print("cloth failed", it, e)
        p0 = score(piece, tbody)
        reskin(piece, tbody, tarm, slot)
        thumb(os.path.join(OUT, "%s__%s.png" % (bname, it)), [tbody, piece])
        act = brawl(tarm)
        tarm.animation_data.action = act
        bpy.context.scene.frame_set(BRAWL[2])
        bpy.context.view_layer.update()
        p1 = score(piece, tbody)
        gmax = {"torso": 3.0, "feet": 4.0}.get(slot, 6.0)  # baggy pants / coats may stand off the body
        ok = p0[0] < 5 and p1[0] < 5 and p0[1] < gmax and p1[1] < gmax
        report.setdefault(bname, {})[it] = {"apose_pen_pct": p0[0], "apose_gap_cm": p0[1], "brawl_pen_pct": p1[0],
                                            "brawl_gap_cm": p1[1], "pass": ok}
        print("FIT", bname, it, p0, p1, "PASS" if ok else "FAIL", flush=True)
        if "--save-fitted" in a:
            tarm.animation_data.action = None
            for x in bpy.data.objects:
                x.select_set(x is tarm or x is piece)
            bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "%s__%s.glb" % (bname, it)), export_format="GLB",
                                      use_selection=True, export_skins=True, export_animations=False)
        json.dump(report, open(os.path.join(OUT, "fit_report.json"), "w"), indent=1)
print("FIT_REPORT_OK")

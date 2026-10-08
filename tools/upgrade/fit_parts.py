"""Fit generated head and hand meshes onto an exported CoH character.

Run inside Blender (headless):

    blender -b --factory-startup --python tools/upgrade/fit_parts.py -- job.json

job.json:
{
  "base_gltf":  ".../Boss_01_b.gltf",          # character to upgrade
  "out_gltf":   ".../Boss_01_c.gltf",
  "check_dir":  ".../checks",                  # check renders + report.json
  "head": {"glb": "head.glb", "image": "head_filled.png",
           "bbox": "head_bbox.json", "faces": 18000,
           "replace": ["Head", "Hair", "EyeDetail"]},
  "hand": {"glb": "hand.glb", "image": "hand_filled.png",
           "bbox": "hand_bbox.json", "faces": 9000,
           "is_right_hand": true}
}

Conventions (verified on Thug_Hellion_Boss_01): the exported character
faces -Y in Blender with the right arm along -X. A Trellis2 hand generated
from a "back of the hand, fingers hanging down" concept comes in with its
long axis on Y and the back of the hand up (+Z). Which end holds the
fingers is detected from the shape (the fingers end is the wider one).

The head is skinned to HEAD and NECK. Hands are skinned along CoH's finger
chains (HAND -> RING -> F2 -> F1 for the four fingers, T3 -> T2 -> T1 for
the thumb) so the game's fist animations curl them, with the cuff blended
into LARM. report.json lists automatic checks; any "ok": false needs a look.
"""
import bmesh
import bpy
import json
import math
import os
import sys
from mathutils import Matrix, Vector

JOB = json.load(open(sys.argv[sys.argv.index("--") + 1]))
os.makedirs(JOB["check_dir"], exist_ok=True)
REPORT = {"checks": []}


def check(name, ok, **info):
    REPORT["checks"].append(dict(name=name, ok=bool(ok), **info))
    print("CHECK", name, "OK" if ok else "FAIL", info)


# ------------------------------------------------------------------ scene
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=JOB["base_gltf"])
sc = bpy.context.scene
for o in [o for o in sc.objects
          if o.type == "MESH" and o.name.startswith("Icosphere")]:
    bpy.data.objects.remove(o)          # glTF importer's bone-shape helper
arm = next(o for o in sc.objects if o.type == "ARMATURE")


def rest_pose():
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()


def pose(clip, frac):
    rest_pose()
    a = next((v for v in bpy.data.actions if v.name.startswith(clip)), None)
    if a is None:
        return False
    arm.animation_data_create()
    arm.animation_data.action = a
    try:
        if a.slots:
            arm.animation_data.action_slot = a.slots[0]
    except Exception:
        pass
    f0, f1 = a.frame_range
    sc.frame_set(int(f0 + (f1 - f0) * frac))
    bpy.context.view_layer.update()
    return True


rest_pose()


def bone(n):
    return arm.matrix_world @ arm.pose.bones[n].head


def world_verts(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    e = ob.evaluated_get(dg)
    m = e.to_mesh()
    pts = [e.matrix_world @ v.co for v in m.vertices]
    e.to_mesh_clear()
    return pts


def bbox(objs):
    pts = [p for o in objs for p in world_verts(o)]
    return (Vector([min(p[i] for p in pts) for i in range(3)]),
            Vector([max(p[i] for p in pts) for i in range(3)]))


meshes = {o.name: o for o in sc.objects if o.type == "MESH"}


def load_part(path, faces):
    before = set(sc.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in sc.objects if o not in before]
    ob = next(o for o in new if o.type == "MESH")
    for o in new:
        if o is not ob:
            bpy.data.objects.remove(o)
    ob.parent = None
    ob.rotation_mode = "XYZ"            # importer leaves quaternion mode
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    if len(ob.data.polygons) > faces:
        d = ob.modifiers.new("dec", "DECIMATE")
        d.ratio = faces / len(ob.data.polygons)
        bpy.ops.object.modifier_apply(modifier="dec")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return ob


def apply(ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def project(ob, image, box, u_axis, v_axis, v_down):
    """Planar projection of the concept image over the mesh's bbox."""
    me = ob.data
    co = [v.co.copy() for v in me.vertices]
    mn = [min(c[i] for c in co) for i in range(3)]
    mx = [max(c[i] for c in co) for i in range(3)]
    uv = me.uv_layers.new(name="concept")
    for poly in me.polygons:
        for li in poly.loop_indices:
            c = co[me.loops[li].vertex_index]
            fu = (c[u_axis] - mn[u_axis]) / (mx[u_axis] - mn[u_axis])
            fv = (c[v_axis] - mn[v_axis]) / (mx[v_axis] - mn[v_axis])
            if v_down:
                fv = 1 - fv
            px = box["x0"] + fu * (box["x1"] - box["x0"])
            py = box["y0"] + (1 - fv) * (box["y1"] - box["y0"])
            uv.data[li].uv = (px / box["w"], 1 - py / box["h"])
    for layer in list(me.uv_layers):
        if layer.name != "concept":
            me.uv_layers.remove(layer)
    mat = bpy.data.materials.new("M_" + ob.name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    t = mat.node_tree.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(image, check_existing=True)
    mat.node_tree.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.6
    bsdf.inputs["Metallic"].default_value = 0.0
    me.materials.clear()
    me.materials.append(mat)


def bind(ob, weights_fn, name):
    for v in ob.data.vertices:
        for g, w in weights_fn(ob.matrix_world @ v.co):
            if w <= 0:
                continue
            vg = ob.vertex_groups.get(g) or ob.vertex_groups.new(name=g)
            vg.add([v.index], w, "REPLACE")
    ob.parent = arm
    ob.matrix_parent_inverse = arm.matrix_world.inverted()
    m = ob.modifiers.new("Armature", "ARMATURE")
    m.object = arm
    apply_smooth(ob)
    ob.name = name
    ob.data.name = name


def apply_smooth(ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_smooth()


# ------------------------------------------------------------------- head
H = JOB.get("head")
if H:
    old = [meshes[n] for n in H.get("replace", ["Head"]) if n in meshes]
    hmn, hmx = bbox(old)
    for o in old:
        bpy.data.objects.remove(o)
    head = load_part(H["glb"], H.get("faces", 18000))
    project(head, H["image"], json.load(open(H["bbox"])), 0, 2, False)
    mn, mx = bbox([head])
    s = (hmx.z - hmn.z) * H.get("height_scale", 1.08) / (mx.z - mn.z)
    head.scale = (s, s, s)
    apply(head)
    mn, mx = bbox([head])
    c = (hmn + hmx) / 2
    head.location = Vector((c.x - (mn.x + mx.x) / 2, c.y - (mn.y + mx.y) / 2,
                            hmn.z - mn.z - 0.01))
    apply(head)
    neck_z, head_z = bone("NECK").z, bone("HEAD").z

    def head_w(p):
        if p.z >= head_z:
            return [("HEAD", 1.0)]
        t = max(0.0, min(1.0, (p.z - neck_z) / max(1e-4, head_z - neck_z)))
        return [("HEAD", t), ("NECK", 1 - t)]
    bind(head, head_w, "Head")
    mn, mx = bbox([head])
    check("head_on_neck", abs(mn.z - hmn.z) < 0.03,
          gap_cm=round((mn.z - hmn.z) * 100, 1))

# ------------------------------------------------------------------ hands


def seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.dot(ab), 1e-9)))
    return (p - (a + ab * t)).length, t


def hand_segments(side):
    s = side
    hand, ring = bone("HAND" + s), bone("RING" + s)
    f2, f1 = bone("F2_" + s), bone("F1_" + s)
    t3, t2, t1 = bone("T3_" + s), bone("T2_" + s), bone("T1_" + s)
    ftip = f1 + (f1 - f2) * 0.9
    ttip = t1 + (t1 - t2) * 0.9
    return [("HAND" + s, hand, ring), ("RING" + s, ring, f2),
            ("F2_" + s, f2, f1), ("F1_" + s, f1, ftip),
            ("T3_" + s, t3, t2), ("T2_" + s, t2, t1), ("T1_" + s, t1, ttip)]


Hd = JOB.get("hand")
if Hd:
    box = json.load(open(Hd["bbox"]))
    for side in "RL":
        old = meshes.get("Hand_" + side)
        if old is None:
            continue
        omn, omx = bbox([old])
        bpy.data.objects.remove(old)
        ob = load_part(Hd["glb"], Hd.get("faces", 9000))
        project(ob, Hd["image"], box, 0, 1, True)
        # which end of the long (Y) axis holds the fingers: the wider one
        pts = [v.co for v in ob.data.vertices]
        y0 = min(p.y for p in pts)
        y1 = max(p.y for p in pts)
        span = y1 - y0

        def width(lo, hi):
            xs = [p.x for p in pts if lo <= p.y <= hi]
            return (max(xs) - min(xs)) if xs else 0.0
        w_neg = width(y0, y0 + 0.2 * span)
        w_pos = width(y1 - 0.2 * span, y1)
        fingers_neg = w_neg >= w_pos
        print('HAND_ENDS', side, 'width -Y', round(w_neg, 3), '+Y', round(w_pos, 3))
        if not fingers_neg:          # make the fingers point -Y
            ob.data.transform(Matrix.Rotation(math.pi, 4, "Z"))
        # a right hand on the left side (or vice versa): mirror X
        want_right = side == "R"
        if Hd.get("is_right_hand", True) != want_right:
            ob.data.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
            ob.data.flip_normals()
        out = 1.0 if bone("HAND" + side).x > bone("LARM" + side).x else -1.0
        # fingers -Y -> outward along the arm (out = -1 for the right arm)
        ob.rotation_euler = (0, 0, math.radians(90 if out > 0 else -90))
        apply(ob)
        mn, mx = bbox([ob])
        s = Hd.get("length_scale", 1.12) * (omx.x - omn.x) / (mx.x - mn.x)
        ob.scale = (s, s, s)
        apply(ob)
        # fingertips at the end of the finger chain, centred on the old hand
        segs = hand_segments(side)
        tip = segs[3][2]
        mn, mx = bbox([ob])
        tip_x = mx.x if out > 0 else mn.x
        c = (omn + omx) / 2
        ob.location = Vector((tip.x - tip_x, c.y - (mn.y + mx.y) / 2,
                              c.z - (mn.z + mx.z) / 2))
        apply(ob)
        wrist = bone("HAND" + side)

        def hand_w(p, segs=segs, wrist=wrist, side=side, out=out):
            u = (p.x - wrist.x) * out          # >0 past the wrist
            if u < -0.01:
                t = max(0.0, min(1.0, (u + 0.05) / 0.04))
                return [("LARM" + side, 1 - t), ("HAND" + side, t)]
            d = sorted((seg_dist(p, a, b)[0], name) for name, a, b in segs)
            (d0, b0), (d1, b1) = d[0], d[1]
            if d1 < d0 * 1.6 and b0 != b1:
                w0 = d1 / (d0 + d1)
                ws = {b0: w0, b1: 1 - w0}
            else:
                ws = {b0: 1.0}
            # generated fingers are already partly curled at rest, so let the
            # finger bones move them only part of the way (finger_follow)
            k = Hd.get("finger_follow", 0.65)
            hb = "HAND" + side
            out_w = {}
            for b, w in ws.items():
                if b == hb:
                    out_w[hb] = out_w.get(hb, 0) + w
                else:
                    out_w[b] = out_w.get(b, 0) + w * k
                    out_w[hb] = out_w.get(hb, 0) + w * (1 - k)
            return list(out_w.items())
        bind(ob, hand_w, "Hand_" + side)

        # checks at rest
        vs = world_verts(ob)
        far = max(vs, key=lambda p: p.x * out)
        check("fingers_point_outward_" + side,
              (far.x - wrist.x) * out > 0.08,
              tip_from_wrist_cm=round((far.x - wrist.x) * out * 100, 1))
        tg = ob.vertex_groups.get("T2_" + side)
        thumb = [ob.matrix_world @ v.co for v in ob.data.vertices
                 if tg and any(g.group == tg.index and g.weight > 0.3
                               for g in v.groups)]
        ty = sum(p.y for p in thumb) / len(thumb) if thumb else 0
        check("thumb_in_front_" + side, bool(thumb) and ty < wrist.y,
              thumb_y=round(ty, 3), wrist_y=round(wrist.y, 3),
              thumb_verts=len(thumb))
        arm_mesh = [o for o in sc.objects if o.type == "MESH"
                    and o.name not in ("Hand_R", "Hand_L", "Head")]
        # wrist gap: nearest arm vertex to the cuff end of the new hand
        cuff = [p for p in vs if (p.x - wrist.x) * out < -0.005]
        armv = [p for o in arm_mesh for p in world_verts(o)
                if abs(p.x - wrist.x) < 0.12 and abs(p.z - wrist.z) < 0.12]
        if cuff and armv:
            gap = min(min((a - p).length for a in armv) for p in cuff[::5])
        else:
            gap = 1.0
        check("cuff_meets_forearm_" + side, gap < 0.015 and bool(cuff),
              nearest_cm=round(gap * 100, 1), cuff_verts=len(cuff))

    # fist test: the punch must curl the fingers relative to the hand
    if pose("attack", 0.45):
        for side in "RL":
            ob = sc.objects.get("Hand_" + side)
            if not ob:
                continue
            hb = arm.matrix_world @ arm.pose.bones["HAND" + side].matrix
            fg = ob.vertex_groups.get("F1_" + side)
            idx = [v.index for v in ob.data.vertices
                   if fg and any(g.group == fg.index and g.weight > 0.3
                                 for g in v.groups)]
            posed = world_verts(ob)
            rest_pose()
            restv = world_verts(ob)
            hb0 = arm.matrix_world @ arm.pose.bones["HAND" + side].matrix
            # compare fingertip positions in the hand bone's own space
            mv = [((hb.inverted() @ posed[i]) - (hb0.inverted() @ restv[i])
                   ).length for i in idx]
            curl = sum(mv) / len(mv) if mv else 0
            check("fist_curls_fingers_" + side, curl > 0.02,
                  fingertip_move_cm=round(curl * 100, 1), verts=len(idx))
            pose("attack", 0.45)
        rest_pose()

# ------------------------------------------------------------ check renders
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "TEXTURE"
sc.render.resolution_x, sc.render.resolution_y = 600, 600
w = bpy.data.worlds.new("w")
sc.world = w
w.color = (0.6, 0.62, 0.65)
sc.view_settings.view_transform = "Standard"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = "ORTHO"


def shoot(fn, target, scale, d):
    cam.data.ortho_scale = scale
    cam.location = target + Vector(d).normalized() * 3
    cam.rotation_euler = (target - cam.location).to_track_quat(
        "-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(JOB["check_dir"], fn)
    bpy.ops.render.render(write_still=True)


for clip, frac, tag in (("", 0, "rest"), ("idle", 0.5, "idle"),
                        ("attack", 0.45, "attack")):
    if clip:
        pose(clip, frac)
    else:
        rest_pose()
    if sc.objects.get("Head"):
        shoot(tag + "_face.png", bone("HEAD") + Vector((0, 0, 0.1)), 0.5,
              (0.3, -1, 0.05))
    for s in "RL":
        if sc.objects.get("Hand_" + s):
            shoot("%s_hand_%s.png" % (tag, s), bone("HAND" + s), 0.45,
                  (0.4 if s == "L" else -0.4, -1, 0.5))
rest_pose()

bpy.ops.export_scene.gltf(filepath=JOB["out_gltf"], export_format="GLTF_SEPARATE",
                          export_texture_dir="textures", export_skins=True,
                          export_animations=True,
                          export_animation_mode="ACTIONS", export_yup=True)
REPORT["ok"] = all(c["ok"] for c in REPORT["checks"])
with open(os.path.join(JOB["check_dir"], "report.json"), "w") as f:
    json.dump(REPORT, f, indent=1)
print("FIT_DONE ok=%s" % REPORT["ok"])

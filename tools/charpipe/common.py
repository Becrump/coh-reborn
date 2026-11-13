"""Shared Blender helpers for the model-upgrade samples.

Same studio (camera, 3-point lights, HDRI, backdrop) for every sample, model
importers for each variant, materials (delit PBR, toon + ink outline) and a
direction-matching retargeter from the Meshy biped skeleton to the CoH
skeleton (male/skel_ready2 bone names).
"""
import math
import os

import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = "C:/Users/rtcru/ClaudeProjects/COHReborn/model-upgrade-samples"
WORK = ROOT + "/work"
COH = "C:/Users/rtcru/CoHReborn"
HDRI = "C:/Program Files/Blender Foundation/Blender 5.2/5.2/datafiles/studiolights/world/studio.exr"

SRC_A = COH + "/out/characters/hellions/Thug_Hellion_01/Thug_Hellion_01.gltf"
SRC_SMOOTH = COH + "/out/upgrade/Hellions/Thug_Hellion_01/smooth/Thug_Hellion_01.gltf"
SRC_FITTED = COH + "/out/upgrade/Hellions/Thug_Hellion_01/fitted/Thug_Hellion_01.gltf"
DELIT_DIR = WORK + "/B_textures"


# ---------------------------------------------------------------- scene
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def studio(res=(1920, 1080), engine="EEVEE", samples=64):
    sc = bpy.context.scene
    try:
        sc.render.engine = "BLENDER_EEVEE"
    except TypeError:
        sc.render.engine = "BLENDER_EEVEE_NEXT"
    if engine == "CYCLES":
        sc.render.engine = "CYCLES"
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "OPTIX"
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            sc.cycles.device = "GPU"
        except Exception as e:  # noqa
            print("cycles gpu setup failed", e)
    else:
        try:
            sc.eevee.taa_render_samples = samples
            sc.eevee.use_shadows = True
            sc.eevee.use_raytracing = True
        except Exception:
            pass
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = 30
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False

    # world: HDRI for light, neutral grey for the camera
    w = bpy.data.worlds.new("Studio")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(HDRI)
    bg_h = nt.nodes.new("ShaderNodeBackground")
    bg_h.inputs["Strength"].default_value = 0.45
    nt.links.new(env.outputs["Color"], bg_h.inputs["Color"])
    bg_c = nt.nodes.new("ShaderNodeBackground")
    bg_c.inputs["Color"].default_value = (0.16, 0.17, 0.19, 1)
    bg_c.inputs["Strength"].default_value = 1.0
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(bg_h.outputs[0], mix.inputs[1])
    nt.links.new(bg_c.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])

    # curved cyclorama backdrop (no visible horizon)
    import bmesh
    prof = [(-20.0, 0.0)]
    y = -20.0
    while y < 3.0:
        y += 1.0
        prof.append((y, 0.0))
    for i in range(1, 13):
        a = math.radians(90 * i / 12)
        prof.append((3.0 + 4.0 * math.sin(a), 4.0 - 4.0 * math.cos(a)))
    prof.append((7.0, 20.0))
    me = bpy.data.meshes.new("Cyc")
    bm = bmesh.new()
    rows = []
    for x in (-25.0, 25.0):
        rows.append([bm.verts.new((x, py, pz)) for py, pz in prof])
    for i in range(len(prof) - 1):
        bm.faces.new((rows[0][i], rows[1][i], rows[1][i + 1], rows[0][i + 1]))
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    fl = bpy.data.objects.new("Floor", me)
    sc.collection.objects.link(fl)
    m = bpy.data.materials.new("Floor")
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.075, 0.078, 0.085, 1)
    p.inputs["Roughness"].default_value = 0.85
    fl.data.materials.append(m)

    def area(name, loc, energy, size, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(ob)
        ob.location = loc
        d = Vector((0, 0, 1.1)) - Vector(loc)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return ob

    area("Key", (-2.6, -3.0, 3.2), 900, 2.0, (1.0, 0.96, 0.9))
    area("Fill", (3.0, -2.4, 1.6), 260, 3.0, (0.9, 0.95, 1.0))
    area("Rim", (0.8, 3.2, 2.8), 700, 1.5)

    cam_d = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam


def frame_camera(cam, shot, head_z=1.7, char_h=1.85, yaw_deg=35, center_x=0.0, head_xy=(0.0, 0.0)):
    """shot = 'full' (whole body, 3/4 front) or 'head' (close-up)."""
    yaw = math.radians(yaw_deg)
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = 20.25
    if shot == "full":
        cam.data.lens = 50
        target = Vector((center_x, 0, char_h * 0.5))
        dist = (char_h * 1.08 / 2) / math.tan(math.atan(10.125 / 50))
    else:
        cam.data.lens = 85
        target = Vector((head_xy[0], head_xy[1], head_z - 0.03))
        dist = 0.26 / math.tan(math.atan(10.125 / 85))
    pos = target + Vector((math.sin(yaw) * dist, -math.cos(yaw) * dist, (0.08 if shot == "full" else 0.02) * dist))
    cam.location = pos
    cam.rotation_euler = (target - pos).to_track_quat("-Z", "Y").to_euler()


def render(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


# ---------------------------------------------------------------- models
def import_gltf(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.name.startswith("Icosphere"):  # importer's bone shape helper
            bpy.data.objects.remove(o, do_unlink=True)
    new = [o for o in bpy.data.objects if o not in before]
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    meshes = [o for o in new if o.type == "MESH"]
    return arm, meshes


def world_bbox(meshes):
    dg = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world
        for v in me.vertices:
            p = mw @ v.co
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
        ev.to_mesh_clear()
    return lo, hi


def ground(arm, meshes):
    """Move the rig so the feet touch z=0 and the body is centred on x/y."""
    lo, hi = world_bbox(meshes)
    top = arm if arm else meshes[0]
    top.location.z -= lo.z
    top.location.x -= (lo.x + hi.x) / 2
    top.location.y -= (lo.y + hi.y) / 2
    bpy.context.view_layer.update()
    return hi.z - lo.z


def set_action(arm, name_or_action, frame=None):
    act = bpy.data.actions[name_or_action] if isinstance(name_or_action, str) else name_or_action
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = act
    try:
        if act.slots and arm.animation_data.action_slot is None:
            arm.animation_data.action_slot = act.slots[0]
    except AttributeError:
        pass
    if frame is not None:
        bpy.context.scene.frame_set(frame)
    return act


# ---------------------------------------------------------------- materials
def principled_of(mat):
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None


def basecolor_image(mat):
    p = principled_of(mat)
    if not p:
        return None
    for l in mat.node_tree.links:
        if l.to_node == p and l.to_socket.name == "Base Color" and l.from_node.type == "TEX_IMAGE":
            return l.from_node
    # sometimes through a mix node (vertex colour)
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image and not n.image.name.endswith(("_n.png", "_orm.png")):
            return n
    return None


def apply_delit(meshes, delit_dir=DELIT_DIR, normal_strength=0.6):
    for o in meshes:
        for slot in o.material_slots:
            m = slot.material
            if not m or not m.use_nodes:
                continue
            t = basecolor_image(m)
            if t and t.image:
                f = os.path.join(delit_dir, os.path.basename(t.image.filepath))
                if os.path.exists(f):
                    t.image = bpy.data.images.load(f, check_existing=True)
            for n in m.node_tree.nodes:
                if n.type == "NORMAL_MAP":
                    n.inputs["Strength"].default_value = normal_strength
            p = principled_of(m)
            if p:
                p.inputs["Specular IOR Level"].default_value = 0.4


def apply_toon(meshes, outline=0.006, rim_color=(1.0, 0.55, 0.25)):
    ink = bpy.data.materials.get("Ink")
    if not ink:
        ink = bpy.data.materials.new("Ink")
        ink.use_nodes = True
        nt = ink.node_tree
        nt.nodes.clear()
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (0.01, 0.008, 0.01, 1)
        nt.links.new(e.outputs[0], o.inputs[0])
        ink.use_backface_culling = True
    done = set()
    for ob in meshes:
        for slot in ob.material_slots:
            m = slot.material
            if not m or m in done or m == ink:
                continue
            done.add(m)
            t = basecolor_image(m)
            nt = m.node_tree
            img = t.image if t else None
            nt.nodes.clear()
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
            s2r = nt.nodes.new("ShaderNodeShaderToRGB")
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.interpolation = "CONSTANT"
            els = ramp.color_ramp.elements
            els[0].position = 0.0
            els[0].color = (0.62, 0.58, 0.70, 1)
            els[1].position = 0.12
            els[1].color = (1.05, 1.02, 1.06, 1)
            e3 = els.new(0.45)
            e3.color = (1.4, 1.37, 1.32, 1)
            bw = nt.nodes.new("ShaderNodeRGBToBW")
            mul = nt.nodes.new("ShaderNodeMix")
            mul.data_type = "RGBA"
            mul.blend_type = "MULTIPLY"
            mul.inputs["Factor"].default_value = 1.0
            lw = nt.nodes.new("ShaderNodeLayerWeight")
            lw.inputs["Blend"].default_value = 0.35
            rr = nt.nodes.new("ShaderNodeValToRGB")
            rr.color_ramp.interpolation = "CONSTANT"
            rr.color_ramp.elements[0].color = (0, 0, 0, 1)
            rr.color_ramp.elements[1].position = 0.62
            rr.color_ramp.elements[1].color = (*rim_color, 1)
            add = nt.nodes.new("ShaderNodeMix")
            add.data_type = "RGBA"
            add.blend_type = "ADD"
            add.inputs["Factor"].default_value = 0.55
            em = nt.nodes.new("ShaderNodeEmission")
            L = nt.links.new
            L(diff.outputs[0], s2r.inputs[0])
            L(s2r.outputs[0], bw.inputs[0])
            L(bw.outputs[0], ramp.inputs[0])
            if img:
                L(tex.outputs["Color"], mul.inputs["A"])
            else:
                mul.inputs["A"].default_value = (0.6, 0.6, 0.6, 1)
            L(ramp.outputs["Color"], mul.inputs["B"])
            L(lw.outputs["Facing"], rr.inputs[0])
            L(mul.outputs["Result"], add.inputs["A"])
            L(rr.outputs["Color"], add.inputs["B"])
            L(add.outputs["Result"], em.inputs["Color"])
            L(em.outputs[0], out.inputs[0])
            if img and img.alpha_mode != "NONE" and t and t.outputs.get("Alpha"):
                pass
    for ob in meshes:
        ob.data.materials.append(ink)
        mod = ob.modifiers.new("Outline", "SOLIDIFY")
        mod.thickness = -outline
        mod.offset = 1.0
        mod.use_flip_normals = True
        mod.use_rim = False
        mod.material_offset = len(ob.material_slots) - 1
        mod.material_offset_rim = len(ob.material_slots) - 1


# ---------------------------------------------------------------- retarget
# Meshy biped -> CoH skeleton.  Torso bones copy the source's world rotation
# change from its rest pose; limb bones are carried by their parent and then
# swung so their direction matches the source limb (twist comes from the
# parent, which avoids candy-wrapper twists from different bone rolls).
TORSO = [("HIPS", "Hips"), ("WAIST", "Spine02"), ("CHEST", "Spine"), ("NECK", "neck"), ("HEAD", "Head")]
LIMBS = []
for s, S in (("L", "Left"), ("R", "Right")):
    LIMBS += [
        # target, parent, target dir child, source joint, source dir end
        ("COL_" + s, "CHEST", "UARM" + s, S + "Shoulder", S + "Arm"),
        ("UARM" + s, "COL_" + s, "LARM" + s, S + "Arm", S + "ForeArm"),
        ("LARM" + s, "UARM" + s, "HAND" + s, S + "ForeArm", S + "Hand"),
        ("HAND" + s, "LARM" + s, "RING" + s, S + "Hand", S + "Hand:tail"),
        ("ULEG" + s, "HIPS", "LLEG" + s, S + "UpLeg", S + "Leg"),
        ("LLEG" + s, "ULEG" + s, "FOOT" + s, S + "Leg", S + "Foot"),
        ("FOOT" + s, "LLEG" + s, "TOE" + s, S + "Foot", S + "ToeBase"),
    ]
PARENT = {"WAIST": "HIPS", "CHEST": "WAIST", "NECK": "CHEST", "HEAD": "NECK"}
MAPPING_DOC = TORSO + [(t, s) for t, _, _, s, _ in LIMBS]


def _q(m):
    return m.to_3x3().normalized().to_quaternion()


def retarget(src_arm, tgt_arm, name, in_place=True, frames=None, time_map=None, fist=0.0):
    """Bake the source armature's current action onto tgt_arm as a new action.

    frames: iterable of source frames to sample (default: whole action).
    time_map: optional list of source frames (float) per output frame.
    fist: 0..1 curl of the CoH finger chain (Meshy rig has no fingers).
    """
    sc = bpy.context.scene
    act = src_arm.animation_data.action
    if time_map is None:
        a, b = act.frame_range
        time_map = list(range(int(math.ceil(a)), int(math.floor(b)) + 1)) if frames is None else list(frames)
    tb = tgt_arm.data.bones
    sb = src_arm.data.bones
    TW = tgt_arm.matrix_world
    TWq = _q(TW)
    SW = src_arm.matrix_world

    def t_head(b):
        return TW @ tb[b].head_local

    t_rest_q = {b.name: _q(TW @ b.matrix_local) for b in tb}
    s_rest_q = {b.name: _q(SW @ b.matrix_local) for b in sb}
    hips_rest_t = t_head("HIPS")
    hips_rest_s = SW @ sb["Hips"].head_local
    ratio = hips_rest_t.z / max(hips_rest_s.z, 1e-3)

    # sample source
    samples = []
    for f in time_map:
        fi = int(math.floor(f))
        sc.frame_set(fi, subframe=f - fi)
        P = src_arm.pose.bones
        rec = {"q": {}, "p": {}}
        for pb in P:
            M = SW @ pb.matrix
            rec["q"][pb.name] = _q(M)
            rec["p"][pb.name] = M.translation.copy()
            rec["p"][pb.name + ":tail"] = SW @ pb.tail
        samples.append(rec)

    # bake target
    if tgt_arm.animation_data is None:
        tgt_arm.animation_data_create()
    tgt_arm.animation_data.action = None
    for pb in tgt_arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    new_act = bpy.data.actions.new(name)
    tgt_arm.animation_data.action = new_act
    xy0 = None
    prevq = {}
    order = [t for t, _ in TORSO] + [l[0] for l in LIMBS]
    for i, rec in enumerate(samples):
        wq = {}
        for t, s in TORSO:
            d = rec["q"][s] @ s_rest_q[s].inverted()
            wq[t] = d @ t_rest_q[t]
        for t, par, tchild, s, send in LIMBS:
            pd = wq[par] @ t_rest_q[par].inverted()
            carried = pd @ t_rest_q[t]
            rest_dir = (t_head(tchild) - t_head(t)).normalized()
            cur_dir = pd @ rest_dir
            sdir = (rec["p"][send] - rec["p"][s]).normalized()
            sw = cur_dir.rotation_difference(sdir)
            wq[t] = sw @ carried
        # hips position
        hp = rec["p"]["Hips"]
        off = (hp - hips_rest_s) * ratio
        if in_place:
            if xy0 is None:
                xy0 = Vector((off.x, off.y, 0))
            off = Vector((0, 0, off.z))
        hips_world = hips_rest_t + off
        # world -> pose basis, parents first
        Marm = {}
        parent_of = {**PARENT, **{l[0]: l[1] for l in LIMBS}}
        for t in order:
            bone = tb[t]
            rest = bone.matrix_local
            par = parent_of.get(t)
            if par is None:
                chain = rest.copy()
            else:
                chain = Marm[par] @ tb[par].matrix_local.inverted() @ rest
            R = (TWq.inverted() @ wq[t]).to_matrix().to_4x4()
            if t == "HIPS":
                loc = TW.inverted() @ hips_world
            else:
                loc = chain.translation
            desired = Matrix.Translation(loc) @ R
            Marm[t] = desired
            basis = chain.inverted() @ desired
            pb = tgt_arm.pose.bones[t]
            q = basis.to_quaternion()
            if t in prevq:
                q.make_compatible(prevq[t])
            prevq[t] = q
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=i)
            if t == "HIPS":
                pb.location = basis.translation
                pb.keyframe_insert("location", frame=i)
        if fist:
            for s in "LR":
                for fb in ("RING" + s, "F2_" + s, "F1_" + s):
                    pb = tgt_arm.pose.bones.get(fb)
                    if pb:
                        pb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(70 * fist))
                        pb.keyframe_insert("rotation_quaternion", frame=i)
    return new_act


def impact_frame(src_arm, frames):
    """Source frame where a hand or foot is furthest in front of the hips (-Y)."""
    sc = bpy.context.scene
    best, bf = -1e9, frames[0]
    for f in frames:
        sc.frame_set(f)
        P = src_arm.pose.bones
        hip = src_arm.matrix_world @ P["Hips"].head
        for e in ("LeftHand", "RightHand", "LeftFoot", "RightFoot"):
            p = src_arm.matrix_world @ P[e].tail
            reach = -(p.y - hip.y)
            if e.endswith("Foot"):
                reach *= 0.9
            if reach > best:
                best, bf = reach, f
    return bf


SRC_J = WORK + "/J/hellion_reuv.glb"


def apply_pbr_set(meshes, base, normal=None, rough=None, metal=None):
    """Replace every material's textures with one PBR set (Meshy retexture output)."""
    for o in meshes:
        for slot in o.material_slots:
            m = slot.material
            nt = m.node_tree
            p = principled_of(m)
            for n in list(nt.nodes):
                if n.type in ("TEX_IMAGE", "NORMAL_MAP", "SEPARATE_COLOR", "SEPRGB"):
                    nt.nodes.remove(n)
            t = nt.nodes.new("ShaderNodeTexImage")
            t.image = bpy.data.images.load(base, check_existing=True)
            nt.links.new(t.outputs[0], p.inputs["Base Color"])
            if normal:
                tn = nt.nodes.new("ShaderNodeTexImage")
                tn.image = bpy.data.images.load(normal, check_existing=True)
                tn.image.colorspace_settings.name = "Non-Color"
                nm = nt.nodes.new("ShaderNodeNormalMap")
                nt.links.new(tn.outputs[0], nm.inputs["Color"])
                nt.links.new(nm.outputs[0], p.inputs["Normal"])
            for path, sock in ((rough, "Roughness"), (metal, "Metallic")):
                if path:
                    tr = nt.nodes.new("ShaderNodeTexImage")
                    tr.image = bpy.data.images.load(path, check_existing=True)
                    tr.image.colorspace_settings.name = "Non-Color"
                    nt.links.new(tr.outputs[0], p.inputs[sock])


def load_j():
    arm, meshes = import_gltf(SRC_J)
    d = WORK + "/J/texture_urls_0_"
    apply_pbr_set(meshes, d + "base_color.png", d + "normal.png", d + "roughness.png", d + "metallic.png")
    return arm, meshes

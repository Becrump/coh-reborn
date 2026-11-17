"""A-pose reference views of an original CoH character for Gemini / Tripo multi-view (Blender).

    blender -b --factory-startup -P bl_refviews_apose.py -- <character.gltf> <out_dir> <name> [--res 1024x1536] [--nogear]

Pose: the CoH rest T-pose with both upper arms lowered 52 deg (the MetaHuman bind A-pose: about
38 deg out from the body), palms facing down/inward, legs 4 deg apart.
Writes <name>_front.png, _left.png, _back.png, _right.png: orthographic, the SAME camera height,
scale and lighting for all four (so they line up for multi-view generation), flat mid-grey
background (sRGB 128), even studio light, full body head to boots. Honours CPU_HOLD.txt.
"""
import math
import os
import sys
import time

import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
src, out, name = args[0], args[1], args[2]
rx, ry = (int(v) for v in (args[args.index("--res") + 1] if "--res" in args else "1024x1536").split("x"))
HOLD = "C:/Users/rtcru/ClaudeProjects/COHReborn/CPU_HOLD.txt"
ARM_DROP = 52.0  # degrees below horizontal (MetaHuman A-pose)
LEG_OUT = 4.0
os.makedirs(out, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
NOGEAR = "--nogear" in args
GEAR_KEYS = ("hair", "eyedetail", "hat", "mask", "helmet", "goggle", "cap")
hidden = []
if NOGEAR:  # CoH puts hats/caps in the Hair part and goggles/masks in EyeDetail; bandanas are baked in the Head texture
    for o in list(meshes):
        if any(k in o.name.lower() for k in GEAR_KEYS):
            o.hide_render = True
            hidden.append(o.name)
            meshes.remove(o)
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
W = arm.matrix_world


def rot_world(bone, axis, deg):
    pb = arm.pose.bones.get(bone)
    if pb is None:
        return False
    head = W @ pb.head
    R = Matrix.Translation(head) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-head)
    pb.matrix = W.inverted() @ (R @ (W @ pb.matrix))
    bpy.context.view_layer.update()
    return True


# CoH skeletons face -Y; the character's left side (bones ...L) is at +X.
posed = []
for bone, sign in (("UARML", 1), ("UARMR", -1)):
    if rot_world(bone, "Y", sign * ARM_DROP):
        posed.append(bone)
for bone, sign in (("ULEGL", -1), ("ULEGR", 1)):
    if rot_world(bone, "Y", sign * LEG_OUT):
        posed.append(bone)

dg = bpy.context.evaluated_depsgraph_get()
lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
for o in meshes:
    me = o.evaluated_get(dg).to_mesh()
    for v in me.vertices:
        p = o.matrix_world @ v.co
        lo, hi = Vector(map(min, lo, p)), Vector(map(max, hi, p))
h = hi.z - lo.z
c = (lo + hi) / 2

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = rx, ry
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"
sc.render.film_transparent = False
w = bpy.data.worlds.new("W")
sc.world = w
w.use_nodes = True
bgc = 0.2158  # linear value of sRGB 128 (mid grey)
w.node_tree.nodes["Background"].inputs["Color"].default_value = (bgc, bgc, bgc, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
for nm, loc, e in (("Key", (-3, -4, h * 1.2), 2.2), ("Fill", (3, -3, h * 0.6), 1.2), ("Back", (0, 4, h), 1.4),
                   ("SideL", (5, 0, h * 0.7), 0.8), ("SideR", (-5, 0, h * 0.7), 0.8)):
    ld = bpy.data.lights.new(nm, "SUN")
    ld.energy = e
    ob = bpy.data.objects.new(nm, ld)
    sc.collection.objects.link(ob)
    ob.rotation_euler = (c - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
cd = bpy.data.cameras.new("Cam")
cd.type = "ORTHO"
width_needed = max(hi.x - lo.x, hi.y - lo.y) * 1.1
cd.ortho_scale = max(h * 1.08, width_needed * ry / rx)
cam = bpy.data.objects.new("Cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
for view, d, rz in (("front", Vector((0, -6, 0)), 0.0), ("left", Vector((6, 0, 0)), math.pi / 2),
                    ("back", Vector((0, 6, 0)), math.pi), ("right", Vector((-6, 0, 0)), -math.pi / 2)):
    while os.path.exists(HOLD):
        print("CPU hold: waiting", flush=True)
        time.sleep(60)
    cam.location = Vector((c.x, c.y, c.z)) + d
    cam.rotation_euler = (math.pi / 2, 0, rz)
    sc.render.filepath = os.path.join(out, "%s_%s.png" % (name, view))
    bpy.ops.render.render(write_still=True)
print("REFVIEWS_APOSE_OK", name, "posed", posed, "hidden", hidden, "height", round(h, 3))

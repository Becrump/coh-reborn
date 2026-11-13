"""Render front / left / back / right reference views of an original CoH character (Blender).

    blender -b --factory-startup -P bl_refviews.py -- <character.gltf> <out_dir> [--size 1024]

Rest pose (T-pose), orthographic, flat studio light, white background: the input charpipe
expects in <in_dir>/<character>/. Writes front.png, left.png, back.png, right.png and height.txt.
"""
import os
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
src, out = args[0], args[1]
size = int(args[args.index("--size") + 1]) if "--size" in args else 1024
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
if arm:
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    me = o.evaluated_get(dg).to_mesh()
    for v in me.vertices:
        p = o.matrix_world @ v.co
        lo, hi = Vector(map(min, lo, p)), Vector(map(max, hi, p))
h = hi.z - lo.z
c = (lo + hi) / 2
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = size
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("W")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
for name, loc in (("Key", (-3, -4, h)), ("Fill", (3, -3, h * 0.6)), ("Back", (0, 4, h))):
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = 1.6 if name == "Key" else 0.8
    ob = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(ob)
    ob.rotation_euler = (c - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
cd = bpy.data.cameras.new("Cam")
cd.type = "ORTHO"
cd.ortho_scale = max(h, hi.x - lo.x, hi.y - lo.y) * 1.1
cam = bpy.data.objects.new("Cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
for name, d, rz in (("front", Vector((0, -6, 0)), 0.0), ("left", Vector((6, 0, 0)), 1.5708),
                    ("back", Vector((0, 6, 0)), 3.1416), ("right", Vector((-6, 0, 0)), -1.5708)):
    cam.location = c + d
    cam.rotation_euler = (1.5708, 0, rz)
    sc.render.filepath = os.path.join(out, name + ".png")
    bpy.ops.render.render(write_still=True)
open(os.path.join(out, "height.txt"), "w").write("%.3f\n" % h)
print("REFVIEWS_OK", out, round(h, 3))

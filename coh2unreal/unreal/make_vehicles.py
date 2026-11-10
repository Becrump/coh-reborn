"""Prepares vehicle models for the living city (run with Blender).

    blender -b --factory-startup -P make_vehicles.py -- <car-kit folder> <out>

- Cars from Kenney's Car Kit (CC0): joined into one mesh each, scaled to a
  real-world length, facing +X, origin on the ground at the centre.
- A blimp, a monorail car and a police drone, built from primitives.
Writes <out>/<name>.glb for each.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
KIT, OUT = os.path.abspath(args[0]), os.path.abspath(args[1])
os.makedirs(OUT, exist_ok=True)

# model -> real length in metres
CARS = {"sedan": 4.7, "sedan-sports": 4.6, "suv": 4.8, "suv-luxury": 5.0,
        "taxi": 4.7, "police": 4.9, "van": 5.2, "hatchback-sports": 4.2,
        "delivery": 6.0, "truck": 7.0, "ambulance": 6.2,
        "garbage-truck": 8.5}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def join_all(name):
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in bpy.data.objects:
        o.select_set(o in meshes)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = o.data.name = name
    for e in [e for e in bpy.data.objects if e.type != "MESH"]:
        bpy.data.objects.remove(e)
    return o


def normalize(o, length):
    """Long axis -> +X, scale to length, origin at ground centre. Works on
    the vertex data directly (the mesh has no object transform left)."""
    me = o.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    if max(ys) - min(ys) > max(xs) - min(xs):
        for v in me.vertices:              # rotate 90 degrees about Z
            v.co = Vector((v.co.y, -v.co.x, v.co.z))
    xs = [v.co.x for v in me.vertices]
    s = length / (max(xs) - min(xs))
    for v in me.vertices:
        v.co *= s
    vs = [v.co for v in me.vertices]
    c = Vector(((max(v.x for v in vs) + min(v.x for v in vs)) / 2,
                (max(v.y for v in vs) + min(v.y for v in vs)) / 2,
                min(v.z for v in vs)))
    for v in me.vertices:
        v.co -= c
    me.update()


def export(name):
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, name + ".glb"),
                              export_format="GLB", export_yup=True)


def material(name, color, metal=0.0, rough=0.5, emit=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = strength
    return m


def add(prim, mat, **kw):
    getattr(bpy.ops.mesh, "primitive_%s_add" % prim)(**kw)
    o = bpy.context.object
    o.data.materials.append(mat)
    return o


# ------------------------------------------------------------------ cars
for name, length in CARS.items():
    src = os.path.join(KIT, "Models", "GLB format", name + ".glb")
    if not os.path.exists(src):
        print("missing", src)
        continue
    reset()
    bpy.ops.import_scene.gltf(filepath=src)
    o = join_all("car_" + name.replace("-", "_"))
    normalize(o, length)
    export("car_" + name.replace("-", "_"))
    print("car", name)

# ----------------------------------------------------------------- blimp
reset()
skin = material("Blimp_Skin", (0.82, 0.83, 0.86), 0.1, 0.45)
fin = material("Blimp_Fin", (0.12, 0.25, 0.55), 0.2, 0.4)
gondola = material("Blimp_Gondola", (0.15, 0.15, 0.17), 0.6, 0.3)
lamp = material("Blimp_Light", (1, 1, 1), emit=(1.0, 0.9, 0.7), strength=8)
b = add("uv_sphere", skin, segments=48, ring_count=24, radius=1)
b.scale = (30, 8, 8)                                  # 60 m long envelope
for ang in (0, 90, 180, 270):
    f = add("cube", fin, size=1, location=(-25, 0, 0))
    f.scale = (6, 0.25, 4)
    f.rotation_euler = (math.radians(ang), 0, 0)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    f.location = (-25, 6 * math.sin(math.radians(ang + 90)) * 0,
                  0)
    f.location = (-25, 5 * math.cos(math.radians(ang)), 5 * math.sin(math.radians(ang)))
g = add("cube", gondola, size=1, location=(4, 0, -8.3))
g.scale = (9, 2.6, 2.2)
for x in (-3, 0, 3, 6, 9):
    add("uv_sphere", lamp, radius=0.35, location=(x, 1.35, -8.2))
add("uv_sphere", lamp, radius=0.5, location=(-30.5, 0, 0))   # tail light
o = join_all("blimp")
export("blimp")

# --------------------------------------------------------- monorail car
reset()
body = material("Mono_Body", (0.85, 0.86, 0.9), 0.5, 0.3)
stripe = material("Mono_Stripe", (0.1, 0.3, 0.75), 0.3, 0.35)
glass = material("Mono_Glass", (0.05, 0.08, 0.1), 0.0, 0.05,
                 emit=(1.0, 0.92, 0.75), strength=1.5)
c = add("cube", body, size=1, location=(0, 0, 1.9))
c.scale = (24, 3.0, 3.2)
bev = c.modifiers.new("b", "BEVEL")
bev.width, bev.segments = 0.6, 4
add("cube", stripe, size=1, location=(0, 0, 1.1)).scale = (24.05, 3.05, 0.5)
add("cube", glass, size=1, location=(0, 0, 2.6)).scale = (21, 3.08, 1.1)
nose = add("uv_sphere", body, radius=1, location=(12, 0, 1.9))
nose.scale = (2.2, 1.5, 1.6)
o = join_all("monorail_car")
export("monorail_car")

# ----------------------------------------------------------- police drone
reset()
shell = material("Drone_Shell", (0.08, 0.09, 0.12), 0.7, 0.35)
blue = material("Drone_Blue", (0.1, 0.3, 1.0), emit=(0.2, 0.45, 1.0), strength=20)
red = material("Drone_Red", (1, 0.1, 0.1), emit=(1.0, 0.1, 0.1), strength=20)
add("uv_sphere", shell, radius=0.55).scale = (1.3, 1.0, 0.45)
for i, (x, y) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
    add("cube", shell, size=1, location=(x * 0.55, y * 0.55, 0)).scale = (0.9, 0.12, 0.08)
    add("cylinder", shell, radius=0.38, depth=0.06,
        location=(x * 0.95, y * 0.95, 0.12))
add("uv_sphere", blue, radius=0.12, location=(0.2, 0.25, 0.25))
add("uv_sphere", red, radius=0.12, location=(0.2, -0.25, 0.25))
add("cylinder", blue, radius=0.25, depth=0.05, location=(0.55, 0, -0.15))
o = join_all("police_drone")
export("police_drone")
print("done")

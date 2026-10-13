"""Builds the modern lamp models that replace CoH's street lamps.

Run with Blender (no UI):
    blender -b --factory-startup -P make_streetlights.py -- <out folder>
Writes modern_streetlight.glb and modern_parkinglight.glb (+ preview PNGs).

Sizes match the CoH lamps they replace: the street lamp head sits 6.5 m up
and 1 m out from the pole (the arm points along +X, which the Unreal setup
script turns to face the CoH lamp's direction); the parking-lot head is
7.5 m up, centred on the pole. Origin is the pole base.
"""
import math
import os
import sys

import bpy

OUT = os.path.abspath(sys.argv[sys.argv.index("--") + 1]
                      if "--" in sys.argv else ".")


def material(name, color, metallic, rough, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = rough
    if emission:
        p.inputs["Emission Color"].default_value = (*emission, 1)
        p.inputs["Emission Strength"].default_value = strength
    return m


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return (material("Lamp_Metal", (0.09, 0.1, 0.11), 0.85, 0.38),
            material("Lamp_Housing", (0.55, 0.57, 0.6), 0.7, 0.3),
            material("Lamp_LED", (1.0, 0.97, 0.9), 0.0, 0.2,
                     emission=(1.0, 0.84, 0.62), strength=6.0))


def tapered_pole(r0, r1, height, mat, z0=0.0, verts=24):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r0, radius2=r1,
                                    depth=height,
                                    location=(0, 0, z0 + height / 2))
    o = bpy.context.object
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return o


def rod(a, b, r, mat, verts=16):
    """Cylinder from point a to point b."""
    ax, ay, az = a
    bx, by, bz = b
    dx, dy, dz = bx - ax, by - ay, bz - az
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=r, depth=length,
        location=((ax + bx) / 2, (ay + by) / 2, (az + bz) / 2))
    o = bpy.context.object
    o.rotation_euler = (0, math.atan2(math.hypot(dx, dy), dz),
                        math.atan2(dy, dx))
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return o


def box(center, size, mat, bevel=0.02, tilt=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    o = bpy.context.object
    o.scale = size
    o.rotation_euler = (0, tilt, 0)
    bpy.ops.object.transform_apply(location=False, rotation=False,
                                   scale=True)
    if bevel:
        mod = o.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        bpy.ops.object.modifier_apply(modifier="bevel")
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return o


def base_plate(metal):
    tapered_pole(0.2, 0.17, 0.12, metal, verts=8)        # anchor plate
    tapered_pole(0.15, 0.13, 0.5, metal, z0=0.12)        # base shroud


def join(name):
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
    bpy.ops.object.join()
    o = bpy.context.object
    o.name = name
    o.data.name = name
    return o


def export(name):
    path = os.path.join(OUT, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB",
                              export_yup=True, export_apply=True)
    preview(name)
    print("wrote", path)


def preview(name):
    o = bpy.data.objects[name]
    cam = bpy.data.cameras.new("cam")
    c = bpy.data.objects.new("cam", cam)
    bpy.context.scene.collection.objects.link(c)
    c.location = (7.5, -9.0, 4.5)
    c.rotation_euler = (math.radians(80), 0, math.radians(40))
    cam.lens = 35
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3
    s = bpy.data.objects.new("sun", sun)
    s.rotation_euler = (math.radians(50), 0, math.radians(30))
    bpy.context.scene.collection.objects.link(s)
    world = bpy.data.worlds.new("w")
    world.color = (0.35, 0.45, 0.6)
    sc = bpy.context.scene
    sc.world = world
    sc.camera = c
    sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [
        e.identifier for e in bpy.types.RenderSettings.bl_rna.properties[
            "engine"].enum_items] else "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 600, 800
    sc.render.filepath = os.path.join(OUT, name + "_preview.png")
    bpy.ops.render.render(write_still=True)
    for ob in (c, s):
        bpy.data.objects.remove(ob)
    o.select_set(True)


# ---------------------------------------------------------- street light
metal, housing, led = reset()
base_plate(metal)
tapered_pole(0.12, 0.065, 6.0, metal, z0=0.6)
# arm: rises from the pole top and reaches 1.15 m out
rod((0.0, 0, 6.35), (0.55, 0, 6.62), 0.045, metal)
rod((0.55, 0, 6.62), (1.05, 0, 6.66), 0.04, metal)
rod((0.0, 0, 5.9), (0.45, 0, 6.6), 0.025, metal)      # brace
# LED cobra head, tilted up 5 degrees
box((1.22, 0, 6.64), (0.78, 0.32, 0.11), housing, bevel=0.04,
    tilt=math.radians(-5))
box((1.24, 0, 6.575), (0.56, 0.22, 0.02), led, bevel=0.005,
    tilt=math.radians(-5))
join("modern_streetlight")
export("modern_streetlight")

# ----------------------------------------------------- parking-lot light
metal, housing, led = reset()
base_plate(metal)
tapered_pole(0.11, 0.08, 6.9, metal, z0=0.6)
box((0, 0, 7.55), (0.62, 0.62, 0.14), housing, bevel=0.03)
box((0, 0, 7.475), (0.5, 0.5, 0.02), led, bevel=0.005)
rod((0, 0, 7.45), (0, 0, 7.6), 0.07, metal)
join("modern_parkinglight")
export("modern_parkinglight")

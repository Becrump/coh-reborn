"""Blender: street furniture for Atlas Park Reborn.

    blender -b --factory-startup -P street_kit.py -- <out dir>

SM_Reborn_TrafficSignal: a mast-arm traffic signal. The pole stands at the
origin (on the right-hand curb of an approach), the arm reaches 5.5 m along
+Y over the road, and two signal heads face +X (toward the oncoming cars).
Material slots: Pole, Housing, LampRed, LampAmber, LampGreen.
"""
import os
import sys

import bpy

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
for n in ["Pole", "Housing", "LampRed", "LampAmber", "LampGreen"]:
    bpy.data.materials.new(n)


def add(o, mat):
    o.data.materials.append(bpy.data.materials[mat])
    return o


parts = []
bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.12, depth=6.2, location=(0, 0, 3.1))
parts.append(add(bpy.context.active_object, "Pole"))
bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.07, depth=5.6, location=(0, 2.8, 5.9), rotation=(1.5708, 0, 0))
parts.append(add(bpy.context.active_object, "Pole"))
for y in (2.4, 4.9):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.05, y, 5.15))
    h = bpy.context.active_object
    h.scale = (0.32, 0.38, 1.05)
    parts.append(add(h, "Housing"))
    for z, mat in ((5.5, "LampRed"), (5.15, "LampAmber"), (4.8, "LampGreen")):
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.12, depth=0.06, location=(0.23, y, z), rotation=(0, 1.5708, 0))
        parts.append(add(bpy.context.active_object, mat))
bpy.ops.object.select_all(action="DESELECT")
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
bpy.context.active_object.name = "SM_Reborn_TrafficSignal"
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "SM_Reborn_TrafficSignal.fbx"), use_selection=True,
                         axis_forward="X", axis_up="Z", mesh_smooth_type="FACE", bake_space_transform=True)
print("SIGNAL_DONE")

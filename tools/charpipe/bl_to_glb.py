"""Convert any model (FBX / OBJ / GLB) to one GLB with its textures (Blender).
    blender -b --factory-startup -P bl_to_glb.py -- <in> <out.glb>"""
import sys

import bpy

a = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
src = a[0].lower()
if src.endswith(".fbx"):
    bpy.ops.import_scene.fbx(filepath=a[0])
elif src.endswith(".obj"):
    bpy.ops.wm.obj_import(filepath=a[0])
else:
    bpy.ops.import_scene.gltf(filepath=a[0])
for o in bpy.data.objects:
    o.select_set(o.type == "MESH" and not o.name.startswith("Icosphere"))
bpy.ops.export_scene.gltf(filepath=a[1], export_format="GLB", use_selection=True)
print("TO_GLB_OK", a[1])

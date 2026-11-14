"""Decimate a heavy generated mesh to a game budget, keeping UVs and textures (Blender).
    blender -b --factory-startup -P bl_decimate.py -- <in.glb> <out.glb> [--target 70000]"""
import sys
import bpy
a = sys.argv[sys.argv.index("--") + 1:]
src, dst = a[0], a[1]
target = int(a[a.index("--target") + 1]) if "--target" in a else 70000
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ms = [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("Icosphere")]
tot = sum(len(m.data.vertices) for m in ms)
r = min(1.0, target / max(tot, 1))
for m in ms:
    # glTF splits vertices at UV seams; weld them first (UVs live per face corner, so they survive),
    # otherwise collapsing the disconnected islands tears holes in the surface
    bpy.context.view_layer.objects.active = m
    bpy.ops.object.select_all(action="DESELECT")
    m.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.00001)
    bpy.ops.object.mode_set(mode="OBJECT")
tot = sum(len(m.data.vertices) for m in ms)
r = min(1.0, target / max(tot, 1))
for m in ms:
    md = m.modifiers.new("dec", "DECIMATE")
    md.ratio = r
    md.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = m
    bpy.ops.object.modifier_apply(modifier="dec")
bpy.ops.object.select_all(action="DESELECT")
for m in ms:
    m.select_set(True)
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True)
print("DECIMATE", tot, "->", sum(len(m.data.vertices) for m in ms), "ratio", round(r, 4))

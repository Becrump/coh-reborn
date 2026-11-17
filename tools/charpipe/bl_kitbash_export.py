"""Export a Tripo part kitbash (.blend: base body + clothing pieces) as separate GLBs in one shared space.

    blender -b <kitbash.blend> -P bl_kitbash_export.py -- <out_dir> --body <obj> --map name=obj[,name=obj...]

All meshes get the same transform: applied, then moved so the body's feet are at z=0 and the body
is centred on X/Y (metres, facing -Y). Writes <out_dir>/body.glb and <out_dir>/<name>.glb per piece,
plus layout.json (offset used). Pieces keep their exact position relative to the body.
"""
import json
import os
import sys

import bpy
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
out = a[0]
BODY = a[a.index("--body") + 1]
MAP = dict(kv.split("=", 1) for kv in a[a.index("--map") + 1].split(","))
os.makedirs(out, exist_ok=True)
if bpy.context.object and bpy.context.object.mode != "OBJECT":
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except RuntimeError:
        pass
body = bpy.data.objects[BODY]
vs = [body.matrix_world @ v.co for v in body.data.vertices]
off = Vector(((min(p.x for p in vs) + max(p.x for p in vs)) / 2, (min(p.y for p in vs) + max(p.y for p in vs)) / 2, min(p.z for p in vs)))
T = Matrix.Translation(-off)


def export(obj, path):
    me = obj.data.copy()
    me.transform(T @ obj.matrix_world)
    if ".sculpt_mask" in me.attributes:
        me.attributes.remove(me.attributes[".sculpt_mask"])
    o = bpy.data.objects.new(os.path.splitext(os.path.basename(path))[0], me)
    bpy.context.scene.collection.objects.link(o)
    for x in bpy.context.view_layer.objects:
        x.select_set(False)
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True)
    bpy.data.objects.remove(o, do_unlink=True)


export(body, os.path.join(out, "body.glb"))
for name, ob in MAP.items():
    export(bpy.data.objects[ob], os.path.join(out, name + ".glb"))
json.dump({"offset": list(off), "body": BODY, "pieces": MAP}, open(os.path.join(out, "layout.json"), "w"), indent=1)
print("KB_EXPORT_OK", len(MAP) + 1, "files, offset", [round(x, 3) for x in off])

"""Give a headless body a temporary proxy head so bl_autorig can fit the neck/head joints (Blender).

    blender -b --factory-startup -P bl_proxy_head.py -- <headless.glb> <out.glb> --height-cm 182 [--report r.json]

The body's top (neck stump) stays where it is; an ellipsoid head (width 0.088 H, depth 0.11 H)
is added from 5 mm above the stump to the full height H, so the whole figure is H tall again.
After rigging, bl_weight_polish.py --cut-above <stump_z + 0.004> removes it again (the report
gives that value).
"""
import json
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
src, dst = a[0], a[1]
H = float(a[a.index("--height-cm") + 1]) / 100.0
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ms = [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("Icosphere")]
vs = [o.matrix_world @ v.co for o in ms for v in o.data.vertices]
top = max(v.z for v in vs)
ring = [v for v in vs if v.z > top - 0.03]
cx = sum(v.x for v in ring) / len(ring)
cy = sum(v.y for v in ring) / len(ring)
z0 = top + 0.005
hh = H - z0
me = bpy.data.meshes.new("PROXY_HEAD")
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=0.5)
bmesh.ops.transform(bm, verts=bm.verts, matrix=Matrix.Translation(Vector((cx, cy, z0 + hh / 2)))
                    @ Matrix.Diagonal((0.088 * H, 0.11 * H, hh, 1.0)))
bm.to_mesh(me)
bm.free()
ob = bpy.data.objects.new("PROXY_HEAD", me)
bpy.context.scene.collection.objects.link(ob)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True)
rep = {"stump_z": top, "cut_above": top + 0.004, "height_m": H}
print("PROXY_OK", json.dumps(rep))
if "--report" in a:
    json.dump(rep, open(a[a.index("--report") + 1], "w"), indent=1)

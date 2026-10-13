"""Blender: road surface tiles (npz from build_road_surface.py) -> FBX.

    blender -b --factory-startup -P road_tiles.py -- <out dir>

Each road_tiles/T_*.npz becomes road_tiles/fbx/SM_Road_T_*.fbx: one mesh with
material slots Asphalt, Curb, Sidewalk, PaintWhite, PaintYellow. Vertices are
in metres relative to the tile corner in Unreal's axes (x east, y south);
Blender is right-handed, so y is mirrored here and the FBX importer turns it
back. UVs are world-aligned: asphalt 6 m, sidewalk 1.5 m, curb / paint 1 m.
"""
import glob
import os
import sys

import bmesh
import bpy
import numpy as np

OUT = sys.argv[sys.argv.index("--") + 1]
SRC = os.path.join(OUT, "road_tiles")
DST = os.path.join(SRC, "fbx")
os.makedirs(DST, exist_ok=True)
SLOTS = [("asphalt", "Asphalt", 6.0), ("curb", "Curb", 1.0), ("sidewalk", "Sidewalk", 1.5),
         ("paint_white", "PaintWhite", 1.0), ("paint_yellow", "PaintYellow", 1.0)]


def build(name, data):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = [bpy.data.materials.new(s[1]) for s in SLOTS]
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for m in mats:
        me.materials.append(m)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    ox, oy = data["origin"]
    for si, (key, _, tile) in enumerate(SLOTS):
        if key + "_v" not in data:
            continue
        v = data[key + "_v"].astype(float)
        f = data[key + "_f"]
        # weld shared corners (per material) so the surface shades smoothly
        q = np.round(v * 200).astype(np.int64)
        uniq, inv = np.unique(q, axis=0, return_inverse=True)
        inv = inv.ravel()
        pos = np.zeros((len(uniq), 3))
        pos[inv] = v
        verts = [bm.verts.new((p[0], -p[1], p[2])) for p in pos]
        for tri in f:
            a, b, c = inv[tri[0]], inv[tri[1]], inv[tri[2]]
            if len({a, b, c}) < 3:
                continue
            try:
                face = bm.faces.new((verts[a], verts[c], verts[b]))     # mirrored y: reverse winding
            except ValueError:
                continue
            face.material_index = si
            for loop in face.loops:
                co = loop.vert.co
                loop[uv].uv = ((co.x + ox) / tile, (-co.y + oy) / tile)
    bm.normal_update()
    # faces point up (or out of the curb): fix any that came out upside down
    for face in bm.faces:
        if abs(face.normal.z) > 0.3 and face.normal.z < 0:
            face.normal_flip()
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    try:
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.shade_smooth_by_angle(angle=0.6)
    except Exception:
        pass
    bpy.ops.export_scene.fbx(filepath=os.path.join(DST, name + ".fbx"), use_selection=True,
                             axis_forward="X", axis_up="Z", mesh_smooth_type="FACE", bake_space_transform=True)


n = 0
for path in sorted(glob.glob(os.path.join(SRC, "T_*.npz"))):
    data = dict(np.load(path))
    name = "SM_Road_" + os.path.splitext(os.path.basename(path))[0].replace("+", "p").replace("-", "m")
    build(name, data)
    n += 1
print("ROAD_TILES_DONE", n)

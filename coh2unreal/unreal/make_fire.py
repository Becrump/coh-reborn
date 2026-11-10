"""Builds the flame-card mesh for braziers and fires (run with Blender).

    blender -b --factory-startup -P make_fire.py -- <out folder>

fire_cards.glb: three upright 1 m x 0.6 m quads crossed at 60 degrees, origin
at the base centre, UV V running up the flame (0 at the base) so the fire
material can scroll its noise upwards.
"""
import math
import os
import sys

import bpy
import bmesh

OUT = os.path.abspath(sys.argv[sys.argv.index("--") + 1:][0])
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
me = bpy.data.meshes.new("fire_cards")
bm = bmesh.new()
uv = bm.loops.layers.uv.new("UVMap")
W, H = 0.3, 1.0
for k in range(3):
    a = math.radians(60 * k)
    dx, dy = math.cos(a) * W, math.sin(a) * W
    vs = [bm.verts.new(p) for p in ((-dx, -dy, 0), (dx, dy, 0),
                                    (dx, dy, H), (-dx, -dy, H))]
    f = bm.faces.new(vs)
    for loop, c in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = c
bm.normal_update()
bm.to_mesh(me)
bm.free()
ob = bpy.data.objects.new("fire_cards", me)
bpy.context.scene.collection.objects.link(ob)
me.materials.append(bpy.data.materials.new("Fire"))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "fire_cards.glb"),
                          export_format="GLB", export_yup=True)
print("fire cards written to", OUT)

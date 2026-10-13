"""Builds water-jet meshes for fountains (run with Blender).

    blender -b --factory-startup -P make_jets.py -- <out folder>

Writes three meshes, 1 m tall/wide at scale 1, origin at the jet base, UV V
running along the flow (0 at the nozzle) so a panning material makes the
water move:
  jet_column.glb  tapered rising column
  jet_bell.glb    water arcing out from the top of a jet and falling back
                  (surface of revolution of a falling parabola), origin at
                  the top where it starts
  jet_crown.glb   short flared foam ring where water lands in the pool
"""
import math
import os
import sys

import bpy
import bmesh

OUT = os.path.abspath(sys.argv[sys.argv.index("--") + 1:][0])
os.makedirs(OUT, exist_ok=True)
SEG = 32


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def revolve(name, profile):
    """Mesh from a (radius, height, v) profile revolved around Z."""
    reset()
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    rings = []
    for r, z, _v in profile:
        ring = []
        for k in range(SEG + 1):
            a = 2 * math.pi * k / SEG
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
        rings.append(ring)
    for i in range(len(profile) - 1):
        for k in range(SEG):
            f = bm.faces.new((rings[i][k], rings[i][k + 1],
                              rings[i + 1][k + 1], rings[i + 1][k]))
            us = (k / SEG, (k + 1) / SEG)
            vs = (profile[i][2], profile[i + 1][2])
            for loop, (u, v) in zip(f.loops, ((us[0], vs[0]), (us[1], vs[0]),
                                              (us[1], vs[1]), (us[0], vs[1]))):
                loop[uv].uv = (u * 2, v)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new("Water_Jet")
    me.materials.append(mat)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, name + ".glb"),
                              export_format="GLB", export_yup=True)


# rising column: 1 m tall, 6 cm at the nozzle narrowing to 2.5 cm
N = 12
revolve("jet_column", [(0.06 - 0.035 * (i / N), i / N, i / N)
                       for i in range(N + 1)])
# bell: from the top, out and down like a falling arc (1 m wide, 1 m drop)
revolve("jet_bell", [(0.02 + 0.98 * (i / N), -(i / N) ** 2, i / N)
                     for i in range(N + 1)])
# crown: low foam ring flaring outwards from the impact point
revolve("jet_crown", [(0.35 + 0.25 * (i / N), 0.25 * math.sin(math.pi * i / N),
                       i / N) for i in range(N + 1)])
print("jets written to", OUT)

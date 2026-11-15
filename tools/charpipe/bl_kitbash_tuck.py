"""Tuck a base body under separately generated clothing pieces (kitbash fix, Blender).

    blender -b <kitbash.blend> -P bl_kitbash_tuck.py -- <out.blend> --body <name> [--skip name,name] [--gap 0.01] [--reach 0.05]

For every body vertex, rays along +/- its normal look for the nearest clothing surface within
--reach (default 5 cm) whose normal faces the same way (dot > 0.3). If the skin is outside that
surface or closer than --gap (1 cm) under it, the vertex is moved to --gap under the cloth.
Result: no skin/underwear pokes through jeans, shirts, vests, boots or masks, and nothing is
deleted (the body stays watertight for rigging). The sculpt mask on the body is cleared.
--skip: clothing objects to ignore (e.g. gloves that are not placed on the hands yet).
"""
import json
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

a = sys.argv[sys.argv.index("--") + 1:]
out = a[0]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
BODY = opt("--body")
SKIP = set(filter(None, (opt("--skip", "") or "").split(",")))
GAP = float(opt("--gap", 0.01))
REACH = float(opt("--reach", 0.05))
dg = bpy.context.evaluated_depsgraph_get()
body = bpy.data.objects[BODY]
cloth = [o for o in bpy.data.objects if o.type == "MESH" and o is not body and o.name not in SKIP and o.visible_get()]
trees = []
for o in cloth:
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    verts = [o.matrix_world @ v.co for v in me.vertices]
    polys = [tuple(p.vertices) for p in me.polygons]
    trees.append((o.name, BVHTree.FromPolygons(verts, polys)))
    ev.to_mesh_clear()

M = body.matrix_world
Mi = M.inverted()
N3 = M.to_3x3().inverted().transposed()
me = body.data
moved, per = 0, {}
for v in me.vertices:
    p = M @ v.co
    n = (N3 @ v.normal).normalized()
    best = None
    for name, t in trees:
        for d in (n, -n):
            hit, hn, _, dist = t.ray_cast(p, d, REACH)
            if hit is None or hn.dot(n) < 0.3 and (-hn).dot(n) < 0.3:
                continue
            s = (hit - p).dot(n)  # + : cloth is outside the skin
            if best is None or abs(s) < abs(best[0]):
                best = (s, hit, name)
    if best is None:
        continue
    s, hit, name = best
    if s < GAP:  # skin outside the cloth or too close under it
        target = hit - n * GAP
        v.co = Mi @ target
        moved += 1
        per[name] = per.get(name, 0) + 1
me.update()
if ".sculpt_mask" in me.attributes:
    me.attributes.remove(me.attributes[".sculpt_mask"])
bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
rep = {"body": BODY, "clothing": [c.name for c in cloth], "skipped": sorted(SKIP), "verts_tucked": moved, "by_piece": per}
print("TUCK_OK", json.dumps(rep))

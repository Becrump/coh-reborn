"""Road centerlines for the whole Reborn map.

    python tools/reborn/plan_roads.py <guide dir> <out dir>

Old zone: the street pixels of the guide (class 1) are thinned to a
one-pixel skeleton, traced into polylines and given a width from the
distance to the road edge. New areas: the polylines from layout.json.
Everything is noded together so every crossing is a junction, short spurs
are dropped, and each road piece is trimmed back from its junctions so
curbs and markings stop at the intersection.

Writes roads.json:
  roads:     [{id, points [[x, y], ...] (m), width (m), lanes, ends: [junction?, junction?]}]
  junctions: [{id, center [x, y], radius, roads: [ids]}]
and roads_plan.png.
"""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np
from scipy import ndimage
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge, unary_union

GUIDE, OUT = sys.argv[1], sys.argv[2]
lay = json.load(open(os.path.join(OUT, "layout.json")))
CORE = lay["core"]
GX0, GY0 = -870.0, -636.0

base = np.load(os.path.join(GUIDE, "base_class.npy"))
road = base == 1
# 1 m grid inside the core
r0, r1 = int((CORE[1] - GY0) * 2), int((CORE[3] - GY0) * 2)
c0, c1 = int((CORE[0] - GX0) * 2), int((CORE[2] - GX0) * 2)
m = road[r0:r1, c0:c1]
m = m[: m.shape[0] // 2 * 2, : m.shape[1] // 2 * 2]
m = m.reshape(m.shape[0] // 2, 2, m.shape[1] // 2, 2).mean((1, 3)) > 0.5
# the street pixels have gaps under trees, bridges and the monorail; the
# original traffic beacons (cars' lane points, ~4 m apart) are continuous,
# so the drivable network is the beacons grown to road width
life = json.load(open(os.path.join(os.path.dirname(GUIDE.rstrip("/\\")), "..", "atlas_park_v5", "atlas_park_life.json")))
bm = np.zeros_like(m)
for t in life["traffic"]:
    x, y = t["p"][0] / 100, t["p"][1] / 100
    r, c = int(y - (GY0 + r0 / 2)), int(x - (GX0 + c0 / 2))
    if 0 <= r < bm.shape[0] and 0 <= c < bm.shape[1]:
        bm[r, c] = True
bm = ndimage.binary_dilation(bm, structure=np.ones((3, 3)), iterations=6)
roadpix = m.copy()
m = ndimage.binary_closing(bm, structure=np.ones((3, 3)), iterations=12)
lab, n = ndimage.label(m)
sizes = ndimage.sum(m, lab, range(1, n + 1))
m = np.isin(lab, 1 + np.nonzero(sizes > 400)[0])
dist = ndimage.distance_transform_edt(ndimage.binary_closing(roadpix | m, iterations=2))
X0, Y0 = GX0 + c0 / 2, GY0 + r0 / 2          # metres of pixel (0, 0) corner


def thin(img):
    """Zhang-Suen thinning"""
    img = img.copy().astype(np.uint8)
    changed = True
    while changed:
        changed = False
        for step in range(2):
            p = np.pad(img, 1)
            P2, P3, P4 = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:]
            P5, P6, P7 = p[2:, 2:], p[2:, 1:-1], p[2:, :-2]
            P8, P9 = p[1:-1, :-2], p[:-2, :-2]
            nb = [P2, P3, P4, P5, P6, P7, P8, P9]
            B = sum(x.astype(int) for x in nb)
            A = sum(((nb[i] == 0) & (nb[(i + 1) % 8] == 1)).astype(int) for i in range(8))
            if step == 0:
                c = (P2 * P4 * P6 == 0) & (P4 * P6 * P8 == 0)
            else:
                c = (P2 * P4 * P8 == 0) & (P2 * P6 * P8 == 0)
            rem = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if rem.any():
                img[rem] = 0
                changed = True
    return img.astype(bool)


sk = thin(m)
ys, xs = np.nonzero(sk)
pix = set(zip(ys.tolist(), xs.tolist()))
NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def nbrs(p):
    return [(p[0] + dy, p[1] + dx) for dy, dx in NB if (p[0] + dy, p[1] + dx) in pix]


deg = {p: len(nbrs(p)) for p in pix}
nodes = {p for p, d in deg.items() if d != 2}
seen = set()
lines = []
for s in nodes:
    for q in nbrs(s):
        if (s, q) in seen:
            continue
        path = [s, q]
        seen.add((s, q))
        seen.add((q, s))
        prev, cur = s, q
        while cur not in nodes:
            nx = [t for t in nbrs(cur) if t != prev and (cur, t) not in seen]
            if not nx:
                break
            prev, cur = cur, nx[0]
            seen.add((prev, cur))
            seen.add((cur, prev))
            path.append(cur)
        lines.append(path)
core_lines = []
for path in lines:
    if len(path) < 6:
        continue
    pts = [(X0 + c + 0.5, Y0 + r + 0.5) for r, c in path]
    w = 2 * float(np.median([dist[r, c] for r, c in path]))
    core_lines.append((LineString(pts).simplify(1.2), w))

# new roads from the layout (16 m), plus the core skeleton
allines = [(LineString(p), lay["road_width"]) for p in lay["roads"].values()]
allines += core_lines
# bridge dead ends to the nearest other road (gaps where the beacons stop
# short of a crossing, and core streets that stop at the old wall)
geoms = [l for l, _ in allines]
for i, (l, w) in enumerate(list(allines)):
    for end in (Point(l.coords[0]), Point(l.coords[-1])):
        others = [g for j, g in enumerate(geoms) if j != i]
        if min(g.distance(end) for g in others) < 3:
            continue
        best = min(others, key=lambda g: g.distance(end))
        if best.distance(end) < 40:
            q = best.interpolate(best.project(end))
            allines.append((LineString([end, q]), w))
noded = unary_union([l for l, _ in allines])
segs = list(getattr(noded, "geoms", [noded]))


def width_of(seg):
    mid = seg.interpolate(0.5, normalized=True)
    best, bw = 1e9, 16.0
    for l, w in allines:
        d = l.distance(mid)
        if d < best:
            best, bw = d, w
    return bw


# junctions: endpoints shared by 3+ segments
ends = defaultdict(list)
for i, s in enumerate(segs):
    for p in (s.coords[0], s.coords[-1]):
        ends[(round(p[0], 1), round(p[1], 1))].append(i)
# merge endpoints that are within 4 m of each other (skeleton junction blobs)
keys = list(ends)
cluster = {}
for k in keys:
    for c in list(cluster):
        if math.dist(k, c) < 12:
            cluster[k] = cluster[c]
            break
    else:
        cluster[k] = k
jn = defaultdict(set)
for k, ids in ends.items():
    for i in ids:
        jn[cluster[k]].add(i)
# drop short dead-end spurs (skeleton noise)
drop = set()
for i, s in enumerate(segs):
    a = cluster[(round(s.coords[0][0], 1), round(s.coords[0][1], 1))]
    b = cluster[(round(s.coords[-1][0], 1), round(s.coords[-1][1], 1))]
    if s.length < 25 and (len(jn[a]) == 1 or len(jn[b]) == 1):
        drop.add(i)
roads, junctions = [], []
jid = {}
for c, ids in jn.items():
    ids = [i for i in ids if i not in drop]
    if len(ids) >= 3:
        jid[c] = len(junctions)
        junctions.append({"id": len(junctions), "center": [c[0], c[1]], "roads": []})
for i, s in enumerate(segs):
    if i in drop or s.length < 4:
        continue
    w = min(18.0, max(10.0, width_of(s)))
    a = cluster[(round(s.coords[0][0], 1), round(s.coords[0][1], 1))]
    b = cluster[(round(s.coords[-1][0], 1), round(s.coords[-1][1], 1))]
    ja, jb = jid.get(a), jid.get(b)
    trim_a = w / 2 + 3 if ja is not None else 0
    trim_b = w / 2 + 3 if jb is not None else 0
    if s.length - trim_a - trim_b < 6:
        continue
    from shapely.ops import substring
    t = substring(s, trim_a, s.length - trim_b)
    rid = len(roads)
    roads.append({"id": rid, "points": [[round(x, 2), round(y, 2)] for x, y in t.coords], "width": round(w, 1),
                  "lanes": 4 if w >= 13 else 2, "ends": [ja, jb], "length": round(t.length, 1)})
    for j in (ja, jb):
        if j is not None:
            junctions[j]["roads"].append(rid)
# points every 20 m with the landscape height, for the road splines in Unreal
from PIL import Image
hm = (np.asarray(Image.open(os.path.join(OUT, "heightmap.png"))).astype(float) - 32768) / 128
LX0, LY0 = lay["landscape"]["origin_cm"][0] / 100, lay["landscape"]["origin_cm"][1] / 100
for r in roads:
    pts = r["points"]
    dense = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.dist((x0, y0), (x1, y1)) // 20))
        for k in range(n):
            dense.append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
    dense.append(tuple(pts[-1]))
    r["dense"] = [[round(x, 2), round(y, 2), round(float(hm[min(max(int(round(y - LY0)), 0), 2016),
                                                           min(max(int(round(x - LX0)), 0), 2016)]), 2)]
                  for x, y in dense]
for j in junctions:
    ws = [roads[r]["width"] for r in j["roads"]]
    j["radius"] = round(max(ws) / 2 + 3, 1) if ws else 10
with open(os.path.join(OUT, "roads.json"), "w") as f:
    json.dump({"roads": roads, "junctions": junctions}, f)
tot = sum(r["length"] for r in roads)
print("roads", len(roads), "junctions", len(junctions), "length km", round(tot / 1000, 1),
      "4-lane", sum(r["lanes"] == 4 for r in roads))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 12))
for r in roads:
    p = np.array(r["points"])
    ax.plot(p[:, 0], p[:, 1], color="#c33" if r["lanes"] == 4 else "#36c", lw=1.2)
for j in junctions:
    ax.add_patch(plt.Circle(j["center"], j["radius"], fill=False, color="k", lw=0.5))
ax.set_aspect("equal")
ax.set_ylim(1000, -1100)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "roads_plan.png"), dpi=80)

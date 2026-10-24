"""City reset, stage 2: road surface from the approved plan (offline part).

    python tools/reborn/build_road_surface.py <out dir>

Reads roads_dense.json (densify_roads.py), heightmap.png and layout.json and
writes, next to them:

  ground_z.npy        THE shared ground height (metres, 1 m grid, landscape
                      layout): road surface on the asphalt, +15 cm on curbs and
                      sidewalks, the landscape graded back to its own height
                      beyond. Roads, sidewalks, building grounding, car and
                      pedestrian lanes all use this one function.
  heightmap.png       the landscape graded to it (the old one is kept as
                      heightmap_pre_stage2.png); 10 cm below the road and
                      sidewalk meshes so they never z-fight
  surface.png         ground paint: old road asphalt and old sidewalk paving
                      that no new street covers become lawn (old one kept)
  roads.json          the new network in the format the lane, lamp and signal
                      steps read (old one kept as roads_pre_stage2.json):
                      avenues and streets, trimmed at junctions; alleys carry
                      no traffic and are left out
  road_tiles/*.npz    road surface meshes per 250 m tile, by material:
                      asphalt, curb (top and face, continuous), sidewalk,
                      paint_white, paint_yellow - for blender/road_tiles.py
  stage2_report.txt

Grading: every road gets a height profile - the terrain along it smoothed over
30 m, pinned to its junctions (each junction one height) - and is flat across.
Sidewalks sit 15 cm above the road. Outside the sidewalks the ground eases
back to the terrain over 10-60 m (4 x the height difference), so there is no
steep lawn terrace at the road edge. Water and lakes are never regraded.
"""
import json
import math
import os
import shutil
import sys
from collections import Counter, defaultdict

import numpy as np
import shapely
from matplotlib.path import Path as MPath
from PIL import Image
from scipy import ndimage
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

OUT = sys.argv[1]
lay = json.load(open(os.path.join(OUT, "layout.json")))
dense = json.load(open(os.path.join(OUT, "roads_dense.json")))
lots_plan = json.load(open(os.path.join(OUT, "lots_plan.json")))
LND = lay["landscape"]
LX0, LY0 = LND["origin_cm"][0] / 100.0, LND["origin_cm"][1] / 100.0
N = LND["verts"]
CLASSES = dense["classes"]
SIDEWALK = 4.0          # sidewalk width (m) outside the curb
CURB = 0.3              # curb top width (m)
CURB_H = 0.15           # curb height (m)
CORNER_R = 6.0          # curb radius at junction corners (m)
TILE = 250.0
UNDER = 0.10            # landscape this far below the road / sidewalk meshes

# ------------------------------------------------------------------ inputs
if not os.path.exists(os.path.join(OUT, "heightmap_pre_stage2.png")):
    shutil.copy(os.path.join(OUT, "heightmap.png"), os.path.join(OUT, "heightmap_pre_stage2.png"))
    shutil.copy(os.path.join(OUT, "surface.png"), os.path.join(OUT, "surface_pre_stage2.png"))
    shutil.copy(os.path.join(OUT, "roads.json"), os.path.join(OUT, "roads_pre_stage2.json"))
T = (np.asarray(Image.open(os.path.join(OUT, "heightmap_pre_stage2.png"))).astype(np.float64) - 32768.0) / 128.0
old_roads = json.load(open(os.path.join(OUT, "roads_pre_stage2.json")))


def terrain(x, y):
    """bilinear terrain height (m) at world metres"""
    c = np.clip(np.asarray(x, float) - LX0, 0, N - 1.001)
    r = np.clip(np.asarray(y, float) - LY0, 0, N - 1.001)
    c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
    fc, fr = c - c0, r - r0
    return (T[r0, c0] * (1 - fc) * (1 - fr) + T[r0, c0 + 1] * fc * (1 - fr) +
            T[r0 + 1, c0] * (1 - fc) * fr + T[r0 + 1, c0 + 1] * fc * fr)


def poly(p):
    g = Polygon(p)
    return g if g.is_valid else g.buffer(0)


water = unary_union([poly(lots_plan["water"])] + [poly(w["poly"]) for w in lay["waters"] if w.get("poly")])

# ------------------------------------------------------------------ network
lines = [(LineString(r["points"]), r["class"]) for r in dense["roads"]]
noded = unary_union([l for l, _ in lines])
pieces = [s for s in getattr(noded, "geoms", [noded]) if s.length > 0.5]
ORDER = {"avenue": 0, "street": 1, "alley": 2}


def class_of(seg):
    mid = seg.interpolate(0.5, normalized=True)
    best = min(lines, key=lambda lc: (round(lc[0].distance(mid), 2), ORDER[lc[1]]))
    return best[1]


def key(p):
    return (round(p[0], 1), round(p[1], 1))


P = [{"line": s, "cls": class_of(s)} for s in pieces]
deg = Counter()
for p in P:
    deg[key(p["line"].coords[0])] += 1
    deg[key(p["line"].coords[-1])] += 1
# join pieces through points where exactly two of the same class meet
changed = True
while changed:
    changed = False
    for k, n in list(deg.items()):
        if n != 2:
            continue
        two = [p for p in P if key(p["line"].coords[0]) == k or key(p["line"].coords[-1]) == k]
        if len(two) != 2 or two[0] is two[1] or two[0]["cls"] != two[1]["cls"]:
            continue
        a, b = two
        ca, cb = list(a["line"].coords), list(b["line"].coords)
        if key(ca[0]) == k:
            ca = ca[::-1]
        if key(cb[-1]) == k:
            cb = cb[::-1]
        if key(ca[0]) == key(cb[-1]):        # closed loop
            continue
        P.remove(a)
        P.remove(b)
        P.append({"line": LineString(ca + cb[1:]), "cls": a["cls"]})
        deg[k] = 0
        changed = True
        break
deg = Counter()
for p in P:
    deg[key(p["line"].coords[0])] += 1
    deg[key(p["line"].coords[-1])] += 1
junction_keys = [k for k, n in deg.items() if n >= 3]
jidx = {k: i for i, k in enumerate(junction_keys)}


def chaikin(pts, n=2):
    """corner cutting: smooth bends, no zigzags; the ends stay"""
    pts = np.asarray(pts, float)
    for _ in range(n):
        if len(pts) < 3:
            break
        q = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            q.append(0.75 * a + 0.25 * b)
            q.append(0.25 * a + 0.75 * b)
        q.append(pts[-1])
        pts = np.array(q)
    return pts


for p in P:
    l = p["line"].simplify(0.5)
    sm = chaikin(list(l.coords), 3)
    p["smooth"] = LineString(sm)
    p["w"] = CLASSES[p["cls"]]["width"]
    p["ja"] = jidx.get(key(p["line"].coords[0]))
    p["jb"] = jidx.get(key(p["line"].coords[-1]))

# ------------------------------------------------------------------ heights
jz = {}
for k, i in jidx.items():
    xs, ys = np.meshgrid(np.linspace(k[0] - 12, k[0] + 12, 9), np.linspace(k[1] - 12, k[1] + 12, 9))
    jz[i] = float(np.median(terrain(xs.ravel(), ys.ravel())))
STEP = 2.0
for p in P:
    l = p["smooth"]
    n = max(2, int(l.length // STEP) + 1)
    ss = np.linspace(0, l.length, n)
    xy = np.array([l.interpolate(s).coords[0] for s in ss])
    t = terrain(xy[:, 0], xy[:, 1])
    win = max(1, int(30 / STEP))
    k = np.ones(2 * win + 1) / (2 * win + 1)
    tp = np.pad(t, win, mode="edge")
    sm = np.convolve(tp, k, mode="valid")
    fa = (ss / max(l.length, 1e-6))
    if p["ja"] is not None:
        sm = sm + (jz[p["ja"]] - sm[0]) * (1 - fa)
    if p["jb"] is not None:
        sm = sm + (jz[p["jb"]] - sm[-1]) * fa
    p["s"], p["xy"], p["z"] = ss, xy, sm

# road height everywhere: the height of the nearest centre-line sample
grid_h = np.full((N, N), np.nan)
for p in P:
    c = np.clip(np.round(p["xy"][:, 0] - LX0).astype(int), 0, N - 1)
    r = np.clip(np.round(p["xy"][:, 1] - LY0).astype(int), 0, N - 1)
    grid_h[r, c] = p["z"]
miss = np.isnan(grid_h)
_, (ri, ci) = ndimage.distance_transform_edt(miss, return_indices=True)
Hroad = grid_h[ri, ci]

# footprints: asphalt (with rounded corners), curb, sidewalk
road_area = unary_union([p["smooth"].buffer(p["w"] / 2, cap_style=2, join_style=1) for p in P])
road_area = road_area.buffer(CORNER_R, join_style=1).buffer(-CORNER_R, join_style=1)
road_area = road_area.difference(water)
curb_area = road_area.buffer(CURB, join_style=1).difference(road_area).difference(water)
walk_area = road_area.buffer(CURB + SIDEWALK, join_style=1).difference(road_area.buffer(CURB, join_style=1)).difference(water)
corridor = road_area.buffer(CURB + SIDEWALK, join_style=1).difference(water)

def raster_px(geom, n, x0, y0, res):
    """polygon fill on an n x n grid (pixel centres at x0 + (i + 0.5) * res); holes cut out"""
    from PIL import ImageDraw
    img = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(img)

    def px(cs):
        return [((x - x0) / res - 0.5, (y - y0) / res - 0.5) for x, y in cs]
    # largest first, so islands inside another part's hole are drawn after the hole is cut
    parts = [g for g in getattr(geom, "geoms", [geom]) if isinstance(g, Polygon) and not g.is_empty]
    for g in sorted(parts, key=lambda g: -g.area):
        d.polygon(px(g.exterior.coords), fill=1)
        for h in g.interiors:
            d.polygon(px(h.coords), fill=0)
    return np.asarray(img).astype(bool)


def raster(geom):
    # landscape vertices sit at LX0 + i (1 m): pixel centre offset -0.5 m
    return raster_px(geom, N, LX0 - 0.5, LY0 - 0.5, 1.0)


m_road = raster(road_area)
m_corr = raster(corridor)
m_water = raster(water.buffer(3))
# shared ground: road on asphalt, +15 cm on curbs / sidewalks, eased to terrain outside
G = T.copy()
G[m_corr] = Hroad[m_corr] + CURB_H
G[m_road] = Hroad[m_road]
dist, (ei, ej) = ndimage.distance_transform_edt(~m_corr, return_indices=True)
E = Hroad[ei, ej] + CURB_H
D = np.clip(4 * np.abs(T - E), 10, 60)
w = np.clip(dist / D, 0, 1)
w = w * w * (3 - 2 * w)
out = ~m_corr
G[out] = (E + (T - E) * w)[out]
G[m_water] = T[m_water]
np.save(os.path.join(OUT, "ground_z.npy"), G.astype(np.float32))
# landscape: 10 cm under the road / sidewalk meshes
Lh = G.copy()
Lh[m_corr] -= UNDER
hm16 = np.clip(np.round(Lh * 128 + 32768), 0, 65535).astype(np.uint16)
Image.fromarray(hm16).save(os.path.join(OUT, "heightmap.png"))
slope = np.hypot(*np.gradient(G))
ring = (~m_corr) & (dist < 60) & ~m_water

# ------------------------------------------------------------------ ground paint
surf = np.array(Image.open(os.path.join(OUT, "surface_pre_stage2.png")))
SN = surf.shape[0]
SRES = (N - 1) / SN
old_corr = unary_union([LineString(r["points"]).buffer(r["width"] / 2 + lay.get("walk_width", 5.0) + 1) for r in old_roads["roads"]])


def sraster(geom):
    return raster_px(geom, SN, LX0, LY0, SRES)


stale = sraster(old_corr.difference(corridor.buffer(1)))
surf[..., 0] = 0                              # no painted asphalt: the road mesh is the road
surf[stale, 2] = 0                            # old sidewalk paving -> lawn
surf[stale, 3] = 0
surf[stale, 1] = 255
Image.fromarray(surf, "RGBA").save(os.path.join(OUT, "surface.png"))


def hroad(x, y):
    c = np.clip(np.asarray(x) - LX0, 0, N - 1.001)
    r = np.clip(np.asarray(y) - LY0, 0, N - 1.001)
    c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
    fc, fr = c - c0, r - r0
    return (Hroad[r0, c0] * (1 - fc) * (1 - fr) + Hroad[r0, c0 + 1] * fc * (1 - fr) +
            Hroad[r0 + 1, c0] * (1 - fc) * fr + Hroad[r0 + 1, c0 + 1] * fc * fr)


# ------------------------------------------------------------------ markings
J = {}
for k, i in jidx.items():
    ws = [p["w"] for p in P if p["ja"] == i or p["jb"] == i]
    J[i] = {"center": k, "radius": max(ws) / 2 + CORNER_R * 0.6 + 1.0}


def ribbon(line, off, width, dash=None, gap=None):
    """quads along a line offset 'off' to the right; returns list of 4-point polygons"""
    if line.length < 1:
        return []
    l = line.offset_curve(off) if abs(off) > 1e-3 else line
    if l.is_empty or not isinstance(l, LineString):
        return []
    out = []
    if dash:
        s = gap / 2
        while s + dash <= l.length:
            seg = shapely.ops.substring(l, s, s + dash)
            out.append(seg.buffer(width / 2, cap_style=2))
            s += dash + gap
    else:
        out.append(l.buffer(width / 2, cap_style=2, join_style=1))
    return out


paint_w, paint_y = [], []
for p in P:
    l = p["smooth"]
    if p["cls"] == "alley" or l.length < 10:
        continue
    t0 = J[p["ja"]]["radius"] + 4.5 if p["ja"] is not None else 2.0
    t1 = J[p["jb"]]["radius"] + 4.5 if p["jb"] is not None else 2.0
    if l.length - t0 - t1 < 4:
        continue
    core = shapely.ops.substring(l, t0, l.length - t1)
    paint_y += ribbon(core, 0.18, 0.12) + ribbon(core, -0.18, 0.12)          # double yellow
    if p["cls"] == "avenue":
        for off in (4.5, -4.5):
            paint_w += ribbon(core, off, 0.12, dash=3.0, gap=6.0)          # lane lines
        for off in (p["w"] / 2 - 0.5, -(p["w"] / 2 - 0.5)):
            paint_w += ribbon(core, off, 0.15)                              # edge lines
    # crosswalks and stop lines at junction approaches
    for end, j in ((0, p["ja"]), (1, p["jb"])):
        if j is None:
            continue
        r = J[j]["radius"]
        if l.length < r + 6:
            continue
        s_c = r + 1.5 if end == 0 else l.length - r - 1.5
        a = l.interpolate(max(0, s_c - 1.5))
        b = l.interpolate(min(l.length, s_c + 1.5))
        d = np.subtract(b.coords[0], a.coords[0])
        d = d / (np.linalg.norm(d) or 1)
        nrm = np.array([-d[1], d[0]])
        c = np.array(l.interpolate(s_c).coords[0])
        half = p["w"] / 2 - 0.4
        o = -half
        while o <= half:
            q = c + nrm * o
            paint_w.append(LineString([q - d * 1.5, q + d * 1.5]).buffer(0.3, cap_style=2))
            o += 1.2
        # stop line on the inbound half, just behind the crosswalk
        s_s = s_c + (2.4 if end == 0 else -2.4)
        cs = np.array(l.interpolate(s_s).coords[0])
        side = -1 if end == 0 else 1
        paint_w.append(LineString([cs, cs + nrm * side * half]).buffer(0.2, cap_style=2))
paint_w = unary_union(paint_w).intersection(road_area)
paint_y = unary_union(paint_y).intersection(road_area)

# ------------------------------------------------------------------ meshes per tile
os.makedirs(os.path.join(OUT, "road_tiles"), exist_ok=True)
for f in os.listdir(os.path.join(OUT, "road_tiles")):
    os.remove(os.path.join(OUT, "road_tiles", f))


def tri_mesh(geom, zfn, seg=2.0):
    V, F = [], []
    for g in getattr(geom, "geoms", [geom]):
        if not isinstance(g, Polygon) or g.area < 0.01:
            continue
        g = shapely.segmentize(g, seg)
        tris = shapely.constrained_delaunay_triangles(g)
        for t in getattr(tris, "geoms", []):
            cs = list(t.exterior.coords)[:3]
            base = len(V)
            V += cs
            # counter-clockwise in UE's top view (x right, y down) is what Blender's flip expects
            F.append([base, base + 1, base + 2])
    if not V:
        return None
    V = np.array(V)
    z = zfn(V[:, 0], V[:, 1])
    return np.column_stack([V, z]), np.array(F)


def wall_mesh(geom, ztop_fn, zbot_fn, seg=2.0):
    """vertical strips along the boundary rings of geom"""
    V, F = [], []
    for g in getattr(geom, "geoms", [geom]):
        if not isinstance(g, Polygon):
            continue
        for ring in [g.exterior] + list(g.interiors):
            cs = np.asarray(shapely.segmentize(LineString(ring.coords), seg).coords)
            zt, zb = ztop_fn(cs[:, 0], cs[:, 1]), zbot_fn(cs[:, 0], cs[:, 1])
            for i in range(len(cs) - 1):
                b = len(V)
                V += [(cs[i][0], cs[i][1], zb[i]), (cs[i + 1][0], cs[i + 1][1], zb[i + 1]),
                      (cs[i + 1][0], cs[i + 1][1], zt[i + 1]), (cs[i][0], cs[i][1], zt[i])]
                F += [[b, b + 1, b + 2], [b, b + 2, b + 3]]
    if not V:
        return None
    return np.array(V), np.array(F)


tiles = 0
x0, y0, x1, y1 = corridor.bounds
for tx in np.arange(math.floor(x0 / TILE) * TILE, x1, TILE):
    for ty in np.arange(math.floor(y0 / TILE) * TILE, y1, TILE):
        bx = box(tx, ty, tx + TILE, ty + TILE)
        if not bx.intersects(corridor):
            continue
        parts = {}
        ra = road_area.intersection(bx)
        parts["asphalt"] = tri_mesh(ra, lambda x, y: hroad(x, y))
        ca = curb_area.intersection(bx)
        top = tri_mesh(ca, lambda x, y: hroad(x, y) + CURB_H)
        face = wall_mesh(road_area.intersection(bx.buffer(0.01)), lambda x, y: hroad(x, y) + CURB_H, lambda x, y: hroad(x, y) - 0.05)
        cv, cf = [], []
        for m in (top, face):
            if m:
                cf.append(m[1] + sum(len(v) for v in cv))
                cv.append(m[0])
        parts["curb"] = (np.vstack(cv), np.vstack(cf)) if cv else None
        wa = walk_area.intersection(bx)
        top = tri_mesh(wa, lambda x, y: hroad(x, y) + CURB_H)
        skirt = wall_mesh(corridor.intersection(bx), lambda x, y: hroad(x, y) + CURB_H, lambda x, y: hroad(x, y) - 0.4)
        sv, sf = [], []
        for m in (top, skirt):
            if m:
                sf.append(m[1] + sum(len(v) for v in sv))
                sv.append(m[0])
        parts["sidewalk"] = (np.vstack(sv), np.vstack(sf)) if sv else None
        parts["paint_white"] = tri_mesh(paint_w.intersection(bx), lambda x, y: hroad(x, y) + 0.025, seg=3.0)
        parts["paint_yellow"] = tri_mesh(paint_y.intersection(bx), lambda x, y: hroad(x, y) + 0.025, seg=3.0)
        arrays = {}
        for k, m in parts.items():
            if m is None:
                continue
            v, f = m
            arrays[k + "_v"] = (v - [tx, ty, 0]).astype(np.float32)       # local to the tile corner
            arrays[k + "_f"] = f.astype(np.int32)
        if arrays:
            np.savez_compressed(os.path.join(OUT, "road_tiles", "T_%+05d_%+05d.npz" % (tx, ty)), origin=np.array([tx, ty]), **arrays)
            tiles += 1

# ------------------------------------------------------------------ roads.json for lanes, lamps, signals
traffic = [p for p in P if p["cls"] != "alley"]
tdeg = Counter()
for p in traffic:
    tdeg[key(p["line"].coords[0])] += 1
    tdeg[key(p["line"].coords[-1])] += 1
tj = {k: i for i, k in enumerate(k for k, n in tdeg.items() if n >= 3)}
roads_out, junc_out = [], [{"id": i, "center": list(k), "roads": []} for k, i in tj.items()]
for p in traffic:
    l = p["smooth"]
    ja, jb = tj.get(key(p["line"].coords[0])), tj.get(key(p["line"].coords[-1]))
    ta = (p["w"] / 2 + 3) if ja is not None else 0
    tb = (p["w"] / 2 + 3) if jb is not None else 0
    if l.length - ta - tb < 6:
        continue
    t = shapely.ops.substring(l, ta, l.length - tb)
    n = max(2, int(t.length // 20) + 1)
    d = [t.interpolate(s) for s in np.linspace(0, t.length, n)]
    rid = len(roads_out)
    roads_out.append({"id": rid, "points": [[round(q.x, 2), round(q.y, 2)] for q in d], "width": p["w"],
                      "lanes": CLASSES[p["cls"]]["lanes"], "class": p["cls"], "ends": [ja, jb], "length": round(t.length, 1),
                      "dense": [[round(q.x, 2), round(q.y, 2), round(float(hroad(q.x, q.y)), 2)] for q in d]})
    for j in (ja, jb):
        if j is not None:
            junc_out[j]["roads"].append(rid)
for j in junc_out:
    ws = [roads_out[r]["width"] for r in j["roads"]]
    j["radius"] = round(max(ws) / 2 + 3, 1) if ws else 10
json.dump({"roads": roads_out, "junctions": junc_out}, open(os.path.join(OUT, "roads.json"), "w"))

# ------------------------------------------------------------------ report
buildings_hit = [l for l in lay["lots"] if poly(l["poly"]).intersects(road_area)]
plan_hit = [l for l in lots_plan["lots"] if "poly" in l and poly(l["poly"]).intersects(road_area)]
rep = {
    "road_pieces": len(P), "traffic_pieces": len(roads_out), "junctions": len(junc_out), "tiles": tiles,
    "asphalt_m2": round(road_area.area), "sidewalk_m2": round(walk_area.area), "curb_km": round(road_area.boundary.length / 1000, 2),
    "max_grade_change_m": round(float(np.max(np.abs(G - T)[~m_water])), 2),
    "mean_grade_change_m_in_corridor": round(float(np.mean(np.abs(G - T)[m_corr])), 2),
    "max_slope_beside_roads_pct": round(float(np.percentile(slope[ring], 99.5) * 100), 1),
    "old_lots_crossed_by_new_roads": len(buildings_hit), "planned_lots_crossed": len(plan_hit),
}
open(os.path.join(OUT, "stage2_report.txt"), "w").write(json.dumps(rep, indent=1))
print(json.dumps(rep, indent=1))

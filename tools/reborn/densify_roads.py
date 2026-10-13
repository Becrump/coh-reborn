"""City reset, stage 1b: street density pass on the regularised plan (plan only).

    python tools/reborn/densify_roads.py <out dir>

Reads roads_regular.json (regularize_roads.py) and writes, without touching
the level:
  roads_dense.json        the denser network (same format)
  street_plan_dense.png   plan picture, same colour key as street_plan.png
  street_report_dense.txt numbers, what was added, what was left

Rules
  * blocks in the core and in tall-building districts are cut to about
    80-120 m a side, elsewhere to no more than 150 m, by 12 m streets laid
    across the block along its own grid (its minimum rotated rectangle,
    snapped to the nearest 45 degrees when close)
  * parks (1,500 m2 and up), lakes and pools, the landmark lots and the City Hall plaza stay
    whole: a block mostly covered by them is left alone, and a cut that
    would cross one is dropped
  * blocks in tall districts that are still deep get a 7 m service alley
    down the middle, behind the buildings
  * dead ends are joined to the nearest street (new or old) within 60 m
    when the link does not cross a protected area
  * avenues, the Atlas Park outline and every existing street stay as they
    are; only streets are added
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import linemerge, polygonize, unary_union

OUT = sys.argv[1]
reg = json.load(open(os.path.join(OUT, "roads_regular.json")))
lay = json.load(open(os.path.join(OUT, "layout.json")))
lots_plan = json.load(open(os.path.join(OUT, "lots_plan.json")))
CLASSES = reg["classes"]
CORE = lay["core"]
TARGET_CORE, MAX_CORE = 100.0, 120.0
TARGET_OUT, MAX_OUT = 130.0, 150.0
ALLEY_MIN_DEPTH = 70.0
JOIN_M = 60.0
PLAZA = Point(39.0, 201.0).buffer(75.0)       # City Hall plaza (spawner no-spawn zone)


def poly(p):
    g = Polygon(p)
    return g if g.is_valid else g.buffer(0)


protected = [("plaza", PLAZA)]
# real parks only: the core's small planting beds (under 1,500 m2) may be crossed
protected += [(p["kind"], poly(p["poly"])) for p in lay["parks"] if p.get("area", 0) >= 1500]
protected += [(w["kind"], poly(w["poly"])) for w in lay["waters"] if w.get("poly")]
protected += [(l["kind"], poly(l["poly"])) for l in lay["lots"] if l["kind"].startswith("landmark")]
prot_union = unary_union([g for _, g in protected])
bay = poly(lots_plan["water"])
tall_pts = [Point(l["center"]) for l in lots_plan["lots"] if l.get("height", 0) >= 60 or l.get("class") in ("tower", "high")]

# ------------------------------------------------------------ network in
lines = []          # (LineString, class)
for r in reg["roads"]:
    lines.append((LineString(r["points"]), r["class"]))
base_union = unary_union([l for l, _ in lines])
blocks = [f for f in polygonize(base_union) if f.area > 400]


def in_core(g):
    c = g.centroid
    return CORE[0] <= c.x <= CORE[2] and CORE[1] <= c.y <= CORE[3]


def is_tall(g):
    return any(g.contains(p) for p in tall_pts)


def frame(g):
    """block axes: the minimum rotated rectangle, snapped to 45 deg if close"""
    rect = g.minimum_rotated_rectangle
    cs = list(rect.exterior.coords)
    e0 = np.subtract(cs[1], cs[0])
    e1 = np.subtract(cs[2], cs[1])
    ang = math.degrees(math.atan2(e0[1], e0[0]))
    snap = round(ang / 45.0) * 45.0
    if abs(ang - snap) < 8:
        ang = snap
    u = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
    v = np.array([-u[1], u[0]])
    pts = np.array(g.exterior.coords)
    pu, pv = pts @ u, pts @ v
    return u, v, (pu.min(), pu.max()), (pv.min(), pv.max())


def cut_line(g, origin_along, axis, other, span):
    """a line across the block at 'origin_along' on 'axis', running along 'other'"""
    a = axis * origin_along + other * (span[0] - 50)
    b = axis * origin_along + other * (span[1] + 50)
    seg = LineString([tuple(a), tuple(b)]).intersection(g)
    if seg.is_empty:
        return []
    parts = list(getattr(seg, "geoms", [seg]))
    return [p for p in parts if isinstance(p, LineString) and p.length > 25]


added_streets, added_alleys, skipped = [], [], []
kept_whole = 0
for g in blocks:
    if g.intersection(bay).area > 0.3 * g.area:
        continue
    pc = g.intersection(prot_union).area / g.area
    if pc > 0.4 or g.contains(PLAZA.centroid):      # the City Hall block stays whole
        kept_whole += 1
        continue
    core_like = in_core(g) or is_tall(g)
    target, mx = (TARGET_CORE, MAX_CORE) if core_like else (TARGET_OUT, MAX_OUT)
    u, v, su, sv = frame(g)
    cuts = []
    for axis, other, span, ospan in ((u, v, su, sv), (v, u, sv, su)):
        L = span[1] - span[0]
        if L <= mx:
            continue
        n = max(1, int(math.ceil(L / target)) - 1)
        for k in range(1, n + 1):
            at = span[0] + L * k / (n + 1)
            # slide the cut up to 30 m to miss a park, lake or landmark
            for off in (0, 8, -8, 16, -16, 24, -24, 32, -32):
                segs_ = cut_line(g, at + off, axis, other, ospan)
                if segs_ and not any(sg.buffer(CLASSES["street"]["width"] / 2 + 2).intersects(prot_union) for sg in segs_):
                    added_streets.extend(segs_)
                    break
            else:
                skipped.append(("protected", [round(c) for c in (axis * at + other * (ospan[0] + ospan[1]) / 2)]))

# a cut that runs alongside a street already there (closer than 30 m for
# much of its middle) is a duplicate: drop it
from shapely.ops import substring


def too_close(seg, others):
    """True when much of the cut runs side by side (parallel, < 30 m) with a
    street already there; crossing streets don't count"""
    ols = [l for l in getattr(others, "geoms", [others]) if isinstance(l, LineString)]
    if seg.length > 60:
        seg = substring(seg, 20, seg.length - 20)
    n = max(4, int(seg.length // 6))
    close = 0
    for i in range(n + 1):
        t = seg.length * i / n
        p = seg.interpolate(t)
        d0 = np.subtract(seg.interpolate(min(seg.length, t + 1)).coords[0], seg.interpolate(max(0, t - 1)).coords[0])
        best = None
        for l in ols:
            d = l.distance(p)
            if d < 30 and (best is None or d < best[0]):
                best = (d, l)
        if not best:
            continue
        l = best[1]
        tl = l.project(p)
        d1 = np.subtract(l.interpolate(min(l.length, tl + 1)).coords[0], l.interpolate(max(0, tl - 1)).coords[0])
        c = abs(np.dot(d0, d1)) / (np.linalg.norm(d0) * np.linalg.norm(d1) + 1e-9)
        if c > 0.85:
            close += 1
    return close > 0.4 * (n + 1)


kept, dup_cuts = [], 0
for seg in sorted(added_streets, key=lambda l: -l.length):
    if too_close(seg, unary_union([base_union] + kept) if kept else base_union):
        dup_cuts += 1
        continue
    kept.append(seg)
added_streets = kept

# big irregular blocks the straight cuts could not break (every cut would
# cross a park or lake): a street that curves around the park / lake edge
# (14 m out from it), then cross streets in the rest of the block that stop
# at that edge street
EDGE_OFF = 14.0
edge_streets = []
mid_union = unary_union([base_union] + added_streets)
for g in [f for f in polygonize(mid_union) if f.area > 400]:
    if g.intersection(bay).area > 0.3 * g.area or g.contains(PLAZA.centroid):
        continue
    core_like = in_core(g) or is_tall(g)
    target, mx = (TARGET_CORE, MAX_CORE) if core_like else (TARGET_OUT, MAX_OUT)
    u, v, su, sv = frame(g)
    if max(su[1] - su[0], sv[1] - sv[0]) < 400:      # only the few big irregular blocks
        continue
    inner = g.intersection(prot_union)
    if inner.area < 1500 or inner.area > 0.6 * g.area:
        continue
    # smooth outline: closing then opening rounds off the park's nooks
    ring = inner.buffer(EDGE_OFF + 15, join_style=1).buffer(-15, join_style=1).simplify(6.0)
    edge = ring.boundary.intersection(g.buffer(-6))
    pieces = [l for l in getattr(edge, "geoms", [edge]) if isinstance(l, LineString) and l.length > 40]
    # reach the block's own streets: extend each piece end straight out to the boundary
    for l in pieces:
        cs = list(l.coords)
        for end, prev in ((cs[-1], cs[-2]), (cs[0], cs[1])):
            d = np.subtract(end, prev)
            d = d / (np.linalg.norm(d) or 1)
            ext = LineString([end, tuple(np.add(end, d * 12))])
            if ext.intersects(g.exterior):
                l = unary_union([l, ext])
        l = l if isinstance(l, LineString) else linemerge(l)
        if isinstance(l, LineString) and not too_close(l, mid_union):
            edge_streets.append(l)
    rest = g.difference(ring)
    for rg in getattr(rest, "geoms", [rest]):
        if rg.area < 3000:
            continue
        u2, v2, su2, sv2 = frame(rg)
        for axis, other, span, ospan in ((u2, v2, su2, sv2), (v2, u2, sv2, su2)):
            L = span[1] - span[0]
            if L <= mx:
                continue
            n = max(1, int(math.ceil(L / target)) - 1)
            for k in range(1, n + 1):
                at = span[0] + L * k / (n + 1)
                for seg in cut_line(rg.buffer(2), at, axis, other, ospan):
                    if seg.length < 40 or seg.buffer(CLASSES["street"]["width"] / 2 + 1).intersects(prot_union):
                        continue
                    if too_close(seg, unary_union([mid_union] + edge_streets)):
                        continue
                    edge_streets.append(seg)
edge_streets = [l for l in edge_streets if isinstance(l, LineString)]
# keep only streets that join the network at both ends (no new dead ends);
# repeat, since dropping one can strand another
while True:
    net = unary_union([mid_union] + edge_streets)
    keep = []
    for l in edge_streets:
        others = unary_union([mid_union] + [o for o in edge_streets if o is not l])
        if Point(l.coords[0]).distance(others) < 3 and Point(l.coords[-1]).distance(others) < 3:
            keep.append(l)
    if len(keep) == len(edge_streets):
        break
    edge_streets = keep
added_streets += edge_streets

# blocks after the street cuts: service alleys behind tall buildings
mid_union = unary_union([base_union] + added_streets)
for g in [f for f in polygonize(mid_union) if f.area > 400]:
    if not is_tall(g) or g.intersection(prot_union).area > 0.2 * g.area or g.intersection(bay).area > 0             or g.contains(PLAZA.centroid):
        continue
    u, v, su, sv = frame(g)
    Lu, Lv = su[1] - su[0], sv[1] - sv[0]
    # alley along the long side, at mid depth
    axis, other, span, ospan, depth = (v, u, sv, su, Lv) if Lu >= Lv else (u, v, su, sv, Lu)
    if depth < ALLEY_MIN_DEPTH:
        continue
    for seg in cut_line(g, (span[0] + span[1]) / 2, axis, other, ospan):
        if seg.buffer(CLASSES["alley"]["width"] / 2 + 2).intersects(prot_union):
            continue
        if too_close(seg, unary_union([mid_union] + added_alleys)):
            continue
        # service alleys run square to the grid and stay short
        dx, dy = np.subtract(seg.coords[-1], seg.coords[0])
        a = math.degrees(math.atan2(dy, dx)) % 90
        if min(a, 90 - a) > 10 or seg.length > 220:
            continue
        added_alleys.append(seg)

# ------------------------------------------------------------ node + classes
src = [(l, c) for l, c in lines] + [(s, "street") for s in added_streets] + [(s, "alley") for s in added_alleys]
noded = unary_union([l for l, _ in src])
segs = [s for s in getattr(noded, "geoms", [noded]) if s.length > 0.5]


def class_of(seg):
    mid = seg.interpolate(0.5, normalized=True)
    best, bc = 1e9, "street"
    order = {"avenue": 0, "street": 1, "alley": 2}
    for l, c in src:
        d = l.distance(mid)
        if d < best - 0.01 or (abs(d - best) < 0.01 and order[c] < order[bc]):
            best, bc = d, c
    return bc


# graph of segment ends
def key(p):
    return (round(p[0], 1), round(p[1], 1))


E = [{"line": s, "cls": class_of(s)} for s in segs]
deg = Counter()
for e in E:
    deg[key(e["line"].coords[0])] += 1
    deg[key(e["line"].coords[-1])] += 1

# dead ends: join to the nearest street within JOIN_M without crossing a protected area
joined = []
all_lines = unary_union([e["line"] for e in E])
for k, n in list(deg.items()):
    if n != 1:
        continue
    p = Point(k)
    own = next(e for e in E if key(e["line"].coords[0]) == k or key(e["line"].coords[-1]) == k)
    best = None
    for e in E:
        if e is own:
            continue
        d = e["line"].distance(p)
        if d < 3 or d > JOIN_M:
            continue
        q = e["line"].interpolate(e["line"].project(p))
        link = LineString([p, q])
        if link.buffer(4).intersects(prot_union) or link.intersection(bay).length > 0:
            continue
        # no crossing through a third road
        if link.crosses(unary_union([x["line"] for x in E if x is not e and x is not own])):
            continue
        if best is None or d < best[0]:
            best = (d, link)
    if best:
        joined.append(best[1])
if joined:
    noded = unary_union([e["line"] for e in E] + joined)
    segs = [s for s in getattr(noded, "geoms", [noded]) if s.length > 0.5]
    src += [(j, "street") for j in joined]
    E = [{"line": s, "cls": class_of(s)} for s in segs]

# merge pieces that meet end to end with nothing else (same class)
deg = Counter()
for e in E:
    deg[key(e["line"].coords[0])] += 1
    deg[key(e["line"].coords[-1])] += 1
by_cls = defaultdict(list)
for e in E:
    by_cls[e["cls"]].append(e["line"])
roads = []
for cls, ls in by_cls.items():
    m = linemerge(ls)
    for l in getattr(m, "geoms", [m]):
        roads.append({"class": cls, "line": l})
deg = Counter()
for r in roads:
    deg[key(r["line"].coords[0])] += 1
    deg[key(r["line"].coords[-1])] += 1
# junction count: points where 3+ noded pieces meet (through roads count too)
pts = Counter()
for e in E:
    for p in (e["line"].coords[0], e["line"].coords[-1]):
        pts[key(p)] += 1
junction_pts = [k for k, n in pts.items() if n >= 3]
dead_ends = [k for k, n in pts.items() if n == 1]

# ------------------------------------------------------------ stats
road_area = {i: r["line"].buffer(CLASSES[r["class"]]["width"] / 2, cap_style=2) for i, r in enumerate(roads)}
all_roads = unary_union(list(road_area.values()))
faces = [f for f in polygonize(unary_union([r["line"] for r in roads])) if f.area > 400 and f.intersection(bay).area < 0.3 * f.area]
areas = [f.area for f in faces]
sides = [math.sqrt(a) for a in areas]
length_by = defaultdict(float)
for r in roads:
    length_by[r["class"]] += r["line"].length
before_faces = [f for f in blocks if f.intersection(bay).area < 0.3 * f.area]
stats = {
    "junctions": len(junction_pts), "road_pieces": len(roads), "dead_ends": len(dead_ends),
    "km_by_class": {k: round(length_by[k] / 1000, 2) for k in CLASSES},
    "km_total": round(sum(length_by.values()) / 1000, 2),
    "blocks": len(faces), "avg_block_m2": round(float(np.mean(areas))), "median_block_m2": round(float(np.median(areas))),
    "median_block_side_m": round(float(np.median(sides))),
    "before": {"blocks": len(before_faces), "avg_block_m2": round(float(np.mean([f.area for f in before_faces]))),
               "median_block_m2": round(float(np.median([f.area for f in before_faces]))),
               "km_by_class": reg["stats"]["by_class"], "junctions": reg["stats"]["junctions_after"]},
    "added_streets": len(added_streets), "added_alleys": len(added_alleys), "dead_ends_joined": len(joined),
    "blocks_kept_whole_protected": kept_whole, "cuts_dropped_protected": len(skipped), "cuts_dropped_duplicate": dup_cuts, "park_edge_and_cross_streets": len(edge_streets),
}
out = {"roads": [{"id": i, "class": r["class"], "width": CLASSES[r["class"]]["width"], "lanes": CLASSES[r["class"]]["lanes"],
                  "points": [[round(x, 2), round(y, 2)] for x, y in r["line"].coords], "length": round(r["line"].length, 1)}
                 for i, r in enumerate(roads)],
       "junctions": [{"center": list(k)} for k in junction_pts], "dead_ends": [list(k) for k in dead_ends],
       "classes": CLASSES, "stats": stats}
json.dump(out, open(os.path.join(OUT, "roads_dense.json"), "w"))

# ------------------------------------------------------------ picture
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch
from matplotlib.patches import Polygon as MPoly
from matplotlib.path import Path


def patch(g, **kw):
    verts, codes = [], []
    for ring in [g.exterior] + list(g.interiors):
        cs = list(ring.coords)
        verts += cs
        codes += [Path.MOVETO] + [Path.LINETO] * (len(cs) - 2) + [Path.CLOSEPOLY]
    return PathPatch(Path(verts, codes), **kw)


COL = {"avenue": "#c0392b", "street": "#2c6fbb", "alley": "#7f8c8d"}
fig, ax = plt.subplots(figsize=(26, 26))
ax.set_facecolor("#e9e6dc")
for gg in getattr(bay, "geoms", [bay]):
    ax.add_patch(MPoly(np.array(gg.exterior.coords), closed=True, fc="#9cc3e6", ec="none", zorder=0))
for w in lay["waters"]:
    if w.get("poly"):
        ax.add_patch(MPoly(np.array(w["poly"]), closed=True, fc="#9cc3e6", ec="none", zorder=0))
for p in lay["parks"]:
    ax.add_patch(MPoly(np.array(p["poly"]), closed=True, fc="#b9d7a8", ec="none", zorder=0))
for l in lay["lots"]:
    if l["kind"].startswith("landmark"):
        ax.add_patch(MPoly(np.array(l["poly"]), closed=True, fc="#f3c86b", ec="#a07010", zorder=1))
ax.add_patch(MPoly(np.array(PLAZA.exterior.coords), closed=True, fc="none", ec="#a07010", ls="--", lw=1.2, zorder=1))
for cls in ("alley", "street", "avenue"):
    rs = [road_area[i] for i, r in enumerate(roads) if r["class"] == cls]
    if not rs:
        continue
    g = unary_union(rs)
    for gg in getattr(g, "geoms", [g]):
        ax.add_patch(patch(gg, fc=COL[cls], ec="none", alpha=0.55, zorder=3))
# new streets and alleys outlined so they stand out
for s in added_streets + joined:
    ax.plot(*np.array(s.coords).T, color="#0b3d91", lw=1.0, ls="--", zorder=4)
for s in added_alleys:
    ax.plot(*np.array(s.coords).T, color="#333", lw=0.8, ls=":", zorder=4)
for k in junction_pts:
    ax.plot(*k, "o", ms=3, color="k", zorder=5)
for k in dead_ends:
    ax.plot(*k, "x", ms=9, mew=2.2, color="#e67e22", zorder=6)
SHORT = {"avenue": "Ave", "street": "St", "alley": "Alley"}
for r in roads:
    ls = r["line"]
    if ls.length < 55:
        continue
    m = ls.interpolate(0.5, normalized=True)
    a, b = ls.interpolate(0.45, normalized=True), ls.interpolate(0.55, normalized=True)
    ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
    ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
    ax.text(m.x, m.y, "%s %dm" % (SHORT[r["class"]], CLASSES[r["class"]]["width"]), fontsize=6.5, ha="center", va="center",
            rotation=-ang, rotation_mode="anchor", color="white", weight="bold", zorder=7,
            bbox=dict(boxstyle="round,pad=0.15", fc=COL[r["class"]], ec="none", alpha=0.9))
ax.set_aspect("equal")
ax.set_xlim(-870, 1180)
ax.set_ylim(980, -760)
ax.set_xlabel("UE X (m)")
ax.set_ylabel("UE Y (m), north is up")
s = stats
ax.set_title("Atlas Park Reborn - street plan, stage 1b (density pass)\n"
             "%d junctions, %d dead ends;  roads %.1f km: avenue %.1f / street %.1f / alley %.1f km;  "
             "%d blocks, average %d m2, median %d m2 (median side ~%d m)" %
             (s["junctions"], s["dead_ends"], s["km_total"], s["km_by_class"]["avenue"], s["km_by_class"]["street"],
              s["km_by_class"]["alley"], s["blocks"], s["avg_block_m2"], s["median_block_m2"], s["median_block_side_m"]), fontsize=16)
leg = [Line2D([0], [0], color=COL[k], lw=8, alpha=0.6, label="%s %d m, %d lanes" % (k, CLASSES[k]["width"], CLASSES[k]["lanes"])) for k in CLASSES]
leg += [Line2D([0], [0], color="#0b3d91", ls="--", label="new street (density pass)"),
        Line2D([0], [0], color="#333", ls=":", label="new service alley"),
        Line2D([0], [0], marker="o", color="k", lw=0, label="junction"),
        Line2D([0], [0], marker="x", color="#e67e22", lw=0, mew=2, ms=9, label="dead end"),
        Line2D([0], [0], color="#a07010", ls="--", label="City Hall plaza (kept whole)")]
ax.legend(handles=leg, loc="lower left", fontsize=13)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "street_plan_dense.png"), dpi=70)

with open(os.path.join(OUT, "street_report_dense.txt"), "w") as f:
    f.write(json.dumps(stats, indent=1) + "\n\nDEAD ENDS\n")
    for k in dead_ends:
        f.write("%s\n" % (k,))
    f.write("\nCUTS DROPPED (would cross a park, lake, landmark or the plaza)\n")
    for why, at in skipped:
        f.write("%s at %s\n" % (why, at))
print(json.dumps(stats, indent=1))

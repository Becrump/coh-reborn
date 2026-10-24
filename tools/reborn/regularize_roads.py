"""City reset, stage 1: a clean street plan from roads.json (plan only).

    python tools/reborn/regularize_roads.py <guide dir> <out dir>

Reads roads.json (plan_roads.py) and writes, without touching the level:
  roads_regular.json   the regularised network
  street_plan.png      top-down plan: every street labelled with class and
                       width, junction count, average block size
  street_report.txt    what changed, water / lake / kept-lot crossings, dead
                       ends, anything left unfixed

Steps
  1. graph: road pieces run junction centre to junction centre again (the
     plan_roads.py trims are undone)
  2. merge junctions closer than MERGE_M, and collapse road pieces shorter
     than SHORT_M that join two junctions (skeleton double-junctions)
  3. straighten: Douglas-Peucker, then a piece whose bends stay within
     STRAIGHT_M of its chord becomes one straight line
  4. snap angles: segments within SNAP_DEG of 0 / 45 / 90 degrees are turned
     onto that angle (both ends move, shared points stay shared); no point
     moves more than MAX_MOVE_M from where it was, so block sizes and the
     overall shape of Atlas Park stay
  5. classes by the original street width (measured on the guide's road
     pixels) and by name for the new areas: avenue 18 m (4 lanes), street
     12 m (2 lanes), alley 7 m (1 lane)
  6. corners: curb radius at junctions by class, fillets on bends
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from scipy import ndimage
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

GUIDE, OUT = sys.argv[1], sys.argv[2]
GX0, GY0 = -870.0, -636.0           # guide grid origin (m), 0.5 m pixels

MERGE_M = 10.0
SHORT_M = 14.0
STRAIGHT_M = 4.0
SNAP_DEG = 12.0
MAX_MOVE_M = 9.0
CLASSES = {                          # width, lanes, curb radius, bend fillet
    "avenue": (18.0, 4, 10.0, 22.0),
    "street": (12.0, 2, 7.0, 18.0),
    "alley": (7.0, 1, 4.0, 8.0),
}
AVENUE_NAMES = ("Atlas_Ring", "Coastal_Boulevard", "Harbor_Ave", "Pier_Ave", "Gate_Ave",
                "_Gate", "West_Avenue", "East_Avenue", "South_Avenue")

lay = json.load(open(os.path.join(OUT, "layout.json")))
src = json.load(open(os.path.join(OUT, "roads.json")))
lots_plan = json.load(open(os.path.join(OUT, "lots_plan.json")))

# ------------------------------------------------------------ 1. graph
pos = {}                             # node id -> [x, y]
orig_pos = {}
for j in src["junctions"]:
    pos[("j", j["id"])] = list(j["center"])
edges = []                           # {a, b, pts (interior), w0, rid}
for r in src["roads"]:
    pts = [tuple(p) for p in r["points"]]
    ja, jb = r["ends"]
    a = ("j", ja) if ja is not None else ("e", r["id"], 0)
    b = ("j", jb) if jb is not None else ("e", r["id"], 1)
    if ja is None:
        pos[a] = list(pts[0])
    if jb is None:
        pos[b] = list(pts[-1])
    edges.append({"a": a, "b": b, "pts": pts, "rid": r["id"], "w0": r["width"]})
for k, v in pos.items():
    orig_pos[k] = tuple(v)
n_roads0, n_junc0 = len(src["roads"]), len(src["junctions"])

# free ends that sit on another road's node: join them
for k in list(pos):
    if k[0] != "e":
        continue
    best, bd = None, 6.0
    for q, p in pos.items():
        if q != k and q[0] == "j":
            d = math.dist(pos[k], p)
            if d < bd:
                best, bd = q, d
    if best:
        for e in edges:
            if e["a"] == k:
                e["a"] = best
            if e["b"] == k:
                e["b"] = best
        del pos[k]

# ------------------------------------------------------------ 2. merge junctions
parent = {k: k for k in pos}


def find(k):
    while parent[k] != k:
        parent[k] = parent[parent[k]]
        k = parent[k]
    return k


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[rb] = ra


keys = list(pos)
for i, a in enumerate(keys):
    for b in keys[i + 1:]:
        if math.dist(pos[a], pos[b]) < MERGE_M:
            union(a, b)
for e in edges:
    L = LineString([pos[e["a"]]] + e["pts"] + [pos[e["b"]]]).length
    if L < SHORT_M and e["a"][0] == "j" and e["b"][0] == "j":
        union(e["a"], e["b"])
groups = defaultdict(list)
for k in pos:
    groups[find(k)].append(k)
merged_junctions = sum(len(g) - 1 for g in groups.values() if len(g) > 1)
npos = {}
for root, ks in groups.items():
    npos[root] = [float(np.mean([pos[k][0] for k in ks])), float(np.mean([pos[k][1] for k in ks]))]
dropped_short = 0
E = []
seen_pairs = set()
for e in edges:
    a, b = find(e["a"]), find(e["b"])
    if a == b:
        dropped_short += 1
        continue
    pts = [npos[a]] + [list(p) for p in e["pts"]] + [npos[b]]
    # trims near the junctions were undone by adding the centres: drop the
    # first / last interior point when it doubles back
    line = LineString(pts)
    key = (min(a, b), max(a, b), round(line.length))
    if key in seen_pairs:            # duplicated piece (both directions traced)
        dropped_short += 1
        continue
    seen_pairs.add(key)
    E.append({"a": a, "b": b, "line": line, "rid": e["rid"], "w0": e["w0"]})
pos = npos


# ------------------------------------------------------------ 2b. close gaps
# the traced core has gaps where the old street pixels stopped short of a
# crossing (trees, bridges, the monorail): a dead end within BRIDGE_M of
# another road is extended onto it, splitting that road into a junction
BRIDGE_M = 30.0


def degree():
    d = Counter()
    for e in E:
        d[e["a"]] += 1
        d[e["b"]] += 1
    return d


_named = [(n, LineString(p)) for n, p in lay["roads"].items()]


def is_named_avenue(line):
    mid = line.interpolate(0.5, normalized=True)
    for n, l in _named:
        if l.distance(mid) < 12 and any(s in n for s in ("Avenue", "Ave", "Ring", "Boulevard")):
            return True
    return False


# a long road that runs alongside other roads, closer than PARALLEL_M for most
# of its length, is a duplicate (the outer edge road 25 m outside the south
# avenue); named avenues always stay
PARALLEL_M = 30.0
dup_removed = []


def remove_duplicates():
    for e in sorted(E, key=lambda e: -e["line"].length):
        Lh = e["line"].length
        if Lh < 150 or is_named_avenue(e["line"]):
            continue
        ends = {e["a"], e["b"]}
        others = [o["line"] for o in E if o is not e and not ({o["a"], o["b"]} & ends)]
        if not others:
            continue
        inside = e["line"].intersection(unary_union(others).buffer(PARALLEL_M)).length
        if inside > 0.75 * Lh:
            dup_removed.append((e["rid"], round(Lh), [round(v) for v in e["line"].interpolate(0.5, normalized=True).coords[0]]))
            E.remove(e)

def bridge():
    n = 0
    for _ in range(3):
        d = degree()
        for k in [k for k, v in d.items() if v == 1]:
            own = [e for e in E if k in (e["a"], e["b"])]
            if not own:
                continue
            own = own[0]
            p = Point(pos[k])
            # heading of the dead end: keep going roughly the same way
            cs = list(own["line"].coords)
            tail = cs[-2] if own["b"] == k else cs[1]
            hx, hy = pos[k][0] - tail[0], pos[k][1] - tail[1]
            hl = math.hypot(hx, hy) or 1.0
            best = None
            for e in E:
                if e is own or k in (e["a"], e["b"]):
                    continue
                dd = e["line"].distance(p)
                if dd > BRIDGE_M:
                    continue
                q = e["line"].interpolate(e["line"].project(p))
                vx, vy = q.x - pos[k][0], q.y - pos[k][1]
                ahead = (vx * hx + vy * hy) / (hl * (math.hypot(vx, vy) or 1.0))
                score = dd * (1.0 if ahead > 0.3 else 2.5)
                if best is None or score < best[0]:
                    best = (score, e, q)
            if not best:
                continue
            _, e, q = best
            # snap onto an existing end of that road when close, else split it
            qa, qb = Point(pos[e["a"]]), Point(pos[e["b"]])
            if q.distance(qa) < 12:
                tgt = e["a"]
            elif q.distance(qb) < 12:
                tgt = e["b"]
            else:
                tgt = ("s", len(pos))
                pos[tgt] = [q.x, q.y]
                t = e["line"].project(q)
                from shapely.ops import substring
                l1, l2 = substring(e["line"], 0, t), substring(e["line"], t, e["line"].length)
                E.remove(e)
                E.append({"a": e["a"], "b": tgt, "line": l1, "rid": e["rid"], "w0": e["w0"]})
                E.append({"a": tgt, "b": e["b"], "line": l2, "rid": e["rid"], "w0": e["w0"]})
            if own["b"] == k:
                own["line"] = LineString(cs + [tuple(pos[tgt])])
                own["b"] = tgt
            else:
                own["line"] = LineString([tuple(pos[tgt])] + cs)
                own["a"] = tgt
            n += 1
    return n


# join pieces that meet end to end at a point with no third road
def join_degree2():
    n = 0
    while True:
        d = degree()
        k = next((k for k, v in d.items() if v == 2 and k[0] != "e"), None)
        if k is None:
            # also free-end points of degree 2 (two traced pieces meeting)
            k = next((k for k, v in d.items() if v == 2), None)
        if k is None:
            return n
        e1, e2 = [e for e in E if k in (e["a"], e["b"])]
        if e1 is e2:
            return n
        c1 = list(e1["line"].coords)
        c2 = list(e2["line"].coords)
        if e1["a"] == k:
            c1 = c1[::-1]
            a = e1["b"]
        else:
            a = e1["a"]
        if e2["b"] == k:
            c2 = c2[::-1]
            b = e2["a"]
        else:
            b = e2["b"]
        if a == b:                    # a closed loop (the ring): keep as is
            return n
        E.remove(e1)
        E.remove(e2)
        E.append({"a": a, "b": b, "line": LineString(c1 + c2[1:]), "rid": e1["rid"], "w0": max(e1["w0"], e2["w0"])})
        del pos[k]
        n += 1


joined = join_degree2()
remove_duplicates()


def pair_dead_ends(max_m=45.0):
    """two dead ends facing each other across a small gap: join them"""
    n = 0
    d = degree()
    free = [k for k, v in d.items() if v == 1]
    used = set()
    cand = sorted(((math.dist(pos[a], pos[b]), a, b) for i, a in enumerate(free) for b in free[i + 1:]), key=lambda t: t[0])
    for dist, a, b in cand:
        if dist > max_m or a in used or b in used:
            continue
        ea = next(e for e in E if a in (e["a"], e["b"]))
        if b in (ea["a"], ea["b"]):
            continue
        E.append({"a": a, "b": b, "line": LineString([pos[a], pos[b]]), "rid": ea["rid"], "w0": ea["w0"]})
        used |= {a, b}
        n += 1
    return n


bridged = pair_dead_ends() + bridge() + bridge() + bridge()
joined += join_degree2()

# small pieces connected to nothing else: drop
comp = {}
for e in E:
    comp.setdefault(e["a"], e["a"])
    comp.setdefault(e["b"], e["b"])


def croot(k):
    while comp[k] != k:
        comp[k] = comp[comp[k]]
        k = comp[k]
    return k


for e in E:
    ra, rb = croot(e["a"]), croot(e["b"])
    if ra != rb:
        comp[rb] = ra
size = defaultdict(float)
for e in E:
    size[croot(e["a"])] += e["line"].length
islands = [e for e in E if size[croot(e["a"])] < 150]
for e in islands:
    E.remove(e)

# ------------------------------------------------------------ 3. straighten
straightened = 0
for e in E:
    l = e["line"].simplify(5.0, preserve_topology=False)
    chord = LineString([l.coords[0], l.coords[-1]])
    dev = max(chord.distance(Point(p)) for p in l.coords) if len(l.coords) > 2 else 0
    if dev < STRAIGHT_M:
        if len(l.coords) > 2:
            straightened += 1
        l = chord
    e["line"] = l

# ------------------------------------------------------------ 4. snap angles
# every polyline vertex becomes a point; shared ends are the junction points
P = {}                               # point id -> [x, y]
P0 = {}
for k, v in pos.items():
    P[k] = list(v)
segs = []                            # (pid, pid, edge index)
for ei, e in enumerate(E):
    cs = list(e["line"].coords)
    ids = [e["a"]]
    for i, c in enumerate(cs[1:-1]):
        pid = ("v", ei, i)
        P[pid] = list(c)
        ids.append(pid)
    ids.append(e["b"])
    e["ids"] = ids
    for p, q in zip(ids[:-1], ids[1:]):
        segs.append((p, q, ei))
for k, v in P.items():
    P0[k] = tuple(orig_pos.get(k, v)) if k in orig_pos else tuple(v)


def snapped_dir(dx, dy):
    ang = math.degrees(math.atan2(dy, dx))
    tgt = round(ang / 45.0) * 45.0
    if abs(ang - tgt) <= SNAP_DEG:
        return math.radians(tgt)
    return None


snap_count = 0
for it in range(80):
    moved = 0.0
    for p, q, ei in segs:
        (x0, y0), (x1, y1) = P[p], P[q]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 1.0:
            continue
        t = snapped_dir(dx, dy)
        if t is None:
            continue
        ux, uy = math.cos(t), math.sin(t)
        # perpendicular error, split between both ends
        err = -dx * uy + dy * ux
        if abs(err) < 1e-3:
            continue
        nx, ny = -uy, ux
        for pid, s in ((p, 0.5), (q, -0.5)):
            P[pid][0] += nx * err * s
            P[pid][1] += ny * err * s
        moved = max(moved, abs(err))
    # keep every point near where it started
    for k, v in P.items():
        ox, oy = P0[k]
        d = math.dist(v, (ox, oy))
        if d > MAX_MOVE_M:
            v[0] = ox + (v[0] - ox) * MAX_MOVE_M / d
            v[1] = oy + (v[1] - oy) * MAX_MOVE_M / d
    if moved < 0.01:
        break
unsnapped = []
for p, q, ei in segs:
    (x0, y0), (x1, y1) = P[p], P[q]
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 1:
        continue
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    off = abs(ang - round(ang / 45.0) * 45.0)
    if off < 0.5:
        snap_count += 1
    elif off <= SNAP_DEG:
        unsnapped.append((ei, round(off, 1), L))
max_move = max(math.dist(P[k], P0[k]) for k in P)

# rebuild lines, drop straight-through vertices
for e in E:
    cs = [tuple(P[i]) for i in e["ids"]]
    keep = [cs[0]]
    for i in range(1, len(cs) - 1):
        a0 = math.atan2(cs[i][1] - keep[-1][1], cs[i][0] - keep[-1][0])
        a1 = math.atan2(cs[i + 1][1] - cs[i][1], cs[i + 1][0] - cs[i][0])
        d = abs((math.degrees(a1 - a0) + 180) % 360 - 180)
        if d > 2.0 and math.dist(cs[i], keep[-1]) > 1.0:
            keep.append(cs[i])
    keep.append(cs[-1])
    e["line"] = LineString(keep)
pos = {k: P[k] for k in pos}

# ------------------------------------------------------------ 5. classes
base = np.load(os.path.join(GUIDE, "base_class.npy"))
roadpix = ndimage.binary_closing(base == 1, iterations=1)
edt = ndimage.distance_transform_edt(roadpix) * 0.5     # metres to the road edge
named = [(n, LineString(p)) for n, p in lay["roads"].items()]
CORE = lay["core"]


def original_width(line):
    ws = []
    N = 25
    for f in np.linspace(0.05, 0.95, N):
        x, y = line.interpolate(f, normalized=True).coords[0]
        r, c = int((y - GY0) * 2), int((x - GX0) * 2)
        if 0 <= r < edt.shape[0] and 0 <= c < edt.shape[1] and roadpix[r, c]:
            # the centre line can sit off the pixel centre: best width nearby
            win = edt[max(r - 6, 0):r + 7, max(c - 6, 0):c + 7]
            ws.append(2 * float(win.max()))
    # gaps under trees and bridges read as narrow: take the upper quartile
    return float(np.percentile(ws, 75)) if len(ws) >= N * 0.3 else None


def name_of(line):
    mid = line.interpolate(0.5, normalized=True)
    best, bn = 12.0, None
    for n, l in named:
        d = l.distance(mid)
        if d < best:
            best, bn = d, n
    return bn


deg = Counter()
for e in E:
    deg[e["a"]] += 1
    deg[e["b"]] += 1
for e in E:
    n = name_of(e["line"])
    e["name"] = n
    w = original_width(e["line"])
    e["w_orig"] = w
    if n and any(s in n for s in AVENUE_NAMES):
        cls = "avenue"
    elif n:
        cls = "street"
    elif w is None:
        cls = "street"
    elif w >= 17.0:
        cls = "avenue"
    elif w >= 9.0:
        cls = "street"
    else:
        cls = "alley"
    # short dead-end spurs are service alleys
    if (deg[e["a"]] == 1 or deg[e["b"]] == 1) and e["line"].length < 60 and cls != "avenue":
        cls = "alley"
    e["cls"] = cls
# one class per straight run: a street piece between two avenue pieces on the
# same line is an avenue (keeps avenues continuous through junctions)
for _ in range(2):
    for e in E:
        if e["cls"] == "avenue":
            continue
        nb = [o for o in E if o is not e and (o["a"] in (e["a"], e["b"]) or o["b"] in (e["a"], e["b"])) and o["cls"] == "avenue"]
        if len(nb) >= 2:
            d0 = np.subtract(e["line"].coords[-1], e["line"].coords[0])
            par = 0
            for o in nb:
                d1 = np.subtract(o["line"].coords[-1], o["line"].coords[0])
                c = abs(np.dot(d0, d1)) / (np.linalg.norm(d0) * np.linalg.norm(d1) + 1e-9)
                par += c > 0.97
            if par >= 2 and e["line"].length < 120:
                e["cls"] = "avenue"

# ------------------------------------------------------------ 6. corners
def fillet(coords, radius):
    """round each bend with an arc of the given radius (clamped to fit)"""
    if len(coords) < 3:
        return list(coords)
    out = [coords[0]]
    for i in range(1, len(coords) - 1):
        p0, p1, p2 = map(np.array, (coords[i - 1], coords[i], coords[i + 1]))
        v0, v1 = p0 - p1, p2 - p1
        l0, l1 = np.linalg.norm(v0), np.linalg.norm(v1)
        if l0 < 1e-6 or l1 < 1e-6:
            continue
        v0, v1 = v0 / l0, v1 / l1
        ang = math.acos(max(-1.0, min(1.0, float(np.dot(v0, v1)))))
        if ang > math.radians(178):
            out.append(tuple(p1))
            continue
        if ang < math.radians(20):      # doubles back: a tracing hairpin, drop the point
            continue
        t = radius / math.tan(ang / 2)
        t = min(t, l0 * 0.45, l1 * 0.45)
        r = t * math.tan(ang / 2)
        a, b = p1 + v0 * t, p1 + v1 * t
        bis = (v0 + v1) / np.linalg.norm(v0 + v1)
        c = p1 + bis * (r / math.sin(ang / 2))
        sa, sb = math.atan2(*(a - c)[::-1]), math.atan2(*(b - c)[::-1])
        d = (sb - sa + math.pi) % (2 * math.pi) - math.pi
        for k in range(9):
            th = sa + d * k / 8
            out.append((c[0] + r * math.cos(th), c[1] + r * math.sin(th)))
    out.append(coords[-1])
    return out


roads = []
nodes = sorted(pos, key=str)
nid = {k: i for i, k in enumerate(nodes)}
for i, e in enumerate(E):
    w, lanes, curb, bend = CLASSES[e["cls"]]
    cs = fillet(list(e["line"].coords), bend)
    roads.append({"id": i, "class": e["cls"], "width": w, "lanes": lanes, "name": e["name"],
                  "points": [[round(x, 2), round(y, 2)] for x, y in cs],
                  "nodes": [nid[e["a"]], nid[e["b"]]], "length": round(e["line"].length, 1),
                  "orig_width": None if e["w_orig"] is None else round(e["w_orig"], 1), "source_road": e["rid"]})
deg = Counter()
for r in roads:
    for n in r["nodes"]:
        deg[n] += 1
junctions, dead_ends = [], []
for k in nodes:
    i = nid[k]
    rs = [r for r in roads if i in r["nodes"]]
    if deg[i] >= 3:
        cls = [r["class"] for r in rs]
        curb = min(CLASSES[c][2] for c in cls)
        junctions.append({"id": i, "center": [round(pos[k][0], 2), round(pos[k][1], 2)], "roads": [r["id"] for r in rs],
                          "curb_radius": curb, "radius": round(max(r["width"] for r in rs) / 2 + curb * 0.3, 1)})
    elif deg[i] == 1:
        dead_ends.append({"node": i, "at": [round(pos[k][0], 1), round(pos[k][1], 1)], "road": rs[0]["id"],
                          "class": rs[0]["class"], "name": rs[0]["name"]})

# ------------------------------------------------------------ checks
road_area = {}
for r in roads:
    road_area[r["id"]] = LineString(r["points"]).buffer(r["width"] / 2, cap_style=2)
all_roads = unary_union(list(road_area.values()))


def poly(p):
    g = Polygon(p)
    return g if g.is_valid else g.buffer(0)


waters = [("bay", poly(lots_plan["water"]))]
for w in lay["waters"]:
    if w.get("poly"):
        waters.append((w["kind"], poly(w["poly"])))
kept = [(l["kind"], poly(l["poly"])) for l in lay["lots"] if l["kind"].startswith("landmark")]
kept += [(p["kind"], poly(p["poly"])) for p in lay["parks"] if p.get("area", 0) > 1500]
crossings = []
for r in roads:
    a = road_area[r["id"]]
    for kind, g in waters:
        x = a.intersection(g)
        if x.area > 4:
            c = x.centroid
            crossings.append({"road": r["id"], "class": r["class"], "what": kind, "area_m2": round(x.area),
                              "at": [round(c.x), round(c.y)]})
    for kind, g in kept:
        x = a.intersection(g)
        if x.area > 20:
            c = x.centroid
            crossings.append({"road": r["id"], "class": r["class"], "what": kind, "area_m2": round(x.area),
                              "at": [round(c.x), round(c.y)]})

# blocks: faces of the centreline network
faces = [f for f in polygonize(unary_union([LineString(r["points"]) for r in roads])) if f.area > 400]
block_areas = [f.buffer(0).area for f in faces]
# usable block = face minus half the road widths around it
usable = [max(0.0, f.difference(all_roads).area) for f in faces]

out = {"roads": roads, "junctions": junctions, "dead_ends": dead_ends, "crossings": crossings,
       "classes": {k: {"width": v[0], "lanes": v[1], "curb_radius": v[2], "bend_radius": v[3]} for k, v in CLASSES.items()},
       "stats": {}}
cnt = Counter(r["class"] for r in roads)
length_by = defaultdict(float)
for r in roads:
    length_by[r["class"]] += r["length"]
stats = {
    "roads_before": n_roads0, "junctions_before": n_junc0,
    "roads_after": len(roads), "junctions_after": len(junctions), "dead_ends": len(dead_ends),
    "merged_junction_points": merged_junctions, "dead_ends_joined": bridged, "pieces_joined_end_to_end": joined,
    "duplicate_parallel_removed": len(dup_removed), "island_pieces_removed": len(islands), "dropped_pieces": dropped_short,
    "straightened_pieces": straightened, "snapped_segments": snap_count, "near_miss_unsnapped": len(unsnapped),
    "max_point_move_m": round(max_move, 1),
    "blocks": len(faces), "avg_block_m2": round(float(np.mean(block_areas))), "median_block_m2": round(float(np.median(block_areas))),
    "avg_block_buildable_m2": round(float(np.mean(usable))),
    "by_class": {k: {"pieces": cnt[k], "km": round(length_by[k] / 1000, 2)} for k in CLASSES},
}
out["stats"] = stats
json.dump(out, open(os.path.join(OUT, "roads_regular.json"), "w"))

# ------------------------------------------------------------ plan image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly, PathPatch
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
for kind, g in waters:
    for gg in getattr(g, "geoms", [g]):
        ax.add_patch(MPoly(np.array(gg.exterior.coords), closed=True, fc="#9cc3e6", ec="none", zorder=0))
for p in lay["parks"]:
    ax.add_patch(MPoly(np.array(p["poly"]), closed=True, fc="#b9d7a8", ec="none", zorder=0))
for l in lay["lots"]:
    if l["kind"].startswith("landmark"):
        ax.add_patch(MPoly(np.array(l["poly"]), closed=True, fc="#f3c86b", ec="#a07010", zorder=1))
# old centrelines, faint
for r in src["roads"]:
    p = np.array(r["points"])
    ax.plot(p[:, 0], p[:, 1], color="#999", lw=0.6, ls=":", zorder=2)
# new road surface with rounded curbs: closing the union rounds the corners
for cls in ("alley", "street", "avenue"):
    rs = [road_area[r["id"]] for r in roads if r["class"] == cls]
    if not rs:
        continue
    g = unary_union(rs)
    for gg in getattr(g, "geoms", [g]):
        ax.add_patch(patch(gg, fc=COL[cls], ec="none", alpha=0.55, zorder=3))
for j in junctions:
    ax.plot(*j["center"], "o", ms=3.5, color="k", zorder=5)
for d in dead_ends:
    ax.plot(*d["at"], "x", ms=9, mew=2.2, color="#e67e22", zorder=6)
for c in crossings:
    ax.plot(*c["at"], "s", ms=10, mfc="none", mec="#8e44ad", mew=2, zorder=6)
SHORT = {"avenue": "Ave", "street": "St", "alley": "Alley"}
for r in roads:
    if r["length"] < 45:
        continue
    ls = LineString(r["points"])
    m = ls.interpolate(0.5, normalized=True)
    a = ls.interpolate(0.45, normalized=True)
    b = ls.interpolate(0.55, normalized=True)
    ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
    if ang > 90:
        ang -= 180
    if ang < -90:
        ang += 180
    ax.text(m.x, m.y, "%s %dm" % (SHORT[r["class"]], r["width"]), fontsize=7, ha="center", va="center",
            rotation=-ang, rotation_mode="anchor", color="white", weight="bold", zorder=7,
            bbox=dict(boxstyle="round,pad=0.15", fc=COL[r["class"]], ec="none", alpha=0.9))
ax.set_aspect("equal")
ax.set_xlim(-870, 1180)
ax.set_ylim(980, -760)              # north up (UE -Y is north)
ax.set_xlabel("UE X (m)")
ax.set_ylabel("UE Y (m), north is up")
s = stats
ax.set_title("Atlas Park Reborn - street plan, stage 1 (regularised)\n"
             "%d junctions, %d road pieces (avenue %d / street %d / alley %d), %d dead ends;  "
             "%d blocks, average block %d m2 (median %d m2, buildable %d m2)" %
             (s["junctions_after"], s["roads_after"], cnt["avenue"], cnt["street"], cnt["alley"], s["dead_ends"],
              s["blocks"], s["avg_block_m2"], s["median_block_m2"], s["avg_block_buildable_m2"]), fontsize=16)
from matplotlib.lines import Line2D
leg = [Line2D([0], [0], color=COL[k], lw=8, alpha=0.6, label="%s %d m, %d lanes" % (k, CLASSES[k][0], CLASSES[k][1])) for k in CLASSES]
leg += [Line2D([0], [0], color="#999", ls=":", label="current plan (before)"),
        Line2D([0], [0], marker="o", color="k", lw=0, label="junction"),
        Line2D([0], [0], marker="x", color="#e67e22", lw=0, mew=2, ms=9, label="dead end"),
        Line2D([0], [0], marker="s", mfc="none", mec="#8e44ad", lw=0, mew=2, ms=10, label="crosses water / park / landmark")]
ax.legend(handles=leg, loc="lower left", fontsize=13)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "street_plan.png"), dpi=70)

# ------------------------------------------------------------ report
with open(os.path.join(OUT, "street_report.txt"), "w") as f:
    f.write(json.dumps(stats, indent=1) + "\n\nCROSSINGS\n")
    for c in crossings:
        f.write("road %d (%s) crosses %s, %d m2 at %s\n" % (c["road"], c["class"], c["what"], c["area_m2"], c["at"]))
    f.write("\nDEAD ENDS\n")
    for d in dead_ends:
        f.write("road %d (%s%s) ends at %s\n" % (d["road"], d["class"], ", " + d["name"] if d["name"] else "", d["at"]))
    f.write("\nDUPLICATE PARALLEL ROADS REMOVED (source road, length m, midpoint)\n")
    for d in dup_removed:
        f.write("%s\n" % (d,))
    f.write("\nNEAR 45-DEGREE SEGMENTS LEFT UNSNAPPED (move limit)\n")
    for ei, off, L in unsnapped:
        f.write("road piece %d: %.1f deg off, %.0f m\n" % (ei, off, L))
print(json.dumps(stats, indent=1))
print("crossings", len(crossings), "dead ends", len(dead_ends))

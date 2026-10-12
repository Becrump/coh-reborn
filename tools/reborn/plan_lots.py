"""Turn layout.json lots and north-district blocks into PCG building lots.

    python tools/reborn/plan_lots.py <out dir>

Needs layout.json (atlas_layout.py) and buildings_catalog.json
(ue/measure_buildings.py). For every lot it lists the City Sample buildings
that fit its footprint and height class; lots with the same candidate list
share a bucket, and the PCG graph picks randomly inside each bucket. Writes
lots_plan.json and lots_plan.png.
"""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np
from PIL import Image
from shapely.geometry import Polygon, box
from shapely import affinity

OUT = sys.argv[1]
lay = json.load(open(os.path.join(OUT, "layout.json")))
cat = json.load(open(os.path.join(OUT, "buildings_catalog.json")))
hm = (np.asarray(Image.open(os.path.join(OUT, "heightmap.png"))).astype(float) - 32768) / 128
LX0, LY0 = lay["landscape"]["origin_cm"][0] / 100, lay["landscape"]["origin_cm"][1] / 100


def ground(x, y):
    c, r = int(round(x - LX0)), int(round(y - LY0))
    win = hm[max(r - 3, 0):r + 4, max(c - 3, 0):c + 4]
    return float(np.median(win))


blds = []
for b in cat:
    sx, sy = b["size_m"]
    # skip empty/ground-floor-only packs and ones whose footprint sits far off their origin
    if min(sx, sy) < 6 or "Level01" in b["name"] or math.hypot(b["center"][0], b["center"][1]) > 800:
        continue
    blds.append({"name": b["name"], "path": b["path"], "long": max(sx, sy), "short": min(sx, sy),
                 "yaw": 0 if sx >= sy else 90, "h": b["height_m"],
                 "off": [b["center"][0] / 100, b["center"][1] / 100]})

HCLASS = {"low": (0, 40), "mid": (20, 160), "high": (60, 270), "tower": (140, 500)}


def candidates(L, W, cls, slack=1.2):
    lo, hi = HCLASS[cls]
    out = []
    for b in blds:
        if not (lo <= b["h"] <= hi):
            continue
        if b["long"] <= L * slack + 6 and b["short"] <= W * slack + 6 and b["long"] >= 0.45 * L:
            out.append(b["name"])
    return out


lots = []
for i, lot in enumerate(lay["lots"]):
    if lot["kind"].startswith("landmark"):
        lots.append({"id": "core_%03d" % i, "kind": lot["kind"], "center": lot["center"], "yaw": lot["yaw"],
                     "size": lot["size"], "class": lot["class"], "candidates": [], "poly": lot["poly"]})
        continue
    L, W = lot["size"]
    cls = lot["class"]
    c = candidates(L, W, cls)
    order = ["low", "mid", "high", "tower"]
    k = order.index(cls)
    for slack, alt in [(1.2, [cls]), (1.45, [cls]), (1.45, order[max(k - 1, 0):k + 2]), (1.8, order)]:
        if c:
            break
        for a in alt:
            c = c or candidates(L, W, a, slack)
    lots.append({"id": "core_%03d" % i, "kind": "core", "center": lot["center"], "yaw": lot["yaw"],
                 "size": [L, W], "class": cls, "height": lot["height"], "candidates": c, "poly": lot["poly"]})

# north district: cut blocks into parcels along their long side
PARCEL = {"outer_district": (58, 46, ["mid", "low", "high", "mid"]),
          "district_mid": (62, 48, ["mid", "high"]), "waterfront_mid": (55, 40, ["low", "mid"]),
          "harbor_rebuild": (90, 60, ["low"])}
for j, blk in enumerate(lay["blocks"]):
    if blk["kind"] not in PARCEL:
        continue
    pw, pd, classes = PARCEL[blk["kind"]]
    poly = Polygon(blk["poly"]).buffer(-3)
    if poly.is_empty:
        continue
    x0, y0, x1, y1 = poly.bounds
    nx = max(1, int((x1 - x0) // pw))
    ny = max(1, int((y1 - y0) // pd))
    cw, ch = (x1 - x0) / nx, (y1 - y0) / ny
    for ix in range(nx):
        for iy in range(ny):
            cell = box(x0 + ix * cw, y0 + iy * ch, x0 + (ix + 1) * cw, y0 + (iy + 1) * ch)
            part = cell & poly
            if part.is_empty or part.area < 0.6 * cell.area:
                continue
            L, W = max(cw, ch), min(cw, ch) * 0.92
            yaw = 0 if cw >= ch else 90
            cls = classes[(ix + iy) % len(classes)]
            c = candidates(L, W, cls) or candidates(L, W, cls, 1.5)
            lots.append({"id": "north_%02d_%d_%d" % (j, ix, iy), "kind": blk["kind"],
                         "center": [part.centroid.x, part.centroid.y], "yaw": yaw, "size": [L, W],
                         "class": cls, "candidates": c, "poly": [list(p) for p in part.exterior.coords]})

# nothing may stand in or right next to water: the bay, the inlet and the ponds
from shapely.ops import unary_union
coast = [w for w in lay["waters"] if w["kind"] == "bay"][0]["coast"]
sea = Polygon([(-5000, -9000), (5000, -9000), (5000, coast[-1][1])] + [tuple(p) for p in coast[::-1]] +
              [(-5000, coast[0][1])])
WATER = unary_union([sea] + [Polygon(w["poly"]) for w in lay["waters"] if w["kind"] == "pond"])
WATER_MARGIN = 12.0
# keep clear of the monorail (track and station), when it has been planned
mono_path = os.path.join(OUT, "monorail.json")
RAIL = None
if os.path.exists(mono_path):
    mono = json.load(open(mono_path))
    from shapely.geometry import LineString as _LS
    from shapely import affinity as _aff
    st = mono["station"]
    sbox = _aff.rotate(box(-40, -12, 40, 12), st["yaw"], origin=(0, 0))
    sbox = _aff.translate(sbox, st["center"][0], st["center"][1])
    RAIL = unary_union([_LS([p[:2] for p in mono["track"]]).buffer(9), sbox.buffer(4)])
kept = []
for lot in lots:
    if RAIL is not None and Polygon(lot["poly"]).intersects(RAIL) and not lot["kind"].startswith("landmark"):
        print("skip lot under the monorail", lot["id"])
        continue
    d = Polygon(lot["poly"]).distance(WATER)
    lot["water_clearance"] = round(d, 1)
    if d < WATER_MARGIN and not lot["kind"].startswith("landmark"):
        print("skip lot near water", lot["id"], round(d, 1))
        continue
    kept.append(lot)
lots = kept


def size_bucket(W):
    return "S" if W < 30 else "M" if W < 45 else "L" if W < 70 else "X"


groups = defaultdict(list)
for lot in lots:
    lot["ground"] = ground(*lot["center"])
    if lot["kind"].startswith("landmark"):
        continue
    groups[(lot["class"], size_bucket(lot["size"][1]))].append(lot)
order = ["low", "mid", "high", "tower"]
bucket_list = []
for n, ((cls, sb), members) in enumerate(sorted(groups.items())):
    L = float(np.percentile([l["size"][0] for l in members], 30))
    W = float(np.percentile([l["size"][1] for l in members], 30))
    k = order.index(cls)
    c = []
    for slack, alt in [(1.2, [cls]), (1.45, [cls]), (1.45, order[max(k - 1, 0):k + 2]), (1.8, order)]:
        for a in alt:
            c = c or candidates(L, W, a, slack)
        if c:
            break
    # prefer the buildings that fill the lot best
    by = {b["name"]: b for b in blds}
    c = sorted(c, key=lambda nm: -(by[nm]["long"] * by[nm]["short"]))[:6]
    bid = "B_%s_%s" % (cls, sb)
    bucket_list.append({"id": bid, "candidates": c, "lots": [l["id"] for l in members], "min_size": [L, W]})
    for l in members:
        l["bucket"] = bid
        l["candidates"] = c
# planting zones: woods on the hills outside the ring, the parks inside
x0r, y0r, x1r, y1r = lay["ring"]
land = Polygon([(x, y) for x, y in [(LX0, 1400)] + [tuple(p) for p in
               [w for w in lay["waters"] if w["kind"] == "bay"][0]["coast"]] + [(LX0 + 2016, 1400)]])
zones = []
BELT = 50.0
LX1, LY1 = LX0 + 2016, LY0 + 2016
for name, b in [("Woods_West", box(LX0 + 2, y0r - 40, LX0 + BELT, LY1 - 2)),
                ("Woods_East", box(LX1 - BELT, y0r - 40, LX1 - 2, LY1 - 2)),
                ("Woods_South", box(LX0 + BELT, LY1 - BELT, LX1 - BELT, LY1 - 2))]:
    g = b & land
    for k, part in enumerate(getattr(g, "geoms", [g])):
        if part.area > 2000:
            zones.append({"name": "%s_%d" % (name, k), "kind": "woods", "density": 1 / 90.0,
                          "poly": [list(p) for p in part.simplify(2).exterior.coords]})
for k, pk in enumerate(lay["parks"]):
    poly = Polygon(pk["poly"]).buffer(-1.5)
    if poly.is_empty:
        continue
    poly = max(getattr(poly, "geoms", [poly]), key=lambda g: g.area)
    if pk["kind"] == "inlet_woods":
        kind, dens = "woods", 1 / 90.0
    elif pk["kind"] == "waterfront_park":
        kind, dens = "park", 1 / 400.0
    else:
        cover = pk.get("tree_cover", 0.1)
        kind, dens = ("park_woods", 1 / 140.0) if cover > 0.2 else ("park", 1 / 350.0)
    zones.append({"name": "Park_%03d" % k, "kind": kind, "density": dens, "area": pk["area"],
                  "poly": [list(p) for p in poly.simplify(1).exterior.coords]})
# landmark spots stay empty: atlas_layout paints them as paved plazas
plan = {"buildings": blds, "lots": lots, "buckets": bucket_list, "zones": zones,
        "water_margin_m": WATER_MARGIN, "water": [list(p) for p in Polygon(sea).exterior.coords]}
with open(os.path.join(OUT, "lots_plan.json"), "w") as f:
    json.dump(plan, f, indent=1)
empty = [l["id"] for l in lots if not l["candidates"] and not l["kind"].startswith("landmark")]
print("lots", len(lots), "buckets", len(bucket_list), "no fit", len(empty), empty[:10])
for b in bucket_list[:40]:
    print(b["id"], len(b["lots"]), b["candidates"])

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MP
fig, ax = plt.subplots(figsize=(12, 10))
cols = plt.cm.tab20(np.linspace(0, 1, max(len(bucket_list), 1)))
bi = {b["id"]: k for k, b in enumerate(bucket_list)}
for lot in lots:
    fc = "#8866ff" if lot["kind"].startswith("landmark") else ("#cccccc" if "bucket" not in lot else cols[bi[lot["bucket"]] % 20])
    ax.add_patch(MP(lot["poly"], closed=True, fc=fc, ec="k", lw=0.4))
    if "bucket" in lot:
        ax.text(lot["center"][0], lot["center"][1], lot["bucket"], fontsize=5, ha="center")
ax.set_xlim(-860, 1170)
ax.set_ylim(760, -760)
ax.set_aspect("equal")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "lots_plan.png"), dpi=90)

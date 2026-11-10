"""City reset, stage 3: blocks, lots and parks on the stage-2 streets.

    python tools/reborn/plan_blocks.py <out dir>

Reads lots_plan.json (plan_lots.py; the first run keeps it as
lots_plan_pre_stage3.json), corridor.wkt / corridor_mask.npy / ground_z.npy
(build_road_surface.py), layout.json and monorail.json. Writes:

  lots_plan.json   lots that lie wholly in their block, off every street and
                   sidewalk; buckets whose every building fits every lot in it;
                   park and planting zones clipped off the streets
  ground_z.npy     the shared ground with a flat pad under every lot (the
                   roads-only version is kept as ground_z_roads.npy)
  heightmap.png    the landscape to match (10 cm under the road meshes)
  lots_plan.png, stage3_report.txt

Lots
  * a lot the new streets don't touch keeps its place and class
  * a lot a street or sidewalk crosses is cut back to the buildable part of
    its block; each part big enough for a building (18 x 14 m) becomes a
    smaller lot, smaller parts become pocket greens
  * the building for a lot must fit inside the largest rectangle that fits
    the lot (in the lot's direction), with room for the model's off-centre
    footprint - nothing can reach into a street
Ground
  * every lot gets a flat pad at the median ground under it, eased into the
    ground around it (never into a street, sidewalk or water), so no
    building floats or sinks
"""
import json
import math
import os
import shutil
import sys
from collections import defaultdict

import numpy as np
from PIL import Image
from scipy import ndimage
from shapely import affinity, wkt
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polylabel, unary_union

OUT = sys.argv[1]
J = lambda n: os.path.join(OUT, n)  # noqa: E731
if not os.path.exists(J("lots_plan_pre_stage3.json")):
    shutil.copy(J("lots_plan.json"), J("lots_plan_pre_stage3.json"))
if not os.path.exists(J("ground_z_roads.npy")) or os.path.getmtime(J("ground_z.npy")) > os.path.getmtime(J("ground_z_roads.npy")) + 5:
    # a fresh ground from build_road_surface.py: keep it as the roads-only base
    if not os.path.exists(J("lots_plan.json.stage3_done")) or os.path.getmtime(J("ground_z.npy")) > os.path.getmtime(J("lots_plan.json.stage3_done")):
        shutil.copy(J("ground_z.npy"), J("ground_z_roads.npy"))
plan = json.load(open(J("lots_plan_pre_stage3.json")))
lay = json.load(open(J("layout.json")))
corridor = wkt.loads(open(J("corridor.wkt")).read())
m_corr = np.load(J("corridor_mask.npy"))
G0 = np.load(J("ground_z_roads.npy")).astype(np.float64)
LND = lay["landscape"]
LX0, LY0 = LND["origin_cm"][0] / 100.0, LND["origin_cm"][1] / 100.0
N = LND["verts"]

MIN_LOT = (18.0, 14.0)        # smallest lot that takes a building (m)
STREET_GAP = 1.0              # lots stay this far back from the sidewalk
WATER_MARGIN = plan.get("water_margin_m", 12.0)


def poly(p):
    g = Polygon(p)
    return g if g.is_valid else g.buffer(0)


water = unary_union([poly(plan["water"])] + [poly(w["poly"]) for w in lay["waters"] if w.get("poly") and w["kind"] != "bay"])
RAIL = None
if os.path.exists(J("monorail.json")):
    mono = json.load(open(J("monorail.json")))
    st = mono["station"]
    sbox = affinity.translate(affinity.rotate(box(-40, -12, 40, 12), st["yaw"], origin=(0, 0)), st["center"][0], st["center"][1])
    RAIL = unary_union([LineString([p[:2] for p in mono["track"]]).buffer(9), sbox.buffer(4)] +
                       # monorail pillar feet (plan_pillars.py), incl. any dedicated gaps
                       [Point(pl["foot"][:2]).buffer(4) for pl in mono.get("pillars", [])])
land = box(LX0, LY0, LX0 + N - 1, LY0 + N - 1)
blocked = [corridor.buffer(STREET_GAP), water.buffer(WATER_MARGIN)]
if RAIL is not None:
    blocked.append(RAIL)
buildable = land.difference(unary_union(blocked))

# ------------------------------------------------------------------ largest rectangle in a lot
def inscribed(g, yaw):
    """largest rectangle (in the lot's direction) inside g: centre, L, W"""
    if g.is_empty or g.area < MIN_LOT[0] * MIN_LOT[1] * 0.8:
        return None
    r = affinity.rotate(g, -yaw, origin=(0, 0))
    best = None
    seeds = [polylabel(r, 0.5) if isinstance(r, Polygon) else r.representative_point(), r.centroid]
    x0, y0, x1, y1 = r.bounds
    for aspect in (1.0, 1.4, 2.0, 2.8, (x1 - x0) / max(y1 - y0, 1), 0.7, 0.5):
        for c in seeds:
            lo, hi = 0.0, max(x1 - x0, y1 - y0)
            for _ in range(18):
                mid = (lo + hi) / 2
                w = mid
                h = mid / aspect
                rect = box(c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2)
                if r.contains(rect):
                    lo = mid
                else:
                    hi = mid
            w, h = lo, lo / aspect
            if best is None or w * h > best[1] * best[2]:
                best = (c, w, h)
    c, w, h = best
    L, W = max(w, h), min(w, h)
    lot_yaw = yaw if w >= h else yaw + 90
    ctr = affinity.rotate(Point(c.x, c.y), yaw, origin=(0, 0))
    return (ctr.x, ctr.y), L, W, lot_yaw


def rect_poly(center, L, W, yaw):
    return affinity.rotate(box(center[0] - L / 2, center[1] - W / 2, center[0] + L / 2, center[1] + W / 2), yaw, origin=center)


# ------------------------------------------------------------------ lots
# City Sample buildings come in two packs: the building and its ground floor
# (lobby / storefront, "Level01"). Without the ground floor a building hangs
# 3-18 m in the air. Pair them; drop a building whose ground floor in this
# content is only a 2.6 m placeholder.
catalog = {c["name"]: c for c in json.load(open(J("buildings_catalog.json")))}


def ground_pack(name):
    for g in (name.replace("_A1_N1", "_A1_Level01_N1"), name.replace("_A1_N1", "_A1l_Level01_N1"),
              name.replace("_A01_N1", "_A01_Level01_N1"), name.replace("_N1", "_Level01_N1")):
        if g != name and g in catalog:
            return catalog[g]
    return None


blds = []
for b in plan["buildings"]:
    g = ground_pack(b["name"])
    if g is not None and g["height_m"] < 2.0:
        continue                      # placeholder ground floor: would float
    b = dict(b)
    if g is not None:
        b["ground_name"], b["ground_path"] = g["name"], g["path"]
        gl, gs = max(g["size_m"]), min(g["size_m"])
        b["long"], b["short"] = max(b["long"], gl), max(b["short"], gs)
    blds.append(b)
pack_stats = {"buildings_with_ground_floor": sum(1 for b in blds if "ground_name" in b),
              "buildings_dropped_placeholder_ground": len(plan["buildings"]) - len(blds)}
HCLASS = {"low": (0, 40), "mid": (20, 160), "high": (60, 270), "tower": (140, 500)}
ORDER = ["low", "mid", "high", "tower"]


def fits(b, L, W):
    off = math.hypot(*b["off"])
    return b["long"] + 2 * off <= L and b["short"] + 2 * off <= W


def candidates(L, W, cls):
    k = ORDER.index(cls)
    for alt in ([cls], ORDER[max(k - 1, 0):k + 2], ORDER):
        out = [b for b in blds if any(HCLASS[a][0] <= b["h"] <= HCLASS[a][1] for a in alt) and fits(b, L, W)]
        if out:
            # the ones that fill the lot best first
            return [b["name"] for b in sorted(out, key=lambda b: -(b["long"] * b["short"]))[:6]]
    return []


lots, pockets, dropped, report = [], [], [], defaultdict(int)
for lot in plan["lots"]:
    lp = poly(lot["poly"])
    if lot["kind"].startswith("landmark"):
        lots.append(dict(lot))
        report["landmarks_kept"] += 1
        continue
    inside = lp.intersection(buildable)
    crossed = lp.area - inside.area > 1.0
    report["crossed" if crossed else "untouched"] += 1
    parts = [p for p in getattr(inside, "geoms", [inside]) if isinstance(p, Polygon) and not p.is_empty]
    made = 0
    for k, part in enumerate(sorted(parts, key=lambda p: -p.area)):
        ins = inscribed(part, lot["yaw"])
        if ins is None:
            if part.area > 200:
                pockets.append(part)
            continue
        ctr, L, W, yaw = ins
        if L < MIN_LOT[0] or W < MIN_LOT[1]:
            if part.area > 200:
                pockets.append(part)
            continue
        new = dict(lot)
        new["id"] = lot["id"] if (not crossed and k == 0) else "%s_%s" % (lot["id"], "abcdefgh"[k])
        new["center"], new["size"], new["yaw"] = [ctr[0], ctr[1]], [round(L, 1), round(W, 1)], yaw
        new["poly"] = [list(p) for p in rect_poly(ctr, L, W, yaw).exterior.coords]
        new["block_poly"] = [list(p) for p in part.exterior.coords]
        new["was_crossed"] = crossed
        lots.append(new)
        made += 1
    if crossed:
        report["crossed_relotted" if made else "crossed_to_green"] += 1
    if not made and not crossed:
        dropped.append(lot["id"])

# vacant ground: blocks the new streets made, or that only had paving, get
# new lots on a 62 x 55 m grid along the block; what's left becomes green.
# Blocks are the holes of the street corridor; the City Hall block stays as is.
CITY_HALL = Point(39.0, 201.0)
blocks = []
for g in getattr(corridor, "geoms", [corridor]):
    for h in g.interiors:
        blocks.append(Polygon(h.coords))
park_area = unary_union([poly(z["poly"]) for z in plan["zones"]] + [poly(p["poly"]) for p in lay["parks"]])
taken = unary_union([poly(l["poly"]).buffer(4) for l in lots] + [park_area])
core_box = box(*lay["core"])
filled = 0
for blk in blocks:
    if blk.contains(CITY_HALL) or blk.area < 800:
        continue
    vac = blk.intersection(buildable).difference(taken)
    for part in getattr(vac, "geoms", [vac]):
        if not isinstance(part, Polygon) or part.area < MIN_LOT[0] * MIN_LOT[1] * 1.2:
            continue
        rect = part.minimum_rotated_rectangle
        cs = list(rect.exterior.coords)
        e = np.subtract(cs[1], cs[0])
        yaw = math.degrees(math.atan2(e[1], e[0]))
        snap = round(yaw / 45.0) * 45.0
        yaw = snap if abs(yaw - snap) < 8 else yaw
        r = affinity.rotate(part, -yaw, origin=(0, 0))
        x0, y0, x1, y1 = r.bounds
        # cells sized to the City Sample catalogue (most footprints are 29-83 m)
        nx, ny = max(1, int(round((x1 - x0) / 62.0))), max(1, int(round((y1 - y0) / 55.0)))
        cw, ch = (x1 - x0) / nx, (y1 - y0) / ny
        in_core = core_box.contains(part.centroid)
        for ix in range(nx):
            for iy in range(ny):
                cell = affinity.rotate(box(x0 + ix * cw, y0 + iy * ch, x0 + (ix + 1) * cw, y0 + (iy + 1) * ch), yaw, origin=(0, 0))
                piece = cell.intersection(part).buffer(-1.5)
                for pc in getattr(piece, "geoms", [piece]):
                    if not isinstance(pc, Polygon):
                        continue
                    ins = inscribed(pc, yaw)
                    if ins is None:
                        pockets.append(pc)
                        continue
                    ctr, L, W, lyaw = ins
                    if L < MIN_LOT[0] or W < MIN_LOT[1]:
                        pockets.append(pc)
                        continue
                    cls = (["mid", "high", "mid", "low"] if in_core else ["mid", "low", "mid", "high"])[(ix + 2 * iy + filled) % 4]
                    lots.append({"id": "fill_%03d" % filled, "kind": "fill", "center": [ctr[0], ctr[1]], "yaw": lyaw,
                                 "size": [round(L, 1), round(W, 1)], "class": cls, "height": 0,
                                 "poly": [list(p) for p in rect_poly(ctr, L, W, lyaw).exterior.coords],
                                 "block_poly": [list(p) for p in pc.exterior.coords], "was_crossed": False, "candidates": []})
                    filled += 1
report["fill_lots"] = filled

# buckets: lots grouped by class and 10 m size steps; a bucket's candidates
# fit its smallest lot, so every candidate fits every lot in the bucket
groups = defaultdict(list)
for lot in lots:
    if lot["kind"].startswith("landmark"):
        continue
    L, W = lot["size"]
    groups[(lot["class"], int(L // 10), int(W // 10))].append(lot)
buckets = []
no_fit = []
for (cls, lq, wq), members in sorted(groups.items()):
    L = min(l["size"][0] for l in members)
    W = min(l["size"][1] for l in members)
    c = candidates(L, W, cls)
    bid = "B_%s_%02d_%02d" % (cls, lq, wq)
    if not c:
        no_fit += [l["id"] for l in members]
        for l in members:
            pockets.append(poly(l["poly"]))
        continue
    buckets.append({"id": bid, "candidates": c, "lots": [l["id"] for l in members], "min_size": [L, W]})
    for l in members:
        l["bucket"], l["candidates"] = bid, c
lots = [l for l in lots if l["kind"].startswith("landmark") or "bucket" in l]

# ------------------------------------------------------------------ parks and planting
zones = []
off_streets = land.difference(corridor.buffer(1.5)).difference(water)
for z in plan["zones"]:
    zp = poly(z["poly"]).intersection(off_streets)
    if any(l for l in lots if not l["kind"].startswith("landmark") and poly(l["poly"]).intersects(zp)):
        zp = zp.difference(unary_union([poly(l["poly"]).buffer(3) for l in lots if not l["kind"].startswith("landmark")]))
    for k, part in enumerate(p for p in getattr(zp, "geoms", [zp]) if isinstance(p, Polygon) and p.area > 150):
        zz = dict(z)
        zz["name"] = "%s_%d" % (z["name"], k)
        zz["poly"] = [list(p) for p in part.simplify(1).exterior.coords]
        zones.append(zz)
pk = unary_union(pockets).intersection(off_streets).buffer(-1) if pockets else Polygon()
for k, part in enumerate(p for p in getattr(pk, "geoms", [pk]) if isinstance(p, Polygon) and p.area > 500):
    zones.append({"name": "Pocket_%03d" % k, "kind": "park", "density": 1 / 350.0, "area": round(part.area),
                  "poly": [list(c) for c in part.simplify(1).exterior.coords]})
    report["pocket_greens"] += 1

# ------------------------------------------------------------------ building pads
XX, YY = np.meshgrid(np.arange(N) + LX0, np.arange(N) + LY0)
acc = np.zeros((N, N))
wsum = np.zeros((N, N))
wmax = np.zeros((N, N))
pads = 0
for lot in lots:
    if lot["kind"].startswith("landmark"):
        continue
    rp = poly(lot["poly"]).buffer(1.5, join_style=2)
    x0, y0, x1, y1 = rp.bounds
    c0, c1 = int(max(x0 - LX0 - 30, 0)), int(min(x1 - LX0 + 31, N))
    r0, r1 = int(max(y0 - LY0 - 30, 0)), int(min(y1 - LY0 + 31, N))
    sub_x, sub_y = XX[r0:r1, c0:c1], YY[r0:r1, c0:c1]
    from matplotlib.path import Path as MPath
    inside = MPath(np.asarray(rp.exterior.coords)).contains_points(np.column_stack([sub_x.ravel(), sub_y.ravel()])).reshape(sub_x.shape)
    if not inside.any():
        continue
    zs = G0[r0:r1, c0:c1][inside]
    if np.percentile(zs, 95) - np.percentile(zs, 5) > 6.0:
        # straddles a terrace or a sunken park: no 6 m+ earthworks, a green instead
        lot["drop"] = True
        report["lots_on_steep_ground_to_green"] += 1
        continue
    pad = float(np.median(zs))
    d = ndimage.distance_transform_edt(~inside)
    delta = np.abs(G0[r0:r1, c0:c1] - pad)
    ease = np.clip(3 * delta, 6, 25)
    w = np.clip(1 - d / ease, 0, 1)
    w = w * w * (3 - 2 * w)
    acc[r0:r1, c0:c1] += w * pad
    wsum[r0:r1, c0:c1] += w
    wmax[r0:r1, c0:c1] = np.maximum(wmax[r0:r1, c0:c1], w)
    lot["ground"] = round(pad, 2)
    lot["pad"] = True
    pads += 1
lots = [l for l in lots if not l.get("drop")]
m_water = np.zeros((N, N), bool)
from PIL import ImageDraw
img = Image.new("L", (N, N), 0)
dr = ImageDraw.Draw(img)
for g in getattr(water.buffer(3), "geoms", [water.buffer(3)]):
    dr.polygon([((x - LX0 + 0.5), (y - LY0 + 0.5)) for x, y in g.exterior.coords], fill=1)
m_water = np.asarray(img).astype(bool)
G = G0.copy()
sel = (wsum > 0) & ~m_corr & ~m_water
target = np.where(wsum > 0, acc / np.maximum(wsum, 1e-9), G0)
# pads keep off the sidewalk verge: no effect within 2 m of a sidewalk,
# full effect from 6 m, so the lawn always meets the sidewalk at its height
dcorr = ndimage.distance_transform_edt(~m_corr)
fade = np.clip((dcorr - 2.0) / 4.0, 0, 1)
G[sel] = (G0 + (target - G0) * wmax * fade)[sel]
np.save(J("ground_z.npy"), G.astype(np.float32))
Lh = G.copy()
Lh[ndimage.binary_erosion(m_corr, iterations=1)] -= 0.10
Image.fromarray(np.clip(np.round(Lh * 128 + 32768), 0, 65535).astype(np.uint16)).save(J("heightmap.png"))
for lot in lots:
    if lot["kind"].startswith("landmark"):
        c, r = int(round(lot["center"][0] - LX0)), int(round(lot["center"][1] - LY0))
        lot["ground"] = round(float(np.median(G[max(r - 3, 0):r + 4, max(c - 3, 0):c + 4])), 2)

# ------------------------------------------------------------------ ground paint
# no bare ground on lots, pads or vacant blocks: old paving (B) and dirt (A)
# outside the streets turn to mown lawn. Only a beach strip along the water
# keeps its sand; the Level01 packs bring their own plaza meshes.
surf = np.array(Image.open(J("surface.png")))
SN = surf.shape[0]
SRES = (N - 1) / SN
sx = (np.arange(SN) + 0.5) * SRES          # surface pixel centre, in landscape cells
sc = np.clip(np.round(sx).astype(int), 0, N - 1)
s_corr = m_corr[np.ix_(sc, sc)]
s_water = ndimage.distance_transform_edt(~m_water)[np.ix_(sc, sc)]
bare = ((surf[..., 2] > 0) | (surf[..., 3] > 0)) & ~s_corr
keep = (surf[..., 3] > 0) & (s_water < 25)  # beach
paint = bare & ~keep
report["bare_ground_to_lawn_m2"] = int(paint.sum() * SRES * SRES)
surf[paint, 1] = np.maximum(surf[paint, 1], np.maximum(surf[paint, 2], surf[paint, 3]))
surf[paint, 2] = 0
surf[paint, 3] = 0
Image.fromarray(surf, "RGBA").save(J("surface.png"))

# ------------------------------------------------------------------ write
out = dict(plan)
out["lots"], out["buckets"], out["zones"] = lots, buckets, zones
out["buildings"] = blds
json.dump(out, open(J("lots_plan.json"), "w"), indent=1)
open(J("lots_plan.json.stage3_done"), "w").write("ok")
report.update(pack_stats)
report.update({"lots": len([l for l in lots if not l["kind"].startswith("landmark")]), "buckets": len(buckets),
               "pads": pads, "zones": len(zones), "lots_without_a_fitting_building": len(no_fit),
               "lots_crossing_streets_now": sum(1 for l in lots if not l["kind"].startswith("landmark") and poly(l["poly"]).intersects(corridor)),
               "max_pad_change_m": round(float(np.max(np.abs(G - G0))), 2)})
open(J("stage3_report.txt"), "w").write(json.dumps(report, indent=1) + "\n\nno fit: %s\n" % no_fit)
print(json.dumps(report, indent=1))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MP
fig, ax = plt.subplots(figsize=(22, 22))
ax.set_facecolor("#e9e6dc")
for g in getattr(corridor, "geoms", [corridor]):
    ax.add_patch(MP(np.asarray(g.exterior.coords), closed=True, fc="#555", ec="none", zorder=1))
    for h in g.interiors:
        ax.add_patch(MP(np.asarray(h.coords), closed=True, fc="#e9e6dc", ec="none", zorder=1))
for z in zones:
    ax.add_patch(MP(z["poly"], closed=True, fc="#9fd08a", ec="#5a9a45", lw=0.4, zorder=2))
for l in lots:
    fc = "#8866ff" if l["kind"].startswith("landmark") else ("#e8a33d" if l.get("was_crossed") else "#3d7cc0" if l["kind"] == "fill" else "#c0603d")
    ax.add_patch(MP(l["poly"], closed=True, fc=fc, ec="k", lw=0.4, zorder=3))
ax.set_xlim(-870, 1180)
ax.set_ylim(980, -760)
ax.set_aspect("equal")
ax.set_title("Stage 3 lots: brown = lot kept, orange = re-cut from a crossed lot, blue = new lot on vacant ground, green = parks / pocket greens, grey = streets + sidewalks", fontsize=14)
fig.tight_layout()
fig.savefig(J("lots_plan.png"), dpi=60)

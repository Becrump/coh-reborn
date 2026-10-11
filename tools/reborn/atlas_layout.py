"""Build the Atlas Park Reborn layout from the original-map guide.

    python tools/reborn/atlas_layout.py <guide dir> <out dir>

The original zone (inside the old War Wall) is kept as the core: its ground
heights, road/sidewalk/grass layout, ponds, parks and building plots. The War
Wall and the filler skyline outside it are dropped. Around the core:
  * a ring boulevard where the wall stood,
  * a new waterfront district to the north that runs down to a bay
    (shoreline, piers, inlet), and
  * wooded hills on the west, south and east edges.

Writes (all in UE world space, centimetres unless noted):
  heightmap.png   16-bit landscape heights, 2017 x 2017, 1 m per vertex
  surface.png     RGBA ground mask over the landscape (R asphalt, G lawn,
                  B paving, A sand/dirt), 4096 x 4096
  layout.json     building lots, parks/woods, water bodies, roads, piers
  layout_plan.png review drawing
Nothing from the original game is placed in Unreal: this only describes
where to build; PCG and the City Sample kits do the building.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage
from shapely.geometry import LineString, Polygon, box, mapping
from shapely.ops import unary_union

GUIDE, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- frames
# guide grid: 0.5 m per pixel (render_guide.py)
GX0, GY0, GMPP = -870.0, -636.0, 0.5
# landscape: 2017 x 2017 vertices, 1 m apart, origin (metres)
LX0, LY0, LN, LRES = -849.0, -1067.0, 2017, 1.0
SN = 4096                                   # surface texture size
SRES = (LN - 1) * LRES / SN                 # metres per surface texel
CORE = (-545.0, -317.0, 863.0, 746.0)       # inside the old War Wall
WALL = (-548.5, -320.0, 866.5, 749.5)
SEA_Z = -1.0                                # bay water level (m)
RING_OFF, ROAD_W, WALK_W = 22.0, 16.0, 5.0

base = np.load(os.path.join(GUIDE, "base_class.npy"))
gz = np.load(os.path.join(GUIDE, "ground_z.npy"))
bld = np.load(os.path.join(GUIDE, "bld.npy"))
veg = np.load(os.path.join(GUIDE, "veg.npy"))
rel = np.load(os.path.join(GUIDE, "rel.npy"))
zt = np.load(os.path.join(GUIDE, "z_top.npy"))[..., 0] - 1000


def g2w(r, c):
    return GX0 + (c + 0.5) * GMPP, GY0 + (r + 0.5) * GMPP


def w2g(x, y):
    return (y - GY0) / GMPP - 0.5, (x - GX0) / GMPP - 0.5


def grid_xy(n, x0, y0, res):
    v = np.arange(n) * res
    return np.meshgrid(x0 + v, y0 + v)          # X[row, col], Y[row, col]


def sample(arr, X, Y, order=0):
    r, c = w2g(X, Y)
    return ndimage.map_coordinates(arr, [r, c], order=order, mode="nearest")


def poly_mask(polys, X, Y, res, x0, y0):
    """rasterise shapely polygons onto a grid"""
    m = np.zeros(X.shape, np.uint8)
    for p in polys if isinstance(polys, list) else [polys]:
        for g in getattr(p, "geoms", [p]):
            if g.is_empty:
                continue
            ext = np.array(g.exterior.coords)
            pts = np.round(np.c_[(ext[:, 0] - x0) / res, (ext[:, 1] - y0) / res]).astype(np.int32)
            cv2.fillPoly(m, [pts], 1)
            for hole in g.interiors:
                h = np.array(hole.coords)
                pts = np.round(np.c_[(h[:, 0] - x0) / res, (h[:, 1] - y0) / res]).astype(np.int32)
                cv2.fillPoly(m, [pts], 0)
    return m.astype(bool)


def clean(poly):
    """largest valid polygon"""
    poly = poly.buffer(0)
    if hasattr(poly, "geoms"):
        poly = max(poly.geoms, key=lambda g: g.area)
    return poly


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def noise(X, Y, scale, seed):
    rng = np.random.default_rng(seed)
    n = rng.standard_normal((64, 64))
    n = ndimage.gaussian_filter(n, 2, mode="wrap")
    n /= n.std()
    return ndimage.map_coordinates(n, [(Y / scale) % 64, (X / scale) % 64], order=1, mode="wrap")


# ---------------------------------------------------------------- design
# shoreline (north is -Y); land lies south of it (larger Y)
COAST = [(-860, -700), (-700, -705), (-550, -690), (-400, -665), (-250, -650),
         (-100, -640), (50, -615), (200, -605), (350, -592), (500, -562),
         (640, -522), (735, -474), (785, -440), (808, -412), (830, -405),
         (852, -414), (876, -440), (940, -500), (1050, -560), (1180, -600)]
cx_, cy_ = np.array(COAST).T


def coast_y(x):
    return np.interp(x, cx_, cy_)


land_poly = Polygon([(LX0, LY0 + 2016 + 50), (LX0 + 2066, LY0 + 2016 + 50)] +
                    [(x, y) for x, y in COAST[::-1]])
x0r, y0r, x1r, y1r = WALL[0] - RING_OFF, WALL[1] - RING_OFF, WALL[2] + RING_OFF, WALL[3] + RING_OFF
ring = LineString([(x0r + 30, y0r), (x1r - 30, y0r), (x1r, y0r + 30), (x1r, y1r - 30),
                   (x1r - 30, y1r), (x0r + 30, y1r), (x0r, y1r - 30), (x0r, y0r + 30),
                   (x0r + 30, y0r)])
# coastal boulevard: 45 m inland from the shore, west edge to the inlet
cb = [(x, coast_y(x) + 45) for x in np.arange(-849, 760, 40)] + [(780, -350)]
coastal = LineString(cb).simplify(3)
roads = {"Atlas_Ring": ring, "Coastal_Boulevard": coastal}
# north district avenues (ring north side -> coast boulevard) and a cross street
for name, x in [("Harbor_Ave_W", -420), ("Harbor_Ave_C", -150), ("Pier_Ave", 120),
                ("Gate_Ave", 320), ("Harbor_Ave_E", 560)]:
    roads[name] = LineString([(x, y0r), (x, coast_y(x) + 45)])
roads["Dock_Street"] = LineString([(-560, -480), (690, -480)])
# gate connectors through the old wall line
roads["North_Gate"] = LineString([(320, -312), (320, y0r)])
roads["South_Gate"] = LineString([(220, 738), (220, y1r)])
roads["West_Gate"] = LineString([(-538, 200), (x0r, 200)])
roads["East_Gate"] = LineString([(856, 580), (x1r, 580)])
road_poly = unary_union([r.buffer(ROAD_W / 2, cap_style=2, join_style=1) for r in roads.values()]) & land_poly
walk_poly = unary_union([r.buffer(ROAD_W / 2 + WALK_W, cap_style=2, join_style=1) for r in roads.values()]) & land_poly
# piers into the bay, like the sketch (three, angled slightly east)
piers = []
for x in (150, 235, 320):
    y = coast_y(x)
    a = math.radians(10)
    dx, dy = math.sin(a) * 110, -math.cos(a) * 110
    piers.append(LineString([(x, y + 5), (x + dx, y + dy)]).buffer(8, cap_style=2))
core_poly = box(*CORE)
north = (land_poly - box(WALL[0] - 60, WALL[1] - 60, WALL[2] + 60, WALL[3] + 60))
north = north & box(LX0, LY0, LX0 + 2016, WALL[1] - RING_OFF - ROAD_W / 2 - WALK_W)
blocks = [b for b in getattr(north - walk_poly, "geoms", [north - walk_poly]) if b.area > 1500]

# ---------------------------------------------------------------- core lots
lots, parks, waters = [], [], []
gr, gc = np.mgrid[0:bld.shape[0], 0:bld.shape[1]]
gwx, gwy = g2w(gr, gc)
gcore = (gwx > CORE[0] + 2) & (gwx < CORE[2] - 2) & (gwy > CORE[1] + 2) & (gwy < CORE[3] - 2)
lab, n = ndimage.label(ndimage.binary_opening(bld & gcore, iterations=3))
for i, sl in enumerate(ndimage.find_objects(lab), 1):
    m = lab[sl] == i
    area = m.sum() * GMPP * GMPP
    if area < 120:
        continue
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, 2.0, True)[:, 0]
    pts = [g2w(sl[0].start + p[1], sl[1].start + p[0]) for p in c]
    if len(pts) < 3:
        continue
    poly = clean(Polygon(pts))
    if not core_poly.contains(poly.centroid):
        continue
    h = float(np.percentile(rel[sl][m], 90))
    rect = poly.minimum_rotated_rectangle
    rc = np.array(rect.exterior.coords)[:4]
    e1, e2 = rc[1] - rc[0], rc[2] - rc[1]
    L, Wd = np.linalg.norm(e1), np.linalg.norm(e2)
    yaw = math.degrees(math.atan2(e1[1], e1[0])) if L >= Wd else math.degrees(math.atan2(e2[1], e2[0]))
    cls = "low" if h < 15 else "mid" if h < 45 else "high" if h < 100 else "tower"
    lots.append({"poly": [list(map(float, p)) for p in poly.exterior.coords],
                 "center": [poly.centroid.x, poly.centroid.y], "size": [max(L, Wd), min(L, Wd)],
                 "yaw": yaw, "height": round(h, 1), "class": cls, "area": round(area),
                 "ground": float(np.median(gz[sl][m])), "kind": "core"})
# civic landmarks stay reserved for hand-picked replacements
for lot in lots:
    x, y = lot["center"]
    if -40 < x < 120 and 60 < y < 140:
        lot["kind"] = "landmark_atlas_statue"
    elif -60 < x < 140 and 170 < y < 270:
        lot["kind"] = "landmark_city_hall"

# ponds
water_pix = base == 5
lab, n = ndimage.label(water_pix)
for i, sl in enumerate(ndimage.find_objects(lab), 1):
    m = lab[sl] == i
    area = m.sum() * GMPP * GMPP
    if area < 400:
        continue
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = cv2.approxPolyDP(max(cnts, key=cv2.contourArea), 1.5, True)[:, 0]
    pts = [g2w(sl[0].start + p[1], sl[1].start + p[0]) for p in c]
    poly = clean(Polygon(pts))
    if not core_poly.contains(poly.centroid):
        continue
    z = float(np.median(zt[sl][m]))
    waters.append({"kind": "pond" if area > 3000 else "pool", "poly": [list(map(float, p)) for p in poly.exterior.coords],
                   "z": z, "area": round(area)})

# parks: grass ground, with the original tree cover as density
grass = (base == 3) & ~bld & gcore
lab, n = ndimage.label(ndimage.binary_closing(grass, iterations=4))
for i, sl in enumerate(ndimage.find_objects(lab), 1):
    m = lab[sl] == i
    area = m.sum() * GMPP * GMPP
    if area < 300:
        continue
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = cv2.approxPolyDP(max(cnts, key=cv2.contourArea), 2.0, True)[:, 0]
    pts = [g2w(sl[0].start + p[1], sl[1].start + p[0]) for p in c]
    poly = clean(Polygon(pts))
    if poly.is_empty or not core_poly.contains(poly.centroid):
        continue
    dens = float(veg[sl][m].mean())
    parks.append({"kind": "core_park", "poly": [list(map(float, p)) for p in poly.exterior.coords],
                  "area": round(area), "tree_cover": round(dens, 3)})

# north district blocks: harbor plaza by the piers, waterfront park in the
# west, the rest city blocks (sketch zone 22 = rebuilding near the piers)
rng = np.random.default_rng(7)
nblocks = []
for b in blocks:
    b = b.buffer(-1.0)
    if b.is_empty:
        continue
    for g in getattr(b, "geoms", [b]):
        c = g.centroid
        near_coast = c.y < coast_y(c.x) + 120
        if c.x > 790:
            kind = "inlet_woods"
        elif c.y < coast_y(c.x) + 45:
            kind = "promenade"
        elif c.x < -430:
            kind = "waterfront_park"
        elif 60 < c.x < 380 and near_coast:
            kind = "harbor_rebuild"
        elif near_coast:
            kind = "waterfront_mid"
        else:
            kind = "district_mid"
        nblocks.append({"kind": kind, "poly": [list(map(float, p)) for p in g.exterior.coords],
                        "area": round(g.area)})
for b in nblocks:
    if b["kind"] in ("waterfront_park", "inlet_woods"):
        parks.append({"kind": b["kind"], "poly": b["poly"], "area": b["area"],
                      "tree_cover": 0.25 if b["kind"] == "waterfront_park" else 0.6})

# ---------------------------------------------------------------- heights
X, Y = grid_xy(LN, LX0, LY0, LRES)
core_m = (X > CORE[0]) & (X < CORE[2]) & (Y > CORE[1]) & (Y < CORE[3])
G = sample(gz, X, Y, order=1)
# ponds: carve 3 m bowls below the original water line
ponds = [w for w in waters if w["kind"] == "pond"]
pond_m = poly_mask([Polygon(w["poly"]) for w in ponds], X, Y, LRES, LX0, LY0)
dpond = ndimage.distance_transform_edt(pond_m) * LRES
pz = np.zeros_like(G)
for w in ponds:
    pm = poly_mask(Polygon(w["poly"]), X, Y, LRES, LX0, LY0)
    pz[pm] = w["z"]
G = np.where(pond_m, pz - 0.4 - 2.6 * smoothstep(0, 12, dpond), G)
# outside the core: continue the edge height, fading to the designed terrain
dcore, (ir, ic) = ndimage.distance_transform_edt(~core_m, return_indices=True)
dcore = dcore * LRES
cw = ndimage.gaussian_filter(core_m.astype(float), 25)
edge = (ndimage.gaussian_filter(np.where(core_m, G, 0.0), 25) / np.maximum(cw, 1e-3))[ir, ic]
land = poly_mask(land_poly, X, Y, LRES, LX0, LY0)
dcoast = ndimage.distance_transform_edt(land) * LRES       # inland distance
dsea = ndimage.distance_transform_edt(~land) * LRES        # offshore distance
# hills on W/E/S beyond the ring boulevard (none on the north waterfront)
ring_m = (X > x0r - 30) & (X < x1r + 30) & (Y > y0r - 30) & (Y < y1r + 30)
dring = ndimage.distance_transform_edt(~ring_m) * LRES
hills = 42 * smoothstep(10, 230, dring) * (0.75 + 0.25 * noise(X, Y, 90, 3))
hills *= smoothstep(20, 160, dcoast) * (Y > y0r - 80)
northland = 0.6 + 0.8 * smoothstep(0, 200, dcoast)
design = np.where(Y < y0r - 30, northland, 0.0) + hills
t = smoothstep(0, 70, dcore)
Hm = np.where(core_m, G, edge * (1 - t) + design * t)
# north of the core the land stays above the bay level
Hm = np.where(land & (Y < CORE[1] - 15), np.maximum(Hm, 0.3), Hm)
# sea: seawall then a shelving bed
Hm = np.where(land, Hm, SEA_Z - 5 - np.minimum(14, dsea * 0.08))
# piers are concrete jetties at quay height
pier_m = poly_mask(piers, X, Y, LRES, LX0, LY0)
Hm[pier_m] = 1.2
hm16 = np.clip(32768 + Hm * 128, 0, 65535).astype(np.uint16)
Image.fromarray(hm16).save(os.path.join(OUT, "heightmap.png"))

# ---------------------------------------------------------------- surface
SX, SY = grid_xy(SN, LX0 + SRES / 2, LY0 + SRES / 2, SRES)
score = (SX > CORE[0]) & (SX < CORE[2]) & (SY > CORE[1]) & (SY < CORE[3])
B = sample(base, SX, SY)
Sbld = sample(bld.astype(np.uint8), SX, SY).astype(bool)
R = score & np.isin(B, [1, 7])
Gl = score & (B == 3) & ~Sbld
Bp = score & ((B == 2) | Sbld)
A = score & np.isin(B, [5, 8])
sland = poly_mask(land_poly, SX, SY, SRES, LX0, LY0)
sroad = poly_mask(road_poly, SX, SY, SRES, LX0, LY0) & ~score
swalk = poly_mask(walk_poly, SX, SY, SRES, LX0, LY0) & ~score & ~sroad
R |= sroad
Bp |= swalk
for b in nblocks:
    m = poly_mask(Polygon(b["poly"]), SX, SY, SRES, LX0, LY0)
    if b["kind"] == "waterfront_park":
        Gl |= m
    elif b["kind"] == "inlet_woods":
        pass
    else:
        Bp |= m
Bp |= poly_mask(piers, SX, SY, SRES, LX0, LY0)
sdc = ndimage.distance_transform_edt(sland) * SRES
A |= ~sland | (sland & (sdc < 6) & (SX < -430))          # beach in the park
Bp |= sland & (sdc < 6) & (SX >= -430) & ~R               # quay elsewhere
surf = np.stack([R, Gl, Bp & ~R, A & ~R & ~Bp], -1).astype(np.uint8) * 255
surf = cv2.GaussianBlur(surf, (3, 3), 0)
Image.fromarray(surf, "RGBA").save(os.path.join(OUT, "surface.png"))

# ---------------------------------------------------------------- json
waters.append({"kind": "bay", "z": SEA_Z, "coast": COAST})
out = {
    "landscape": {"origin_cm": [LX0 * 100, LY0 * 100, 0], "scale": [100, 100, 100],
                  "verts": LN, "height_png": "heightmap.png", "surface_png": "surface.png",
                  "surface_texel_m": SRES},
    "core": CORE, "ring": [x0r, y0r, x1r, y1r],
    "lots": lots, "blocks": nblocks, "parks": parks, "waters": waters,
    "roads": {k: [list(p) for p in v.coords] for k, v in roads.items()},
    "road_width": ROAD_W, "walk_width": WALK_W,
    "piers": [[list(p) for p in p.exterior.coords] for p in piers],
    "hills": "wooded hills outside the ring boulevard on the west, south and east",
}
with open(os.path.join(OUT, "layout.json"), "w") as f:
    json.dump(out, f)
cnt = {}
for lot in lots:
    cnt[lot["class"]] = cnt.get(lot["class"], 0) + 1
print("lots", len(lots), cnt, "blocks", len(nblocks), {k: sum(b["kind"] == k for b in nblocks) for k in set(b["kind"] for b in nblocks)},
      "parks", len(parks), "ponds", len(waters) - 1, "height range", float(Hm.min()), float(Hm.max()))

# ---------------------------------------------------------------- plan
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MP
small = cv2.resize(surf, (1024, 1024), interpolation=cv2.INTER_AREA).astype(float) / 255
img = np.ones((1024, 1024, 3)) * np.array([0.55, 0.62, 0.45])
for ch, col in [(3, (0.82, 0.76, 0.58)), (2, (0.72, 0.72, 0.70)), (1, (0.35, 0.62, 0.30)), (0, (0.18, 0.18, 0.2))]:
    img = img * (1 - small[..., ch:ch + 1]) + small[..., ch:ch + 1] * np.array(col)
sea = cv2.resize((~sland).astype(np.uint8), (1024, 1024)) > 0
img[sea] = (0.2, 0.42, 0.65)
fig, ax = plt.subplots(figsize=(13, 13))
ax.imshow(img, extent=[LX0, LX0 + 2016, LY0 + 2016, LY0])
hs = cv2.resize(Hm.astype(np.float32), (512, 512))
ax.contour(np.linspace(LX0, LX0 + 2016, 512), np.linspace(LY0, LY0 + 2016, 512), hs, levels=[10, 20, 30, 40], colors="#3d5a2a", linewidths=0.6)
colors = {"low": "#e8d36a", "mid": "#e9a24a", "high": "#e0603a", "tower": "#b0203a"}
for lot in lots:
    c = "#7a5cff" if lot["kind"].startswith("landmark") else colors[lot["class"]]
    ax.add_patch(MP(lot["poly"], closed=True, fc=c, ec="k", lw=0.3, alpha=0.9))
kc = {"promenade": "#b9b9b0", "inlet_woods": "#2f6a2c", "harbor_rebuild": "#c98bd6", "waterfront_mid": "#e9a24a", "district_mid": "#e9c27a", "waterfront_park": "#4f9a4a"}
for b in nblocks:
    ax.add_patch(MP(b["poly"], closed=True, fc=kc[b["kind"]], ec="k", lw=0.5, alpha=0.55))
for p in parks:
    if p["kind"] == "core_park":
        ax.add_patch(MP(p["poly"], closed=True, fc="none", ec="#1e6b22", lw=0.8))
for w in ponds:
    ax.add_patch(MP(w["poly"], closed=True, fc="#3f7fd0", ec="none"))
ax.set_xlim(LX0, LX0 + 2016)
ax.set_ylim(LY0 + 2016, LY0)
ax.set_title("Atlas Park Reborn layout: original core + north waterfront and bay, wooded hills around", fontsize=11)
ax.set_xlabel("UE X (m)")
ax.set_ylabel("UE Y (m), north is up")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "layout_plan.png"), dpi=90)

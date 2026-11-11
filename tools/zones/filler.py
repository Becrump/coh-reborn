"""Maps the negative space between zones: what fills each gap.

Run in docs/zones/ after place_all.py:
    python ../../tools/zones/filler.py <paragon_city_zones_map_hires.png>

Lays a grid (CELL m) over the reference map's city area, in world meters
(game x, z; same frame as zone_offsets.json). Each cell is:
  Z  inside a placed zone (playable, nothing to fill)
  W  water on the reference map (ocean, harbor, canals): water plane only
  G  green on the reference map (parks, woods): forest filler
  C  any other land: city filler (HLOD-only PCG blocks, no interiors)
and a 1-cell band of land around each zone is marked B (War Wall buffer:
low buildings so the wall reads, nothing tall right at the wall).

Writes filler/filler_grid.json (grid, legend, areas, wall lengths) and
filler/filler_overlay.jpg.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

CELL = 250.0                     # meters
U_RANGE = (60, 1470)             # display px of the map frame (legend excluded)
V_RANGE = (60, 1250)

Z = json.load(open("zone_offsets.json"))
fit = Z["map_fit"]
k = fit["m_per_display_px"]
a = float(fit["x"].split(" - ")[0])
b = float(fit["z"].split(" + ")[0])
S = fit["display_scale_to_original"]
im = Image.open(sys.argv[1]).convert("RGB")
px = np.asarray(im).astype(int)


def world(u, v):
    return a - k * u, b + k * v


def display(x, z):
    return (a - x) / k, (z - b) / k


x0, z0 = world(U_RANGE[1], V_RANGE[0])      # map west = +x: largest u = min x
x1, z1 = world(U_RANGE[0], V_RANGE[1])
nx = int((x1 - x0) // CELL) + 1
nz = int((z1 - z0) // CELL) + 1
rects = [v["world_rect_m"] for v in Z["zones"].values()]


def classify(x, z):
    for r in rects:
        if r[0] <= x <= r[2] and r[1] <= z <= r[3]:
            return "Z"
    u, v = display(x, z)
    # sample a small patch of the original-resolution map
    cu, cv = int(u * S), int(v * S)
    h = max(2, int(CELL / k * S / 2))
    patch = px[max(cv - h, 0):cv + h, max(cu - h, 0):cu + h].reshape(-1, 3)
    if len(patch) == 0:
        return "C"
    r_, g_, b_ = patch[:, 0], patch[:, 1], patch[:, 2]
    water = ((b_ > r_ + 35) & (b_ > 190)).mean()
    green = ((g_ > r_ + 12) & (g_ >= b_ - 5) & (b_ < r_ + 35)).mean()
    if water > 0.5:
        return "W"
    if green > 0.45:
        return "G"
    return "C"


grid = [[classify(x0 + (i + 0.5) * CELL, z0 + (j + 0.5) * CELL)
         for i in range(nx)] for j in range(nz)]
# War Wall buffer: land cells touching a zone cell
for j in range(nz):
    for i in range(nx):
        if grid[j][i] in "CG" and any(
                0 <= j + dj < nz and 0 <= i + di < nx and grid[j + dj][i + di] == "Z"
                for dj in (-1, 0, 1) for di in (-1, 0, 1)):
            grid[j][i] = "B"
counts = {c: sum(row.count(c) for row in grid) for c in "ZWGCB"}
area = {c: round(n * CELL * CELL / 1e6, 1) for c, n in counts.items()}
walls = {v["name"]: round(2 * ((v["world_rect_m"][2] - v["world_rect_m"][0]) +
                               (v["world_rect_m"][3] - v["world_rect_m"][1])) / 1000, 2)
         for v in Z["zones"].values()}
os.makedirs("filler", exist_ok=True)
json.dump({"cell_m": CELL, "origin_m": [round(x0, 1), round(z0, 1)],
           "size": [nx, nz], "frame": Z["frame"],
           "rows": "row j = z from origin_z + j*cell (map north first); "
                   "column i = x from origin_x + i*cell",
           "legend": {"Z": "placed zone", "W": "water", "G": "forest filler",
                      "C": "city filler (HLOD only)", "B": "War Wall buffer (low city)"},
           "area_km2": area, "war_wall_km": walls,
           "grid": ["".join(r) for r in grid]},
          open("filler/filler_grid.json", "w"))
print("grid %d x %d cells of %d m; km2: %s" % (nx, nz, CELL, area))
print("War Wall perimeter total %.1f km" % sum(walls.values()))
# overlay
col = {"Z": None, "W": (40, 110, 220, 90), "G": (30, 150, 50, 120),
       "C": (120, 120, 120, 110), "B": (230, 140, 20, 140)}
d = ImageDraw.Draw(im, "RGBA")
for j in range(nz):
    for i in range(nx):
        c = col[grid[j][i]]
        if c is None:
            continue
        xa, za = x0 + i * CELL, z0 + j * CELL
        ua, va = display(xa, za)
        ub, vb = display(xa + CELL, za + CELL)
        d.rectangle([min(ua, ub) * S, min(va, vb) * S, max(ua, ub) * S, max(va, vb) * S],
                    fill=c)
for v in Z["zones"].values():
    r = v["world_rect_m"]
    ua, va = display(r[2], r[1])
    ub, vb = display(r[0], r[3])
    d.rectangle([ua * S, va * S, ub * S, vb * S], outline=(200, 0, 0, 255), width=6)
w = int(U_RANGE[1] * S)
im.crop((0, 0, w, im.size[1])).resize((w // 2, im.size[1] // 2)).save(
    "filler/filler_overlay.jpg", quality=85)

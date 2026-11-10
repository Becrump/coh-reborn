"""Monorail line for Atlas Park Reborn, from the original zone's route.

    python tools/reborn/plan_monorail.py <out dir> <original life.json>

Orders the original monorail path points (east wall -> station -> south
wall, 22.8 m up), then extends both ends over the new districts along their
streets to tunnel portals at the map edge: east toward Steel Canyon, south
as the return/next line. Writes monorail.json:
  track:    [[x, y, z]] metres, beam top
  station:  {center, yaw, ground}   (original station spot, snapped to track)
  portals:  [{name, at, yaw}]
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

OUT, LIFE = sys.argv[1], sys.argv[2]
lay = json.load(open(os.path.join(OUT, "layout.json")))
roads = json.load(open(os.path.join(OUT, "roads.json")))
hm = (np.asarray(Image.open(os.path.join(OUT, "heightmap.png"))).astype(float) - 32768) / 128
LX0, LY0 = lay["landscape"]["origin_cm"][0] / 100, lay["landscape"]["origin_cm"][1] / 100


def ground(x, y):
    return float(hm[min(max(int(round(y - LY0)), 0), 2016), min(max(int(round(x - LX0)), 0), 2016)])


pts = [(p["p"][0] / 100, p["p"][1] / 100, p["p"][2] / 100) for p in json.load(open(LIFE))["monorail"]]
rest = pts[:]
cur = max(rest, key=lambda p: p[0])
path = [cur]
rest.remove(cur)
while rest:
    nxt = min(rest, key=lambda p: math.dist(p[:2], cur[:2]))
    path.append(nxt)
    rest.remove(nxt)
    cur = nxt
H = sum(p[2] for p in path) / len(path)       # 22.8 m
# thin to ~10 m spacing
track = [path[0]]
for p in path[1:]:
    if math.dist(p[:2], track[-1][:2]) > 9:
        track.append(p)
# extensions over the new districts, following streets, to the map edge
x0r, y0r, x1r, y1r = lay["ring"]
east_street_y = min((y0r + 60 + 130 * k for k in range(10)), key=lambda y: abs(y - track[0][1]))
south_street_x = min((x0r + 60 + 140 * k for k in range(12)), key=lambda x: abs(x - track[-1][0]))
LX1, LY1 = LX0 + 2016, LY0 + 2016
east = [(track[0][0] + 25, east_street_y, H), (x1r + 10, east_street_y, H), (LX1 - 30, east_street_y, H)]
south = [(south_street_x, track[-1][1] + 25, H), (south_street_x, y1r + 10, H), (south_street_x, LY1 - 30, H)]
full = east[::-1] + track + south


def dense(seq, step=10.0):
    out = []
    for a, b in zip(seq[:-1], seq[1:]):
        n = max(1, int(math.dist(a[:2], b[:2]) // step))
        for k in range(n):
            t = k / n
            out.append(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))
    out.append(seq[-1])
    return out


# the original points are noisy: smooth (moving average), simplify, then
# densify, keeping the two ends fixed
from shapely.geometry import LineString
xy = np.array([p[:2] for p in dense(full, 4.0)])
k = 9
sm = xy.copy()
for i in range(k, len(xy) - k):
    sm[i] = xy[i - k:i + k + 1].mean(0)
line = LineString(sm).simplify(2.5)
full = dense([(x, y, H) for x, y in line.coords], 10.0)
# the original station (trainstation model) stood beside the line south of
# the ponds; the station needs straight track under its whole length, so take
# the straightest stretch of line within 120 m of that spot
STATION_HINT = (190.0, 470.0)
HALF = 48.0                      # half the platform plus a car


def deviation(i):
    a = next((q for q in full[i::-1] if math.dist(q[:2], full[i][:2]) >= HALF), full[0])
    b = next((q for q in full[i:] if math.dist(q[:2], full[i][:2]) >= HALF), full[-1])
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    L = math.hypot(bx - ax, by - ay) or 1.0
    seg = [q for q in full if min(math.dist(q[:2], (ax, ay)), math.dist(q[:2], (bx, by))) <= 2 * HALF]
    return max(abs((bx - ax) * (ay - q[1]) - (ax - q[0]) * (by - ay)) / L
               for q in full if math.dist(q[:2], full[i][:2]) <= HALF), (a, b)


cands = [i for i in range(len(full)) if math.dist(full[i][:2], STATION_HINT) < 120]
si = min(cands, key=lambda i: deviation(i)[0] + 0.01 * math.dist(full[i][:2], STATION_HINT))
dev, (a, b) = deviation(si)
yaw = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
c = full[si]
ux, uy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
# pull the track onto the straight line under the station (and ease off it)
out = []
for p in full:
    along = (p[0] - c[0]) * ux + (p[1] - c[1]) * uy
    d = math.dist(p[:2], c[:2])
    on = (c[0] + ux * along, c[1] + uy * along, p[2])
    w = 1.0 if d <= HALF else max(0.0, 1.0 - (d - HALF) / 25.0)
    w = w * w * (3 - 2 * w)
    out.append((p[0] + (on[0] - p[0]) * w, p[1] + (on[1] - p[1]) * w, p[2]))
full = out
station = {"center": list(c), "yaw": round(yaw, 2), "ground": ground(*c[:2]), "straightness_m": round(dev, 2)}


def end_yaw(p, q):
    return math.degrees(math.atan2(p[1] - q[1], p[0] - q[0]))


portals = [{"name": "Steel Canyon", "at": list(full[0]), "yaw": end_yaw(full[0], full[3])},
           {"name": "South Line", "at": list(full[-1]), "yaw": end_yaw(full[-1], full[-4])}]
L = sum(math.dist(p[:2], q[:2]) for p, q in zip(full, full[1:]))
json.dump({"track": [[round(v, 2) for v in p] for p in full], "height": H, "station": station,
           "portals": portals, "length_m": round(L)}, open(os.path.join(OUT, "monorail.json"), "w"))
print("track points", len(full), "length m", round(L), "height", round(H, 2), "station", station)

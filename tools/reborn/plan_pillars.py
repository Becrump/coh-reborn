"""Monorail support pillars that keep out of the streets.

    python tools/reborn/plan_pillars.py <out dir>

Runs after plan_monorail.py and plan_lots.py. A pillar goes roughly every
30 m along the track, on clear ground: not on a road or junction (curb plus
a margin), not on a building lot, not in water. Where the track runs straight
down a street there is no clear ground under it, so the support stands on the
sidewalk beside the street with an arm out under the beam (a hammerhead).
Adds to monorail.json:
  pillars: [{s, foot: [x, y, ground], beam: [x, y], arm_m}]
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

OUT = sys.argv[1]
mono = json.load(open(os.path.join(OUT, "monorail.json")))
roads = json.load(open(os.path.join(OUT, "roads.json")))
lots = json.load(open(os.path.join(OUT, "lots_plan.json")))
lay = json.load(open(os.path.join(OUT, "layout.json")))
hm = (np.asarray(Image.open(os.path.join(OUT, "heightmap.png"))).astype(float) - 32768) / 128
LX0, LY0 = lay["landscape"]["origin_cm"][0] / 100, lay["landscape"]["origin_cm"][1] / 100

SPACING = 30.0       # usual span
MIN_SPAN, MAX_SPAN = 18.0, 40.0
REACH = 14.0         # longest hammerhead arm
CLEAR = 1.5          # pillar radius plus margin, kept off curbs and lots


def ground(x, y):
    return float(hm[min(max(int(round(y - LY0)), 0), 2016), min(max(int(round(x - LX0)), 0), 2016)])


# road widths as built by build_streets (16 or 18 m between curbs)
blocked = [LineString(r["points"]).buffer((18 if r["width"] >= 17 else 16) / 2 + CLEAR) for r in roads["roads"]]
blocked += [Point(j["center"]).buffer(j["radius"] + CLEAR) for j in roads["junctions"]]
road_area = unary_union(blocked)
lot_area = unary_union([Polygon(l["poly"]).buffer(CLEAR) for l in lots["lots"]])
w = lots["water"]
water = unary_union([Polygon(p) for p in (w if isinstance(w[0][0], list) else [w])]).buffer(CLEAR)
no_go = unary_union([road_area, lot_area, water])

track = LineString([p[:2] for p in mono["track"]])
L = track.length


def clear(x, y):
    return not no_go.contains(Point(x, y))


def frame(s):
    p = track.interpolate(s)
    q = track.interpolate(min(s + 1.0, L))
    o = track.interpolate(max(s - 1.0, 0.0))
    dx, dy = q.x - o.x, q.y - o.y
    n = math.hypot(dx, dy) or 1.0
    return p.x, p.y, dx / n, dy / n


def on_track(lo, hi, target):
    """Clear spot right under the beam between lo and hi, nearest the target."""
    best = None
    s = lo
    while s <= hi:
        x, y, _, _ = frame(s)
        if clear(x, y) and (best is None or abs(s - target) < abs(best - target)):
            best = s
        s += 1.0
    return best


def hammerhead(lo, hi, target):
    """A foot beside the track (shortest arm) for a beam point between lo and hi."""
    best = None
    for ds in sorted(np.arange(lo - target, hi - target + 0.1, 2.0), key=abs):
        s = target + ds
        x, y, ux, uy = frame(s)
        for off in np.arange(2.0, REACH + 0.1, 0.5):
            for side in (1, -1):
                fx, fy = x - uy * off * side, y + ux * off * side
                if clear(fx, fy):
                    if best is None or off < best[0]:
                        best = (off, s, fx, fy, x, y)
                    break
            if best and best[1] == s:
                break
        if best and best[0] <= 6:
            break
    return best


pillars = []
s_last = None
s = 5.0
stuck = 0
while s < L - 5:
    lo = 5.0 if s_last is None else s_last + MIN_SPAN
    hi = min(L - 5, (lo + 12) if s_last is None else s_last + MAX_SPAN)
    target = lo if s_last is None else min(s_last + SPACING, hi)
    got = on_track(lo, hi, target)
    if got is not None:
        x, y, _, _ = frame(got)
        pillars.append({"s": round(got, 1), "foot": [round(x, 2), round(y, 2), round(ground(x, y), 2)],
                        "beam": [round(x, 2), round(y, 2)], "arm_m": 0.0})
        s_last = got
    else:
        hh = hammerhead(lo, hi, target)
        if hh is None:            # nowhere clear: stand in the road and say so
            x, y, _, _ = frame(target)
            stuck += 1
            print("no clear ground near", round(x), round(y))
            hh = (0.0, target, x, y, x, y)
        off, sb, fx, fy, bx, by = hh
        pillars.append({"s": round(sb, 1), "foot": [round(fx, 2), round(fy, 2), round(ground(fx, fy), 2)],
                        "beam": [round(bx, 2), round(by, 2)], "arm_m": round(off, 2)})
        s_last = sb
    s = s_last + SPACING

mono["pillars"] = pillars
json.dump(mono, open(os.path.join(OUT, "monorail.json"), "w"))
arms = [p for p in pillars if p["arm_m"] > 0]
spans = [b["s"] - a["s"] for a, b in zip(pillars, pillars[1:])]
print(len(pillars), "pillars,", len(arms), "hammerheads (longest arm %.1f m)," % max([p["arm_m"] for p in arms] or [0]),
      stuck, "in the road; spans %.0f-%.0f m" % (min(spans), max(spans)))

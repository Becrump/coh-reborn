"""Monorail support pillars on the stage-2 street plan.

    python tools/reborn/plan_pillars.py <out dir>

Runs after build_road_surface.py (corridor.wkt, ground_z.npy) and before
plan_blocks.py. A pillar goes roughly every 30 m along the track and never
stands on a road, curb, sidewalk (plus 1 m) or in water. In order of
preference it stands:
  1. right under the beam on open ground (park strips, verges, plazas),
  2. beside the beam on open ground, with a hammerhead arm (up to 22 m),
  3. in a dedicated gap cut out of a lot (marked "gap": plan_blocks.py
     carves a 4 m pad there and re-cuts the lot).
Adds to monorail.json:
  pillars: [{s, foot: [x, y, ground], beam: [x, y], arm_m, gap}]
Writes pillars_moved.txt: every pillar compared with the previous plan.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from shapely import wkt
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

OUT = sys.argv[1]
mono = json.load(open(os.path.join(OUT, "monorail.json")))
roads = json.load(open(os.path.join(OUT, "roads.json")))
lots = json.load(open(os.path.join(OUT, "lots_plan.json")))
lay = json.load(open(os.path.join(OUT, "layout.json")))
hm = np.load(os.path.join(OUT, "ground_z.npy"))       # the shared ground
LX0, LY0 = lay["landscape"]["origin_cm"][0] / 100, lay["landscape"]["origin_cm"][1] / 100

SPACING = 30.0       # usual span
MIN_SPAN, MAX_SPAN = 18.0, 40.0
REACH = 22.0         # longest hammerhead arm
CLEAR = 1.5          # pillar radius plus margin, kept off curbs and lots


def ground(x, y):
    return float(hm[min(max(int(round(y - LY0)), 0), 2016), min(max(int(round(x - LX0)), 0), 2016)])


# streets: the stage-2 road + curb + sidewalk outline, plus a margin
corridor = wkt.loads(open(os.path.join(OUT, "corridor.wkt")).read())
road_area = corridor.buffer(1.0)
# lots before any pillar gaps (plan_blocks.py output from the previous run
# keeps its carved gaps out of this test through the "pillar_gap" flag)
lot_area = unary_union([Polygon(l["poly"]).buffer(CLEAR) for l in lots["lots"] if not l["kind"].startswith("landmark")])
w = lots["water"]
water = unary_union([Polygon(p) for p in (w if isinstance(w[0][0], list) else [w])]).buffer(CLEAR)
water = unary_union([water] + [Polygon(x["poly"]).buffer(CLEAR) for x in lay["waters"] if x.get("poly") and x["kind"] != "bay"])
no_go = unary_union([road_area, water])
old = {round(p["s"]): p for p in mono.get("pillars", [])}

track = LineString([p[:2] for p in mono["track"]])
L = track.length


def clear(x, y):
    return not no_go.contains(Point(x, y))


def in_lot(x, y):
    return lot_area.contains(Point(x, y))


def frame(s):
    p = track.interpolate(s)
    q = track.interpolate(min(s + 1.0, L))
    o = track.interpolate(max(s - 1.0, 0.0))
    dx, dy = q.x - o.x, q.y - o.y
    n = math.hypot(dx, dy) or 1.0
    return p.x, p.y, dx / n, dy / n


def best_spot(lo, hi, target):
    """the cheapest foot for a beam point between lo and hi: under the beam
    beats an arm, open ground beats a gap cut out of a lot, and nearer the
    usual span beats further"""
    best = None
    for s in np.arange(lo, hi + 0.1, 1.0):
        x, y, ux, uy = frame(s)
        for off in np.arange(0.0, REACH + 0.1, 0.5):
            for side in ((1,) if off == 0 else (1, -1)):
                fx, fy = x - uy * off * side, y + ux * off * side
                if not clear(fx, fy):
                    continue
                lot = in_lot(fx, fy)
                cost = off + (30.0 if lot else 0.0) + 0.3 * abs(s - target)
                if best is None or cost < best[0]:
                    best = (cost, off, s, fx, fy, x, y, lot)
    return best


pillars = []
s_last = None
s = 5.0
stuck = 0
while s < L - 5:
    lo = 5.0 if s_last is None else s_last + MIN_SPAN
    hi = min(L - 5, (lo + 12) if s_last is None else s_last + MAX_SPAN)
    target = lo if s_last is None else min(s_last + SPACING, hi)
    got = best_spot(lo, hi, target)
    if got is None:            # a junction under the track: allow a longer span once
        got = best_spot(lo, min(L - 5, hi + 12), target)
    if got is None:            # nowhere clear: say so, stand under the beam
        x, y, _, _ = frame(target)
        stuck += 1
        print("no clear ground near", round(x), round(y))
        got = (0, 0.0, target, x, y, x, y, False)
    _, off, sb, fx, fy, bx, by, lot = got
    pillars.append({"s": round(float(sb), 1), "foot": [round(fx, 2), round(fy, 2), round(ground(fx, fy), 2)],
                    "beam": [round(bx, 2), round(by, 2)], "arm_m": round(float(off), 2), "gap": bool(lot)})
    s_last = sb
    s = s_last + SPACING

# compare with the previous plan: which pillars moved, and why
base = os.path.join(OUT, "pillars_pre_stage4.json")
if not os.path.exists(base):
    json.dump(mono.get("pillars", []), open(base, "w"))
prev = json.load(open(base))
if os.path.exists(os.path.join(OUT, "pillars_pre_stage4_actors.json")) and not prev:
    prev = [{"foot": [a["x"], a["y"], 0], "beam": [a["x"], a["y"]]} for a in json.load(open(os.path.join(OUT, "pillars_pre_stage4_actors.json")))
            if "Arm" not in a["label"]]
lines = []
for i, p in enumerate(pillars):
    q = min(prev, key=lambda q: math.dist(q["beam"], p["beam"])) if prev else None
    moved = q is None or math.dist(q["foot"][:2], p["foot"][:2]) > 1.0
    was = ""
    if q is not None:
        qf = Point(q["foot"][:2])
        was = "road/sidewalk" if corridor.buffer(1.0).contains(qf) else ("lot" if lot_area.contains(qf) else "clear")
    where = "gap cut from a lot" if p["gap"] else ("under the beam" if p["arm_m"] == 0 else "beside the street, arm %.1f m" % p["arm_m"])
    if moved:
        lines.append("P%02d at track %.0f m: %s -> (%.0f, %.0f) %s%s" % (
            i + 1, p["s"], ("was on %s at (%.0f, %.0f)" % (was, q["foot"][0], q["foot"][1])) if q else "new",
            p["foot"][0], p["foot"][1], where, ""))
mono["pillars"] = pillars
json.dump(mono, open(os.path.join(OUT, "monorail.json"), "w"))
open(os.path.join(OUT, "pillars_moved.txt"), "w").write(chr(10).join(lines) + chr(10))
arms = [p for p in pillars if p["arm_m"] > 0]
spans = [b["s"] - a["s"] for a, b in zip(pillars, pillars[1:])]
print(len(pillars), "pillars,", len(arms), "hammerheads (longest arm %.1f m)," % max([p["arm_m"] for p in arms] or [0]),
      sum(p["gap"] for p in pillars), "gaps cut from lots,", stuck, "with no clear ground; spans %.0f-%.0f m" % (min(spans), max(spans)),
      "; moved", len(lines))

"""Build check: no building may stand in or next to water.

Samples a grid over every spawned building's footprint (its bounds grown by
the plan's water margin) and tests it against the bay (sea side of the
shoreline) and the ponds. Raises (so the run reports FAILED) when any
building touches water; prints the offenders. Writes water_check.json."""
import json
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
plan = json.load(open(os.path.join(OUT, "lots_plan.json")))
lay = layout()
margin = plan.get("water_margin_m", 12.0)
polys = [plan["water"]] + [w["poly"] for w in lay["waters"] if w["kind"] == "pond"]


def inside(x, y, poly):
    c = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi:
            c = not c
        j = i
    return c


bad, n = [], 0
for a in actors.get_all_level_actors():
    if "BPP_" not in a.get_class().get_name():
        continue
    n += 1
    o, e = a.get_actor_bounds(False, True)
    ex, ey = e.x / 100 + margin, e.y / 100 + margin
    cx, cy = o.x / 100, o.y / 100
    hit = False
    for i in range(9):
        for j in range(9):
            x = cx - ex + 2 * ex * i / 8
            y = cy - ey + 2 * ey * j / 8
            if any(inside(x, y, p) for p in polys):
                hit = True
                break
        if hit:
            break
    if hit:
        bad.append({"actor": a.get_actor_label(), "center_m": [round(cx), round(cy)]})
with open(os.path.join(OUT, "water_check.json"), "w") as f:
    json.dump({"buildings": n, "margin_m": margin, "in_or_near_water": bad}, f, indent=1)
print("water check: %d buildings, %d touch water (margin %.0f m)" % (n, len(bad), margin))
for b in bad:
    print("  ", b)
if bad:
    raise RuntimeError("buildings in or next to water: %d" % len(bad))

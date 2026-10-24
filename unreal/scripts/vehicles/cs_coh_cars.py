"""Offline: the original CoH parked cars of Atlas Park, as centres and footprints.

python -I cs_coh_cars.py <atlas_park_placements.json>   (out\\atlas_park_v3)
Writes coh_cars_in_map.json next to this script: kind, CoH location l,
yaw, centre c (the CoH mesh origin is not the middle of the car) and half
extents (x = half width, y = half length; CoH cars point down -Y).
"""
import json
import math
import os
import sys

# local bounds of the six _Prkd_ meshes (cm): x min/max, y min/max, z max
BOUNDS = {
    "_Prkd_Compact1__dmgcarLod1": (-98, 97, -170, 174, 132),
    "_Prkd_Lux1_2__dmgcarLod5": (-126, 126, -290, 288, 138),
    "_Prkd_Lux2_1__dmgcarLod1": (-140, 140, -348, 265, 143),
    "_Prkd_Sport1_1__dmgcarLod1": (-122, 122, -261, 269, 135),
    "_Prkd_Sport2_1__dmgcarLod1": (-108, 108, -248, 260, 124),
    "_Prkd_Truck_1__dmgtruckLod1a": (-169, 169, -323, 300, 335),
}

rows = []
for p in json.load(open(sys.argv[1])):
    b = BOUNDS.get(p["m"])
    if not b:
        continue
    yaw = p["r"][1]
    cx, cy = (b[0] + b[1]) / 2.0, (b[2] + b[3]) / 2.0
    s, c = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    x, y, z = p["l"]
    rows.append(dict(kind=p["m"], l=[x, y, z], yaw=yaw,
                     c=[x + cx * c - cy * s, y + cx * s + cy * c],
                     half=[(b[1] - b[0]) / 2.0, (b[3] - b[2]) / 2.0], height=b[4]))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coh_cars_in_map.json")
json.dump(rows, open(out, "w"), indent=0)
print(len(rows), "cars ->", out)

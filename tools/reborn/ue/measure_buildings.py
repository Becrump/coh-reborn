"""Measure every packed City Sample building (BPP_*) for the PCG building table.

Spawns each one far below the map, records its footprint and height relative
to the actor origin, then removes it. Writes buildings_catalog.json."""
import json
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
paths = []
for d in ["/Game/CitySampleBuildings/Building/Library/Kit_Ref_Bldg/LevelInstance",
          "/Game/CitySampleBuildings/Building/Library/Kit_Hero_Bldg/LevelInstance"]:
    for a in el.list_assets(d, recursive=False):
        if a.split("/")[-1].startswith("BPP_"):
            paths.append(a.split(".")[0])
cat = []
for p in sorted(paths):
    cls = el.load_blueprint_class(p)
    if not cls:
        print("no class", p)
        continue
    a = actors.spawn_actor_from_class(cls, unreal.Vector(0, 0, 0))
    o, e = a.get_actor_bounds(False, True)
    n = len(a.get_components_by_class(unreal.PrimitiveComponent))
    rel = [o.x, o.y, o.z]
    cat.append({"name": p.split("/")[-1], "path": p, "center": rel, "extent": [e.x, e.y, e.z],
                "size_m": [round(2 * e.x / 100, 1), round(2 * e.y / 100, 1)], "height_m": round((rel[2] + e.z) / 100, 1),
                "base_m": round((rel[2] - e.z) / 100, 1), "components": n})
    actors.destroy_actor(a)
    print(cat[-1]["name"], cat[-1]["size_m"], cat[-1]["height_m"], "base", cat[-1]["base_m"], "off", round(rel[0] / 100, 1), round(rel[1] / 100, 1), n)
with open(os.path.join(OUT, "buildings_catalog.json"), "w") as f:
    json.dump(cat, f, indent=1)

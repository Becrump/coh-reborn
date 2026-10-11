"""Step 3: bay and ponds with the Water plugin.

The bay is a WaterBodyOcean in its own water zone, which stops north of the
old zone; the zone's far-distance ocean mesh is switched off because it
would flood the low parts of the old zone (they lie below the bay level). Each original pond becomes a WaterBodyLake at its original water
level, in a second small zone around the park."""
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
lay = layout()
for a in actors.get_all_level_actors():
    if a.get_actor_label().startswith("Reborn_Water"):
        actors.destroy_actor(a)


def zone(label, cx, cy, ex, ey):
    """ex, ey: full width/height in metres"""
    z = actors.spawn_actor_from_class(unreal.WaterZone, unreal.Vector(cx * 100, cy * 100, 0))
    z.set_actor_label(label)
    z.set_folder_path("AtlasReborn/Water")
    z.set_editor_property("zone_extent", unreal.Vector2D(ex * 100, ey * 100))
    return z


def body(cls, label, pts, z, wz, closed=True):
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    a = actors.spawn_actor_from_class(cls, unreal.Vector(cx * 100, cy * 100, z * 100))
    a.set_actor_label(label)
    a.set_folder_path("AtlasReborn/Water")
    s = a.get_editor_property("spline_comp")
    s.clear_spline_points(False)
    for x, y in pts:
        s.add_spline_point(unreal.Vector(x * 100, y * 100, z * 100), unreal.SplineCoordinateSpace.WORLD, False)
    s.set_closed_loop(closed, True)
    c = a.get_editor_property("water_body_component")
    for prop, val in [("affects_landscape", False)]:
        try:
            c.set_editor_property(prop, val)
        except Exception as e:
            print("skip", prop, e)
    try:
        c.set_editor_property("water_zone_override", wz)
    except Exception as e:
        print("zone override", e)
    return a


sea = [w for w in lay["waters"] if w["kind"] == "bay"][0]
zn = zone("Reborn_Water_BayZone", 150, -2200, 7000, 3600)
zn.get_editor_property("water_mesh").set_editor_property("far_distance_mesh_extent", 0.0)
coast = sea["coast"]
loop = [(x, y - 4) for x, y in coast] + [(1180, 1000), (-860, 1000)]
ocean = body(unreal.WaterBodyOcean, "Reborn_Water_Bay", loop, sea["z"], zn)
oc = ocean.get_editor_property("water_body_component")
oc.set_editor_property("ocean_extents", unreal.Vector2D(700000, 360000))
ponds = [w for w in lay["waters"] if w["kind"] == "pond"]
xs = [p[0] for w in ponds for p in w["poly"]]
ys = [p[1] for w in ponds for p in w["poly"]]
zl = zone("Reborn_Water_ParkZone", (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
          max(xs) - min(xs) + 80, max(ys) - min(ys) + 80)
zl.get_editor_property("water_mesh").set_editor_property("far_distance_mesh_extent", 0.0)
for i, w in enumerate(ponds):
    pts = w["poly"][:-1]
    lk = body(unreal.WaterBodyLake, "Reborn_Water_Pond_%d" % i, pts, w["z"], zl)
    lk.get_editor_property("water_body_component").set_editor_property("always_generate_water_mesh_tiles", True)
print("water: bay +", len(ponds), "ponds")

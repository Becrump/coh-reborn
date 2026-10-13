"""Step 8: ZoneGraph lanes for traffic (Mass Traffic) and civilians (Mass Crowd).

From roads.json:
  * every road piece -> a spline ZoneShape with lane profile Reborn_Road4
    (2 + 2 lanes, tag Vehicles), along the road centre;
  * both sidewalks -> spline ZoneShapes with Reborn_Sidewalk (tag
    Pedestrians), 2.5 m outside the curb;
  * every junction -> a polygon ZoneShape joining the road ends (cars can
    turn), and a second polygon joining the sidewalk ends (people cross).
The lane profiles live in Config/DefaultPlugins.ini (ZoneGraphSettings).
ZoneGraph rebuilds its lane data in the editor when shapes change."""
import json
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
data = json.load(open(os.path.join(OUT, "roads.json")))
ROAD = unreal.ZoneLaneProfileRef()
ROAD.set_editor_property("name", "Reborn_Road4")
ROAD.set_editor_property("id", unreal.Guid.from_string("A1B2C3D4-0000-4000-8000-000000000001") if hasattr(unreal.Guid, "from_string")
                         else unreal.GuidLibrary.parse_string_to_guid("A1B2C3D4-0000-4000-8000-000000000001")[0])
WALK = unreal.ZoneLaneProfileRef()
WALK.set_editor_property("name", "Reborn_Sidewalk")
WALK.set_editor_property("id", unreal.GuidLibrary.parse_string_to_guid("A1B2C3D4-0000-4000-8000-000000000002")[0])
FOLDER = "AtlasReborn/Lanes"
POLY_FLIP = float(os.environ.get("REBORN_POLY_FLIP", "180"))
for a in actors.get_all_level_actors():
    if str(a.get_folder_path()).startswith(FOLDER):
        actors.destroy_actor(a)


def offset_line(pts, d):
    """pts [[x,y,z]...] shifted d metres to the right of travel"""
    out = []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1.0
        # UE is left-handed (Y down on the map): right of travel is (-dy, dx)
        out.append([p[0] - dy / n * d, p[1] + dx / n * d, p[2]])
    return out


def shape(label, pts, profile, polygon=False, center=None, rots=None, point_profiles=None):
    o = center or pts[0]
    a = actors.spawn_actor_from_class(unreal.ZoneShape, unreal.Vector(o[0] * 100, o[1] * 100, o[2] * 100 + 20))
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    c = a.get_editor_property("shape_component")
    c.set_editor_property("lane_profile", profile)
    c.set_shape_type(unreal.FZoneShapeType.POLYGON if polygon else unreal.FZoneShapeType.SPLINE)
    zp = []
    for i, p in enumerate(pts):
        q = unreal.ZoneShapePoint()
        q.set_editor_property("position", unreal.Vector((p[0] - o[0]) * 100, (p[1] - o[1]) * 100, (p[2] - o[2]) * 100))
        if polygon:
            q.set_editor_property("type", unreal.FZoneShapePointType.LANE_PROFILE)
            q.set_editor_property("rotation", unreal.Rotator(yaw=rots[i] + POLY_FLIP))
        else:
            q.set_editor_property("type", unreal.FZoneShapePointType.AUTO_BEZIER)
        zp.append(q)
    c.set_editor_property("points", zp)
    return a


roads = data["roads"]
n_road = n_walk = 0
for r in roads:
    pts = r["dense"]
    if len(pts) < 2:
        continue
    # one profile everywhere (junction polygons can't mix profiles from Python):
    # Reborn_Road4 has 3 m lanes, so it fits the 12 m streets as well as the avenues
    shape("Lane_Road_%03d" % r["id"], pts, ROAD)
    n_road += 1
    # stage 2 sidewalks: 0.3 m curb + 4 m walk, 15 cm up; walk down the middle
    half = r["width"] / 2 + 2.3
    pts = [[x, y, z + 0.15] for x, y, z in pts]
    for side, d in (("R", half), ("L", -half)):
        shape("Lane_Walk_%03d_%s" % (r["id"], side), offset_line(pts, d), WALK)
        n_walk += 1

# junction polygons: one point per connecting road end, facing out of the
# junction along the road
n_j = 0
for j in data["junctions"]:
    cx, cy = j["center"]
    rp, rr, wp, wr, rprof = [], [], [], [], []
    for rid in j["roads"]:
        r = roads[rid]
        pts = r["dense"]
        if len(pts) < 2:
            continue
        start = math.dist(pts[0][:2], (cx, cy)) < math.dist(pts[-1][:2], (cx, cy))
        e, nxt = (pts[0], pts[1]) if start else (pts[-1], pts[-2])
        yaw = math.degrees(math.atan2(nxt[1] - e[1], nxt[0] - e[0]))
        rp.append(e)
        rr.append(yaw)
        rprof.append(0 if r.get("lanes", 4) >= 4 else 1)
        half = r["width"] / 2 + 2.3
        for d in (half, -half):
            o = offset_line([e, nxt], d)[0]
            wp.append(o)
            wr.append(yaw)
    if len(rp) < 2:
        continue
    # polygon points go round the junction in order
    order = sorted(range(len(rp)), key=lambda k: math.atan2(rp[k][1] - cy, rp[k][0] - cx))
    z = sum(p[2] for p in rp) / len(rp)
    shape("Lane_Junction_%03d" % j["id"], [rp[k] for k in order], ROAD, True, [cx, cy, z], [rr[k] for k in order],
          None)
    worder = sorted(range(len(wp)), key=lambda k: math.atan2(wp[k][1] - cy, wp[k][0] - cx))
    shape("Lane_Crossing_%03d" % j["id"], [wp[k] for k in worder], WALK, True, [cx, cy, z], [wr[k] for k in worder])
    n_j += 1
print("zone shapes: roads", n_road, "sidewalks", n_walk, "junctions", n_j)

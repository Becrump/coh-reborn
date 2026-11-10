"""Put the working Reborn monorail into the Nanite dressing map.

The dressing map (/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite) is the
original Atlas Park rebuilt from its own tiles, so it already has the
original guideway, pillars and station. The track is the original zone's
monorail route (the CoHLife json "monorail" points, same world frame),
corner-rounded (Chaikin, 2 passes), which sits on the original beam; Reborn's
thinned spline cut the corners off the beam. Both ends are trimmed back to
where the line is clear of the War Wall (the train turns round there). No new
beam, pillars or station are placed.

Placed in the RebornMonorail folder (rerunning replaces them):
  Monorail_Track    spline (BP_RebornZone, like Reborn)
  Monorail_Train    ARebornMonorail: one stop at the original station,
                    destinations (round trip = this map), ride level
  Arrivals          PlayerStarts tagged MonorailArrival inside the train at
                    the station
The CoHLife decorative monorail is switched off (it would run a second train
on the same beam). Run with the Nanite map open; saves the map."""
import json
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import OUT, ROOT, el, actors, world, find, mark_spline_edited  # noqa

MAP = "/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite"
RIDE = ROOT + "/Transit/L_MonorailRide"
FOLDER = "RebornMonorail"

assert world().get_path_name().startswith(MAP), "open %s first (current: %s)" % (MAP, world().get_path_name())
assert unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world() is None, "stop Play-In-Editor first"
mono = json.load(open(os.path.join(OUT, "monorail.json")))   # station stop (original spot)
for a in actors.get_all_level_actors():
    if str(a.get_folder_path()).startswith(FOLDER):
        actors.destroy_actor(a)
life = find(cls=unreal.CoHLifeManager)[0]
pts = [tuple(p["p"]) for p in json.load(open(life.get_editor_property("life_json").file_path))["monorail"]]


def route(pts):
    """order the route points end to end (east wall first), drop doubles,
    round the corners, resample every 5 m (cm in, metres out)"""
    rest = pts[:]
    cur = max(rest, key=lambda p: p[0])
    path = [cur]
    rest.remove(cur)
    while rest:
        cur = min(rest, key=lambda p: math.dist(p[:2], cur[:2]))
        path.append(cur)
        rest.remove(cur)
    P = [path[0]]
    for p in path[1:]:
        if math.dist(p[:2], P[-1][:2]) > 150:
            P.append(p)
    for _ in range(2):
        Q = [P[0]]
        for a, b in zip(P, P[1:]):
            Q += [tuple(a[i] * .75 + b[i] * .25 for i in range(3)), tuple(a[i] * .25 + b[i] * .75 for i in range(3))]
        P = Q + [P[-1]]
    out = []
    for a, b in zip(P, P[1:]):
        n = max(1, int(math.dist(a[:2], b[:2]) // 500))
        out += [tuple((a[i] + (b[i] - a[i]) * k / n) / 100 for i in range(3)) for k in range(n)]
    return out + [tuple(v / 100 for v in P[-1])]


def clear(a, b):
    """nothing in the car's space between two track points (a rider-sized
    capsule at four heights, and the car body)"""
    A = unreal.Vector(a[0] * 100, a[1] * 100, a[2] * 100)
    B = unreal.Vector(b[0] * 100, b[1] * 100, b[2] * 100)
    up = lambda v, dz: unreal.Vector(v.x, v.y, v.z + dz)
    vis = unreal.TraceTypeQuery.ECC_VISIBILITY
    for dz in (130, 200, 280, 360):
        r = unreal.SystemLibrary.capsule_trace_single(world(), up(A, dz), up(B, dz), 45.0, 60.0, vis, True, [],
                                                      unreal.DrawDebugTrace.NONE, True)
        if r and r.to_tuple()[0]:
            return False
    for dz in (150, 280, 420):
        r = unreal.SystemLibrary.sphere_trace_single(world(), up(A, dz), up(B, dz), 130.0, vis, True, [],
                                                     unreal.DrawDebugTrace.NONE, True)
        if r and r.to_tuple()[0]:
            return False
    return True


full = route(pts)


def wall_end(seq):
    """first index from this end after which 60 m of line is clear (the War Wall
    and its tunnel are behind it), plus 5 m"""
    for i in range(len(seq) - 13):
        if all(clear(seq[j], seq[j + 1]) for j in range(i, i + 12)):
            return min(i + 1, len(seq) - 1)
    return 0


i0 = wall_end(full)
i1 = len(full) - 1 - wall_end(full[::-1])
track = full[i0:i1 + 1]

# ------------------------------------------------------------ track spline
zone_cls = el.load_blueprint_class(ROOT + "/Layout/BP_RebornZone")
x0, y0, z0 = track[0]
tr = actors.spawn_actor_from_class(zone_cls, unreal.Vector(x0 * 100, y0 * 100, z0 * 100))
tr.set_actor_label("Monorail_Track")
tr.set_folder_path(FOLDER)
tr.set_editor_property("tags", ["RebornMonorail"])
s = tr.get_component_by_class(unreal.SplineComponent)
s.clear_spline_points(False)
for x, y, z in track:
    s.add_spline_point(unreal.Vector(x * 100, y * 100, z * 100), unreal.SplineCoordinateSpace.WORLD, False)
s.set_closed_loop(False, True)
mark_spline_edited(s)

# ------------------------------------------------------------ train
D = ROOT + "/Monorail/"
t = actors.spawn_actor_from_class(unreal.RebornMonorail, unreal.Vector(0, 0, 0))
t.set_actor_label("Monorail_Train")
t.set_folder_path(FOLDER)
t.set_editor_property("track", tr)
t.set_editor_property("car_mesh", el.load_asset(D + "SM_Mono_Car"))
t.set_editor_property("nose_mesh", el.load_asset(D + "SM_Mono_CarNose"))
t.set_editor_property("door_mesh", el.load_asset(D + "SM_Mono_Door"))
st = mono["station"]
cx, cy, cz = st["center"]
stop = unreal.RebornMonorailStop()
stop.set_editor_property("name", "Atlas Park")
stop.set_editor_property("location", unreal.Vector(cx * 100, cy * 100, cz * 100))
t.set_editor_property("stops", [stop])
dest = []
for name, path in [("Atlas Park (round trip)", MAP), ("Steel Canyon", None), ("King's Row", None),
                   ("Skyway City", None), ("Galaxy City", None)]:
    d = unreal.RebornDestination()
    d.set_editor_property("name", name)
    if path:
        d.set_editor_property("map", el.load_asset(path))
    dest.append(d)
t.set_editor_property("destinations", dest)
t.set_editor_property("ride_map", el.load_asset(RIDE))
actors.set_actor_transform(t, t.get_actor_transform())   # reruns construction: cars appear

# ------------------------------------------------------------ arrivals (as build_ride.py)
yaw = math.radians(st["yaw"])
fx, fy = math.cos(yaw), math.sin(yaw)
n = 0
for car in (-15.5, 0.0, 15.5):
    for along in (-4.5, 0.0, 4.5):
        x, y = cx + fx * (car + along), cy + fy * (car + along)
        ps = actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(x * 100, y * 100, cz * 100 + 200))
        ps.set_actor_rotation(unreal.Rotator(pitch=0, yaw=st["yaw"] + 90, roll=0), False)
        ps.set_editor_property("player_start_tag", "MonorailArrival")
        ps.set_folder_path(FOLDER + "/Arrivals")
        n += 1

# ------------------------------------------------------------ CoHLife: no second (decorative) train
for life in find(cls=unreal.CoHLifeManager):
    life.set_editor_property("monorail_mesh", None)

unreal.EditorLoadingAndSavingUtils.save_map(world(), MAP)
print("monorail ported: track points %d (of %d, trimmed %d / %d at the walls), %.0f m; arrivals %d" % (len(track), len(full), i0, len(full) - 1 - i1, tr.get_component_by_class(unreal.SplineComponent).get_spline_length() / 100, n))

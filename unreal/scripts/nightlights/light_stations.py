"""Night lights for the monorail stations: ACoHStationLamp downlights under the station roof.

The original stations have no lamp material and were lit only by baked light, so at night they are dark.
This places a grid of ACoHStationLamp actors (warm downlight cones, shadows off, on only at night via
MPC_CoH.Night) under the roof of the station in the open level.

Where: the zone's monorail arrival point (docs/zones/stations.json, zone-local game metres) converted to this
level's Unreal frame (x, -z, y in cm, as the converter does), plus NL_OFFSET_CM for a level placed at an offset.
Around it, a 6 m grid within NL_RADIUS_M is tested with line traces: a point gets a lamp when the floor below
and a roof 2.5-12 m above it are found (so the grid fits the roof footprint by itself). Lamps hang 30 cm under
the roof. Rerunning replaces the lamps (folder NightLights/Station).

Env:
  NL_ZONE        zone id in stations.json (default city_01_01 = Atlas Park)
  NL_OFFSET_CM   "x,y,z" added to the converted point (default 0,0,0)
  NL_CENTER_CM   "x,y,z" use this point instead of stations.json
  NL_RADIUS_M    search radius (default 30)
  NL_SPACING_M   grid spacing (default 6)
  NL_DRY=1       report only
  NL_SAVE=1      save the level's changed actor packages (default 0: leave dirty for a look first)

Run once in the editor via an exec wrapper (never re-send after a lost connection).
"""
import json
import math
import os

import unreal

REPO = os.environ.get("NL_REPO", r"C:/Users/rtcru/ClaudeProjects/coh-reborn")
ZONE = os.environ.get("NL_ZONE", "city_01_01")
RADIUS = float(os.environ.get("NL_RADIUS_M", "30")) * 100
SPACING = float(os.environ.get("NL_SPACING_M", "6")) * 100
DRY = os.environ.get("NL_DRY") == "1"
FOLDER = "NightLights/Station"
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def vec(env, default):
    v = os.environ.get(env)
    return unreal.Vector(*[float(x) for x in v.split(",")]) if v else default


if os.environ.get("NL_CENTER_CM"):
    center = vec("NL_CENTER_CM", None)
else:
    st = json.load(open(os.path.join(REPO, "docs", "zones", "stations.json")))[ZONE]
    gx, gy, gz = st["local_m"]
    center = unreal.Vector(gx * 100, -gz * 100, gy * 100) + vec("NL_OFFSET_CM", unreal.Vector(0, 0, 0))
print("station centre", center)


def trace(a, b):
    hit = unreal.SystemLibrary.line_trace_single(world, a, b, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [],
                                                 unreal.DrawDebugTrace.NONE, True)
    if not hit:
        return None
    t = hit.to_tuple()
    return t[4] if len(t) > 4 else None   # impact point


spots = []
n = int(RADIUS // SPACING)
for i in range(-n, n + 1):
    for j in range(-n, n + 1):
        x, y = center.x + i * SPACING, center.y + j * SPACING
        if math.hypot(x - center.x, y - center.y) > RADIUS:
            continue
        top = unreal.Vector(x, y, center.z + 400)
        floor = trace(top, unreal.Vector(x, y, center.z - 1500))
        if floor is None:
            continue
        roof = trace(unreal.Vector(x, y, floor.z + 50), unreal.Vector(x, y, floor.z + 1200))
        if roof is None or roof.z - floor.z < 250:
            continue
        spots.append((unreal.Vector(x, y, roof.z - 30), roof.z - floor.z))
print("lamp spots", len(spots))

if not DRY:
    for a in asub.get_all_level_actors():
        if str(a.get_folder_path()) == FOLDER:
            asub.destroy_actor(a)
    mpc = unreal.load_asset("/Game/CoH/Materials/MPC_CoH")
    for k, (p, h) in enumerate(spots):
        a = asub.spawn_actor_from_class(unreal.CoHStationLamp, p)
        a.set_actor_label("StationLamp_%02d" % k)
        a.set_folder_path(FOLDER)
        a.set_editor_property("radius", h + 200)
        a.set_editor_property("intensity", 4000.0)
        if mpc:
            a.set_editor_property("only_at_night", True)
            a.set_editor_property("night_collection", mpc)
    if os.environ.get("NL_SAVE") == "1":
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(False, True)
        print("saved")
print("done", "(dry)" if DRY else "")

"""One-world steps 2 and 3, headless (docs/zones/city_playable.md). Never loads the zone Level Instances.

    UnrealEditor-Cmd COHREBORN.uproject -run=pythonscript -script=".../world_step23.py" -unattended -nullrhi
Env: CITY_REPO (repo root), CITY_OUT (results json), CITY_PLAZA ("x,y,z" cm of Atlas's PlayerStart_AtlasPlaza).

Step 2 (base): every 250 m cell of docs/zones/filler/filler_grid.json that no zone covers (zone_offsets.json
world rects + Atlas's rebuilt rect) gets a flat tile: water cells ("W") a water plane at -2 m, all others a ground
plane at -0.3 m, grouped into one CoHInstances actor per 1 km block and material (runtime grid "Ground").
Corridors: for every gate pair whose two zones name each other and now stand more than 60 m apart, a 24 m wide
road strip at ground level joins the two gates. Zones keep their own War Walls (the originals ring each zone);
no new walls are added here.
Step 3 (start): one PlayerStart at Atlas Park's plaza (the old Galaxy City start, now in a gap, is removed).
Only L_ParagonCity's packages are saved. Re-running replaces the actors this script made (labels CityBase_*,
CityRoad_*, PlayerStart_AtlasPlaza_World).
"""
import collections
import json
import math
import os
import time

import unreal

REPO = os.environ["CITY_REPO"]
OUT = os.environ.get("CITY_OUT", os.path.join(REPO, "docs", "zones", "city_playable.json"))
WORLD = "/Game/Zones/L_ParagonCity"
PLANE = "/Engine/BasicShapes/Plane"     # 100 x 100 cm
ROAD_W_CM = 2400.0
KEYS = {"PEREZ": "hazard_01_01", "STEEL": "city_02_01", "GALAXY": "city_01_03", "KINGS": "city_01_02",
        "SKYWAY": "city_02_02", "ATLAS": "city_01_01", "TALOS": "city_03_01", "INDEPENDENCE": "city_03_02",
        "BRICKSTOWN": "city_04_02", "FOUNDERS": "city_04_01", "EDEN": "hazard_04_01", "CREY": "hazard_03_02",
        "BOOMTOWN": "hazard_02_01", "HOLLOW": "hazard_01_02", "ASTORIA": "hazard_03_01", "FAULTLINE": "city_02_05",
        "OVERBROOK": "city_02_05", "PEREGRINE": "city_05_01", "CROATOA": "city_03_03", "CRASH": "trial_05_01"}

asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()
res = {}


def log(msg):
    print("[city] " + msg)
    unreal.log("[city] " + msg)


def ue(x_m, z_m, h_cm):
    """game metres (x, z) -> Unreal cm (place_world: X = x, Y = -z)"""
    return unreal.Vector(x_m * 100.0, -z_m * 100.0, h_cm)


def pick_material(words, avoid=("glow", "add", "night", "glass", "window")):
    for path in ("/Game/atlas_park/Materials", "/Game/Zones/Library/Materials", "/Game"):
        for d in reg.get_assets_by_path(path, True):
            n = str(d.asset_name).lower()
            if str(d.asset_class_path.asset_name) in ("MaterialInstanceConstant", "Material") and \
                    any(w in n for w in words) and not any(a in n for a in avoid):
                return "%s.%s" % (d.package_name, d.asset_name)
    return None


def clear_ours():
    gone = 0
    for a in asub.get_all_level_actors():
        lab = a.get_actor_label()
        if lab.startswith(("CityBase_", "CityRoad_", "PlayerStart_AtlasPlaza_World")) or lab == "PlayerStart_GalaxyCity":
            asub.destroy_actor(a)
            gone += 1
    return gone


def base_tiles(zones):
    g = json.load(open(os.path.join(REPO, "docs", "zones", "filler", "filler_grid.json")))
    cell = g["cell_m"]
    ox, oz = g["origin_m"]
    rects = [v["world_rect_m"] for k, v in zones.items() if k != "city_01_01"]
    atlas = json.load(open(os.path.join(REPO, "docs", "zones", "zone_offsets.json"))).get("atlas_rebuilt_rect_m")
    if atlas:
        rects.append(atlas)
    groups = collections.defaultdict(list)
    counts = collections.Counter()
    for j, row in enumerate(g["grid"]):
        for i, ch in enumerate(row):
            cx, cz = ox + (i + 0.5) * cell, oz + (j + 0.5) * cell
            if any(r[0] <= cx <= r[2] and r[1] <= cz <= r[3] for r in rects):
                continue
            kind = "water" if ch == "W" else "ground"
            counts[kind] += 1
            block = (int((cx - ox) // 1000), int((cz - oz) // 1000))
            t = unreal.Transform(ue(cx, cz, -200.0 if kind == "water" else -30.0), unreal.Rotator(0, 0, 0),
                                 unreal.Vector(cell, cell, 1.0))
            groups[(kind, block)].append(t)
    return groups, counts


def spawn_group(label, mesh, mat, ts, grid):
    a = asub.spawn_actor_from_class(unreal.CoHInstances, unreal.Vector(0, 0, 0))
    a.set_instances(mesh, ts)
    a.set_actor_label(label)
    a.set_folder_path("City/Base")
    if mat:
        ic = a.get_component_by_class(unreal.InstancedStaticMeshComponent)
        ic.set_material(0, unreal.load_asset(mat))
    try:
        a.set_editor_property("runtime_grid", grid)
    except Exception:
        pass
    return a


def corridors(zones):
    def target(name):
        n = name.upper()
        for k, z in KEYS.items():
            if k in n:
                return z
        return None
    pairs = []
    seen = set()
    for za, va in zones.items():
        for ga, pa in va.get("gates_world_m", {}).items():
            zb = target(ga)
            if not zb or zb == za or zb not in zones:
                continue
            best = None
            for gb, pb in zones[zb].get("gates_world_m", {}).items():
                if target(gb) == za:
                    d = math.dist(pa, pb)
                    if best is None or d < best[0]:
                        best = (d, gb, pb)
            if best and best[0] > 60 and (zb, za) not in seen:
                seen.add((za, zb))
                pairs.append((va["name"], ga, pa, zones[zb]["name"], best[1], best[2], round(best[0])))
    return pairs


def main():
    t0 = time.time()
    unreal.EditorLoadingAndSavingUtils.load_map(WORLD)
    zones = json.load(open(os.path.join(REPO, "docs", "zones", "zone_offsets.json")))["zones"]
    # step 1 fix: move the shifted zones' Level Instances (place_world's moves were not saved: no modify())
    moved = {"hazard_01_01", "city_01_03", "city_02_02", "hazard_01_02", "city_03_01", "hazard_03_01"}
    wpl = unreal.WorldPartitionBlueprintLibrary
    ids = [d.guid for d in wpl.get_actor_descs()
           if str(d.get_editor_property("label")).replace("ZoneInstance_", "") in moved
           and str(d.get_editor_property("label")).startswith("ZoneInstance_")]
    wpl.load_actors(ids)
    res["moved"] = []
    for a in asub.get_all_level_actors():
        zid = a.get_actor_label().replace("ZoneInstance_", "")
        if a.get_actor_label().startswith("ZoneInstance_") and zid in moved:
            o = zones[zid]["offset_m"]
            loc = unreal.Vector(o[0] * 100.0, -o[1] * 100.0, a.get_actor_location().z)
            a.modify()
            a.set_actor_location(loc, False, False)
            res["moved"].append("%s -> X %.0f m, Y %.0f m" % (zid, loc.x / 100, loc.y / 100))
    log("moved zone instances: %s" % res["moved"])
    res["removed_old"] = clear_ours()
    mesh = unreal.load_asset(PLANE)
    water = pick_material(("water", "ocean", "sea"))
    ground = pick_material(("grass", "dirt", "ground"))
    road = pick_material(("asphalt", "4lane", "2lane", "street"))
    res["materials"] = {"water": water, "ground": ground, "road": road}
    log("materials %s" % res["materials"])

    groups, counts = base_tiles(zones)
    for (kind, (bx, bz)), ts in sorted(groups.items()):
        spawn_group("CityBase_%s_%d_%d" % (kind, bx, bz), mesh, water if kind == "water" else ground, ts, "Ground")
    res["base"] = {"cells": dict(counts), "actors": len(groups)}
    log("base: %s cells in %d actors" % (dict(counts), len(groups)))

    pairs = corridors(zones)
    roads = []
    for za, ga, pa, zb, gb, pb, dist in pairs:
        mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
        yaw = math.degrees(math.atan2(-(pb[1] - pa[1]), pb[0] - pa[0]))
        length_cm = dist * 100 + ROAD_W_CM
        t = unreal.Transform(ue(mid[0], mid[1], 5.0), unreal.Rotator(0, 0, yaw),
                             unreal.Vector(length_cm / 100, ROAD_W_CM / 100, 1.0))
        spawn_group("CityRoad_%s_%s" % (ga, gb), mesh, road, [t], "Ground")
        roads.append("%s %s <-> %s %s: %d m" % (za, ga, zb, gb, dist))
    res["corridors"] = roads
    log("corridors: %d %s" % (len(roads), roads))

    plaza = [float(v) for v in os.environ["CITY_PLAZA"].split(",")]
    ps = asub.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(*plaza), unreal.Rotator(0, 0, 0))
    ps.set_actor_label("PlayerStart_AtlasPlaza_World")
    ps.set_folder_path("Game")
    res["player_start"] = plaza
    log("player start at Atlas plaza %s" % plaza)

    E = unreal.EditorLoadingAndSavingUtils
    keep = ("/Game/Zones/L_ParagonCity", "/Game/__ExternalActors__/Zones/L_ParagonCity",
            "/Game/__ExternalObjects__/Zones/L_ParagonCity")
    dirty = E.get_dirty_content_packages() + E.get_dirty_map_packages()
    mine = [p for p in dirty if p.get_name().startswith(keep)]
    if mine:
        E.save_packages(mine, True)
    res["saved_packages"] = len(mine)
    res["other_dirty"] = [p.get_name() for p in dirty if not p.get_name().startswith(keep)][:10]
    res["minutes"] = round((time.time() - t0) / 60, 1)
    json.dump(res, open(OUT, "w"), indent=1)
    log("saved %d world packages in %.1f min" % (len(mine), res["minutes"]))


main()

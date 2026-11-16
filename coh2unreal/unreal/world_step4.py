"""One-world step 4, headless: Galaxy City - Kings Row road and zone-gate arrival starts.

    UnrealEditor-Cmd COHREBORN.uproject -run=pythonscript -script=".../world_step4.py" -unattended -nullrhi
Env: CITY_REPO (repo root), CITY_OUT (results json).

- Kings Row has no gate sign facing Galaxy City, so the road runs from Galaxy's GALAXYCITY_KINGSROW gate to the
  nearest point of Kings Row's rectangle (24 m wide, ground level, label CityRoad_GALAXYCITY_KINGSROW_edge).
- One PlayerStart per zone gate, 30 m inside the zone towards its centre, tagged Gate_<zone id>_<gate>, used only
  with the travel option Arrive=Gate_<zone id>_<gate> (ACoHGameMode::ChoosePlayerStart). Labels PlayerStart_Gate_*.
Re-running replaces what it made. Only L_ParagonCity's packages are saved.
"""
import json
import math
import os

import unreal

REPO = os.environ["CITY_REPO"]
OUT = os.environ.get("CITY_OUT", os.path.join(REPO, "docs", "zones", "city_step4.json"))
WORLD = "/Game/Zones/L_ParagonCity"
PLANE = "/Engine/BasicShapes/Plane"
ROAD_W_CM = 2400.0
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def log(msg):
    print("[city4] " + msg)
    unreal.log("[city4] " + msg)


def ue(x_m, z_m, h_cm):
    return unreal.Vector(x_m * 100.0, -z_m * 100.0, h_cm)


def main():
    unreal.EditorLoadingAndSavingUtils.load_map(WORLD)
    zones = json.load(open(os.path.join(REPO, "docs", "zones", "zone_offsets.json")))["zones"]
    for a in asub.get_all_level_actors():
        if a.get_actor_label().startswith(("CityRoad_GALAXYCITY_KINGSROW_edge", "PlayerStart_Gate_")):
            asub.destroy_actor(a)
    res = {}
    # Galaxy -> Kings Row road
    g = zones["city_01_03"]["gates_world_m"].get("GALAXYCITY_KINGSROW")
    k = zones["city_01_02"]["world_rect_m"]
    if g:
        px = min(max(g[0], k[0]), k[2])
        pz = min(max(g[1], k[1]), k[3])
        dist = math.dist(g, (px, pz))
        mid = ((g[0] + px) / 2, (g[1] + pz) / 2)
        yaw = math.degrees(math.atan2(-(pz - g[1]), px - g[0]))
        road = unreal.load_asset("/Game/atlas_park/Materials/4lane_2to4_tga")
        a = asub.spawn_actor_from_class(unreal.CoHInstances, unreal.Vector(0, 0, 0))
        a.set_instances(unreal.load_asset(PLANE), [unreal.Transform(ue(mid[0], mid[1], 5.0), unreal.Rotator(0, 0, yaw),
                                                                    unreal.Vector((dist * 100 + ROAD_W_CM) / 100, ROAD_W_CM / 100, 1.0))])
        a.set_actor_label("CityRoad_GALAXYCITY_KINGSROW_edge")
        a.set_folder_path("City/Base")
        if road:
            a.get_component_by_class(unreal.InstancedStaticMeshComponent).set_material(0, road)
        res["galaxy_kings_road_m"] = round(dist)
        log("Galaxy - Kings Row road: %d m" % dist)
    # gate starts
    starts = []
    for zid, z in sorted(zones.items()):
        x0, z0, x1, z1 = z["world_rect_m"]
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        for gate, (gx, gz) in z.get("gates_world_m", {}).items():
            d = math.dist((gx, gz), (cx, cz)) or 1.0
            px, pz = gx + (cx - gx) / d * 30.0, gz + (cz - gz) / d * 30.0
            yaw = math.degrees(math.atan2(-(cz - gz), cx - gx))
            ps = asub.spawn_actor_from_class(unreal.PlayerStart, ue(px, pz, 300.0), unreal.Rotator(0, 0, yaw))
            tag = "Gate_%s_%s" % (zid, gate)
            ps.set_editor_property("player_start_tag", tag)
            ps.set_actor_label("PlayerStart_" + tag)
            ps.set_folder_path("Game/GateStarts")
            starts.append(tag)
    res["gate_starts"] = starts
    log("gate starts: %d" % len(starts))
    E = unreal.EditorLoadingAndSavingUtils
    keep = ("/Game/Zones/L_ParagonCity", "/Game/__ExternalActors__/Zones/L_ParagonCity",
            "/Game/__ExternalObjects__/Zones/L_ParagonCity")
    mine = [p for p in E.get_dirty_content_packages() + E.get_dirty_map_packages() if p.get_name().startswith(keep)]
    if mine:
        E.save_packages(mine, True)
    res["saved_packages"] = len(mine)
    json.dump(res, open(OUT, "w"), indent=1)
    log("saved %d world packages" % len(mine))


main()

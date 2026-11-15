"""Lamp culling pass for the Atlas Park map (headless; docs/zones/atlas_streamline.md).

    UnrealEditor-Cmd COHREBORN.uproject -run=pythonscript -script="<repo>/coh2unreal/unreal/atlas_lights.py" -unattended -nullrhi
Env: ATLAS_OUT (json results), ATLAS_DRY=1 (count only, save nothing).

Every Spot/Point/Rect light in the map gets a max draw distance of 200 m (30 m fade) and no shadows, except:
  - monorail station downlights (owned by the night-lights work, light_stations.py): the tile_1_3 station box
    (x 163-199 m, y 407-457 m) plus any light within 30 m of a station, or labelled/foldered as a station
    light, are left exactly as they are;
  - lights within 40 m of the City Hall plaza centre (PlayerStart_AtlasPlaza) keep their shadows (logged).
Folders, labels, tags and materials (lamp glow) are not touched. Only the Atlas map's packages are saved.
"""
import collections
import json
import os
import time

import unreal

MAP = "/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite"
DRAW_CM = 20000.0
FADE_CM = 3000.0
PLAZA_SHADOW_CM = 4000.0
STATION_BOX = (16300.0, 19900.0, 40700.0, 45700.0)   # x min/max, y min/max (cm), tile_1_3 station lights
STATION_MARGIN_CM = 3000.0
OUT = os.environ.get("ATLAS_OUT", os.path.join(os.environ.get("TEMP", "."), "atlas_lights.json"))
DRY = os.environ.get("ATLAS_DRY") == "1"

asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def log(msg):
    print("[atlas lights] " + msg)
    unreal.log("[atlas lights] " + msg)


def station_light(a, loc):
    x0, x1, y0, y1 = STATION_BOX
    m = STATION_MARGIN_CM
    if x0 - m <= loc.x <= x1 + m and y0 - m <= loc.y <= y1 + m:
        return True
    text = (a.get_actor_label() + " " + str(a.get_folder_path())).lower()
    return "station" in text or "monorail" in text


def main():
    t0 = time.time()
    unreal.EditorLoadingAndSavingUtils.load_map(MAP)
    descs = unreal.WorldPartitionBlueprintLibrary.get_actor_descs()
    unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in descs])
    plaza = None
    for a in asub.get_all_level_actors():
        if a.get_actor_label() == "PlayerStart_AtlasPlaza":
            plaza = a.get_actor_location()
    res = {"plaza_centre": str(plaza), "changed": 0, "skipped_station": [], "kept_shadows": [],
           "by_class": collections.Counter(), "before": collections.Counter()}
    for a in asub.get_all_level_actors():
        for lc in a.get_components_by_class(unreal.LocalLightComponent):
            loc = lc.get_world_location()
            res["before"]["shadows" if lc.get_editor_property("cast_shadows") else "no_shadows"] += 1
            if station_light(a, loc):
                res["skipped_station"].append(a.get_actor_label())
                continue
            keep_shadow = plaza is not None and (loc - plaza).length() <= PLAZA_SHADOW_CM \
                and lc.get_editor_property("cast_shadows")
            res["by_class"][lc.get_class().get_name()] += 1
            if keep_shadow:
                res["kept_shadows"].append(a.get_actor_label())
            if DRY:
                continue
            a.modify()
            lc.modify()
            lc.set_editor_property("max_draw_distance", DRAW_CM)
            lc.set_editor_property("max_distance_fade_range", FADE_CM)
            if not keep_shadow:
                lc.set_editor_property("cast_shadows", False)
            res["changed"] += 1
    saved = 0
    if not DRY:
        E = unreal.EditorLoadingAndSavingUtils
        keep = ("/Game/AtlasPark4/", "/Game/__ExternalActors__/AtlasPark4/", "/Game/__ExternalObjects__/AtlasPark4/")
        mine = [p for p in E.get_dirty_content_packages() + E.get_dirty_map_packages() if p.get_name().startswith(keep)]
        if mine:
            E.save_packages(mine, True)
        saved = len(mine)
    res.update({"saved_packages": saved, "minutes": round((time.time() - t0) / 60, 1), "dry": DRY,
                "by_class": dict(res["by_class"]), "before": dict(res["before"])})
    json.dump(res, open(OUT, "w"), indent=1)
    log("lights changed %d %s (200 m draw, 30 m fade, shadows off); station lights left alone %d; "
        "kept shadows (plaza) %d %s; before %s; saved %d packages%s"
        % (res["changed"], res["by_class"], len(res["skipped_station"]), len(res["kept_shadows"]),
           res["kept_shadows"][:12], res["before"], saved, " (DRY RUN)" if DRY else ""))


main()

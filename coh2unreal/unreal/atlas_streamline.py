"""Streamlines the Atlas Park map for the one world (docs/zones/atlas_audit.md), headless.

Run with the editor closed (it loads and saves the Atlas map's actors):
    UnrealEditor-Cmd COHREBORN.uproject -run=pythonscript -script="<repo>/coh2unreal/unreal/atlas_streamline.py" -unattended -nullrhi
Env: ATLAS_PASSES (default "enemies,trees,grids,skylayer,report"), ATLAS_OUT (json results file),
     ATLAS_TREES_DIR (folder with atlas_park_trees.json), ATLAS_SETUP_TREES (path to setup_trees.py).

Passes (each logged with counts before/after; only the Atlas map's packages and the new data layer asset are saved):
  enemies   the 4,666 CoHOriginal_* encounter preview figures (skeletal meshes from
            /Game/Characters/OriginalEnemies) become editor-only: kept in the editor as the layout reference,
            never cooked or loaded in the game. Live enemies already come from ACoHEnemySpawner's
            original-encounters mode, which hid these previews at runtime anyway, so no group is lost.
  trees     the 1.4 km CoHTrees actor is re-planted as 256 m chunk actors with a 500 m draw distance
            (setup_trees.py, same input and seed).
  grids     static mesh / instance / packed-level actors wider than 256 m go on runtime grid "Far" (flat ones
            on "Ground"), flat ground pieces >= 20 m on "Ground", as in the zone fix pass.
  skylayer  sky set, StarDome, DayNightCycle, the CoHLife manager and the PlayerStarts go on data layer
            DL_AtlasStandaloneSky (initially active), so Atlas alone is unchanged and the one world can switch
            it off (the world has its own sky, day/night and start).
  report    cars and lights: counts and current draw distances only (no changes; other threads own them).
"""
import collections
import json
import os
import re
import sys
import time

import unreal

MAP = "/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite"
DL_DIR = "/Game/AtlasPark4/DataLayers"
DL_NAME = "DL_AtlasStandaloneSky"
CELL = 25600.0
PASSES = [p.strip() for p in os.environ.get("ATLAS_PASSES", "enemies,trees,grids,skylayer,report").split(",") if p.strip()]
OUT = os.environ.get("ATLAS_OUT", os.path.join(os.environ.get("TEMP", "."), "atlas_streamline.json"))
SKY_CLASSES = {"DirectionalLight", "SkyLight", "SkyAtmosphere", "ExponentialHeightFog", "VolumetricCloud",
               "PostProcessVolume", "LevelSequenceActor", "CoHLifeManager", "PlayerStart"}
SKY_LABELS = {"StarDome", "Moon", "DayNightCycle"}
GROUND_NAME = re.compile(r"grnd|ground|street|lane|road|sidewalk|plaza|curb|walkway|pavement|asphalt|grass|dirt|"
                         r"terrain|tile|floor|blk_|block|turf|apron", re.I)

asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
results = {"map": MAP, "passes": {}}


def log(msg):
    print("[atlas] " + msg)
    unreal.log("[atlas] " + msg)


def actors():
    return asub.get_all_level_actors()


def cls_of(a):
    return a.get_class().get_name()


def pass_enemies():
    per = collections.Counter()
    before = sum(1 for a in actors() if isinstance(a, unreal.SkeletalMeshActor) and not a.get_editor_property("is_editor_only_actor"))
    for a in actors():
        if not isinstance(a, unreal.SkeletalMeshActor):
            continue
        comp = a.get_editor_property("skeletal_mesh_component")
        mesh = comp.get_skeletal_mesh_asset() if comp else None
        if not mesh or not mesh.get_path_name().startswith("/Game/Characters/OriginalEnemies/"):
            continue
        if a.get_editor_property("is_editor_only_actor"):
            continue
        a.modify()
        a.set_editor_property("is_editor_only_actor", True)
        m = re.match(r"CoHOriginal_([A-Za-z]+)", a.get_actor_label())
        per[m.group(1) if m else "other"] += 1
    after = sum(1 for a in actors() if isinstance(a, unreal.SkeletalMeshActor) and not a.get_editor_property("is_editor_only_actor"))
    results["passes"]["enemies"] = {"runtime_skeletal_before": before, "runtime_skeletal_after": after,
                                    "made_editor_only": sum(per.values()), "per_faction": dict(per.most_common())}
    log("enemies: %d preview figures made editor-only (runtime skeletal actors %d -> %d); per faction %s"
        % (sum(per.values()), before, after, dict(per.most_common(8))))


def pass_trees():
    src = os.environ.get("ATLAS_SETUP_TREES")
    folder = os.environ.get("ATLAS_TREES_DIR")
    before = [a.get_actor_label() for a in actors() if a.get_actor_label().startswith("CoHTrees")]
    code = open(src).read()
    # this script saves only Atlas packages itself; setup_trees' tile-mode save-all is not wanted here
    code = code.replace("unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)", "pass")
    g = {"__file__": src, "__name__": "__main__"}
    old_argv = sys.argv
    sys.argv = ["setup_trees.py", folder]
    try:
        exec(compile(code, "setup_trees.py", "exec"), g)
    finally:
        sys.argv = old_argv
    after = [a for a in actors() if a.get_actor_label().startswith("CoHTrees")]
    results["passes"]["trees"] = {"tree_actors_before": len(before), "tree_chunk_actors_after": len(after)}
    log("trees: %d tree actor(s) -> %d chunk actors" % (len(before), len(after)))


def pass_grids():
    far = ground = 0
    big = []
    for a in actors():
        if not isinstance(a, (unreal.StaticMeshActor, unreal.CoHInstances, getattr(unreal, "PackedLevelActor", unreal.StaticMeshActor))):
            continue
        if a.get_actor_label() in SKY_LABELS:
            continue
        o, e = a.get_actor_bounds(False)
        width, height = 2 * max(e.x, e.y), 2 * e.z
        grid = None
        if width > CELL:
            grid = "Ground" if height < 600 else "Far"
            big.append((round(width / 100), grid, a.get_actor_label()))
        elif height < 600 and width >= 2000 and (GROUND_NAME.search(a.get_actor_label()) or width >= 6000):
            grid = "Ground"
        if grid:
            a.modify()
            a.set_editor_property("runtime_grid", grid)
            if grid == "Far":
                far += 1
            else:
                ground += 1
    big.sort(reverse=True)
    results["passes"]["grids"] = {"far": far, "ground": ground, "wider_than_256m": big[:30]}
    log("grids: Far %d, Ground %d; actors wider than 256 m: %d" % (far, ground, len(big)))


def pass_skylayer():
    picked = [a for a in actors() if cls_of(a) in SKY_CLASSES or a.get_actor_label() in SKY_LABELS]
    names = sorted("%s:%s" % (cls_of(a), a.get_actor_label()) for a in picked)
    res = {"actors": names}
    try:
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        path = DL_DIR + "/" + DL_NAME
        asset = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else \
            tools.create_asset(DL_NAME, DL_DIR, unreal.DataLayerAsset, None)
        asset.set_editor_property("data_layer_type", unreal.DataLayerType.RUNTIME)
        dls = unreal.get_editor_subsystem(unreal.DataLayerEditorSubsystem)
        inst = None
        for i in dls.get_all_data_layers():
            if i.get_asset() == asset:
                inst = i
        if inst is None:
            params = unreal.DataLayerCreationParameters()
            params.set_editor_property("data_layer_asset", asset)
            inst = dls.create_data_layer_instance(params)
        inst.set_editor_property("initial_runtime_state", unreal.DataLayerRuntimeState.ACTIVATED)
        ok = dls.add_actors_to_data_layer(picked, inst)
        res.update({"data_layer": path, "added": bool(ok), "count": len(picked)})
        log("skylayer: %d actors on %s (initially active): %s" % (len(picked), DL_NAME, names))
    except Exception as e:
        res["error"] = str(e)
        log("skylayer: NOT DONE: %s" % e)
    results["passes"]["skylayer"] = res


def pass_report():
    cars = collections.Counter()
    lights = collections.Counter()
    dist = collections.Counter()
    for a in actors():
        lab = a.get_actor_label().lower()
        if any(k in lab for k in ("car", "vehicle", "van", "taxi", "truck", "bus_")):
            cars[cls_of(a)] += 1
        for lc in a.get_components_by_class(unreal.LightComponent):
            lights[lc.get_class().get_name()] += 1
            try:
                d = lc.get_editor_property("max_draw_distance")
                dist["none" if d <= 0 else ("<=50m" if d <= 5000 else ("<=150m" if d <= 15000 else ">150m"))] += 1
            except Exception:
                dist["?"] += 1
    results["passes"]["report"] = {"car_actors_by_class": dict(cars), "light_components": dict(lights),
                                   "light_max_draw_distance": dict(dist)}
    log("report: cars %s; lights %s; light draw distances %s" % (dict(cars), dict(lights), dict(dist)))


def save_atlas():
    E = unreal.EditorLoadingAndSavingUtils
    keep = ("/Game/AtlasPark4/", "/Game/__ExternalActors__/AtlasPark4/", "/Game/__ExternalObjects__/AtlasPark4/")
    dirty = E.get_dirty_content_packages() + E.get_dirty_map_packages()
    mine = [p for p in dirty if p.get_name().startswith(keep)]
    other = [p.get_name() for p in dirty if not p.get_name().startswith(keep)]
    if mine:
        E.save_packages(mine, True)
    results["saved_packages"] = len(mine)
    results["other_dirty_not_saved"] = other[:20]
    log("saved %d Atlas packages; left unsaved: %s" % (len(mine), other[:10]))


def main():
    t0 = time.time()
    unreal.EditorLoadingAndSavingUtils.load_map(MAP)
    descs = unreal.WorldPartitionBlueprintLibrary.get_actor_descs()
    unreal.WorldPartitionBlueprintLibrary.load_actors([d.guid for d in descs])
    results["actors_before"] = len(actors())
    for p in PASSES:
        t = time.time()
        try:
            {"enemies": pass_enemies, "trees": pass_trees, "grids": pass_grids,
             "skylayer": pass_skylayer, "report": pass_report}[p]()
        except Exception as e:
            results["passes"][p] = {"error": str(e)}
            log("%s: FAILED: %s" % (p, e))
        log("%s took %.0fs" % (p, time.time() - t))
    results["actors_after"] = len(actors())
    save_atlas()
    results["minutes"] = round((time.time() - t0) / 60, 1)
    json.dump(results, open(OUT, "w"), indent=1, default=str)
    log("done in %.1f min; results %s" % (results["minutes"], OUT))


main()

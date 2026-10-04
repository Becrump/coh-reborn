"""Command line: export a City of Heroes zone to glTF for Unreal.

Example (Atlas Park):
    python -m coh2unreal --data path/to/i24/data --piggs path/to/piggs \
        --map maps/city_zones/city_01_01/city_01_01_layer_geometry.txt \
        --out out/atlas_park --name atlas_park
"""
import argparse
import glob
import json
import os
import shutil
import time

from .pigg import AssetStore
from . import maplayout as ml
from . import sky as skymod
from . import replace as replacemod
from .export import Exporter, write_instances


def main():
    ap = argparse.ArgumentParser(prog="coh2unreal")
    ap.add_argument("--data", action="append", default=[],
                    help="extracted data folder (repeatable)")
    ap.add_argument("--piggs", action="append", default=[],
                    help="folder of .pigg archives (repeatable)")
    ap.add_argument("--map", required=True,
                    help="map file relative to data, e.g. "
                         "maps/city_zones/city_01_01/city_01_01.txt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="zone")
    ap.add_argument("--tile", type=float, default=400.0,
                    help="tile size in feet (default 400)")
    ap.add_argument("--area", default="",
                    help="only export objects inside x0,z0,x1,z1 (feet)")
    ap.add_argument("--coh-lights", choices=("none", "all"), default="none",
                    help="put the zone's CoH point lights in the glTF "
                         "(default none: thousands of interior fill lights;"
                         " they are always saved to <name>_lights.json)")
    ap.add_argument("--instanced", action="store_true",
                    help="export each model once (<name>.gltf as a library)"
                         " plus <name>_placements.json, instead of merged "
                         "tiles; Unreal places them as actors / instances")
    ap.add_argument("--keep-props", action="store_true",
                    help="keep CoH street lamps in the tiles instead of "
                         "writing them out for modern replacements")
    ap.add_argument("--limit", type=int, default=0,
                    help="only export the first N instances (testing)")
    args = ap.parse_args()

    t0 = time.time()
    piggs = []
    for d in args.piggs:
        piggs += glob.glob(os.path.join(d, "*.pigg"))
    store = AssetStore(data_dirs=args.data, pigg_paths=piggs)
    print("files indexed: %d (%.0fs)" % (len(store._files), time.time() - t0))
    lib = ml.Library(store)
    print("library defs: %d (%.0fs)" % (len(lib.defs), time.time() - t0))
    local, refs = ml.load_map(store, lib, args.map)
    lights = []
    insts, missing = ml.resolve(lib, local, refs, lights=lights)
    print("placed objects: %d, unresolved names: %d, lights: %d" % (
        len(insts), len(missing), len(lights)))
    if args.area:
        x0, z0, x1, z1 = (float(v) for v in args.area.split(","))
        insts = [i for i in insts
                 if x0 <= i.matrix[3][0] <= x1 and z0 <= i.matrix[3][2] <= z1]
        lights = [lt for lt in lights
                  if x0 <= lt.pos[0] <= x1 and z0 <= lt.pos[2] <= z1]
        print("objects inside area: %d, lights: %d" % (len(insts),
                                                         len(lights)))
    if args.limit:
        insts = insts[:args.limit]
    os.makedirs(args.out, exist_ok=True)
    write_instances(insts, os.path.join(args.out, args.name + "_instances.json"))
    props = []
    if not args.keep_props:
        insts, props = replacemod.split(insts)
        with open(os.path.join(args.out, args.name + "_props.json"),
                  "w") as f:
            json.dump(props, f)
        kinds = {}
        for p in props:
            k = p["kind"] + (" (on traffic pole)" if p["keep_pole"] else "")
            kinds[k] = kinds.get(k, 0) + 1
        print("props for replacement: %s" % ", ".join(
            "%s=%d" % kv for kv in sorted(kinds.items())))

    ex = Exporter(store, lib, args.out, tile_size_ft=args.tile)
    ex.lights = lights
    ex.library = args.instanced
    ex.khr_lights = args.coh_lights == "all"
    skip = ex.plan_lods(insts)
    print("detail levels: %d low-detail duplicates dropped" % len(skip))
    for n, inst in enumerate(insts):
        ex.add(inst, id(inst) in skip)
        if n and n % 20000 == 0:
            print("  %d/%d (%.0fs)" % (n, len(insts), time.time() - t0))
    if not args.instanced:
        print("water tops added: %d" % ex.add_water_tops(insts))
    path = ex.write(args.name)
    s = ex.stats
    print("wrote %s (%.0fs)" % (path, time.time() - t0))
    print("exported %d, hidden %d, far-LOD skipped %d, fake reflection/"
          "shadow layers skipped %d" % (s["placed"], s["hidden"], s["lod"],
                                        s["fake_fx"]))
    print("draw modes: %s" % ", ".join(
        "%s=%d" % (k or "normal", v) for k, v in sorted(s["modes"].items())))

    sky = skymod.load(store, args.map)
    if sky:
        with open(os.path.join(args.out, args.name + "_sky.json"), "w") as f:
            json.dump(sky, f, indent=1)
        print("sky: %s, %d time-of-day keys, lamps %s" % (
            sky["sky_file"], len(sky["keys"]), sky["lamp_light_time"]))
    else:
        print("sky: none found for this map")
    unreal_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "unreal")
    for f in ("setup_level.py", "apply_tuning.py", "coh_materials.py",
              "modern_streetlight.glb",
              "modern_parkinglight.glb"):
        if os.path.exists(os.path.join(unreal_dir, f)):
            shutil.copy(os.path.join(unreal_dir, f), args.out)
    for key in ("missing_geo", "missing_model", "missing_tex", "bad_geo"):
        items = sorted(s[key])
        print("%s: %d %s" % (key, len(items), items[:10]))
    with open(os.path.join(args.out, args.name + "_report.txt"), "w") as f:
        for key in ("missing_geo", "missing_model", "missing_tex", "bad_geo"):
            f.write("[%s]\n" % key)
            f.writelines(x + "\n" for x in sorted(s[key]))
        f.write("[unresolved]\n")
        f.writelines(x + "\n" for x in sorted(missing))


if __name__ == "__main__":
    main()

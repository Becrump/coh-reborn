"""Command line: export a City of Heroes zone to glTF for Unreal.

Example (Atlas Park):
    python -m coh2unreal --data path/to/i24/data --piggs path/to/piggs \
        --map maps/city_zones/city_01_01/city_01_01_layer_geometry.txt \
        --out out/atlas_park --name atlas_park
"""
import argparse
import glob
import os
import time

from .pigg import AssetStore
from . import maplayout as ml
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
    insts, missing = ml.resolve(lib, local, refs)
    print("placed objects: %d, unresolved names: %d" % (len(insts),
                                                        len(missing)))
    if args.area:
        x0, z0, x1, z1 = (float(v) for v in args.area.split(","))
        insts = [i for i in insts
                 if x0 <= i.matrix[3][0] <= x1 and z0 <= i.matrix[3][2] <= z1]
        print("objects inside area: %d" % len(insts))
    if args.limit:
        insts = insts[:args.limit]
    os.makedirs(args.out, exist_ok=True)
    write_instances(insts, os.path.join(args.out, args.name + "_instances.json"))

    ex = Exporter(store, lib, args.out, tile_size_ft=args.tile)
    for n, inst in enumerate(insts):
        ex.add(inst)
        if n and n % 20000 == 0:
            print("  %d/%d (%.0fs)" % (n, len(insts), time.time() - t0))
    path = ex.write(args.name)
    s = ex.stats
    print("wrote %s (%.0fs)" % (path, time.time() - t0))
    print("exported %d, hidden %d, far-LOD skipped %d" % (
        s["placed"], s["hidden"], s["lod"]))
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

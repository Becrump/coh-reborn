"""Exports the "living city" markers of a zone for the Unreal game code.

    python -m coh2unreal.life --data i24/data --piggs piggs \\
        --map maps/city_zones/city_01_01/city_01_01_layer_geometry.txt \\
        --out out/atlas_park --name atlas_park

Writes <name>_life.json, all positions in Unreal centimetres (X forward,
Y right, Z up, same as the imported zone):

  traffic   [{p, d}]  lane arrows built into road pieces (CoH TrafficBeacon
                      "_DIR"); d is the direction of travel (unit, XY)
  monorail  [{p, d}]  the same arrows inside monorail track pieces
  npc       [p]       civilian spawn/walk nodes (CoH NPCGenerator "_NPC")
  cars      [{p, d}]  traffic spawn points (CoH CarGenerator "_CAR")
  fx        [{p, fx}] particle effect spots (street steam, flies, leaves)
  blimp     [{p, d}]  blimp flight arrows (from the zone's blimp layer)
  drones    [p]       police drone posts (persistent NPC layer)

CoH computed which beacons connect at server start (nothing is stored), so
the game code links them itself: arrows to the nearest arrow ahead in the
same direction, walk nodes to neighbours it can see.
"""
import argparse
import glob
import json
import math
import os

from .pigg import AssetStore
from . import maplayout as ml

FT_TO_CM = 30.48


def ue_pos(m):
    x, y, z = m[3]
    return [round(x * FT_TO_CM, 1), round(-z * FT_TO_CM, 1),
            round(y * FT_TO_CM, 1)]


def ue_dir(m, row=2):
    """Unit XY direction of a matrix axis (row 2 = local Z: CoH arrows)."""
    x, _y, z = m[row]
    dx, dy = x, -z
    n = math.hypot(dx, dy) or 1.0
    return [round(dx / n, 4), round(dy / n, 4)]


def collect(store, lib, map_path, extra_layers=()):
    out = {k: [] for k in ("traffic", "monorail", "npc", "cars", "fx",
                           "blimp", "drones")}
    folder = os.path.dirname(map_path)
    paths = [map_path] + [os.path.join(folder, l).replace("\\", "/")
                          for l in extra_layers]
    for path in paths:
        if path.lower() not in store:
            continue
        local, refs = ml.load_map(store, lib, path)
        markers = []
        insts, _missing = ml.resolve(lib, local, refs, markers=markers)
        layer = os.path.basename(path).lower()
        for inst in insts:
            model = inst.model.lower()
            low = inst.path.lower()
            if model == "_dir":
                entry = {"p": ue_pos(inst.matrix), "d": ue_dir(inst.matrix)}
                if "blimp" in low or "blimp" in layer:
                    out["blimp"].append(entry)
                elif "monorail" in low:
                    out["monorail"].append(entry)
                elif "boat" not in low:
                    out["traffic"].append(entry)
            elif model == "_npc":
                out["npc"].append(ue_pos(inst.matrix))
            elif model == "_car":
                out["cars"].append({"p": ue_pos(inst.matrix),
                                    "d": ue_dir(inst.matrix)})
        for name, fx, props, mat, mpath in markers:
            low = (name + " " + mpath).lower()
            if fx:
                out["fx"].append({"p": ue_pos(mat), "fx": fx})
            if "policedrone" in low:
                out["drones"].append(ue_pos(mat))
    return out


def main():
    ap = argparse.ArgumentParser(prog="coh2unreal.life")
    ap.add_argument("--data", action="append", default=[])
    ap.add_argument("--piggs", action="append", default=[])
    ap.add_argument("--map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="zone")
    args = ap.parse_args()
    piggs = []
    for d in args.piggs:
        piggs += glob.glob(os.path.join(d, "*.pigg"))
    store = AssetStore(data_dirs=args.data, pigg_paths=piggs)
    lib = ml.Library(store)
    zone = os.path.basename(os.path.dirname(args.map))
    extra = [zone + "_layer_blimp.txt", zone + "_layer_persistentnpc.txt"]
    life = collect(store, lib, args.map, extra)
    with open(os.path.join(args.out, args.name + "_life.json"), "w") as f:
        json.dump(life, f)
    print("life: " + ", ".join("%s %d" % (k, len(v)) for k, v in life.items()))
    kinds = {}
    for e in life["fx"]:
        k = e["fx"].rsplit("/", 1)[-1].lower()
        kinds[k] = kinds.get(k, 0) + 1
    print("effects: %s" % sorted(kinds.items(), key=lambda kv: -kv[1])[:12])


if __name__ == "__main__":
    main()

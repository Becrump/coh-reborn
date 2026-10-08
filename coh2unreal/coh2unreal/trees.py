"""Lists a zone's trees for replacement with modern ones in Unreal.

    python -m coh2unreal.trees --data i24/data --piggs piggs --out out/atlas_park \\
        --name atlas_park

Reads <name>_instances.json (written by the main export) and writes
<name>_trees.json:

  trees      [{p, yaw, h, kind, model}]  one per tree: base position (Unreal
             cm), facing (deg), height (cm, trunk + leaves) and a kind
             (oak, oak_small, poplar, poplar_tall, park, pine, palm, tree)
  materials  [name]  Unreal material names used only by trees (bark, leaf
             cards), so the setup script can hide the old trees on the tiles

A CoH tree is several models at one spot (trunk, leaf layers, far LOD); they
are grouped by position so each tree is listed once.
"""
import argparse
import glob
import json
import math
import os
import re

from .pigg import AssetStore
from . import maplayout as ml
from .export import Exporter, ue_transform

FT_TO_CM = 30.48
# tree geo files: tree.geo, trees.geo, praet_tree_urban01.geo, ...
# (not street*.geo, which also contains "tree")
TREE_GEO = re.compile(r"(^|/|_)trees?(_[a-z0-9_]*)?\.geo$|/trees/", re.I)


def kind_of(model):
    low = model.lower()
    if "palm" in low:
        return "palm"
    if "pine" in low or "spruce" in low or "fir" in low or "evergreen" in low:
        return "pine"
    if "oak" in low:
        return "oak_small" if "small" in low or "sm" in low.split("oak", 1)[1][:3] \
            else "oak"
    if "pop" in low:
        return "poplar_tall" if "tall" in low else "poplar"
    if "park" in low:
        return "park"
    return "tree"


def is_tree(inst):
    return bool(TREE_GEO.search(inst["geo"].lower())) and \
        not inst["model"].lower().startswith(("_omni", "omni"))


def material_name(tex):
    """Unreal asset name Interchange gives a glTF material named tex."""
    return re.sub(r"[^A-Za-z0-9_]", "_", tex)


def main():
    ap = argparse.ArgumentParser(prog="coh2unreal.trees")
    ap.add_argument("--data", action="append", default=[])
    ap.add_argument("--piggs", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="zone")
    args = ap.parse_args()
    piggs = []
    for d in args.piggs:
        piggs += glob.glob(os.path.join(d, "*.pigg"))
    store = AssetStore(data_dirs=args.data, pigg_paths=piggs)
    lib = ml.Library(store)
    ex = Exporter(store, lib, args.out)
    rows = json.load(open(os.path.join(args.out,
                                       args.name + "_instances.json")))

    def model(r):
        res = ex._model(r["geo"], r["model"])
        return res if isinstance(res, tuple) else None

    tree_tex, other_tex = set(), set()
    spots = {}
    for r in rows:
        res = model(r)
        if res is None:
            continue
        name, mesh, mode, far = res
        texs = {t for t, _ in mesh["groups"]}
        if not is_tree(r):
            other_tex |= texs
            continue
        tree_tex |= texs
        if far:
            continue
        m = r["matrix"]
        key = tuple(round(v, 1) for v in m[3])
        pos = mesh["positions"]
        ys = pos[1::3]
        sy = math.sqrt(sum(m[1][j] ** 2 for j in range(3)))
        top = (max(ys) if ys else 0) * sy
        s = spots.setdefault(key, {"m": m, "top": 0.0, "models": []})
        s["top"] = max(s["top"], top)
        s["models"].append(r["model"])
    trees = []
    for key, s in spots.items():
        loc, rot, _scale = ue_transform(s["m"])
        trunk = min(s["models"], key=lambda n: ("fol" in n.lower(), len(n)))
        trees.append({"p": loc, "yaw": rot[1],
                      "h": round(s["top"] * FT_TO_CM, 1),
                      "kind": kind_of(trunk), "model": trunk})
    only_trees = sorted(material_name(t) for t in tree_tex - other_tex)
    out = os.path.join(args.out, args.name + "_trees.json")
    with open(out, "w") as f:
        json.dump({"trees": trees, "materials": only_trees}, f)
    kinds = {}
    for t in trees:
        kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1
    print("trees: %d %s" % (len(trees), sorted(kinds.items())))
    print("tree-only materials: %d %s" % (len(only_trees), only_trees[:12]))
    shared = sorted(tree_tex & other_tex)
    print("textures shared with non-trees (left visible): %s" % shared[:12])


if __name__ == "__main__":
    main()

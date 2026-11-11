"""Builds the tree replacement table for all zones.

Reads docs/zones/data/<zone>/<name>_trees.json (from coh2unreal.trees, via
the batch converter) and writes docs/zones/tree_replacement.json:

  models  {original model: {category, action, species, count, zones}}
  zones   {zone: {replace, keep, total}}
  species the Megaplant species each category plants

action "replace": the original model is left out of the zone and a
Megaplant tree is planted at its spot (setup_trees.py --table). "keep": the
original stays for now: forest edge walls, backdrop cards and canopy fill
(to be redone with the forest filler between zones), burnt dead trees and
twisted spooky trees (part of those zones' look; Megaplant has none).

    python tools/zones/tree_table.py
"""
import collections
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
DATA = os.path.join(REPO, "docs", "zones", "data")
OUT = os.path.join(REPO, "docs", "zones", "tree_replacement.json")

# Megaplant species that Atlas Park already uses (setup_trees.py).
SPECIES = {
    "street_small": ["Common_Hazel", "Hornbeam"],
    "street_large": ["Hornbeam", "Black_Alder", "Black_Poplar"],
    "birch_small": ["Silver_Birch"],
    "conifer": ["Norway_Spruce", "Baltic_Pine"],
    "forest_pine": ["Baltic_Pine", "Norway_Spruce", "Aleppo_Pine"],
    "forest_broadleaf": ["Black_Alder", "Hornbeam", "Silver_Birch"],
    "palm": ["Ginkgo"],          # no palm in Megaplant: placeholder
}
RULES = [  # (regex on the model name, category, action)
    (r"brntdead", "dead_burnt", "keep"),
    (r"twisted", "twisted", "keep"),
    (r"frst_(fringe|bkdrop)", "forest_edge", "keep"),
    (r"canopy", "canopy_fill", "keep"),
    (r"frst_leafs", "foliage_cards", "keep"),
    (r"frst_treetop", "forest_canopy_top", "keep"),
    (r"frst_lopotree", "forest_pine", "replace"),
    (r"frst_fftree", "forest_broadleaf", "replace"),
    (r"palm", "palm", "replace"),
    (r"conifer", "conifer", "replace"),
    (r"maple_(sml|smlsqsh)", "street_small", "replace"),
    (r"maple_", "street_large", "replace"),
    (r"tree_(sml|smlsqsh)", "birch_small", "replace"),
    (r"tree_(lrg|xlrg)", "street_large", "replace"),
]


def classify(model):
    low = model.lower()
    for rx, cat, action in RULES:
        if re.search(rx, low):
            return cat, action
    return "other", "keep"


def main():
    models = {}
    zones = {}
    for f in sorted(glob.glob(os.path.join(DATA, "*", "*_trees.json"))):
        zone = re.match(r"[a-z]+_\d\d_\d\d",
                        os.path.basename(os.path.dirname(f))).group(0)
        counts = collections.Counter()
        for t in json.load(open(f))["trees"]:
            cat, action = classify(t["model"])
            m = models.setdefault(t["model"], {
                "category": cat, "action": action,
                "species": SPECIES.get(cat, []), "count": 0, "zones": {}})
            m["count"] += 1
            m["zones"][zone] = m["zones"].get(zone, 0) + 1
            counts[action] += 1
        zones[zone] = {"replace": counts["replace"], "keep": counts["keep"],
                       "total": sum(counts.values())}
    out = {"note": "action replace: original left out, Megaplant tree "
                   "planted; keep: original stays for now",
           "species": SPECIES,
           "models": dict(sorted(models.items(), key=lambda kv: -kv[1]["count"])),
           "zones": zones}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    by = collections.Counter()
    for m in models.values():
        by[(m["action"], m["category"])] += m["count"]
    for (a, c), n in sorted(by.items()):
        print("%-8s %-18s %6d" % (a, c, n))
    print("zones:", {z: v["replace"] for z, v in zones.items() if v["total"]})


if __name__ == "__main__":
    main()

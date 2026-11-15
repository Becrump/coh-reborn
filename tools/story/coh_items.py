"""Export the original game's item and reward data as JSON, in the same node
tree form as tools/story/coh_story.py (text inlined from strings):

  badges.json        badges.def + defs/badges/*.def (titles, requirements,
                     the stats they count)
  enhancements.json  enhancement powers (defs/powers/boosts*), invention set
                     bonuses (defs/boostsets), enhancement value schedules and
                     combining odds (boost_effect_*, combine_*)
  inventions.json    salvage, recipes, concepts, merits (defs/invention)
  stores.json        store NPC inventories and prices (defs/stores)
  rewards.json       reward and drop tables (defs/reward: salvage, recipe,
                     enhancement and inspiration drops per rank and level)
  inventory.json     inventory sizes, tier bonus, tracked salvage, auction
  misc.json          origins, emotes, task force time limits, map
                     objectives, monorail destinations, temporary powers

    python tools/story/coh_items.py <i24>/data <out_dir> [--strings strings.json]

--strings reuses coh_story.py's strings.json (otherwise rebuilt, about 10 s).
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import coh_story as cs  # noqa: E402

GROUPS = {
    "badges": ["defs/badges.def", "defs/badges/*.def"],
    "enhancements": ["defs/powers/boosts.categories",
                     "defs/powers/boosts*.powersets", "defs/powers/boosts*.powers",
                     "defs/boostsets/*", "defs/boost_effect_*.def",
                     "defs/combine_*.def"],
    "inventions": ["defs/invention/**/*"],
    "stores": ["defs/stores/**/*"],
    "rewards": ["defs/reward/**/*"],
    "inventory": ["defs/inventory_sizes.def", "defs/inventory_tier_bonus.def",
                  "defs/trackedsalvage.def", "defs/auctionconfig.def"],
    "misc": ["defs/origins.def", "defs/emotes.def", "defs/tftimelimits.def",
             "defs/mapobjectives.def", "defs/monorails.def",
             "defs/powers/temporary_powers*.powers*"],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--strings")
    a = ap.parse_args()
    if a.strings:
        with open(a.strings, encoding="utf-8") as f:
            strings = json.load(f)
    else:
        strings = cs.load_strings(os.path.join(a.data, "texts", "english"))
    os.makedirs(a.out, exist_ok=True)
    unresolved = set()
    for name, pats in GROUPS.items():
        files = []
        for p in pats:
            files += [f for f in glob.glob(os.path.join(a.data, p), recursive=True)
                      if os.path.isfile(f)]
        defs = {}
        for full in sorted(set(files)):
            rel = os.path.relpath(full, a.data).replace("\\", "/").lower()
            with open(full, encoding="latin-1") as f:
                defs[rel] = cs.to_json(cs.parse_braces(f.read()), strings,
                                       unresolved)
        with open(os.path.join(a.out, name + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump(defs, f, ensure_ascii=False)
        top = sum(len(t) for t in defs.values())
        print("%-13s %5d files %6d top-level defs" % (name, len(defs), top),
              flush=True)
    print("unresolved string ids: %d" % len(unresolved))
    return 0


if __name__ == "__main__":
    sys.exit(main())

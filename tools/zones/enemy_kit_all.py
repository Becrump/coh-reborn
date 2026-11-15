"""Enemy kit for every imported zone: one roster of all villains that the
zones' original encounters can spawn, then coh2unreal.enemies on it.

tools/zones/encounters.py writes <enc>/<zone>/encounters.json for each zone.
This merges them (Atlas Park included), builds the roster the way
tools/ai/coh_encounters.py does for Atlas Park, and writes into <out>:

  roster.json           villain -> group, rank, class, AI config, ally,
                        powers, levels, costumes, encounters (zone:name)
  encounters_all.json   every zone's spawn definitions, keyed "<zone>:<name>"
                        (the game keeps reading Atlas Park's encounters.json;
                        this file only feeds the idle behaviors of the kit)
  kit.json, enemy_power_anims.json, models/   from coh2unreal.enemies

kit.json is a superset of Atlas Park's kit (same schema), so it can replace
Content/CoH/Data/enemies/kit.json as is.

    python tools/zones/enemy_kit_all.py <i24>/data <piggs> <enc_dir> <out> \
        [--zones city_01_01 ...] [--events] [--no-models] [--all-costumes]

Zones default to those in docs/zones/zone_offsets.json (the city map).
Seasonal/zone-event spawn definitions are left out unless --events.
Re-runs skip models that already exist in <out>/models.
"""
import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "coh2unreal"))
sys.path.insert(0, os.path.join(REPO, "tools", "ai"))
sys.path.insert(0, os.path.join(REPO, "tools", "rules"))
import coh_encounters as ce  # noqa: E402
import coh_rules  # noqa: E402


def merge(enc_dir, zones, events):
    merged = {}
    for z in zones:
        p = os.path.join(enc_dir, z, "encounters.json")
        if not os.path.exists(p):
            print("no encounters for", z)
            continue
        with open(p) as f:
            for name, sd in json.load(f)["encounters"].items():
                if sd.get("event") and not events:
                    continue
                merged["%s:%s" % (z, name)] = sd
    return merged


def roster_of(villains, encounters):
    acc = collections.defaultdict(lambda: {"slots": 0, "levels": set(),
                                           "encounters": set()})
    for key, sd in encounters.items():
        spots = sum((sd.get("spots") or {"": 1}).values())
        for act in sd["actors"]:
            if act.get("type") != "villain":
                continue
            for lvl, names in (act.get("rolls") or {}).items():
                for n in names:
                    r = acc[n]
                    r["slots"] += spots * act.get("number", 1)
                    r["levels"].add(int(lvl))
                    r["encounters"].add(key)
    lower = {k.lower(): k for k in villains}   # names are case-blind in CoH
    out = {}
    for n, r in sorted(acc.items()):
        n = lower.get(n.lower(), n)
        v = villains.get(n, {})
        if n in out:  # same villain spelled two ways
            o = out[n]
            o["spawn_levels"] = sorted(set(o["spawn_levels"]) | r["levels"])
            o["weight"] += r["slots"]
            o["encounters"] = sorted(set(o["encounters"]) | r["encounters"])
            o["zones"] = sorted({e.split(":", 1)[0] for e in o["encounters"]})
            continue
        out[n] = {"group": v.get("VillainGroup"), "rank": v.get("Rank"),
                  "class": v.get("Class"), "ai_config": v.get("AIConfig"),
                  "ally": v.get("Ally") or "Monster",
                  "powers": [".".join(p) for p in v.get("powers", [])],
                  "def_levels": sorted(v.get("levels", {})),
                  "costumes": ce._costumes(v),
                  "spawn_levels": sorted(r["levels"]),
                  "weight": r["slots"],
                  "zones": sorted({e.split(":", 1)[0] for e in r["encounters"]}),
                  "encounters": sorted(r["encounters"])}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data")
    ap.add_argument("piggs")
    ap.add_argument("enc_dir")
    ap.add_argument("out")
    ap.add_argument("--zones", nargs="*")
    ap.add_argument("--events", action="store_true")
    ap.add_argument("--no-models", action="store_true")
    ap.add_argument("--all-costumes", action="store_true")
    a = ap.parse_args()
    zones = a.zones or sorted(json.load(open(os.path.join(
        REPO, "docs", "zones", "zone_offsets.json")))["zones"])
    encounters = merge(a.enc_dir, zones, a.events)
    villains = coh_rules.load_villains(os.path.join(a.data, "defs"))
    roster = roster_of(villains, encounters)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "roster.json"), "w") as f:
        json.dump(roster, f, indent=1)
    with open(os.path.join(a.out, "encounters_all.json"), "w") as f:
        json.dump({"zones": zones, "encounters": encounters}, f)
    groups = collections.Counter(r["group"] for r in roster.values())
    print("%d zones, %d spawn definitions, %d villains in %d groups" % (
        len(zones), len(encounters), len(roster), len(groups)), flush=True)
    from coh2unreal import enemies
    argv = ["--data", a.data, "--piggs", a.piggs, "--out", a.out,
            "--encounters", os.path.join(a.out, "encounters_all.json")]
    if a.no_models:
        argv.append("--no-models")
    if a.all_costumes:
        argv.append("--all-costumes")
    return enemies.main(argv)


if __name__ == "__main__":
    sys.exit(main())

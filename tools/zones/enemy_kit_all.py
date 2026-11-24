"""Enemy kit for every imported zone: one roster of all villains that the
zones' original encounters can spawn, then coh2unreal.enemies on it.

tools/zones/encounters.py writes <enc>/<zone>/encounters.json for each zone.
This merges them (Atlas Park included), builds the roster the way
tools/ai/coh_encounters.py does for Atlas Park, and writes into <out>:

  roster.json           villain -> group, rank, class, AI config, ally,
                        powers, levels, costumes, encounters (zone:name);
                        plus the pets powers call (Fire Imps, henchmen...,
                        ally "Pet", no encounters) unless --no-pets, and the
                        villains zone events spawn (<enc>/zone_events.json)
  encounters_all.json   every zone's spawn definitions, keyed "<zone>:<name>"
                        (the game keeps reading Atlas Park's encounters.json;
                        this file only feeds the idle behaviors of the kit)
  kit.json, enemy_power_anims.json, models/   from coh2unreal.enemies

kit.json is a superset of Atlas Park's kit (same schema), so it can replace
Content/CoH/Data/enemies/kit.json as is.

    python tools/zones/enemy_kit_all.py <i24>/data <piggs> <enc_dir> <out> \
        [--zones city_01_01 ...] [--events] [--no-models] [--all-costumes]
        [--no-pets] [--all-villains]

--all-villains adds every other villain definition that has a costume (the
Rogue Isles, Praetoria, trials, Incarnate content ...: about 5,900), with no
encounters yet, so their models and powers are in for later zones.

Zones default to those in docs/zones/zone_offsets.json (the city map).
Seasonal/zone-event spawn definitions are left out unless --events.
Re-runs skip models that already exist in <out>/models.
"""
import argparse
import collections
import json
import os
import re
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


PLAYER_CATEGORIES = re.compile(
    r"^(Blaster|Controller|Defender|Scrapper|Tanker|Peacebringer|Warshade|"
    r"Brute|Stalker|Mastermind|Dominator|Corruptor|Arachnos_Soldiers|"
    r"Arachnos_Widows|Sentinel)_|^(Pool|Epic|Inherent|Incarnate\w*|"
    r"Temporary_Powers|Pets|Kheldian_Pets)$")


def pets_of(powers, villains, roster):
    """The pets heroes' powers call (kEntCreate entity defs of player power
    categories: Fire Imps, Phantasm, Mastermind henchmen, patron pets) that
    need a model: the invisible patches (Pets_Ignore: Rain of Fire, Ice
    Slick, Caltrops) are left out."""
    called = set()
    for pid, pw in powers.items():
        if PLAYER_CATEGORIES.match(pid.split(".")[0]):
            called.update(m["EntityDef"] for m in pw.get("mods", [])
                          if m.get("EntityDef"))
    lower = {k.lower(): k for k in villains}
    out = {}
    for n in sorted(called):
        n = lower.get(n.lower(), n)
        v = villains.get(n)
        if not v or n in roster or v.get("AIConfig") == "Pets_Ignore":
            continue
        costumes = ce._costumes(v)
        if not costumes:
            continue
        out[n] = {"group": v.get("VillainGroup") or "Pets", "rank": v.get("Rank"),
                  "class": v.get("Class"), "ai_config": v.get("AIConfig"),
                  "ally": "Pet",
                  "powers": [".".join(p) for p in v.get("powers", [])],
                  "def_levels": sorted(v.get("levels", {})),
                  "costumes": costumes, "spawn_levels": [], "weight": 0,
                  "zones": [], "encounters": []}
    return out


def event_villains(enc_dir, villains, roster):
    """The villains zone events spawn (<enc_dir>/zone_events.json, tools/zones/zone_events.py)."""
    p = os.path.join(enc_dir, "zone_events.json")
    if not os.path.exists(p):
        return {}
    ev = json.load(open(p))
    names = set()
    for e in [x for z in ev.get("zone", {}).values() for x in z] + ev.get("city", []):
        for vl in e.get("villains", {}).values():
            names.update(vl)
        for k in ("BossName",):
            if e.get("vars", {}).get(k):
                names.add(e["vars"][k])
    lower = {k.lower(): k for k in villains}
    out = {}
    for n in sorted(names):
        n = lower.get(n.lower(), n)
        v = villains.get(n)
        if not v or n in roster or not ce._costumes(v):
            continue
        out[n] = {"group": v.get("VillainGroup"), "rank": v.get("Rank"), "class": v.get("Class"),
                  "ai_config": v.get("AIConfig"), "ally": v.get("Ally") or "Monster",
                  "powers": [".".join(p) for p in v.get("powers", [])],
                  "def_levels": sorted(v.get("levels", {})), "costumes": ce._costumes(v),
                  "spawn_levels": [], "weight": 0, "zones": [], "encounters": []}
    return out


def all_villains(villains, roster):
    """Every villain definition with a costume that is not in the roster yet."""
    out = {}
    for n, v in sorted(villains.items()):
        if n in roster or v.get("AIConfig") == "Pets_Ignore":
            continue
        costumes = ce._costumes(v)
        if not costumes:
            continue
        out[n] = {"group": v.get("VillainGroup"), "rank": v.get("Rank"), "class": v.get("Class"),
                  "ai_config": v.get("AIConfig"), "ally": v.get("Ally") or "Monster",
                  "powers": [".".join(p) for p in v.get("powers", [])],
                  "def_levels": sorted(v.get("levels", {})), "costumes": costumes,
                  "spawn_levels": [], "weight": 0, "zones": [], "encounters": []}
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
    ap.add_argument("--no-pets", action="store_true")
    ap.add_argument("--all-villains", action="store_true")
    a = ap.parse_args()
    zones = a.zones or sorted(json.load(open(os.path.join(
        REPO, "docs", "zones", "zone_offsets.json")))["zones"])
    encounters = merge(a.enc_dir, zones, a.events)
    villains = coh_rules.load_villains(os.path.join(a.data, "defs"))
    roster = roster_of(villains, encounters)
    if not a.no_pets:
        pets = pets_of(coh_rules.load_powers(os.path.join(a.data, "defs")),
                       villains, roster)
        roster.update(pets)
        print("%d pets" % len(pets), flush=True)
    evs = event_villains(a.enc_dir, villains, roster)
    roster.update(evs)
    print("%d zone event villains" % len(evs), flush=True)
    if a.all_villains:
        rest = all_villains(villains, roster)
        roster.update(rest)
        print("%d more villain definitions (--all-villains)" % len(rest), flush=True)
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

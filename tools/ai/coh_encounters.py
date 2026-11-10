"""Atlas Park's original encounters: which groups spawn, how many, at what
levels, doing what, and which villain defs each slot can roll.

The zone's spawn layers (maps/city_zones/city_01_01/*_spawndefs.txt) name
the spawn definitions each encounter spot can use (`CanSpawnN`). A spawn
definition (scripts.loc/spawndefs/city_01_01/*.spawndef, parsed like
MapServer/src/generator/encounter.c) gives the level band, team size range,
respawn time and its actors: group and rank (or a named villain or a
civilian model), how many, which team sizes they appear for, the behavior
while idle (AI_InActive: Loiter, Menace, RobPerson...) and when alerted, and
their dialog. The villain behind "Hellions Minion at level 3" is rolled the
way villainFindByCriteria (Common/gameComm/VillainDef.c) does: the group's
villains of that rank whose level range holds the level (or the nearest
level if none), skipping SpawnLimit 0 and CoV-only defs, picked at random.

    python tools/ai/coh_encounters.py <i24>/data export <out_dir>   # encounters.json, roster.json
    python tools/ai/coh_encounters.py <i24>/data summary
    python tools/ai/coh_encounters.py <i24>/data roll Hellions Minion 3

Needs the sparse paths data/maps/city_zones/city_01_01 and
data/scripts.loc/spawndefs/city_01_01 in the i24 checkout.
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rules"))
import coh_rules  # noqa: E402
from coh2unreal.defs import parse_braces  # noqa: E402

ZONE = "city_01_01"
LAYERS = ("city_01_01_layer_spawndefs.txt",
          "city_01_01_layer_makeover_spawndefs.txt")
RANKS = ("Minion", "Lieutenant", "Boss", "Sniper", "Elite", "ArchVillain",
         "ArchVillain2", "BigMonster", "Small", "Pet", "Destructible")
_CANSPAWN = re.compile(r'"CanSpawn\d+"\s+"([^"]+)"', re.I)


def layer_refs(data):
    """{spawndef file (lower, relative to scripts.loc): {layer: spots}}."""
    out = collections.defaultdict(lambda: collections.Counter())
    folder = os.path.join(data, "maps", "city_zones", ZONE)
    for layer in LAYERS:
        path = os.path.join(folder, layer)
        if not os.path.exists(path):
            continue
        with open(path, encoding="latin-1") as f:
            for m in _CANSPAWN.finditer(f.read()):
                out[m.group(1).replace("\\", "/").lower()][
                    "makeover" if "makeover" in layer else "base"] += 1
    return out


def _val(node, key, default=None):
    for c in node.children:
        if c.key.lower() == key.lower() and c.args:
            return c.args[0]
    return default


def _int(s, default=0):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return default


def parse_spawndef(path):
    with open(path, encoding="latin-1") as f:
        text = f.read()
    variables = {}
    for m in re.finditer(r"(?m)^\s*var\s+(\w+)\s*=\s*(\S+)", text):
        variables[m.group(1)] = m.group(2)
    text = re.sub(r"(?m)^\s*var\s+.*$", "", text)
    nodes = [n for n in parse_braces(text) if n.key.lower() == "spawndef"]
    if not nodes:
        return None
    n = nodes[0]
    sd = {"min_level": _int(_val(n, "VillainMinLevel")),
          "max_level": _int(_val(n, "VillainMaxLevel")),
          "min_team": _int(_val(n, "MinTeamSize"), 1),
          "max_team": _int(_val(n, "MaxTeamSize"), 8),
          "respawn": _int(_val(n, "RespawnTimer"), -1),
          "alliance": _val(n, "EncounterAlliance"),
          "dialog": _val(n, "Dialog"),
          "flags": [c.args for c in n.children if c.key == "Flags"],
          "actors": []}
    for a in n.all("Actor"):
        act = {"name": _val(a, "ActorName"),
               "number": _int(_val(a, "Number"), 1),
               "locations": [_int(x) for c in a.children
                             if c.key == "Location" for x in c.args],
               "type": (_val(a, "Type") or "eVillain")[1:].lower()}
        for k, key in (("min_heroes", "MinimumHeroesRequired"),
                       ("max_heroes", "MaximumHeroesRequired"),
                       ("exact_heroes", "ExactHeroesRequired"),
                       ("heroes", "HeroesRequired")):
            v = _val(a, key)
            if v is not None:
                act[k] = _int(v)
        for k, key in (("group", "VillainGroup"), ("rank", "VillainType"),
                       ("villain", "Villain"), ("model", "Model"),
                       ("display_name", "Name"), ("gang", "Gang"),
                       ("ally", "Ally"), ("class_override", "ClassOverride"),
                       ("ai_inactive", "AI_InActive"),
                       ("ai_active", "AI_Active"),
                       ("ai_alerted", "AI_Alerted"),
                       ("ai_completion", "AI_Completion"),
                       ("dialog_inactive", "Dialog_InActive"),
                       ("dialog_active", "Dialog_Active"),
                       ("dialog_alerted", "Dialog_Alerted"),
                       ("dialog_completion", "Dialog_Completion"),
                       ("dialog_thank", "Dialog_ThankHero"),
                       ("shout_chance", "ShoutChance"),
                       ("shout_range", "ShoutRange"),
                       ("level_mod", "VillainLevelMod"),
                       ("vision_phase", "ExclusiveVisionPhase")):
            v = _val(a, key)
            if v is not None:
                act[k] = variables.get(v, v)
        sd["actors"].append(act)
    return sd


def kind_of(name):
    """Encounter kind from the file name: Loiter, Patrol, Mugging ..."""
    base = os.path.basename(name).rsplit(".", 1)[0]
    parts = base.split("_")
    if parts[0].lower() in ("base", "mission1", "mission2", "mission3",
                            "phsd", "gcty", "ze", "named") and len(parts) > 1:
        return parts[0] + "/" + parts[1]
    return parts[0]


class Roller:
    """villainFindByCriteria over the villain defs."""

    def __init__(self, villains):
        self.by = collections.defaultdict(list)
        self.villains = villains
        for name, v in sorted(villains.items()):
            if not v["levels"]:
                continue
            if str(v.get("Exclusion", "")).lower() == "covonly":
                continue
            if _int(v.get("SpawnLimit"), -1) == 0:
                continue
            g = str(v.get("VillainGroup", "")).lower()
            r = str(v.get("Rank", "")).lower()
            self.by[(g, r)].append(name)

    def candidates(self, group, rank, level):
        names = self.by.get((group.lower(), rank.lower()), [])
        if not names:
            return [], level
        lo_best, hi_best = -1000, 1000
        for n in names:
            lv = self.villains[n]["levels"]
            lo, hi = min(lv), max(lv)
            if lo <= level <= hi:
                lo_best = hi_best = level
                break
            if level < lo < hi_best:
                hi_best = lo
            elif lo_best < hi < level:
                lo_best = hi
        level = lo_best if level - lo_best < hi_best - level else hi_best
        return [n for n in names if min(self.villains[n]["levels"]) <= level
                <= max(self.villains[n]["levels"])], level


def build(data):
    defs = os.path.join(data, "defs")
    villains = coh_rules.load_villains(defs)
    roller = Roller(villains)
    refs = layer_refs(data)
    root = os.path.join(data, "scripts.loc")
    index = {}
    for d, _s, files in os.walk(os.path.join(root, "spawndefs")):
        for fn in files:
            full = os.path.join(d, fn)
            index[os.path.relpath(full, root).replace("\\", "/").lower()] = full
    encounters = {}
    roster = collections.defaultdict(lambda: {"slots": 0, "levels": set(),
                                              "encounters": set()})
    missing = []
    for ref, spots in sorted(refs.items()):
        path = index.get(ref)
        if not path:
            missing.append(ref)
            continue
        sd = parse_spawndef(path)
        if sd is None:
            missing.append(ref)
            continue
        sd["kind"] = kind_of(ref)
        sd["spots"] = dict(spots)
        name = os.path.basename(ref).rsplit(".", 1)[0]
        groups = set()
        for act in sd["actors"]:
            if act["type"] != "villain":
                continue
            rolls = {}
            if act.get("villain"):
                v = act["villain"]
                rolls = {str(l): [v] for l in range(sd["min_level"],
                                                     sd["max_level"] + 1)}
                if v in villains:
                    groups.add(villains[v].get("VillainGroup"))
            elif act.get("group") and act.get("rank"):
                groups.add(act["group"])
                lo = max(sd["min_level"], 1)
                hi = max(min(sd["max_level"], 54), lo)
                for lvl in range(lo, hi + 1):
                    lvl2 = lvl + _int(act.get("level_mod"))
                    c, _l = roller.candidates(act["group"], act["rank"], lvl2)
                    rolls[str(lvl)] = c
            act["rolls"] = rolls
            for lvl, names in rolls.items():
                for n in names:
                    r = roster[n]
                    r["slots"] += sum(spots.values()) * act["number"]
                    r["levels"].add(int(lvl))
                    r["encounters"].add(name)
        sd["groups"] = sorted(g for g in groups if g)
        encounters[name] = sd
    out_roster = {}
    for n, r in sorted(roster.items()):
        v = villains.get(n, {})
        out_roster[n] = {"group": v.get("VillainGroup"), "rank": v.get("Rank"),
                         "class": v.get("Class"), "ai_config": v.get("AIConfig"),
                         # VillainCreate: Hero = on the heroes' side
                         # (police, Freedom Corps); default Monster
                         "ally": v.get("Ally") or "Monster",
                         "powers": [".".join(p) for p in v.get("powers", [])],
                         "def_levels": sorted(v.get("levels", {})),
                         "costumes": _costumes(v),
                         "spawn_levels": sorted(r["levels"]),
                         "weight": r["slots"],
                         "encounters": sorted(r["encounters"])}
    return encounters, out_roster, missing


def _costumes(v):
    out = []
    for lv in sorted(v.get("levels", {})):
        c = v["levels"][lv].get("Costumes")
        for n in (c if isinstance(c, list) else [c] if c else []):
            if n not in out:
                out.append(n)
    return out


def summary(encounters, roster):
    kinds = collections.Counter()
    groups = collections.Counter()
    for name, sd in encounters.items():
        spots = sum(sd["spots"].values())
        kinds[sd["kind"]] += spots
        for g in sd["groups"]:
            groups[g] += spots
    print("%d spawn definitions in Atlas Park's layers" % len(encounters))
    print("groups (encounter spots):", ", ".join(
        "%s %d" % kv for kv in groups.most_common()))
    print("kinds:", ", ".join("%s %d" % kv for kv in kinds.most_common(25)))
    print("villain defs that can spawn: %d" % len(roster))
    by_group = collections.defaultdict(list)
    for n, r in roster.items():
        by_group[r["group"]].append((r["weight"], n, r))
    for g, items in sorted(by_group.items(), key=lambda kv: -sum(
            i[0] for i in kv[1])):
        print("  %s:" % g)
        for w, n, r in sorted(items, reverse=True)[:12]:
            print("    %-40s %-10s lv %s-%s  weight %d" % (
                n, r["rank"], min(r["spawn_levels"]), max(r["spawn_levels"]),
                w))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data", help="i24/data folder")
    ap.add_argument("cmd", choices=["export", "summary", "roll"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    if a.cmd == "roll":
        villains = coh_rules.load_villains(os.path.join(a.data, "defs"))
        c, lvl = Roller(villains).candidates(a.args[0], a.args[1],
                                              int(a.args[2]))
        print("level %d: %s" % (lvl, ", ".join(c) or "none"))
        return 0
    encounters, roster, missing = build(a.data)
    summary(encounters, roster)
    if missing:
        print("missing spawn definitions: %d" % len(missing))
    if a.cmd == "export":
        out = a.args[0]
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "encounters.json"), "w") as f:
            json.dump({"zone": ZONE, "encounters": encounters,
                       "missing": missing}, f, indent=1)
        with open(os.path.join(out, "roster.json"), "w") as f:
            json.dump(roster, f, indent=1)
        print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

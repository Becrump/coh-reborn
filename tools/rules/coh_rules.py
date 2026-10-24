"""Reads the City of Heroes rules data (powers, classes, villains, combat mods)
from the i24 text defs and answers the first questions the Unreal rules need.

Reads data/defs from a checkout of Thunderspies/i24 and never writes game data
into the repo; `export` writes JSON to a folder you choose (keep it outside git).

    python tools/rules/coh_rules.py <i24>/data/defs show Hellions.Hellions_Brawl.Brawl
    python tools/rules/coh_rules.py <i24>/data/defs show Blaster_Ranged.Fire_Blast.Flares --class Class_Blaster --level 1
    python tools/rules/coh_rules.py <i24>/data/defs villain Hellions_Brawl_Thug --level 1
    python tools/rules/coh_rules.py <i24>/data/defs export <out_dir>
"""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "coh2unreal"))
from coh2unreal.defs import parse_braces  # noqa: E402


def _read(path):
    with open(path, encoding="latin-1") as f:
        return f.read()


def _num(s):
    try:
        f = float(s)
    except (TypeError, ValueError):
        return s
    # "inf" / "nan" would be written as Infinity / NaN, which is not valid
    # JSON (Unreal's reader rejects the whole file): keep those as text
    return f if math.isfinite(f) else s


def _simple(node):
    """Flattens a node's `Key value...` children into a dict (first wins)."""
    out = {}
    for c in node.children:
        if c.children or not c.args:
            continue
        k = c.key
        v = [_num(a) for a in c.args]
        out.setdefault(k, v[0] if len(v) == 1 else v)
    return out


def _files(defs, folder, ext):
    d = os.path.join(defs, folder)
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(ext))


# ------------------------------------------------------------------ classes
_MODTABLE_NO_BRACE = re.compile(r"(?m)^([ \t]*)ModTable[ \t]*\r?\n(?![ \t]*\{)")


def load_classes(defs):
    out = {}
    for path in _files(defs, "classes", ".def"):
        # Class files open each ModTable without a "{" but still close it with "}".
        text = _MODTABLE_NO_BRACE.sub(r"\1ModTable\n\1{\n", _read(path))
        for n in parse_braces(text):
            if n.key != "Class":
                continue
            name = n.arg("Name")
            cls = {"name": name, "tables": {}, "base": {}, "max": {}}
            ab = n.get("AttribBase")
            if ab:
                cls["base"] = _simple(ab)
            amt = n.get("AttribMaxTable")
            if amt:
                cls["max"] = {c.key: [_num(a) for a in c.args] for c in amt.children}
            for mt in n.all("ModTable"):
                tname = mt.arg("Name")
                vals = mt.get("values")
                if tname and vals:
                    cls["tables"][tname] = [_num(a) for a in vals.args]
            cls["fields"] = _simple(n)
            out[name] = cls
    return out


# ------------------------------------------------------------------- powers
def _power(n):
    p = _simple(n)
    p["full_name"] = n.args[0] if n.args else ""
    p["mods"] = [_simple(m) for m in n.all("AttribMod")]
    return p


def load_powers(defs):
    out = {}
    for path in _files(defs, "powers", ".powers"):
        for n in parse_braces(_read(path)):
            if n.key == "Power" and n.args:
                out[n.args[0]] = _power(n)
    return out


def load_powersets(defs):
    out = {}
    for path in _files(defs, "powers", ".powersets"):
        for n in parse_braces(_read(path)):
            if n.key != "PowerSet" or not n.args:
                continue
            powers = []
            for c in n.children:
                if c.key == "Powers":
                    powers.append({"power": c.args[0], "available": None})
                elif c.key == "Available" and powers:
                    powers[-1]["available"] = _num(c.args[0])
            s = _simple(n)
            s["full_name"] = n.args[0]
            s["powers"] = powers
            out[n.args[0]] = s
    return out


# ----------------------------------------------------------------- villains
def load_villains(defs):
    out = {}
    for path in _files(defs, "villains", ".villain"):
        for n in parse_braces(_read(path)):
            if n.key != "VillainDef" or not n.args:
                continue
            v = _simple(n)
            v["name"] = n.args[0]
            v["powers"] = [c.args for c in n.all("Power")]
            v["levels"] = {int(c.args[0]): _simple(c) for c in n.all("Level") if c.args}
            out[n.args[0]] = v
    return out


# ------------------------------------------------------------- combat mods
def load_combat_mods(defs):
    out = []
    for n in parse_braces(_read(os.path.join(defs, "combat_mods.def"))):
        if n.key != "CombatMods":
            continue
        entry = {"min": _num(n.arg("MinSize")), "max": _num(n.arg("MaxSize"))}
        for side in ("HigherLevel", "LowerLevel"):
            s = n.get(side)
            if s:
                entry[side] = {c.key: [_num(a) for a in c.args] for c in s.children}
        out.append(entry)
    return out


# ---------------------------------------------------------------- AI configs
_CFG_START = re.compile(r"^\s*Config:\s*(\S+)")
_CFG_KEY = re.compile(r"^\s*([A-Za-z][\w.]*):\s*(.*?)\s*$")


def load_ai_configs(defs):
    """aiscript/config/*.cfg: `Config: Name { Key: value }` blocks, with
    BaseConfig inheritance resolved (child keys win). Repeated keys such as
    AssignPowerByFlag are kept as lists."""
    folder = os.path.join(os.path.dirname(os.path.normpath(defs)), "aiscript", "config")
    raw = {}
    for path in sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".cfg")):
        cur = None
        for line in _read(path).splitlines():
            line = line.split("//", 1)[0]
            m = _CFG_START.match(line)
            if m:
                cur = raw.setdefault(m.group(1), {})
                continue
            if cur is None or line.strip() in ("{", ""):
                continue
            if line.strip() == "}":
                cur = None
                continue
            m = _CFG_KEY.match(line)
            if not m:
                continue
            k, v = m.group(1), m.group(2)
            vals = [_num(x.strip()) for x in v.split(",")] if "," in v else _num(v)
            if k in cur and k.startswith("Assign"):
                cur[k] = (cur[k] if isinstance(cur[k], list) and isinstance(cur[k][0], list) else [cur[k]]) + [vals]
            else:
                cur[k] = vals

    def resolve(name, seen=()):
        c = raw.get(name, {})
        base = c.get("BaseConfig")
        out = dict(resolve(base, seen + (name,))) if isinstance(base, str) and base not in seen and base in raw else {}
        out.update({k: v for k, v in c.items() if k != "BaseConfig"})
        return out

    return {n: resolve(n) for n in raw}


# ------------------------------------------------------------------ queries
def mod_value(cls, table, level):
    vals = cls["tables"].get(table)
    if not vals:
        return None
    return vals[min(max(level, 1), len(vals)) - 1]


def power_summary(power, cls=None, level=1):
    keys = ("Type", "Accuracy", "Range", "Radius", "Arc", "EnduranceCost",
            "TimeToActivate", "RechargeTime", "EffectArea", "Target", "EntsAffected")
    s = {k: power.get(k) for k in keys if k in power}
    s["mods"] = []
    for m in power["mods"]:
        row = {k: m.get(k) for k in ("Attrib", "Aspect", "Table", "Scale", "Target",
                                     "Duration", "Magnitude", "Delay", "Chance", "Requires")
               if k in m}
        if cls and isinstance(m.get("Scale"), float) and m.get("Table"):
            tv = mod_value(cls, m["Table"], level)
            if tv is not None:
                row["value_at_level"] = round(tv * m["Scale"], 4)
        s["mods"].append(row)
    return s


PLAYER_FAMILIES = {"Blaster", "Controller", "Defender", "Scrapper", "Tanker", "Peacebringer",
                   "Warshade", "Brute", "Stalker", "Dominator", "Corruptor", "Mastermind",
                   "Arachnos", "Pool", "Epic"}
DAMAGE_TYPES = {"smashing", "lethal", "fire", "cold", "energy", "negative_energy",
                "psionic", "toxic"}


def _attrib(m):
    return str(m.get("Attrib", "")).lower().lstrip("k")


def power_row(name, power, available):
    """One power flattened for the creator and the Unreal data tables."""
    dmg, riders = {}, set()
    for m in power["mods"]:
        a = _attrib(m)
        # Skip bookkeeping mods (the "Ones" tables that mark a hit) and self-targeted aspects.
        if not a or str(m.get("Table", "")).endswith("_Ones") or m.get("Aspect") == "kStr":
            continue
        if a in DAMAGE_TYPES and m.get("Aspect") == "kAbs" and isinstance(m.get("Scale"), float):
            dmg[a] = round(dmg.get(a, 0) + m["Scale"], 4)
        else:
            riders.add(a)
    row = {k: power.get(k) for k in ("Type", "Range", "Radius", "Arc", "Accuracy",
                                     "TimeToActivate", "RechargeTime", "EnduranceCost",
                                     "EffectArea", "Target")}
    row.update({"power": name, "available": available, "damage_scale": dmg,
                "riders": sorted(riders)})
    return row


def catalog(defs):
    """Every player power set, flattened, with its dominant damage type as the
    element guess. Output stays out of git (derived from the game data)."""
    powers, sets = load_powers(defs), load_powersets(defs)
    out = []
    for key, s in sorted(sets.items()):
        cat, _, name = key.partition(".")
        rows = [power_row(e["power"], powers[e["power"]], e["available"])
                for e in s["powers"] if e["power"] in powers]
        total = {}
        for r in rows:
            for t, v in r["damage_scale"].items():
                total[t] = total.get(t, 0) + v
        element = max(total, key=total.get) if total else None
        out.append({"set": key, "category": cat, "name": name, "element": element,
                    "damage_total": {k: round(v, 3) for k, v in total.items()},
                    "powers": rows})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("defs", help="path to i24 data/defs")
    ap.add_argument("cmd", choices=["show", "villain", "export", "counts", "catalog", "testhero"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--class", dest="cls", default="Class_Minion_Grunt")
    ap.add_argument("--level", type=int, default=1)
    a = ap.parse_args()

    if a.cmd == "counts":
        print("classes", len(load_classes(a.defs)), "powers", len(load_powers(a.defs)),
              "powersets", len(load_powersets(a.defs)), "villains", len(load_villains(a.defs)))
    elif a.cmd == "show":
        classes = load_classes(a.defs)
        power = load_powers(a.defs)[a.name]
        print(json.dumps(power_summary(power, classes.get(a.cls), a.level), indent=1))
    elif a.cmd == "villain":
        v = load_villains(a.defs)[a.name]
        classes = load_classes(a.defs)
        cls = classes[v["Class"]]
        print(json.dumps({k: v[k] for k in ("name", "Class", "Rank", "AIConfig", "VillainGroup", "powers")}, indent=1))
        print("base:", {k: cls["base"].get(k) for k in ("ToHit", "Regeneration", "Recovery")})
        print("hit points at level %d: %s" % (a.level, cls["max"].get("HitPoints", [None])[min(a.level, 54) - 1]
                                             if cls["max"].get("HitPoints") else None))
        powers = load_powers(a.defs)
        for g, s, p in v["powers"]:
            full = "%s.%s.%s" % (g, s, p) if p != "*" else None
            if full and full in powers:
                print(full, json.dumps(power_summary(powers[full], cls, a.level)))
            elif p == "*":
                for fn, pw in powers.items():
                    if fn.startswith("%s.%s." % (g, s)):
                        print(fn, json.dumps(power_summary(pw, cls, a.level)))
    elif a.cmd == "catalog":
        cat = catalog(a.defs)
        os.makedirs(a.name, exist_ok=True)
        with open(os.path.join(a.name, "catalog.json"), "w") as f:
            json.dump(cat, f)
        print("sets", len(cat), "powers", sum(len(c["powers"]) for c in cat))
    elif a.cmd == "testhero":
        # A hero that owns every player power set, for testing the tray and creator.
        cat = catalog(a.defs)
        hero = {"format": 1, "name": "Test Hero", "level": 50, "class": "Class_Blaster",
                "sets": [{"set": c["set"], "element": c["element"],
                          "powers": [r["power"] for r in c["powers"]]}
                         for c in cat if c["category"].split("_")[0] in PLAYER_FAMILIES]}
        os.makedirs(a.name, exist_ok=True)
        with open(os.path.join(a.name, "hero_all_sets.json"), "w") as f:
            json.dump(hero, f, indent=1)
        print("sets", len(hero["sets"]), "powers", sum(len(x["powers"]) for x in hero["sets"]))
    elif a.cmd == "export":
        os.makedirs(a.name, exist_ok=True)
        for fn, data in (("classes", load_classes(a.defs)), ("powers", load_powers(a.defs)),
                         ("powersets", load_powersets(a.defs)), ("villains", load_villains(a.defs)),
                         ("combat_mods", load_combat_mods(a.defs)), ("ai_configs", load_ai_configs(a.defs))):
            with open(os.path.join(a.name, fn + ".json"), "w") as f:
                json.dump(data, f)
            print(fn, len(data))


if __name__ == "__main__":
    main()

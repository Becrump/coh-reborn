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
        return float(s)
    except (TypeError, ValueError):
        return s


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("defs", help="path to i24 data/defs")
    ap.add_argument("cmd", choices=["show", "villain", "export", "counts"])
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
    elif a.cmd == "export":
        os.makedirs(a.name, exist_ok=True)
        for fn, data in (("classes", load_classes(a.defs)), ("powers", load_powers(a.defs)),
                         ("powersets", load_powersets(a.defs)), ("villains", load_villains(a.defs)),
                         ("combat_mods", load_combat_mods(a.defs))):
            with open(os.path.join(a.name, fn + ".json"), "w") as f:
                json.dump(data, f)
            print(fn, len(data))


if __name__ == "__main__":
    main()

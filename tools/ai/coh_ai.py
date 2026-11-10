"""Enemy behavior recipes (Loiter, Wander, Patrol...) from the original AI data.

AI configs are exported by tools/rules/coh_rules.py (ai_configs.json); this tool adds
what that export lacks: the behavior aliases, and a per-group enemy listing.
Reads a checkout of Thunderspies/i24; `export` writes JSON outside git.

    python tools/ai/coh_ai.py <i24>/data show Hellions_Melee
    python tools/ai/coh_ai.py <i24>/data group Hellions
    python tools/ai/coh_ai.py <i24>/data export <out_dir>   # behavior_aliases.json
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rules"))
import coh_rules  # noqa: E402

_CONFIG = re.compile(r"^\s*Config\s*:\s*(\S+)\s*$")
_KEY = re.compile(r"^\s*([\w.]+)\s*:\s*(.*?)\s*$")
_ALIAS = re.compile(r'^\s*Alias\s*:\s*(\w+)\s*,\s*(<<)?\s*(Loop\()?\s*"?(.*?)"?\)?(?:>>)?\s*$')


def _strip(line):
    return line.split("//", 1)[0]


def _value(s):
    s = s.strip()
    try:
        return float(s) if "." in s or "e" in s.lower() else int(s)
    except ValueError:
        return s


def load_aliases(aidir):
    out = {}
    with open(os.path.join(aidir, "behavioraliases.bal"), encoding="latin-1") as f:
        for raw in f:
            m = _ALIAS.match(_strip(raw))
            if m:
                out[m.group(1)] = {"recipe": m.group(4), "loop": bool(m.group(3))}
    return out


def group_enemies(data, group):
    """Every villain of a group with its rank, class, powers and resolved AI config."""
    configs = coh_rules.load_ai_configs(os.path.join(data, "defs"))
    villains = coh_rules.load_villains(os.path.join(data, "defs"))
    out = []
    for name, v in sorted(villains.items()):
        if v.get("VillainGroup") != group:
            continue
        cfg = v.get("AIConfig")
        out.append({"name": name, "rank": v.get("Rank"), "class": v.get("Class"),
                    "ai_config": cfg, "powers": [".".join(p) for p in v["powers"]],
                    "resolved": configs.get(cfg)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", help="path to i24 data")
    ap.add_argument("cmd", choices=["show", "group", "export"])
    ap.add_argument("name", nargs="?")
    a = ap.parse_args()
    ai = os.path.join(a.data, "aiscript")
    if a.cmd == "show":
        print(json.dumps(coh_rules.load_ai_configs(os.path.join(a.data, "defs")).get(a.name), indent=1))
    elif a.cmd == "group":
        for e in group_enemies(a.data, a.name):
            print(e["name"], e["rank"], e["ai_config"], len(e["powers"]), "powers")
    else:
        os.makedirs(a.name, exist_ok=True)
        aliases = load_aliases(ai)
        with open(os.path.join(a.name, "behavior_aliases.json"), "w") as f:
            json.dump(aliases, f)
        print("behavior_aliases", len(aliases))


if __name__ == "__main__":
    main()

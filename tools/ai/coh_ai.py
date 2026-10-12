"""Converts the City of Heroes enemy AI data (aiscript configs, behavior aliases and
villain definitions) into JSON the Unreal enemy code can load.

Reads a checkout of Thunderspies/i24 and never writes game data into the repo;
`export` writes JSON to a folder you choose (keep it outside git).

    python tools/ai/coh_ai.py <i24>/data show Hellions_Melee
    python tools/ai/coh_ai.py <i24>/data group Hellions
    python tools/ai/coh_ai.py <i24>/data export <out_dir>
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


def load_configs(aidir):
    """Raw configs: name -> {"base": [..], "values": {key: value | [values]}, "blocks": [..]}."""
    out = {}
    folder = os.path.join(aidir, "config")
    for fn in sorted(os.listdir(folder)):
        if not fn.lower().endswith(".cfg"):
            continue
        cur, depth, block = None, 0, None
        with open(os.path.join(folder, fn), encoding="latin-1") as f:
            for raw in f:
                line = _strip(raw)
                if not line.strip():
                    continue
                m = _CONFIG.match(line)
                if m and depth == 0:
                    cur = {"base": [], "values": {}, "blocks": [], "file": fn}
                    out[m.group(1)] = cur
                    continue
                if cur is None:
                    continue
                if line.strip() == "{":
                    depth += 1
                    continue
                if line.strip() == "}":
                    depth -= 1
                    if depth == 1 and block is not None:
                        cur["blocks"].append(block)
                        block = None
                    if depth <= 0:
                        cur, depth = None, 0
                    continue
                if depth == 1 and line.split(":")[0].strip() in ("PowerConfig", "TargetPreference"):
                    block = {"type": line.split(":")[0].strip()}
                    continue
                if depth == 2 and block is not None:
                    k = _KEY.match(line)
                    if k:
                        block[k.group(1)] = _value(k.group(2))
                    continue
                if depth == 1 and line.strip() in ("PowerConfig", "TargetPreference"):
                    block = {"type": line.strip()}
                    continue
                k = _KEY.match(line)
                if k and depth == 1:
                    key, val = k.group(1), k.group(2)
                    if key == "BaseConfig":
                        cur["base"] += [b.strip() for b in val.split(",") if b.strip()]
                    elif key.startswith("AssignPower"):
                        cur["values"].setdefault(key, []).append(
                            [x.strip() for x in val.split(",")])
                    else:
                        cur["values"][key] = _value(val)
    return out


def resolve(configs, name, _seen=None):
    """Applies the BaseConfig chain in order, then the config itself (default.cfg rules)."""
    _seen = _seen or set()
    cfg = configs.get(name)
    if cfg is None or name in _seen:
        return {"values": {}, "blocks": []}
    _seen.add(name)
    out = {"values": {}, "blocks": []}
    for b in cfg["base"]:
        r = resolve(configs, b, _seen)
        out["values"].update(r["values"])
        out["blocks"] += r["blocks"]
    out["values"].update(cfg["values"])
    out["blocks"] += cfg["blocks"]
    return out


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
    configs = load_configs(os.path.join(data, "aiscript"))
    villains = coh_rules.load_villains(os.path.join(data, "defs"))
    out = []
    for name, v in sorted(villains.items()):
        if v.get("VillainGroup") != group:
            continue
        cfg = v.get("AIConfig")
        out.append({"name": name, "rank": v.get("Rank"), "class": v.get("Class"),
                    "ai_config": cfg, "powers": [".".join(p) for p in v["powers"]],
                    "resolved": resolve(configs, cfg) if cfg else None})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", help="path to i24 data")
    ap.add_argument("cmd", choices=["show", "group", "export"])
    ap.add_argument("name", nargs="?")
    a = ap.parse_args()
    ai = os.path.join(a.data, "aiscript")
    if a.cmd == "show":
        print(json.dumps(resolve(load_configs(ai), a.name), indent=1))
    elif a.cmd == "group":
        for e in group_enemies(a.data, a.name):
            print(e["name"], e["rank"], e["ai_config"], len(e["powers"]), "powers")
    else:
        configs = load_configs(ai)
        os.makedirs(a.name, exist_ok=True)
        out = {n: resolve(configs, n) for n in configs}
        for fn, d in (("ai_configs", out), ("behavior_aliases", load_aliases(ai))):
            with open(os.path.join(a.name, fn + ".json"), "w") as f:
                json.dump(d, f)
            print(fn, len(d))


if __name__ == "__main__":
    main()

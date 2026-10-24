"""Export the original City of Heroes power system to JSON for Unreal.

    python tools/powers/export_powers.py <i24 data dir> <out dir>

Reads the Issue 24 plain-text defs (defs/classes, defs/powers) and the
English strings (texts/english) and writes:
  archetypes.json  player classes (hero, villain and epic): base attribs, HP/endurance by level,
                   modifier tables (damage, heal, mez... by level), and their
                   primary / secondary powerset categories
  powersets.json   every powerset in the player categories (primaries,
                   secondaries, pools, inherent): powers and the level each
                   becomes available
  powers.json      every power in those sets: activation, recharge,
                   endurance, range, radius, targets, FX and its attrib mods
  critters.json    the same class data for enemy ranks (minion, lt, boss...)
Display strings (Pnnnn ids) are resolved to English text.
"""
import glob
import json
import os
import re
import sys

DATA, OUT = sys.argv[1], sys.argv[2]
DEFS = os.path.join(DATA, "defs")
os.makedirs(OUT, exist_ok=True)

# ------------------------------------------------------------ text format
TOKEN = re.compile(r'"[^"]*"|[^\s,]+')


def strip_comment(line):
    out, q = [], False
    for i, ch in enumerate(line):
        if ch == '"':
            q = not q
        if not q and line.startswith("//", i):
            break
        out.append(ch)
    return "".join(out)


def parse(path):
    """Brace-structured def file -> list of (head tokens, body) blocks.
    body: list of (key, [values]) and nested blocks as (head, body) with
    key == None."""
    root = []
    stack = [root]
    pending = None
    for raw in open(path, encoding="utf-8-sig", errors="replace"):
        line = strip_comment(raw).strip()
        if not line:
            continue
        toks = [t.strip('"') for t in TOKEN.findall(line)]
        if toks[0] == "{":
            blk = (pending or [], [])
            stack[-1].append((None, blk))
            stack.append(blk[1])
            pending = None
            continue
        if toks[0] == "}":
            if pending is not None:
                stack[-1].append((pending[0], pending[1:]))
                pending = None
            if len(stack) > 1:
                stack.pop()
            continue
        if toks[0] == "ModTable":      # this block has no opening brace
            blk = (toks, [])
            stack[-1].append((None, blk))
            stack.append(blk[1])
            continue
        if toks[0] == "include":
            continue
        if pending is not None:
            stack[-1].append((pending[0], pending[1:]))
        pending = toks
    if pending is not None:
        stack[-1].append((pending[0], pending[1:]))
    return root


def blocks(body, head=None):
    for k, v in body:
        if k is None and (head is None or (v[0] and v[0][0] == head)):
            yield v


def fields(body):
    d = {}
    for k, v in body:
        if k is None:
            continue
        val = v if len(v) != 1 else v[0]
        if k in d:
            if not isinstance(d[k], list) or not d.get("__multi_" + k):
                d[k] = [d[k]]
                d["__multi_" + k] = True
            d[k].append(val)
        else:
            d[k] = val
    return {k: v for k, v in d.items() if not k.startswith("__multi_")}


def num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() and "." not in str(v) else f
    except (TypeError, ValueError):
        return v


# ------------------------------------------------------------ strings
STR = {}
for p in glob.glob(os.path.join(DATA, "texts", "english", "**", "*.ms"), recursive=True):
    for line in open(p, encoding="utf-8-sig", errors="replace"):
        m = re.match(r'\s*"(P\d+)"\s+"(.*)"\s*$', line)
        if m:
            STR[m.group(1)] = m.group(2).replace('""', '"')


def text(v):
    if isinstance(v, str) and re.fullmatch(r"P\d+", v):
        return STR.get(v, v)
    return v


# ------------------------------------------------------------ classes
def read_class(path):
    out = []
    for head, body in blocks(parse(path), "Class"):
        f = fields(body)
        c = {"name": f.get("Name"), "display": text(f.get("DisplayName")),
             "help": text(f.get("DisplayShortHelp")),
             "primary": f.get("PrimaryCategory"), "secondary": f.get("SecondaryCategory"),
             "pool": f.get("PowerPoolCategory"), "epic": f.get("EpicPoolCategory"),
             "origins": f.get("AllowedOrigins"), "icon": f.get("Icon")}
        for sub in ("AttribBase", "AttribMin", "AttribStrengthMin", "AttribResistanceMin"):
            for _, b in blocks(body, sub):
                c[sub] = {k: num(v[0]) for k, v in b if k}
        for _, b in blocks(body, "AttribMaxTable"):
            c["AttribMaxTable"] = {k: [num(x) for x in v] for k, v in b if k and k in
                                   ("HitPoints", "Endurance", "Absorb", "Insight")}
        for _, b in blocks(body, "AttribMaxMaxTable"):
            c["AttribMaxMaxTable"] = {k: [num(x) for x in v] for k, v in b if k and k == "HitPoints"}
        mods = {}
        for h, b in blocks(body, "ModTable"):
            ff = fields(b)
            vals = ff.get("values") or ff.get("Values")
            if ff.get("Name") and vals:
                mods[ff["Name"]] = [num(x) for x in (vals if isinstance(vals, list) else [vals])]
        c["ModTable"] = mods
        out.append(c)
    return out


# hero, villain and epic archetypes (v_pc_* also holds non-player helpers)
VILLAIN_ATS = ("brute", "corruptor", "dominator", "mastermind", "stalker", "arachnos_soldier", "arachnos_widow")
archetypes, critters = [], []
for p in sorted(glob.glob(os.path.join(DEFS, "classes", "*.def"))):
    b = os.path.basename(p).lower()[:-4]
    if b.startswith("pc_") or (b.startswith("v_pc_") and b[5:] in VILLAIN_ATS):
        archetypes += read_class(p)
    elif not b.startswith("v_pc_"):
        critters += read_class(p)

# ------------------------------------------------------------ powersets
CATS = set()
for a in archetypes:
    for k in ("primary", "secondary", "pool", "epic"):
        if a.get(k):
            CATS.add(a[k].lower())
CATS.add("inherent")

powersets = []
for p in sorted(glob.glob(os.path.join(DEFS, "powers", "*.powersets"))):
    for head, body in blocks(parse(p), "PowerSet"):
        full = head[1]
        cat = full.split(".")[0]
        if cat.lower() not in CATS:
            continue
        f = fields(body)
        entries, cur = [], None
        for k, v in body:
            if k == "Powers":
                cur = {"power": v[0]}
                entries.append(cur)
            elif cur is not None and k == "Available":
                cur["level"] = int(num(v[0])) + 1        # Available is 0-based
        powersets.append({"id": full, "category": cat, "name": f.get("Name"),
                          "display": text(f.get("DisplayName")), "help": text(f.get("DisplayHelp")),
                          "icon": f.get("IconName"), "powers": entries})
WANTED = {e["power"].lower() for s in powersets for e in s["powers"]}

# ------------------------------------------------------------ powers
KEEP = ["Type", "Accuracy", "AttackTypes", "EntsAffected", "EntsAutoHit", "Target", "Range",
        "EnduranceCost", "TimeToActivate", "RechargeTime", "ActivatePeriod", "InterruptTime",
        "EffectArea", "Radius", "Arc", "MaxTargetsHit", "BoostsAllowed", "IconName", "VisualFX",
        "AttackBits", "ToggleIgnoreHold", "AIGroups", "TravelSuppression", "MovementSuppression"]
MOD_KEEP = ["Name", "Table", "Aspect", "Attrib", "Target", "Scale", "Type", "Delay", "Duration",
            "Magnitude", "Period", "Chance", "StackType", "Requires", "CancelOnMiss", "AllowStrength",
            "AllowResistance"]
powers = {}
for p in sorted(glob.glob(os.path.join(DEFS, "powers", "*.powers"))):
    for head, body in blocks(parse(p), "Power"):
        full = head[1]
        if full.lower() not in WANTED:
            continue
        f = fields(body)
        pw = {"id": full, "name": f.get("Name"), "display": text(f.get("DisplayName")),
              "short": text(f.get("DisplayShortHelp")), "help": text(f.get("DisplayHelp"))}
        for k in KEEP:
            if k in f:
                v = f[k]
                pw[k] = [num(x) for x in v] if isinstance(v, list) else num(v)
        pw["mods"] = []
        for _, mb in blocks(body, "AttribMod"):
            mf = fields(mb)
            pw["mods"].append({k: (num(mf[k]) if not isinstance(mf[k], list) else mf[k])
                               for k in MOD_KEEP if k in mf})
        powers[full] = pw

for name, data in [("archetypes", archetypes), ("critters", critters), ("powersets", powersets),
                   ("powers", list(powers.values()))]:
    json.dump(data, open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8"), indent=1)
missing = sorted(WANTED - {k.lower() for k in powers})
print("archetypes", len(archetypes), "critter classes", len(critters), "powersets", len(powersets),
      "powers", len(powers), "missing", len(missing), "strings", len(STR))
if missing:
    print("  e.g.", missing[:8])

"""Enhancements and stores the game reads: compiled from the converted item defs.

    python tools/items/items_game.py <out>

Reads <out>/items/enhancements.json and stores.json (tools/story/coh_items.py) and
<out>/story/story_game.json (which stores the placed store NPCs and contacts use).
Writes <out>/items/items_game.json:

  "boosts": {"Generic_Damage": {"name": "Training: Damage", "grade": "TO" | "DO" | "SO",
             "origins": ["Magic"] (empty: any origin), "type": "kDamage_Boost",
             "scale": 0.0833, "attribs": ["kSmashing", ...], "schedule": "A" | "B", "icon": ...}}
  "stores": {"FBSA": [{"boost": "Generic_Damage", "level": 10, "price": 1000}, ...]}
  "slots": [3, 3, 5, 5, ...]     player levels a new enhancement slot comes (schedules.def AssignableBoost + 1)
  "effect_above" / "effect_below": [1.0, 1.05, ...]   strength by enhancement level above / below the hero's

Only the origin enhancements the core game hands out (Training, Dual and Single Origin);
invention sets, Hamidon origins and attuned items come later.
"""
import json
import os
import re
import sys

ORIGINS = {"magic": "Magic", "natural": "Natural", "science": "Science", "technology": "Technology",
           "mutation": "Mutation"}
SCHEDULE_B = {"kDefense_Boost", "kDefenseDebuff_Boost", "kToHit_Boost", "kToHitDebuff_Boost",
              "kRange_Boost", "kRes_Damage_Boost", "kDefense_Buff_Boost", "kDefense_DeBuff_Boost",
              "kToHit_Buff_Boost", "kToHit_DeBuff_Boost"}
# schedules.def (Powers / AssignableBoost), zero-based levels
ASSIGNABLE = [2, 2, 4, 4, 6, 6, 8, 8, 10, 10, 12, 12, 14, 14, 16, 16, 18, 18, 20, 20, 22, 22, 24, 24, 26,
              26, 28, 28, 30, 30, 30, 32, 32, 32, 33, 33, 33, 35, 35, 35, 36, 36, 36, 38, 38, 38, 39, 39,
              39, 41, 41, 41, 42, 42, 42, 44, 44, 44, 45, 45, 45, 47, 47, 47, 49, 49, 49]


def kid_vals(node, key):
    return [c for c in node.get("c", []) if c["k"] == key]


def first(node, key, default=""):
    k = kid_vals(node, key)
    return (k[0].get("a") or [default])[0] if k else default


def text(node, key):
    k = kid_vals(node, key)
    return ((k[0].get("t") or k[0].get("a") or [""])[0]) if k else ""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = sys.argv[1]
    enh = json.load(open(os.path.join(out, "items", "enhancements.json"), encoding="utf-8"))
    stores = json.load(open(os.path.join(out, "items", "stores.json"), encoding="utf-8"))
    boosts = {}
    for path, nodes in enh.items():
        m = re.match(r"defs/powers/boosts_([a-z]+)(?:_([a-z]+))?_", path)
        if not m or not path.endswith(".powers"):
            continue
        a, b = m.group(1), m.group(2)
        if a == "generic":
            grade, origins = "TO", []
        elif a in ORIGINS and b in ORIGINS:
            grade, origins = "DO", [ORIGINS[a], ORIGINS[b]]
        elif a in ORIGINS:
            grade, origins = "SO", [ORIGINS[a]]
        else:
            continue
        for p in nodes:
            if p.get("k") != "Power":
                continue
            bid = (p.get("a") or [""])[0].split(".")[-1]
            allowed = [x for c in kid_vals(p, "BoostsAllowed") for x in c.get("a", [])]
            kind = [x for x in allowed if not any(x == "k%s_Boost" % o for o in ORIGINS.values())]
            mods = [{c["k"]: (c.get("a") or [""])[0] for c in mod.get("c", [])} for mod in kid_vals(p, "AttribMod")]
            if not mods or not kind:
                continue
            try:
                scale = float(mods[0].get("Scale", "0"))
            except ValueError:
                continue
            boosts[bid] = {"name": text(p, "DisplayName"), "grade": grade, "origins": origins,
                           "type": kind[0], "scale": scale,
                           "attribs": sorted({x["Attrib"] for x in mods if x.get("Attrib")}),
                           "schedule": "B" if kind[0] in SCHEDULE_B else "A",
                           "icon": first(p, "IconName"), "help": text(p, "DisplayShortHelp")}
    # items: (boost, level) -> sale price, by department
    dept_items = {}
    for it in stores["defs/stores/items.def"]:
        pw = next((c for c in it.get("c", []) if c["k"] == "Power"), None)
        if not pw or (pw.get("a") or [""])[0] != "Boosts" or len(pw["a"]) < 4:
            continue
        bid = pw["a"][1]
        if bid not in boosts:
            continue
        sell = first(it, "Sell", "0")
        try:
            price, level = int(float(sell)), int(pw["a"][3]) + 1
        except ValueError:
            continue
        for c in kid_vals(it, "Departments"):
            for dpt in c.get("a", []):
                dept_items.setdefault(dpt.lower(), []).append((bid, level, price))
    story = json.load(open(os.path.join(out, "story", "story_game.json"), encoding="utf-8"))
    used = {s for c in story["contacts"].values() for s in c.get("stores", [])}
    used |= {p["store"] for p in story["people"].values() if p.get("store")}
    out_stores = {}
    for st in stores["defs/stores/stores.def"]:
        sid = (st.get("a") or [""])[0]
        if sid not in used:
            continue
        rows = {}
        for c in kid_vals(st, "Sell"):
            a = c.get("a", [])
            if not a:
                continue
            rate = float(a[1]) if len(a) > 1 else 1.0
            for bid, level, price in dept_items.get(a[0].lower(), []):
                rows[(bid, level)] = int(price * rate)
        if rows:
            out_stores[sid] = [{"boost": b, "level": l, "price": p} for (b, l), p in sorted(rows.items())]
    eff = lambda k: [float(x) for x in (enh.get(k) or [{}])[0].get("c", [{}])[0].get("a", [])]  # noqa: E731
    result = {"boosts": boosts, "stores": out_stores, "slots": [x + 1 for x in ASSIGNABLE],
              "effect_above": eff("defs/boost_effect_above.def") or [1.0, 1.05, 1.1, 1.15],
              "effect_below": eff("defs/boost_effect_below.def") or [1.0, 0.9, 0.8, 0.7]}
    with open(os.path.join(out, "items", "items_game.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    grades = {}
    for b in boosts.values():
        grades[b["grade"]] = grades.get(b["grade"], 0) + 1
    print("boosts %d %s, stores %d of %d used (%d items), items_game.json written" % (
        len(boosts), grades, len(out_stores), len(used), sum(len(v) for v in out_stores.values())))


if __name__ == "__main__":
    main()

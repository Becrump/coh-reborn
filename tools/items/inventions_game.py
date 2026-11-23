"""Inventions the game reads: salvage, recipes, invention enhancements and the
salvage / recipe drop tables, compiled from the converted item defs.

    python tools/items/inventions_game.py <out>

Reads <out>/items/inventions.json, enhancements.json and rewards.json
(tools/story/coh_items.py). Writes <out>/items/inventions_game.json:

  "caps": {"salvage": [3, 4, 8, ...], "recipe": [1, 1, ...]}   room by level (index = level)
  "salvage": {"S_LuckCharm": {"name": "Luck Charm", "rarity": "Common", "icon": ..., "sell": 250}}
             invention salvage only (Type Invention)
  "recipes": {"Invention_Damage_15": {"name": "Invention: Damage (Recipe)", "level": 15,
              "rarity": "Common", "cost": 9600, "sell": 1200,
              "boost": "Crafted_Damage" | "power": "Temporary_Powers...",
              "salvage": [[1, "S_LuckCharm"], ...]}}
  "boosts": {"Crafted_Damage": {"name": "Invention: Damage", "grade": "IO", "set": "" | "Aegis",
             "types": ["kDamage_Boost"], "table": "Melee_Boosts_33",
             "scales": {"kSmashing": 1.0, ...}, "unique": false, "icon": ..., "help": ...}}
             invention enhancements: strength = scale x the class table at the
             enhancement's level, never weaker or stronger by the hero's level
  "sets": {"InventionSalvageAll1-19": [[22, "S:S_LuckCharm"], ...],
           "InventionRecipes15-19@17": [[32.0, "R:Invention_Damage_15"], ...]}
           weighted items: S: salvage, R: recipe ("@<level>" when the set
           reads reward tables at the villain's level)
  "drops": {"Minion": {"17": [{"chance": 8, "groups": [...]} | {"chance": 8, "default": true},
            "sets": [[100, "InventionSalvageAll1-19"], ...]}]}}
           the rank's salvage table (minion_salvage.reward ...): each line rolls
           its chance; one item from its sets (by weight) drops

How the original drops them (defs/reward/<rank>_salvage.reward): every
defeat rolls each line of the villain rank's salvage table for its level;
lines name villain groups (magic / science salvage) or the default; a line
that rolls gives one item of its item set. Item sets may read further reward
tables at the villain's level (InventionRecipes15-19 = common, uncommon and
rare recipe tables).
"""
import json
import os
import re
import sys

RANK_FILES = {"Minion": "minion_salvage", "Lieutenant": "lieutenant_salvage", "Boss": "boss_salvage",
              "Elite": "elite_salvage", "ArchVillain": "archvillain_salvage",
              "ArchVillain2": "archvillain2_salvage"}
RECIPE_FILES = ["enhancements", "sets", "setsi11", "setsi13", "setsi14", "setsi24", "powers"]
ORIGIN_BOOSTS = {"kScience_Boost", "kTechnology_Boost", "kMagic_Boost", "kMutation_Boost", "kNatural_Boost"}


def kids(node, key):
    return [c for c in node.get("c", []) if c.get("k") == key]


def first(node, key, default=""):
    k = kids(node, key)
    return (k[0].get("a") or [default])[0] if k else default


def text(node, key):
    k = kids(node, key)
    return ((k[0].get("t") or k[0].get("a") or [""])[0]) if k else ""


def num(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def strip_prefix(name):
    return name.split(".", 1)[1] if re.match(r"^(PL|IS|RT|sg)\.", name) else name


class Tables:
    def __init__(self, rewards, recipes):
        self.itemsets, self.tables = {}, {}
        # set recipes drop by base name ("Annoyance_A") at the villain's level: Annoyance_A_<level>
        self.recipes = recipes
        self.by_base = {}
        for rid in recipes:
            m = re.match(r"(.+)_(\d+)$", rid)
            if m:
                self.by_base.setdefault(m.group(1), []).append(int(m.group(2)))
        for path, nodes in rewards.items():
            for n in nodes:
                if n.get("k") == "ItemSetDef" and n.get("a"):
                    self.itemsets[n["a"][0]] = n
                elif n.get("k") == "RewardTable" and n.get("a"):
                    self.tables[n["a"][0].lower()] = n
        self.out = {}

    def row(self, table, level):
        rows = {int(num(lv["a"][0])): lv for lv in kids(table, "Level") if lv.get("a")}
        if not rows:
            return None
        return rows.get(level) or rows[min(rows, key=lambda r: (abs(r - level), -r))]

    def lines(self, table, level):
        """(chance, groups, default, [[weight, set name]]) of a table's row."""
        out = []
        row = self.row(table, level)
        for ch in kids(row or {}, "Chance"):
            req = " ".join(first_args(ch, "Requires"))
            if req and not req.strip().endswith("!"):
                continue          # needs something owned (loot booster, veteran badge)
            a = ch.get("a") or ["0"]
            always = len(a) > 1 and a[1].lower() == "always"
            groups = [g for c in kids(ch, "VillainGroup") for g in c.get("a", [])]
            sets = []
            for dg in kids(ch, "DropGroup"):
                w = num((dg.get("a") or ["100"])[0], 100)
                for i in kids(dg, "ItemSetName"):
                    name = self.itemset((i.get("a") or [""])[0], level)
                    if name:
                        sets.append([w, name])
            if sets:
                out.append({"chance": 100.0 if always else num(a[0]), "groups": groups,
                            "default": bool(kids(ch, "DefaultVillainGroup")) or not groups, "sets": sets})
        return out

    def itemset(self, name, level, depth=0):
        """Resolve an item set to weighted S:/R: items; returns its key, or None if empty."""
        name = strip_prefix(name)
        node = self.itemsets.get(name)
        if node is None or depth > 4:
            return None
        at_level = any(c.get("k") == "RewardTable" or (c.get("k") == "Recipe" and len(c.get("a", [])) >= 2 and
                                                        c["a"][1] not in self.recipes and c["a"][1] in self.by_base)
                       for c in node.get("c", []))
        key = "%s@%d" % (name, level) if at_level else name
        if key in self.out:
            return key if self.out[key] else None
        items = []
        for c in node.get("c", []):
            a = c.get("a") or []
            k = c.get("k")
            if k == "Recipe" and len(a) >= 2 and a[1] not in self.recipes and a[1] in self.by_base:
                lv = self.by_base[a[1]]
                ok = [x for x in lv if x <= level] or [min(lv)]
                items.append([num(a[0], 1), "R:%s_%d" % (a[1], max(ok))])
            elif k in ("Salvage", "Recipe") and len(a) >= 2:
                items.append([num(a[0], 1), "%s:%s" % (k[0], a[1])])
            elif k == "RewardTable" and len(a) >= 2:
                t = self.tables.get(a[1].lower())
                if t is None:
                    continue
                sub = []
                for ln in self.lines(t, level):
                    for w, s in ln["sets"]:
                        sub += [[w * ln["chance"] / 100.0 * iw, it] for iw, it in self.out.get(s, [])]
                tot = sum(w for w, _ in sub)
                items += [[round(num(a[0], 1) * w / tot, 4), it] for w, it in sub if tot > 0]
        self.out[key] = items
        return key if items else None


def first_args(node, key):
    k = kids(node, key)
    return k[0].get("a", []) if k else []


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = sys.argv[1]
    d = os.path.join(out, "items")
    inv = json.load(open(os.path.join(d, "inventions.json"), encoding="utf-8"))
    enh = json.load(open(os.path.join(d, "enhancements.json"), encoding="utf-8"))
    rewards = json.load(open(os.path.join(d, "rewards.json"), encoding="utf-8"))
    caps = {}
    try:
        sizes = json.load(open(os.path.join(d, "inventory.json"), encoding="utf-8"))["defs/inventory_sizes.def"]
        for n in sizes:
            if n.get("k") in ("Salvage", "Recipe"):
                caps[n["k"].lower()] = [int(num(x)) for x in first_args(n, "AmountAtLevel")]
    except (OSError, KeyError):
        pass

    salvage = {}
    for s in inv.get("defs/invention/salvage.salvage", []):
        if first(s, "Type") != "Invention":
            continue
        salvage[first(s, "Name")] = {"name": text(s, "DisplayName"), "rarity": first(s, "Rarity"),
                                     "icon": first(s, "Icon"), "sell": int(num(first(s, "SellAmount")))}

    recipes = {}
    for f in RECIPE_FILES:
        for r in inv.get("defs/invention/%s.recipe" % f, []):
            if r.get("k") != "DetailRecipe" or not r.get("a") or first(r, "Type") != "Drop":
                continue
            boost = first(r, "EnhancementReward").split(".")
            power = first(r, "PowerReward")
            if len(boost) < 2 and not power:
                continue
            rec = {"name": text(r, "DisplayName"),
                   "level": int(num(first(r, "Level") or first(r, "LevelMin"), 1)),
                   "rarity": first(r, "Rarity"), "cost": int(num(first(r, "CreationCost"))),
                   "sell": int(num(first(r, "SellToVendor"))),
                   "salvage": [[int(num(c["a"][0], 1)), c["a"][1]] for c in kids(r, "SalvageComponent")
                               if len(c.get("a", [])) >= 2]}
            if len(boost) >= 2:
                rec["boost"] = boost[1]
            else:
                rec["power"] = power
            recipes[r["a"][0]] = rec

    boosts = {}
    for path, nodes in enh.items():
        if not re.match(r"defs/powers/boosts_crafted_", path):
            continue
        for p in nodes:
            if p.get("k") != "Power":
                continue
            bid = (p.get("a") or [""])[0].split(".")[-1]
            types = [x for c in kids(p, "BoostsAllowed") for x in c.get("a", []) if x not in ORIGIN_BOOSTS]
            scales, table = {}, ""
            for m in kids(p, "AttribMod"):
                if first(m, "Aspect") != "kStr":
                    continue
                scales[first(m, "Attrib")] = num(first(m, "Scale"), 0)
                table = table or first(m, "Table")
            if not types or not scales:
                continue
            m = re.match(r"Crafted_(.+)_[A-Z]$", bid)
            boosts[bid] = {"name": text(p, "DisplayName"), "grade": "IO", "set": m.group(1) if m else "",
                           "types": types, "table": table, "scales": scales,
                           "unique": "BoostsSlotted>" in first_args(p, "SlotRequires"),
                           "icon": first(p, "IconName"), "help": text(p, "DisplayShortHelp")}

    t = Tables(rewards, recipes)
    drops = {}
    for rank, fn in RANK_FILES.items():
        table = t.tables.get(fn.replace("_salvage", "_Salvage").lower()) or t.tables.get(fn.lower())
        if table is None:
            continue
        rows = {}
        for lv in range(1, 55):
            lines = [ln for ln in t.lines(table, lv) if ln["chance"] > 0]
            for ln in lines:
                if not ln["groups"]:
                    del ln["groups"]
            if lines:
                rows[str(lv)] = lines
        drops[rank] = rows
    used = {s for r in drops.values() for row in r.values() for ln in row for _, s in ln["sets"]}
    sets = {k: v for k, v in t.out.items() if k in used and v}
    # keep only items the game knows
    for k, v in sets.items():
        sets[k] = [[w, it] for w, it in v if (it[0] == "S" and it[2:] in salvage) or
                   (it[0] == "R" and "boost" in recipes.get(it[2:], {}))]   # temporary power recipes: later
    # drop lines whose sets came out empty (costume recipes...), and only the recipes that can drop
    for r in drops.values():
        for lv in list(r):
            r[lv] = [ln for ln in r[lv] if any(sets.get(s) for _, s in ln["sets"])]
            for ln in r[lv]:
                ln["sets"] = [[w, s] for w, s in ln["sets"] if sets.get(s)]
            if not r[lv]:
                del r[lv]
    sets = {k: v for k, v in sets.items() if v}
    dropped = {it[2:] for v in sets.values() for _, it in v if it[0] == "R"}
    recipes = {k: v for k, v in recipes.items() if k in dropped}
    boosts = {k: v for k, v in boosts.items() if k in {r.get("boost") for r in recipes.values()}}
    result = {"caps": caps, "salvage": salvage, "recipes": recipes, "boosts": boosts, "sets": sets, "drops": drops}
    with open(os.path.join(d, "inventions_game.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    n_r = sum(1 for v in sets.values() for _, it in v if it[0] == "R")
    print("salvage %d, recipes %d, invention boosts %d (%d in sets), drop sets %d (%d recipe items), ranks %s;"
          " inventions_game.json written" % (len(salvage), len(recipes), len(boosts),
                                             sum(1 for b in boosts.values() if b["set"]), len(sets), n_r,
                                             ", ".join(drops)))


if __name__ == "__main__":
    main()

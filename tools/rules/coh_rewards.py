"""Leveling rules from the original City of Heroes data: XP and influence for
defeating a villain, team split, level difference, XP cap, defeat debt,
level-ups and inspiration drops.

Reads data/defs from a checkout of Thunderspies/i24 (game data stays out of
git; output goes to a folder you choose).

    python tools/rules/coh_rewards.py <i24>/data/defs export <rules_dir>      # rewards.json
    python tools/rules/coh_rewards.py <i24>/data/defs defeat --villain-level 1 --rank Minion --hero-level 1 [--team 3]
    python tools/rules/coh_rewards.py <i24>/data/defs curve                  # defeats per level, solo, even minions
    python tools/rules/coh_rewards.py <i24>/data/defs selftest

How the game does it (MapServer/src/TeamReward.c, Reward.c,
Common/entity/character_level.c in Thunderspies/CityOfHeroes):
- The villain's rank picks the table (defs/reward/minion.reward,
  lieutenant, boss, elite, archvillain, small, sniper, pet...). The row is the
  villain's level. Its `Chance 100 Always` sets give Experience and Influence;
  other sets roll their chance (percent) and give one item from a weighted
  item set (defs/reward/*.itemset), such as a small inspiration.
- Each team gets the share of the reward equal to its share of the damage.
  Inside a team, every member on the map gets
      ceil(table XP x team share x TeamReward(members) / members
           x LevelBonus(member level - villain level) x villain RewardScale)
  TeamReward (team_xp_boost.def) is 1.0 solo, 1.25 for two ... 2.2 for 7, 2.5
  for 8. LevelBonus (level_bonus.def): +20% a level for a higher villain (to
  2.0), -20% a level for a lower one (0 at 5 below).
- Cap: no more than the table XP four levels above the member's XP level
  times 1.9, and no more than half the XP between that level and the next.
- Items (inspirations, enhancements) go to one member of the team that did the
  most damage, rotating; none when the hero is 3 or more levels above the
  villain's con level (level plus 1 for a lieutenant, 2 for a boss, 3 for an
  elite boss, 4 for an archvillain).
- Debt: a defeat by villains adds DefeatPenalty[XP level] (experience.def; 0
  below level 10) to the debt, halved inside missions, capped at 5 times the
  penalty. While in debt, half of every XP award pays off debt.
- Levels: the XP table (experience.def) gives the XP level; the hero trains to
  it (the game's "level up" button), which opens the next power pick. At 50,
  XP pays debt and the rest becomes influence.
- Inspiration tray: InspirationCol / InspirationRow in schedules.def.
"""
import argparse
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "coh2unreal"))
from coh2unreal.defs import parse_braces  # noqa: E402

RANKS = {"Small": "small", "Minion": "minion", "Lieutenant": "lieutenant", "Sniper": "sniper",
         "Boss": "boss", "Elite": "elite", "ArchVillain": "archvillain",
         "ArchVillain2": "archvillain2", "Pet": "pet"}
# VillainDef - Validate.c villainRankConningAdjust
CON_ADJUST = {"Small": -1, "Minion": 0, "Lieutenant": 1, "Sniper": 1, "Boss": 2, "Elite": 3,
              "ArchVillain": 4, "ArchVillain2": 4, "BigMonster": 4, "Pet": 0}
XP_CAP_LEVELS = 4          # TeamReward.c
NO_ITEMS_ABOVE = 3         # villainWillGiveItems: hero >= villain + 3 gets no items
KILL_CREDIT_FT = 200.0     # DIST_FOR_KILL_CREDIT
NO_DAMAGE_REWARD_FT = 300.0  # DIST_FOR_NO_DAMAGE_REWARD: members who did no damage must be this close
DEBT_CAP_PENALTIES = 5     # character_CapExperienceDebt
MAX_LEVEL = 50


def _read(p):
    with open(p, encoding="latin-1") as f:
        return f.read()


def _nums(node, key):
    n = node.get(key)
    return [float(x.strip(",")) for x in n.args if x.strip(",")] if n else []


class Rewards:
    def __init__(self, defs):
        r = os.path.join(defs, "reward")
        lb = {n.key: [float(a.strip(",")) for a in n.args if a.strip(",")]
              for n in parse_braces(_read(os.path.join(r, "level_bonus.def")))}
        self.bonus_above, self.bonus_below = lb["BonusAbove"], lb["BonusBelow"]
        self.team = {int(n.args[0]): float(n.args[1])
                     for n in parse_braces(_read(os.path.join(r, "team_xp_boost.def")))
                     if n.key == "TeamReward"}
        xp = next(n for n in parse_braces(_read(os.path.join(defs, "experience.def"))) if n.key == "Powers")
        self.xp = [int(v) for v in _nums(xp, "ExperienceRequired")]
        self.penalty = [int(v) for v in _nums(xp, "DefeatPenalty")]
        sched = next(n for n in parse_braces(_read(os.path.join(defs, "schedules.def"))) if n.key == "Powers")
        self.insp_cols = [int(v) for v in _nums(sched, "InspirationCol")]
        self.insp_rows = [int(v) for v in _nums(sched, "InspirationRow")]
        self.tables = {rank: self._table(os.path.join(r, fn + ".reward"))
                       for rank, fn in RANKS.items() if os.path.exists(os.path.join(r, fn + ".reward"))}
        self.itemsets = {}
        for p in sorted(glob.glob(os.path.join(r, "*.itemset"))):
            for n in parse_braces(_read(p)):
                if n.key == "ItemSetDef" and n.args:
                    items = []
                    for c in n.children:
                        k = c.key
                        if k == "Chance" and len(c.args) >= 2:
                            items.append({"weight": int(c.args[0]), "kind": c.args[1],
                                          "item": ".".join(c.args[2:])})
                        elif k in ("Power", "Salvage", "Recipe", "DetailRecipe", "Detail"):
                            items.append({"weight": 1, "kind": k, "item": ".".join(c.args)})
                    self.itemsets[n.args[0]] = items

    @staticmethod
    def _table(path):
        levels = {}
        for t in parse_braces(_read(path)):
            if t.key != "RewardTable":
                continue
            for lv in t.all("Level"):
                sets = []
                for s in lv.all("Chance"):
                    req = s.get("Requires")
                    req = " ".join(req.args) if req else None
                    # the veteran-reward variants need Veteran75 owned
                    if req and "veteran" in req.lower() and not req.strip().endswith("!"):
                        continue
                    e = {"chance": float(s.args[0]), "always": "always" in [a.lower() for a in s.args[1:]]}
                    vg = [c.args[0] for c in s.all("VillainGroup") if c.args]
                    if vg:
                        e["villain_groups"] = vg
                    if s.get("DefaultVillainGroup") is not None:
                        e["default_group"] = True
                    org = [c.args[0] for c in s.all("Origin") if c.args]
                    if org:
                        e["origins"] = org
                    for k in ("Experience", "Influence"):
                        if s.get(k) is not None:
                            e[k.lower()] = int(float(s.arg(k)))
                    drops = []
                    for d in s.all("DropGroup"):
                        drops.append({"weight": int(float(d.args[0])) if d.args else 100,
                                      "itemsets": [i.args[0] for i in d.all("ItemSetName") if i.args]})
                    if drops:
                        e["drops"] = drops
                    if len(e) > 2:
                        sets.append(e)
                levels[int(lv.args[0])] = sets
        return levels

    # ------------------------------------------------------------ the rules
    def sets_for(self, rank, level0, group=None):
        """The reward sets that apply to a villain of this group (None: an
        ordinary group, which the DefaultVillainGroup sets catch)."""
        rows = self.tables[rank]
        row = rows.get(min(max(level0 + 1, 1), max(rows)), [])
        listed = {g for s in row for g in s.get("villain_groups", [])}
        out = []
        for s in row:
            vg = s.get("villain_groups")
            if vg:
                if group not in vg:
                    continue
            elif s.get("default_group") and group in listed:
                continue
            out.append(s)
        return out

    def table_xp(self, rank, level0, group=None):
        xp = inf = 0
        for s in self.sets_for(rank, level0, group):
            if s["always"]:
                xp += s.get("experience", 0)
                inf += s.get("influence", 0)
        return xp, inf

    def level_bonus(self, hero0, villain0):
        d = hero0 - villain0
        t = self.bonus_above if d >= 0 else self.bonus_below
        return t[min(abs(d), len(t) - 1)]

    def team_bonus(self, n):
        return self.team.get(n, 1.0)

    def xp_level(self, xp):
        """1-based level the XP total reaches."""
        lvl = 1
        while lvl < MAX_LEVEL and xp >= self.xp[lvl]:
            lvl += 1
        return lvl

    def cap(self, rank, exp0, group=None):
        e = min(exp0 + 1, MAX_LEVEL - 1)
        avg_max = (self.xp[e] - self.xp[e - 1]) // 2
        cxp, cinf = self.table_xp(rank, e + XP_CAP_LEVELS, group)
        mb = self.level_bonus(0, XP_CAP_LEVELS)
        cxp, cinf = cxp * mb, cinf * mb
        if cxp > avg_max:
            cinf *= avg_max / cxp
            cxp = avg_max
        return cxp, cinf

    def gives_items(self, rank, villain0, hero0):
        return hero0 < villain0 + CON_ADJUST.get(rank, 0) + NO_ITEMS_ABOVE

    def defeat(self, rank, villain0, members, team_share=1.0, reward_scale=1.0, group=None):
        """XP and influence for each member of one team: members are the
        0-based combat levels of the team members on the map."""
        n = len(members)
        base_xp, base_inf = self.table_xp(rank, villain0, group)
        out = []
        for lvl0 in members:
            k = team_share * self.team_bonus(n) * (1.0 / n) * self.level_bonus(lvl0, villain0) * reward_scale
            xp, inf = math.ceil(base_xp * k), math.ceil(base_inf * k)
            cxp, cinf = self.cap(rank, lvl0, group)
            out.append({"xp": int(min(xp, cxp)), "influence": int(min(inf, cinf)),
                        "items": self.gives_items(rank, villain0, lvl0)})
        return out

    def give_xp(self, hero, amount):
        """Applies an XP award to a hero record {xp, debt, influence, level}:
        half pays debt while there is any (character_ApplyAndReduceDebt);
        at level 50 it all pays debt and the rest becomes influence."""
        if hero["level"] >= MAX_LEVEL:
            paid = min(hero.get("debt", 0), amount)
            hero["debt"] = hero.get("debt", 0) - paid
            hero["influence"] = hero.get("influence", 0) + amount - paid
            return
        debt = hero.get("debt", 0)
        if debt:
            worked = amount - amount // 2
            got = amount // 2
            if worked > debt:
                got += worked - debt
                worked = debt
            hero["debt"] = debt - worked
            amount = got
        hero["xp"] = min(hero.get("xp", 0) + amount, self.xp[MAX_LEVEL - 1])

    def defeated(self, hero, in_mission=False, protection=0.0):
        """Debt for a defeat by villains (character_ApplyDefeatPenalty)."""
        e0 = self.xp_level(hero.get("xp", 0)) - 1
        pen = self.penalty[min(e0, len(self.penalty) - 1)]
        add = int(pen * (1.0 - protection) * (0.5 if in_mission else 1.0))
        hero["debt"] = min(hero.get("debt", 0) + add, pen * DEBT_CAP_PENALTIES)
        return add

    def tray(self, level):
        cols = sum(1 for v in self.insp_cols if v <= level - 1)
        rows = sum(1 for v in self.insp_rows if v <= level - 1)
        return cols, rows

    def export(self):
        return {"format": 1,
                "xp_for_level": self.xp[:MAX_LEVEL],
                "defeat_penalty": self.penalty[:MAX_LEVEL],
                "level_bonus_above": self.bonus_above, "level_bonus_below": self.bonus_below,
                "team_bonus": {str(k): v for k, v in sorted(self.team.items())},
                "con_adjust": CON_ADJUST,
                "constants": {"xp_cap_levels": XP_CAP_LEVELS, "xp_cap_bonus": self.level_bonus(0, XP_CAP_LEVELS),
                              "no_items_levels_above": NO_ITEMS_ABOVE,
                              "kill_credit_ft": KILL_CREDIT_FT, "no_damage_reward_ft": NO_DAMAGE_REWARD_FT,
                              "debt_cap_penalties": DEBT_CAP_PENALTIES, "debt_share_of_xp": 0.5,
                              "mission_debt_scale": 0.5, "max_level": MAX_LEVEL},
                "inspiration_tray": [{"level": lv, "columns": self.tray(lv)[0], "rows": self.tray(lv)[1]}
                                     for lv in range(1, MAX_LEVEL + 1)],
                "tables": {rank: {str(k): v for k, v in sorted(t.items())} for rank, t in self.tables.items()},
                "itemsets": self.itemsets}


def selftest(rw):
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("ok   " if cond else "FAIL ") + msg)
        ok = ok and cond

    m1 = rw.defeat("Minion", 0, [0])[0]
    check(m1["xp"] == 10 and m1["items"], "level 1 minion, level 1 hero, solo: %s" % m1)
    lt = rw.defeat("Lieutenant", 0, [0])[0]
    check(lt["xp"] == 33, "level 1 lieutenant: %d XP" % lt["xp"])
    up = rw.defeat("Minion", 2, [0])[0]
    check(up["xp"] == math.ceil(rw.table_xp("Minion", 2)[0] * 1.4) or up["xp"] < math.ceil(
        rw.table_xp("Minion", 2)[0] * 1.4), "+2 minion pays 1.4x (capped): %s" % up)
    gray = rw.defeat("Minion", 0, [5])[0]
    check(gray["xp"] == 0 and not gray["items"], "a minion 5 levels below gives nothing: %s" % gray)
    no_items = rw.defeat("Minion", 0, [3])[0]
    check(not no_items["items"] and rw.defeat("Boss", 0, [3])[0]["items"],
          "items stop at 3 levels above a minion, a boss still drops")
    t3 = rw.defeat("Minion", 0, [0, 0, 0])
    check(all(m["xp"] == math.ceil(10 * 1.5 / 3) for m in t3), "team of 3: each %d XP (x1.5 split 3)" % t3[0]["xp"])
    check(rw.team_bonus(7) == 2.2 and rw.team_bonus(8) == 2.5, "team bonus 7 = 2.2, 8 = 2.5")
    check(rw.xp_level(105) == 1 and rw.xp_level(106) == 2 and rw.xp_level(rw.xp[49]) == 50,
          "XP levels: 106 for 2, %d for 50" % rw.xp[49])
    h = {"xp": rw.xp[9], "level": 10}
    add = rw.defeated(h)
    check(add == rw.penalty[9] == 160 and h["debt"] == 160, "defeat at 10 adds %d debt" % add)
    for _ in range(10):
        rw.defeated(h)
    check(h["debt"] == 800, "debt caps at 5 penalties: %d" % h["debt"])
    rw.give_xp(h, 100)
    check(h["debt"] == 750 and h["xp"] == rw.xp[9] + 50, "half of 100 XP pays debt")
    h1 = {"xp": rw.xp[8], "level": 9}
    check(rw.defeated(h1) == 0, "no debt below level 10")
    check(rw.tray(1) == (3, 1) and rw.tray(50) == (5, 4), "tray 3x1 at 1, %dx%d at 50" % rw.tray(50))
    drops = [s for s in rw.sets_for("Minion", 0) if not s["always"]]
    insp = [s for s in drops if any("Inspiration" in i for d in s.get("drops", []) for i in d["itemsets"])]
    check(insp and insp[0]["chance"] == 35, "level 1 minion: %d%% small inspiration" % (insp[0]["chance"] if insp else 0))
    iset = rw.itemsets.get("InspirationsSmallNoMez", [])
    check(len(iset) == 7 and iset[0]["item"] == "Inspirations.Small.Luck",
          "small inspiration set: %s" % ", ".join("%s %d" % (i["item"].split(".")[-1], i["weight"]) for i in iset))
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("defs")
    ap.add_argument("cmd", choices=["export", "defeat", "curve", "selftest"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--villain-level", type=int, default=1)
    ap.add_argument("--rank", default="Minion")
    ap.add_argument("--hero-level", type=int, default=1)
    ap.add_argument("--team", type=int, default=1)
    a = ap.parse_args()
    rw = Rewards(a.defs)
    if a.cmd == "export":
        os.makedirs(a.path, exist_ok=True)
        with open(os.path.join(a.path, "rewards.json"), "w") as f:
            json.dump(rw.export(), f, indent=1)
        print("ranks %s, item sets %d" % (", ".join(rw.tables), len(rw.itemsets)))
    elif a.cmd == "defeat":
        r = rw.defeat(a.rank, a.villain_level - 1, [a.hero_level - 1] * a.team)
        print(json.dumps(r[0]), "each, team of", a.team)
        for s in rw.sets_for(a.rank, a.villain_level - 1):
            if not s["always"]:
                print("  %3.0f%%  %s" % (s["chance"], ", ".join(i for d in s.get("drops", []) for i in d["itemsets"])))
    elif a.cmd == "curve":
        print("level  xp-to-next  even-minions  even-lieutenants  even-bosses")
        for lvl in range(1, MAX_LEVEL):
            need = rw.xp[lvl] - rw.xp[lvl - 1]
            per = [rw.defeat(r, lvl - 1, [lvl - 1])[0]["xp"] for r in ("Minion", "Lieutenant", "Boss")]
            print("%5d  %10d  %12s  %16s  %11s" % (lvl, need, *[math.ceil(need / p) if p else "-" for p in per]))
    elif a.cmd == "selftest":
        return 0 if selftest(rw) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

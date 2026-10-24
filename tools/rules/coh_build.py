"""Hero build rules from the original City of Heroes data: archetypes and their
power sets, power picks by level, pools, epics, inherent powers, XP.

Reads data/defs from a checkout of Thunderspies/i24 (game data stays out of
git; output goes to a folder you choose).

    python tools/rules/coh_build.py <i24>/data/defs export <out_dir>
    python tools/rules/coh_build.py <i24>/data/defs new <hero.json> --class Class_Blaster \\
        --primary Fire_Blast --secondary Fire_Manipulation --first Flares [--name ..] [--origin ..] [--preset Model_Positron]
    python tools/rules/coh_build.py <i24>/data/defs options <hero.json>
    python tools/rules/coh_build.py <i24>/data/defs pick <hero.json> <power>     (next free pick)
    python tools/rules/coh_build.py <i24>/data/defs level <hero.json> <level>    (sets level and the XP for it)
    python tools/rules/coh_build.py <i24>/data/defs validate <hero.json>
    python tools/rules/coh_build.py <i24>/data/defs starters <out_dir>          (one level-1 hero per archetype)
    python tools/rules/coh_build.py <i24>/data/defs selftest

The rules, all read from the data:
- schedules.def: a power pick at each level listed in `Power` (0-based, so
  two picks at level 1, then 2, 4, 6 ... 49), a new pool set allowed at
  levels 4, 6, 8, 10 (`PoolPowerSet`), an epic set at 35 (`EpicPowerSet`).
  Enhancement slots (`AssignableBoost`) and inspiration tray size are
  exported for later.
- classes: PrimaryCategory / SecondaryCategory / PowerPoolCategory per
  archetype, AllowedOrigins, SpecialRestrictions (Kheldians and Arachnos
  are the epic archetypes; the game unlocked them with a level 20 hero).
- powersets: each power's `Available` level (0-based). Level 1 is one of the
  primary's level 1 powers plus the secondary's level 1 power.
- power BuyRequires (postfix: owned powers, $archetype, &&, ||, !, level),
  powerset SetBuyRequires (the four origin pools exclude each other) and
  SpecializeRequires. Store, promotion and veteran tokens (productOwned?,
  auth>, TokenOwned?) count as not owned, so prestige sprints, pets and
  event costumes are left out; power sets the store sold (SetAccountRequires)
  are open to everyone.
- Inherent (Inherent.Inherent, Inherent.Fitness): every power is free and
  auto-issued once its level is reached and its BuyRequires holds (Brawl,
  Sprint, Rest, the archetype inherent such as Defiance, Fitness at 2).
- experience.def: XP needed for each level.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import coh_rules as R  # noqa: E402

FORMAT = 2
# Promotional powers gated on store / event tokens: not part of the game a
# player levels through, so the private server leaves them out.
PROMO = re.compile(r"prestige_|_Sprintp$|Inherent\.Inherent\.(Ninja_Run|Beast_Run|"
                   r"Steam_Jump|Rocket_Board|Ice_Slide|Hover_Board|Alt_Hover_Board|Magic_Carpet)",
                   re.I)


def _read(p):
    with open(p, encoding="latin-1") as f:
        return f.read()


class Rules:
    def __init__(self, defs):
        self.defs = defs
        self.powers = R.load_powers(defs)
        self.sets = R.load_powersets(defs)
        self.classes = R.load_classes(defs)
        self.power_ci = {k.lower(): k for k in self.powers}
        self.set_ci = {k.lower(): k for k in self.sets}
        self.categories = {}
        for path in R._files(defs, "powers", ".categories"):
            for n in R.parse_braces(_read(path)):
                if n.key == "PowerCategory" and n.args:
                    self.categories[n.args[0].lower()] = [
                        c.args[0] for c in n.all("PowerSets") if c.args]
        sched = R.parse_braces(_read(os.path.join(defs, "schedules.def")))
        p = next(n for n in sched if n.key == "Powers")

        def ints(key):
            n = p.get(key)
            return [int(x.strip(",")) for x in n.args if x.strip(",")] if n else []
        self.sched = {k: ints(k) for k in ("PoolPowerSet", "EpicPowerSet", "Power",
                                           "AssignableBoost", "InspirationCol",
                                           "InspirationRow")}
        xp = R.parse_braces(_read(os.path.join(defs, "experience.def")))
        e = next(n for n in xp if n.key == "Powers")
        self.xp = [int(x.strip(",")) for x in e.get("ExperienceRequired").args if x.strip(",")]
        self.origins = [n.arg("Name") for n in R.parse_braces(_read(os.path.join(defs, "origins.def")))
                        if n.key == "Origin"]

    # ------------------------------------------------------------ data
    def player_classes(self):
        out = []
        for name, c in self.classes.items():
            f = c["fields"]
            restr = f.get("SpecialRestrictions")
            if not restr or "PrimaryCategory" not in f:
                continue
            restr = restr if isinstance(restr, list) else [restr]
            restr = [str(x).strip(",") for x in restr]
            origins = f.get("AllowedOrigins")
            origins = origins if isinstance(origins, list) else [origins]
            out.append({"class": name, "display": f.get("DisplayName"),
                        "side": "Villain" if "Villain" in restr else "Hero",
                        "epic": any(x in ("Kheldian", "ArachnosSoldier", "ArachnosWidow")
                                    for x in restr),
                        "origins": [str(o).strip(",") for o in origins],
                        "primary": self.category_sets(f["PrimaryCategory"]),
                        "secondary": self.category_sets(f["SecondaryCategory"]),
                        "pool_category": f.get("PowerPoolCategory", "Pool")})
        return sorted(out, key=lambda c: (c["side"], c["epic"], c["class"]))

    def category_sets(self, cat):
        return [self.set_ci.get(s.lower(), s) for s in self.categories.get(str(cat).lower(), [])
                if s.lower() in self.set_ci]

    def set_of(self, power):
        return power.rsplit(".", 1)[0]

    def available(self, set_name, power):
        """0-based level the power becomes available in its set."""
        for e in self.sets[set_name]["powers"]:
            if e["power"].lower() == power.lower():
                return int(e["available"] or 0)
        return None

    def flag(self, power, key):
        v = self.powers.get(power, {}).get(key)
        return str(v).lower() in ("ktrue", "true", "1", "1.0")

    # ------------------------------------------------------------ requires
    def requires(self, expr, hero, owned):
        """Evaluates a postfix BuyRequires expression for the hero."""
        if expr in (None, ""):
            return True
        toks = expr if isinstance(expr, list) else [expr]
        st = []
        lvl0 = hero["level"] - 1
        for t in toks:
            if isinstance(t, (int, float)):
                st.append(t)
                continue
            t = str(t)
            lt = t.lower()
            if lt in ("&&", "||"):
                b, a = st.pop(), st.pop()
                st.append(bool(a) and bool(b) if lt == "&&" else bool(a) or bool(b))
            elif lt == "!":
                st.append(not st.pop())
            elif lt in ("==", ">", ">=", "<", "<=", "!="):
                b, a = st.pop(), st.pop()
                if isinstance(a, str) or isinstance(b, str):
                    a, b = str(a).lower(), str(b).lower()
                st.append({"==": a == b, "!=": a != b, ">": a > b, ">=": a >= b,
                           "<": a < b, "<=": a <= b}[lt])
            elif lt == "$archetype":
                st.append(hero["class"])
            elif lt.startswith("@"):
                st.append(t[1:])
            elif lt == "char>":
                attr = str(st.pop()).lower()
                st.append(lvl0 if attr == "level" else 0)
            elif lt in ("auth>", "productowned?", "tokenowned?", "owned?"):
                st.pop()
                # store, promotion, veteran and badge tokens: not part of the
                # levelled game (whole power sets the store sold are only
                # gated by SetAccountRequires, which is not checked)
                st.append(False)
            elif lt in ("isvip?", "isaccountinventoryloaded?"):
                st.append(True)
            elif lt.endswith("?"):
                st.append(False)
            elif "." in t and not re.match(r"^-?[\d.]+$", t):
                st.append(t.lower() in owned)
            else:
                try:
                    st.append(float(t))
                except ValueError:
                    st.append(t)
        return bool(st[-1]) if st else True

    # ------------------------------------------------------------ hero
    def owned(self, hero):
        return {p["power"].lower() for p in hero["picks"]} | \
               {p.lower() for p in self.auto_powers(hero)}

    def auto_powers(self, hero, owned=None):
        """Free, auto-issued powers: the inherent sets plus AutoIssue powers
        of the sets the hero has."""
        picked = {p["power"].lower() for p in hero["picks"]}
        owned = set(picked) if owned is None else owned
        sets = ["Inherent.Inherent", "Inherent.Fitness"] + self.hero_sets(hero)
        out = []
        for s in sets:
            if s not in self.sets:
                continue
            inherent = s.lower().startswith("inherent.")
            for e in self.sets[s]["powers"]:
                pw = e["power"]
                if pw not in self.powers or PROMO.search(pw):
                    continue
                if int(e["available"] or 0) > hero["level"] - 1:
                    continue
                if not (inherent or self.flag(pw, "AutoIssue")):
                    continue
                if self.requires(self.powers[pw].get("BuyRequires"), hero, owned | picked):
                    out.append(pw)
        return out

    def hero_sets(self, hero):
        out = [hero["primary"], hero["secondary"]]
        for p in hero["picks"]:
            s = self.set_of(p["power"])
            if s not in out:
                out.append(s)
        return out

    def picks_allowed(self, level):
        return sum(1 for x in self.sched["Power"] if x <= level - 1)

    def pools_allowed(self, level):
        return sum(1 for x in self.sched["PoolPowerSet"] if x <= level - 1)

    def epics_allowed(self, level):
        return sum(1 for x in self.sched["EpicPowerSet"] if x <= level - 1)

    def pick_level(self, index):
        """Character level (1-based) at which pick number index (0-based) opens."""
        return self.sched["Power"][index] + 1

    def kind(self, hero, set_name):
        cls = next(c for c in self.player_classes() if c["class"] == hero["class"])
        if set_name == hero["primary"]:
            return "primary"
        if set_name == hero["secondary"]:
            return "secondary"
        if set_name in self.category_sets(cls["pool_category"]):
            return "pool"
        if set_name in self.category_sets("Epic"):
            return "epic"
        return None

    def can_pick(self, hero, power, at_level, prior):
        """Why the hero cannot take `power` as a pick made at character level
        at_level after the picks in `prior`, or None if it can."""
        power = self.power_ci.get(power.lower(), power)
        if power not in self.powers:
            return "unknown power"
        s = self.set_of(power)
        if s not in self.sets:
            return "unknown set"
        if PROMO.search(power):
            return "promotional power"
        h = dict(hero, level=at_level, picks=prior)
        k = self.kind(h, s)
        if k is None:
            return "%s is not a %s set" % (s, hero["class"])
        av = self.available(s, power)
        if av is None or av > at_level - 1:
            return "available at level %s" % ((av or 0) + 1)
        owned = self.owned(h)
        if power.lower() in owned:
            return "already owned"
        if at_level == 1:
            # creation: one level 1 primary power and the level 1 secondary power
            kinds = [self.kind(h, self.set_of(p["power"])) for p in prior]
            if k not in ("primary", "secondary") or k in kinds:
                return "level 1 takes one primary and one secondary power"
        sets = self.hero_sets(h)
        if k == "pool" and s not in sets:
            have = sum(1 for x in sets if self.kind(h, x) == "pool")
            if have >= self.pools_allowed(at_level):
                if have >= len(self.sched["PoolPowerSet"]):
                    return "already has the most pool sets (%d)" % have
                return "no new pool set until level %d" % (self.sched["PoolPowerSet"][have] + 1)
        if k == "epic" and s not in sets:
            have = sum(1 for x in sets if self.kind(h, x) == "epic")
            if have >= self.epics_allowed(at_level):
                return "epic sets open at level %d" % (self.sched["EpicPowerSet"][0] + 1)
        sd = self.sets[s]
        for key in ("SetBuyRequires", "SpecializeRequires"):
            if sd.get(key) and not self.requires(sd[key], h, owned):
                return "%s %s not met" % (s, key)
        if not self.requires(self.powers[power].get("BuyRequires"), h, owned):
            return "requirements not met (%s)" % self.powers[power].get("BuyRequires")
        return None

    def options(self, hero):
        """Powers the hero's next pick may take, or [] when no pick is open."""
        n = len(hero["picks"])
        if n >= self.picks_allowed(hero["level"]):
            return []
        at = max(self.pick_level(n), 1)
        cls = next(c for c in self.player_classes() if c["class"] == hero["class"])
        cands = [hero["primary"], hero["secondary"]] + \
            self.category_sets(cls["pool_category"]) + self.category_sets("Epic")
        out = []
        for s in cands:
            for e in self.sets.get(s, {}).get("powers", []):
                if e["power"] in self.powers and self.can_pick(hero, e["power"], at,
                                                               hero["picks"]) is None:
                    out.append(e["power"])
        return out

    def validate(self, hero):
        errs = []
        cls = next((c for c in self.player_classes() if c["class"] == hero["class"]), None)
        if cls is None:
            return ["unknown archetype %s" % hero["class"]]
        if hero["primary"] not in cls["primary"]:
            errs.append("%s is not a %s primary" % (hero["primary"], hero["class"]))
        if hero["secondary"] not in cls["secondary"]:
            errs.append("%s is not a %s secondary" % (hero["secondary"], hero["class"]))
        if hero.get("origin") and hero["origin"] not in cls["origins"]:
            errs.append("origin %s not allowed for %s" % (hero["origin"], hero["class"]))
        if len(hero["picks"]) > self.picks_allowed(hero["level"]):
            errs.append("%d picks, level %d allows %d" % (
                len(hero["picks"]), hero["level"], self.picks_allowed(hero["level"])))
        for i, p in enumerate(hero["picks"]):
            at = self.pick_level(i) if i < len(self.sched["Power"]) else 99
            if p.get("level") and p["level"] < at:
                errs.append("pick %d (%s) at level %d, opens at %d" % (i + 1, p["power"], p["level"], at))
            why = self.can_pick(hero, p["power"], max(p.get("level") or at, at), hero["picks"][:i])
            if why:
                errs.append("pick %d %s: %s" % (i + 1, p["power"], why))
        if hero["level"] > 1 and hero.get("xp", 0) < self.xp[hero["level"] - 1]:
            errs.append("xp %s below level %d (%d)" % (hero.get("xp"), hero["level"], self.xp[hero["level"] - 1]))
        return errs

    def finish(self, hero):
        """Fills the derived fields: the owned powers by set (the format the
        Unreal rules loader reads as `sets`) and the next pick level."""
        auto = self.auto_powers(hero)
        by_set = {}
        for p in auto + [x["power"] for x in hero["picks"]]:
            by_set.setdefault(self.set_of(p), []).append(p)
        hero["sets"] = [{"set": s, "powers": ps} for s, ps in by_set.items()]
        hero["auto_powers"] = auto
        n = len(hero["picks"])
        hero["next_pick_level"] = self.pick_level(n) if n < len(self.sched["Power"]) else None
        hero["format"] = FORMAT
        return hero

    def resolve_set(self, names, want):
        for s in names:
            if s.lower() == want.lower() or s.split(".", 1)[1].lower() == want.lower():
                return s
        raise SystemExit("set %s not in %s" % (want, ", ".join(n.split(".", 1)[1] for n in names)))

    def new_hero(self, cls_name, primary, secondary, first, name, origin, preset):
        cls = next((c for c in self.player_classes() if c["class"].lower() == cls_name.lower()
                    or c["class"].lower() == "class_" + cls_name.lower()), None)
        if cls is None:
            raise SystemExit("unknown archetype %s" % cls_name)
        hero = {"format": FORMAT, "name": name or "New Hero", "class": cls["class"],
                "origin": origin or cls["origins"][0], "level": 1, "xp": 0,
                "model": {"preset": preset} if preset else {},
                "primary": self.resolve_set(cls["primary"], primary),
                "secondary": self.resolve_set(cls["secondary"], secondary), "picks": []}
        firsts = [e["power"] for e in self.sets[hero["primary"]]["powers"]
                  if int(e["available"] or 0) == 0 and e["power"] in self.powers]
        if first:
            p = next((x for x in firsts if x.lower().endswith("." + first.lower())
                      or x.lower() == first.lower()), None)
            if p is None:
                raise SystemExit("first power must be one of %s" % ", ".join(firsts))
        else:
            p = firsts[0]
        sec = next(e["power"] for e in self.sets[hero["secondary"]]["powers"]
                   if int(e["available"] or 0) == 0 and e["power"] in self.powers)
        hero["picks"] = [{"level": 1, "power": p}, {"level": 1, "power": sec}]
        return self.finish(hero)

    def export(self):
        player_sets = set()
        classes = self.player_classes()
        for c in classes:
            player_sets.update(c["primary"] + c["secondary"])
        player_sets.update(self.category_sets("Pool") + self.category_sets("Epic") +
                           ["Inherent.Inherent", "Inherent.Fitness"])
        sets = {}
        for s in sorted(player_sets):
            sd = self.sets[s]
            sets[s] = {"display": sd.get("DisplayName"), "icon": sd.get("IconName"),
                       "set_requires": sd.get("SetBuyRequires"),
                       "specialize_requires": sd.get("SpecializeRequires"),
                       "powers": [{"power": e["power"], "level": int(e["available"] or 0) + 1,
                                   "requires": self.powers.get(e["power"], {}).get("BuyRequires"),
                                   "free": self.flag(e["power"], "Free") or s.startswith("Inherent."),
                                   "auto": self.flag(e["power"], "AutoIssue") or s.startswith("Inherent."),
                                   "promo": bool(PROMO.search(e["power"]))}
                                  for e in sd["powers"] if e["power"] in self.powers]}
        lv = lambda xs: [x + 1 for x in xs]  # noqa: E731
        return {"format": FORMAT, "origins": self.origins, "archetypes": classes,
                "pool_sets": self.category_sets("Pool"), "epic_sets": self.category_sets("Epic"),
                "schedule": {"power_picks": lv(self.sched["Power"]),
                             "new_pool_set": lv(self.sched["PoolPowerSet"]),
                             "new_epic_set": lv(self.sched["EpicPowerSet"]),
                             "enhancement_slots": lv(self.sched["AssignableBoost"]),
                             "inspiration_columns": lv(self.sched["InspirationCol"]),
                             "inspiration_rows": lv(self.sched["InspirationRow"])},
                "xp_for_level": self.xp[:50], "max_level": 50, "sets": sets}


# Starter heroes: a classic pick of sets per archetype and a player-body
# preset from coh2unreal.player to wear until hero creation exists.
STARTERS = {
    "Class_Blaster": ("Fire_Blast", "Fire_Manipulation", "Model_Positron"),
    "Class_Controller": ("Mind_Control", "Empathy", "Model_Sister_Psyche"),
    "Class_Defender": ("Empathy", "Energy_Blast", "Model_MsLiberty"),
    "Class_Scrapper": ("Martial_Arts", "Super_Reflexes", "Model_Synapse"),
    "Class_Tanker": ("Invulnerability", "Super_Strength", "Model_Back_Alley_Brawler"),
    "Class_Brute": ("Super_Strength", "Invulnerability", None),
    "Class_Corruptor": ("Fire_Blast", "Thermal_Radiation", None),
    "Class_Dominator": ("Fire_Control", "Fiery_Assault", None),
    "Class_Mastermind": ("Robotics", "Force_Field", None),
    "Class_Stalker": ("Martial_Arts", "Ninjitsu", None),
}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)


def selftest(rules):
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("ok   " if cond else "FAIL ") + msg)
        ok = ok and cond

    sched = rules.sched["Power"]
    check(len(sched) == 24 and rules.picks_allowed(1) == 2 and rules.picks_allowed(50) == 24,
          "24 power picks: 2 at level 1, last at %d" % (sched[-1] + 1))
    h = rules.new_hero("Blaster", "Fire_Blast", "Fire_Manipulation", "Flares", "T", None, None)
    auto = [p.split(".")[-1] for p in h["auto_powers"]]
    check({"Brawl", "Sprint", "Defiance"} <= set(auto), "level 1 inherents: %s" % ", ".join(auto))
    check(not any("Swift" in a or "Rest" in a for a in auto), "Fitness and Rest not before level 2")
    auto2 = [p.split(".")[-1] for p in rules.auto_powers(dict(h, level=2))]
    check({"Rest", "Swift", "Hurdle", "Health", "Stamina"} <= set(auto2),
          "level 2 adds: %s" % ", ".join(sorted(set(auto2) - set(auto))))
    check(rules.validate(h) == [], "new Fire/Fire blaster is valid")
    bad = dict(h, picks=[{"level": 1, "power": "Blaster_Ranged.Fire_Blast.Fire_Ball"}])
    check(rules.validate(bad) != [], "Fire Ball at level 1 refused")
    h2 = dict(h, level=4, xp=rules.xp[3])
    opts = rules.options(h2)
    check(any(o.startswith("Pool.") for o in opts) is False, "level 2 pick: no pools (%d options)" % len(opts))
    h3 = dict(h, level=50, xp=rules.xp[49])
    h3["picks"] = list(h["picks"]) + [{"level": rules.pick_level(2), "power": "Pool.Flight.Fly"}]
    check(rules.validate(h3) != [], "Fly at level 2 refused (pools open at 4)")
    base = h["picks"] + [{"level": 2, "power": "Blaster_Ranged.Fire_Blast.Fire_Ball"}]

    def build(*powers, level=50):
        picks = list(base)
        for pw in powers:
            picks.append({"level": rules.pick_level(len(picks)), "power": pw})
        return dict(h, level=level, xp=rules.xp[level - 1], picks=picks)
    four = ["Pool.Flight.Combat_Flight", "Pool.Leaping.Combat_Jumping",
            "Pool.Speed.Hasten", "Pool.Medicine.Aid_Other"]
    check(rules.validate(build(*four)) == [], "four pool sets at levels 4, 6, 8, 10")
    e = rules.validate(build(*(four + ["Pool.Fighting.Boxing"])))
    check(e != [], "fifth pool set refused: %s" % e[:1])
    e = rules.validate(build("Pool.Sorcery.Arcane_Bolt", "Pool.Gadgetry.Wrist_Blaster"))
    check(e != [], "origin pools exclude each other: %s" % e[:1])
    e = rules.validate(build("Pool.Flight.Combat_Flight", "Pool.Flight.Air_Superiority",
                             "Pool.Flight.Afterburner"))
    check(e != [], "Afterburner refused before level 14: %s" % e[:1])
    # full greedy builds for every archetype, 1 -> 50: primary first, then
    # secondary, then pools and epics, all through options()
    for c in rules.player_classes():
        hero = rules.new_hero(c["class"], c["primary"][0].split(".", 1)[1],
                              c["secondary"][0].split(".", 1)[1], None, "T", None, None)
        for lvl in range(2, 51):
            hero["level"], hero["xp"] = lvl, rules.xp[lvl - 1]
            while True:
                o = rules.options(hero)
                if not o:
                    break
                hero["picks"].append({"level": lvl, "power": o[0]})
        rules.finish(hero)
        errs = rules.validate(hero)
        kinds = {}
        for p in hero["picks"]:
            k = rules.kind(hero, rules.set_of(p["power"]))
            kinds[k] = kinds.get(k, 0) + 1
        check(not errs and len(hero["picks"]) == 24,
              "%s 1-50: %d picks %s, %d auto %s" % (c["class"], len(hero["picks"]), kinds,
                                                     len(hero["auto_powers"]), errs[:2]))
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("defs")
    ap.add_argument("cmd", choices=["export", "new", "options", "pick", "level", "validate",
                                    "starters", "selftest"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--class", dest="cls", default="Class_Blaster")
    ap.add_argument("--primary")
    ap.add_argument("--secondary")
    ap.add_argument("--first")
    ap.add_argument("--name")
    ap.add_argument("--origin")
    ap.add_argument("--preset")
    a = ap.parse_args()
    rules = Rules(a.defs)

    if a.cmd == "export":
        data = rules.export()
        _save(os.path.join(a.path, "hero_rules.json"), data)
        print("archetypes %d, sets %d, pools %d, epics %d" % (
            len(data["archetypes"]), len(data["sets"]), len(data["pool_sets"]), len(data["epic_sets"])))
    elif a.cmd == "new":
        cls = next(c for c in rules.player_classes() if c["class"].lower() in
                   (a.cls.lower(), "class_" + a.cls.lower()))
        hero = rules.new_hero(a.cls, a.primary or cls["primary"][0].split(".", 1)[1],
                              a.secondary or cls["secondary"][0].split(".", 1)[1],
                              a.first, a.name, a.origin, a.preset)
        _save(a.path, hero)
        print(json.dumps({k: hero[k] for k in ("name", "class", "origin", "primary", "secondary",
                                               "picks", "auto_powers")}, indent=1))
    elif a.cmd == "options":
        hero = _load(a.path)
        o = rules.options(hero)
        print("\n".join(o) if o else "no pick open (next at level %s)" % hero.get("next_pick_level"))
    elif a.cmd == "pick":
        hero = _load(a.path)
        n = len(hero["picks"])
        if n >= rules.picks_allowed(hero["level"]):
            raise SystemExit("no pick open at level %d" % hero["level"])
        at = rules.pick_level(n)
        power = rules.power_ci.get(a.arg.lower(), a.arg)
        if power not in rules.powers:
            power = next((p for p in rules.options(hero) if p.lower().endswith("." + a.arg.lower())), a.arg)
        why = rules.can_pick(hero, power, at, hero["picks"])
        if why:
            raise SystemExit("%s: %s" % (power, why))
        hero["picks"].append({"level": at, "power": power})
        _save(a.path, rules.finish(hero))
        print("pick %d at level %d: %s" % (n + 1, at, power))
    elif a.cmd == "level":
        hero = _load(a.path)
        lvl = max(1, min(50, int(a.arg)))
        hero["level"], hero["xp"] = lvl, max(hero.get("xp", 0), rules.xp[lvl - 1])
        _save(a.path, rules.finish(hero))
        print("level %d, %d picks open" % (lvl, rules.picks_allowed(lvl) - len(hero["picks"])))
    elif a.cmd == "validate":
        errs = rules.validate(_load(a.path))
        print("\n".join(errs) if errs else "valid")
        return 1 if errs else 0
    elif a.cmd == "starters":
        for c in rules.player_classes():
            pri, sec, preset = STARTERS.get(c["class"], (
                c["primary"][0].split(".", 1)[1], c["secondary"][0].split(".", 1)[1], None))
            hero = rules.new_hero(c["class"], pri, sec, None,
                                  c["class"].replace("Class_", "") + " Starter", None, preset)
            _save(os.path.join(a.path, c["class"] + ".json"), hero)
            print(c["class"], [p["power"] for p in hero["picks"]])
    elif a.cmd == "selftest":
        return 0 if selftest(rules) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Rolls random rivals (CoH Reborn Nemesis system) from rival_data.json.

    python tools/rivals/gen_rivals.py                     # 12 random rivals, all stages
    python tools/rivals/gen_rivals.py --faction Hellions --count 5 --seed 7
    python tools/rivals/gen_rivals.py --path Skulls       # one rival grown stage 0 -> 5
    python tools/rivals/gen_rivals.py --catalog <out>/catalog.json   # check set names
    python tools/rivals/gen_rivals.py --selftest

A rival keeps its street handle for life; at stage 3 it gains a title, at
stage 4 (Breakout) it takes an origin and a signature power set, at stage 5
it becomes a Supervillain with a primary + secondary set. See
/mnt/project-files/research/nemesis-system.md for the design.
"""
import argparse
import json
import os
import random
import sys

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rival_data.json")


def load(path=DATA):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def new_rival(data, rng, faction=None, hero="", taken=()):
    """Stage 0 rival: a named minion with a memory. `taken` avoids duplicate handles for one hero."""
    faction = faction or rng.choice(sorted(data["factions"]))
    f = data["factions"][faction]
    free = [h for h in f["handles"] if h not in taken] or f["handles"]
    return {"id": "rv_%06x" % rng.getrandbits(24), "hero": hero, "faction": faction,
            "handle": rng.choice(free), "name": None, "stage": 0, "rank": "Minion",
            "traits": [], "origin": None, "power_sets": [], "crew_from": [faction],
            "customModel": None, "grudge": 1, "arrests": 0, "status": "free", "history": []}


def promote(data, rival, rng):
    """Moves a rival one stage up and rolls what that stage adds."""
    if rival["stage"] >= len(data["stages"]) - 1:
        return rival
    f = data["factions"][rival["faction"]]
    st = data["stages"][rival["stage"] + 1]
    rival["stage"], rival["rank"] = st["stage"], st["rank"]
    pool = [t for t in f["traits"] if t not in rival["traits"]]
    while len(rival["traits"]) < st["traits"] and pool:
        rival["traits"].append(pool.pop(rng.randrange(len(pool))))
    h = rival["handle"]
    if st["name"] in ("legend_titles", "super_titles"):
        rival["name"] = rng.choice(f[st["name"]]).format(h=h)
    elif st["name"] == "{prefix_or_handle}" and (f["prefixes"] or f["suffixes"]) and rng.random() < 0.5:
        if f["prefixes"] and (not f["suffixes"] or rng.random() < 0.5):
            rival["name"] = "%s %s" % (rng.choice(f["prefixes"]), h)
        else:
            rival["name"] = "%s %s" % (h, rng.choice(f["suffixes"]))
    if st.get("origin"):
        if not rival["origin"]:
            o = rng.choice(f["origins"])
            rival["origin"] = {"origin": o["origin"], "story": o["story"]}
            rival["power_sets"] = [rng.choice(o["power_sets"])]
        if st["id"] == "Supervillain" and len(rival["power_sets"]) < 2:
            o = next(x for x in f["origins"] if x["origin"] == rival["origin"]["origin"])
            rest = [p for p in o["power_sets"] if p not in rival["power_sets"]]
            if rest:
                rival["power_sets"].append(rng.choice(rest))
            rival["crew_from"] = sorted(set(f["crew_from"]) | {rival["faction"]})
    return rival


def display(r):
    return r["name"] or r["handle"]


def line(data, r):
    st = data["stages"][r["stage"]]["id"]
    s = "%-34s %-9s stage %d %-12s %-11s" % (display(r), r["faction"], r["stage"], st, r["rank"])
    if r["traits"]:
        s += " traits: " + ", ".join(r["traits"])
    if r["origin"]:
        s += " | %s (%s): %s" % (r["origin"]["origin"], r["origin"]["story"], " + ".join(r["power_sets"]))
    return s


def check_catalog(data, path):
    with open(path, encoding="utf-8") as f:
        names = {c["name"].lower() for c in json.load(f)}
    missing = sorted({p for fac in data["factions"].values() for o in fac["origins"]
                      for p in o["power_sets"] if p.lower() not in names})
    print("power sets not found in catalog:", missing or "none")
    return missing


def selftest():
    data = load()
    rng = random.Random(1)
    assert len(data["stages"]) == 6
    for fac, f in data["factions"].items():
        assert len(set(f["handles"])) == len(f["handles"]) >= 20, fac
        assert f["origins"] and all(o["power_sets"] for o in f["origins"]), fac
        for key in ("legend_titles", "super_titles"):
            assert all("{h}" in t for t in f[key]), (fac, key)
        r = new_rival(data, rng, fac, "Test")
        for _ in range(7):
            promote(data, r, rng)
        assert r["stage"] == 5 and r["rank"] == "Archvillain", r
        assert r["origin"] and len(r["power_sets"]) == 2, r
        assert len(r["traits"]) == 3 and r["name"], r
    taken = set()
    for _ in range(20):
        taken.add(new_rival(data, rng, "Hellions", "Test", taken)["handle"])
    assert len(taken) == 20
    print("selftest ok:", len(data["factions"]), "factions")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--faction")
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--path", metavar="FACTION", help="show one rival grown through all stages")
    ap.add_argument("--json", action="store_true", help="print records as JSON")
    ap.add_argument("--catalog")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    data = load()
    if a.catalog:
        return 1 if check_catalog(data, a.catalog) else 0
    rng = random.Random(a.seed)
    if a.path:
        r = new_rival(data, rng, a.path)
        print(line(data, r))
        for _ in range(5):
            print(line(data, promote(data, r, rng)))
        return
    out = []
    for _ in range(a.count):
        r = new_rival(data, rng, a.faction)
        for _ in range(rng.randrange(6)):
            promote(data, r, rng)
        out.append(r)
    out.sort(key=lambda r: -r["stage"])
    print(json.dumps(out, indent=1) if a.json else "\n".join(line(data, r) for r in out))


if __name__ == "__main__":
    sys.exit(main())

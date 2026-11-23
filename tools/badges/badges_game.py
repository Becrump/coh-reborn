"""Badges the game reads: the original's exploration, history, accomplishment,
achievement and defeat badges, compiled from the badge defs.

    python tools/badges/badges_game.py <i24>/data <out>

Reads <i24>/data/defs/badges.def (+ defs/badges/*.def), <out>/story/strings.json
(display text) and <out>/story/world_points.json (badge markers in the zones:
"namedvolume" tourism markers and "Plaque" history plaques, world_points.py).
Writes <out>/badges/badges_game.json:

  "badges": [{"id": "AtlasPark1", "category": "kTourism", "title": "...", "text": "...",
              "icon": "...", "requires": ["visits.AtlasPark1"]}]       requires: the
              original's postfix expression as tokens (kills.Hellions 100 >= ...)
  "spots":  [{"name": "atlaspark1", "pos": [x, y, z], "zone": "city_01_01"}]

Only badges a hero can earn in the core game are kept: no villain-side, event,
veteran, PvP, invention, architect, day job or incarnate badges.
"""
import glob
import json
import os
import re
import sys

KEEP = {"kTourism", "kHistory", "kAccomplishment", "kAchievement", "kDefeat"}
# stats the game keeps; a badge that needs anything else can't be earned yet
STATS = re.compile(r"^(visits\.|kills\.|level$|badgecount$|influence$|xpdebt$|damage$|healing$|time$|"
                   r"type$|alignment$|origin$|class$|hero$|char>$|owned\?$|eq$|[<>]=?$|&&$|\|\|$|!$|[+\-*/%]$|"
                   r"-?\d+(\.\d+)?$)")
VILLAIN = re.compile(r"villain|rogue|praetor", re.I)


def blocks(text):
    for b in re.findall(r"^\s*Badge\s*\{(.*?)^\s*\}", text, re.S | re.M):
        d = {}
        for line in b.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            k, _, v = line.partition(" ")
            d[k] = v.strip()
        yield d


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    data, out = sys.argv[1], sys.argv[2]
    text = ""
    for f in [os.path.join(data, "defs", "badges.def")] + sorted(glob.glob(os.path.join(data, "defs", "badges", "*.def"))):
        with open(f, encoding="latin-1") as fh:
            text += fh.read() + "\n"
    strings = json.load(open(os.path.join(out, "story", "strings.json"), encoding="utf-8"))
    s = lambda v: strings.get(v.strip('"'), v.strip('"'))  # noqa: E731
    points = json.load(open(os.path.join(out, "story", "world_points.json"), encoding="utf-8"))["zones"]
    spots, have = [], set()
    for zone, zp in points.items():
        for p in zp.get("badges", []):
            if "world_cm" in p:
                spots.append({"name": p["name"], "pos": p["world_cm"], "zone": zone})
                have.add(p["name"])
    # badges the story gives as reward tokens (SecondaryReward "TaskForceReward, SynapseTF"): the
    # original gives them outright (Requires 0); the game grants them when the task force is done
    tokens = set()
    sg = os.path.join(out, "story", "story_game.json")
    if os.path.isfile(sg):
        for t in json.load(open(sg, encoding="utf-8")).get("tasks", {}).values():
            tokens.update(x.lower() for x in t.get("secondary", []) + t.get("return_secondary", []))
    badges, seen, skipped = [], set(), 0
    for d in blocks(text):
        bid, cat = d.get("Name", ""), d.get("Category", "")
        req = d.get("Requires", "").split()
        if req == ["0"] and cat in KEEP and bid.lower() in tokens and d.get("DisplayTitle") and bid not in seen:
            seen.add(bid)
            badges.append({"id": bid, "category": cat, "title": s(d.get("DisplayTitle", bid)),
                           "text": s(d.get("DisplayText", "")), "icon": d.get("Icon", "").strip('"'),
                           "requires": ["0"]})
            continue
        if not bid or cat not in KEEP or bid in seen or not req or req == ["0"]:
            continue
        if any(not STATS.match(t) and not re.match(r"^[A-Za-z_0-9]+$", t) for t in req) \
                or any(VILLAIN.search(t) for t in req) or not d.get("DisplayTitle"):
            skipped += 1
            continue
        # an exploration badge whose marker is not in our zones can't be earned
        if any(t.startswith("visits.") and t[7:].lower() not in have for t in req):
            skipped += 1
            continue
        seen.add(bid)
        badges.append({"id": bid, "category": cat, "title": s(d.get("DisplayTitle", bid)),
                       "text": s(d.get("DisplayText", "")), "icon": d.get("Icon", "").strip('"'),
                       "requires": req})
    os.makedirs(os.path.join(out, "badges"), exist_ok=True)
    with open(os.path.join(out, "badges", "badges_game.json"), "w", encoding="utf-8") as f:
        json.dump({"badges": badges, "spots": spots}, f, ensure_ascii=False)
    by = {}
    for b in badges:
        by[b["category"]] = by.get(b["category"], 0) + 1
    print("badges %d %s (%d skipped), %d markers, badges_game.json written" % (len(badges), by, skipped, len(spots)))


if __name__ == "__main__":
    main()

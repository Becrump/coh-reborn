"""Indoor mission maps: pick the original layouts the hero tasks need, convert them for Unreal and
write where everything inside them is (start, encounters, objectives, rooms).

    python tools/missions/mission_maps.py <i24>/data <piggs> <out>/missions [--per 2] [--only id,id] [--redo]

Needs <out>/story/story_game.json next to <out>/missions (tools/story/story_game.py) for the
map sets and lengths the tasks ask for.

The original game picks a layout per mission: the task's MapSet + MapLength
(maps/missions/mission.mapspecs), or, with no MapSet, a set its villain group
can use (defs/generic/randommapselection.def). We convert --per layouts per
set and length (2 by default) and pick among them in the game.

Writes:
  <out>/missions/<id>/            converter output (coh2unreal --instanced), editor markers left out
  <out>/missions/missions.json    {"sets": {set: {length: [id]}}, "select": [...], "maps": {id: {...}}}

Per map: "start" (player spawn, Unreal cm, yaw), "exit" (MissionReturn spawn or start),
"rooms" [{id, center, rank}] rank = Lobby / Front / Middle / Back by distance from the start,
"encounters" [{pos, yaw, room, kind, rank, spots: [[x,y,z,yaw], ...]}],
"objectives" {"ItemFloor"|"ItemAgainstWall"|"PersonObjective": [{pos, yaw, room, rank}]},
"bounds" [min xyz, max xyz]. Positions are local to the map; the game moves the map where it loads it.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
CONVERTER = os.path.join(REPO, "coh2unreal")
sys.path.insert(0, CONVERTER)
from coh2unreal.pigg import AssetStore  # noqa: E402
from coh2unreal import maplayout as ml  # noqa: E402
from coh2unreal.export import ue_transform  # noqa: E402

OBJECTIVE_KEYS = ("itemfloor", "itemagainstwall", "personobjective")
OBJECTIVE_NAME = {"itemfloor": "ItemFloor", "itemagainstwall": "ItemAgainstWall",
                  "personobjective": "Person"}


def parse_mapspecs(text):
    """{set (lower): {"name": set, "times": {length: [map rel path]}}}"""
    out, cur, time_ = {}, None, None
    for raw in text.splitlines():
        s = raw.split("//")[0].strip()
        m = re.match(r"MissionSet\s+(\S+)", s)
        if m:
            cur = out.setdefault(m.group(1).lower(), {"name": m.group(1), "times": {}})
            continue
        m = re.match(r"Time\s+(\d+)", s)
        if m and cur is not None:
            time_ = int(m.group(1))
            cur["times"].setdefault(time_, [])
            continue
        m = re.match(r"Map\s+(\S+)", s)
        if m and cur is not None and time_ is not None:
            cur["times"][time_].append(m.group(1).replace("\\", "/"))
    return out


def parse_selection(text):
    """[{groups: [lower], min, max, set}] from randommapselection.def"""
    out = []
    for block in re.findall(r"MapSelection\s*\{(.*?)\}", text, re.S):
        d = {}
        for line in block.splitlines():
            p = line.split(None, 1)
            if len(p) == 2:
                d[p[0].lower()] = p[1].strip()
        out.append({"groups": [g.strip().lower() for g in d.get("villaingroups", "").split(",") if g.strip()],
                    "min": int(d.get("minlevel", 1)), "max": int(d.get("maxlevel", 50)),
                    "set": d.get("mapset", "")})
    return out


def real_path(data, rel):
    """case-insensitive file lookup (the specs are mixed case, the files are not always)"""
    cur = data
    for part in rel.split("/"):
        if not os.path.isdir(cur):
            return None
        names = {n.lower(): n for n in os.listdir(cur)}
        n = names.get(part.lower())
        if n is None:
            return None
        cur = os.path.join(cur, n)
    return os.path.relpath(cur, data).replace("\\", "/") if os.path.isfile(cur) else None


def map_id(rel):
    return re.sub(r"[^a-z0-9_]", "_", os.path.splitext(os.path.basename(rel))[0].lower())


def needed(story, specs, selection):
    """{(set lower, length)} the hero tasks can ask for"""
    want = set()
    for t in story["tasks"].values():
        m = t.get("mission")
        if t.get("type") != "mission" or not m:
            continue
        length = m.get("length") or 15
        sets = [m["mapset"].lower()] if m.get("mapset") else \
            [s["set"].lower() for s in selection if (m.get("group") or "").lower() in s["groups"]]
        if not sets:
            sets = ["warehouse", "office"]
        for s in sets:
            if s in specs:
                want.add((s, length))
    return want


def pick(specs, want, per, data):
    """[(set, length, rel)] up to `per` existing layouts per pair, nearest length when one is missing"""
    out = []
    for s, length in sorted(want):
        times = specs[s]["times"]
        if not times:
            continue
        t = length if length in times and times[length] else min(
            (k for k in times if times[k]), key=lambda k: abs(k - length), default=None)
        if t is None:
            continue
        maps = [real_path(data, r) for r in times[t]]
        maps = [r for r in maps if r]
        # spread the picks over the list (layout families differ, variants _01/_02 barely do)
        step = max(1, len(maps) // per) if maps else 1
        for r in maps[::step][:per]:
            out.append((specs[s]["name"], length, r))
    return out


def walk_markers(store, lib, rel):
    """markers of one layout: (kind, props, ue loc, yaw, path, room)"""
    local, refs = ml.load_map(store, lib, rel)
    found = []

    def find(name):
        k = ml.short_name(name)
        return local.get(k) or lib.defs.get(k)

    def walk(name, mat, path, room, depth):
        d = find(name)
        if d is None or depth > 64:
            return
        if room is None and d.source and "/trays/" in d.source.lower():
            room = path
        if d.props:
            loc, rot, _s = ue_transform(mat)
            found.append((dict(d.props), loc, rot[1], path, room))
        for child, pos, pyr in d.groups:
            walk(child, ml.mat_mul(mat, ml.mat_from_pyr(pos, pyr)), path + "/" + ml.short_name(child),
                 room, depth + 1)

    for i, (name, pos, pyr) in enumerate(refs):
        walk(name, ml.mat_from_pyr(pos, pyr), "%d:%s" % (i, ml.short_name(name)), None, 0)
    return found


def build_markers(found, bounds):
    start = exit_ = None
    rooms = {}
    encounters, objectives = [], {v: [] for v in OBJECTIVE_NAME.values()}
    groups = []
    for props, loc, yaw, path, room in found:
        if room:
            rooms.setdefault(room, []).append(loc)
        sl = props.get("spawnlocation", "").lower()
        if sl and sl.startswith("_lobby") and start is None:
            start = {"pos": loc, "yaw": yaw, "room": room}
        if props.get("gotospawn", "").lower() == "missionreturn" and exit_ is None:
            exit_ = {"pos": loc, "yaw": yaw}
        if "encountergroup" in props:
            groups.append((path, {"pos": loc, "yaw": yaw, "room": room, "kind": "", "spots": []}))
        for k in OBJECTIVE_KEYS:
            if k in props:
                objectives[OBJECTIVE_NAME[k]].append({"pos": loc, "yaw": yaw, "room": room})
    # encounter spots and spawn kind belong to the group whose path they sit under
    for props, loc, yaw, path, room in found:
        if "encounterposition" not in props and "encounterspawn" not in props:
            continue
        best = None
        for gp, g in groups:
            if path == gp or path.startswith(gp + "/"):
                if best is None or len(gp) > len(best[0]):
                    best = (gp, g)
        if best is None:
            continue
        g = best[1]
        if "encounterspawn" in props and not g["kind"]:
            g["kind"] = props["encounterspawn"]
        if "encounterposition" in props:
            g["spots"].append([loc[0], loc[1], loc[2], yaw])
    encounters = [g for _p, g in groups]
    if start is None:   # no lobby marker: the room nearest the bounds' min corner
        start = {"pos": [bounds[0][0], bounds[0][1], bounds[0][2] + 100], "yaw": 0.0, "room": None}
    # rooms ranked by distance from the start room
    centers = {r: [sum(p[i] for p in pts) / len(pts) for i in range(3)] for r, pts in rooms.items()}
    sp = start["pos"]
    dist = {r: math.dist(c, sp) for r, c in centers.items()}
    order = sorted((r for r in centers if r != start.get("room")), key=lambda r: dist[r])
    rank = {start.get("room"): "Lobby"}
    n = len(order)
    for i, r in enumerate(order):
        rank[r] = "Front" if i < n / 3 else ("Middle" if i < 2 * n / 3 else "Back")
    room_ids = {r: k for k, r in enumerate(sorted(centers, key=lambda r: dist[r]))}

    def tag(x):
        x["rank"] = rank.get(x.get("room"), "Middle")
        x["room"] = room_ids.get(x.get("room"), -1)
        return x
    for e in encounters:
        tag(e)
    for lst in objectives.values():
        for o in lst:
            tag(o)
    start["room"] = room_ids.get(start.get("room"), -1)
    return {"start": start, "exit": exit_ or {"pos": start["pos"], "yaw": start["yaw"]},
            "rooms": [{"id": room_ids[r], "center": [round(v, 1) for v in centers[r]], "rank": rank[r]}
                      for r in sorted(centers, key=lambda r: room_ids[r])],
            "encounters": encounters, "objectives": objectives, "bounds": bounds}


def convert(data, piggs, out, mid, rel, redo):
    d = os.path.join(out, mid)
    if os.path.isfile(os.path.join(d, "DONE.txt")) and not redo:
        return True, "already done"
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "convert.log"), "w") as log:
        rc = subprocess.run([sys.executable, "-m", "coh2unreal", "--data", data, "--piggs", piggs,
                             "--map", rel, "--out", d, "--name", mid, "--instanced"],
                            cwd=CONVERTER, stdout=log, stderr=subprocess.STDOUT).returncode
    if rc:
        return False, "converter exit %d, see %s" % (rc, os.path.join(d, "convert.log"))
    # editor markers (Omni library: spawn beacons, encounter dummies, light helpers) stay out of the level
    inst = json.load(open(os.path.join(d, mid + "_instances.json")))
    skip = sorted({i["model"] for i in inst if i["geo"].lower().startswith("object_library/omni/")})
    rows = json.load(open(os.path.join(d, mid + "_placements.json")))
    keep = [r for r in rows if r["m"].split("__")[0] not in skip and r["m"] not in skip]
    json.dump(keep, open(os.path.join(d, mid + "_placements.json"), "w"), separators=(",", ":"))
    g = json.load(open(os.path.join(d, mid + ".gltf")))
    skip_meshes = sorted(m["name"] for m in g["meshes"] if m["name"].split("__")[0] in skip)
    json.dump(skip_meshes, open(os.path.join(d, "skip_meshes.json"), "w"))
    rep = open(os.path.join(d, "convert.log"), encoding="utf-8", errors="replace").read()
    missing = re.findall(r"^(missing_geo|missing_model|bad_geo): (\d+)", rep, re.M)
    note = ", ".join("%s %s" % m for m in missing if m[1] != "0") or "nothing missing"
    with open(os.path.join(d, "DONE.txt"), "w") as f:
        f.write("%s\n%d placements (%d markers left out)\n" % (note, len(keep), len(rows) - len(keep)))
    return True, note


def bounds_of(d, mid):
    rows = json.load(open(os.path.join(d, mid + "_placements.json")))
    if not rows:
        return [[0, 0, 0], [0, 0, 0]]
    lo = [min(r["l"][i] for r in rows) for i in range(3)]
    hi = [max(r["l"][i] for r in rows) for i in range(3)]
    return [[round(v, 1) for v in lo], [round(v, 1) for v in hi]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("piggs")
    ap.add_argument("out")
    ap.add_argument("--per", type=int, default=2)
    ap.add_argument("--only", default="")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--list", action="store_true", help="only print the picked layouts")
    a = ap.parse_args()
    specs = parse_mapspecs(open(os.path.join(a.data, "maps", "missions", "mission.mapspecs"),
                                encoding="latin-1").read())
    selection = parse_selection(open(os.path.join(a.data, "defs", "generic", "randommapselection.def"),
                                     encoding="latin-1").read())
    story = json.load(open(os.path.join(os.path.dirname(os.path.abspath(a.out)), "story", "story_game.json")))
    picks = pick(specs, needed(story, specs, selection), a.per, a.data)
    only = set(a.only.split(",")) if a.only else None
    print("%d layouts for %d set/length pairs" % (len(picks), len({(s, t) for s, t, _r in picks})), flush=True)
    if a.list:
        for s, t, r in picks:
            print("%-22s %3d  %s" % (s, t, r))
        return 0
    os.makedirs(a.out, exist_ok=True)
    idx_path = os.path.join(a.out, "missions.json")
    index = json.load(open(idx_path)) if os.path.isfile(idx_path) else {}
    index.setdefault("maps", {})
    index["units"] = "Unreal cm, local to the map (X = game x, Y = -game z)"
    index["sets"] = {}
    index["select"] = selection
    store = AssetStore(data_dirs=[a.data], pigg_paths=[])
    lib = ml.Library(store)
    fails = 0
    for s, t, rel in picks:
        mid = map_id(rel)
        index["sets"].setdefault(s, {}).setdefault(str(t), [])
        if mid not in index["sets"][s][str(t)]:
            index["sets"][s][str(t)].append(mid)
        if only and mid not in only:
            continue
        t0 = time.time()
        ok, note = convert(a.data, a.piggs, a.out, mid, rel, a.redo)
        if not ok:
            fails += 1
            print("FAIL %-36s %s" % (mid, note), flush=True)
            continue
        if mid not in index["maps"] or a.redo:
            mk = build_markers(walk_markers(store, lib, rel.lower() if rel.lower() in store else rel),
                               bounds_of(os.path.join(a.out, mid), mid))
            mk.update({"set": s, "length": t, "source": rel})
            index["maps"][mid] = mk
            json.dump(index, open(idx_path, "w"))
        m = index["maps"][mid]
        print("OK   %-36s %-20s %2d rooms, %3d encounters, objectives %s; %s (%.0fs)" % (
            mid, s, len(m["rooms"]), len(m["encounters"]),
            "/".join(str(len(v)) for v in m["objectives"].values()), note, time.time() - t0), flush=True)
    json.dump(index, open(idx_path, "w"))
    print("missions.json: %d maps" % len(index["maps"]))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

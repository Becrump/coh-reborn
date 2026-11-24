"""The original game's civilians and traffic for every outdoor zone: who walks
and drives, how many, where they appear and the beacon networks they follow.

    python tools/zones/civilians.py <i24>/data <out_dir>/civilians [zone ...]

Writes <out_dir>/civilians/<zone>.json (one per zone, below), civilians.json
(the index: zone -> name, offset_cm, counts) and models.json (every civilian
and vehicle costume, for the character export). Positions are Unreal cm, local to
the zone plus "offset_cm" for zones placed in the one world
(world = local + offset, as zone_events.py).

How the original server did it (MapServer/src/generator/entgen*.c,
ai/entaiNPC.c, ai/entaiCar.c, beacon/beaconConnection.c):

* data/server/spawnarea/globals.txt, then <map>.txt over it, define NPC and
  Car types (a list of NPC costumes, MaxActiveEntities, RunSpeed feet per
  tick + RunSpeedVariation * rand(-1..1), ScaredType, BeaconTypeNumber) and
  Generators (MaxActiveEntities alive per generator, MaxSpawnCount,
  GeneratedTypes). The SpawnArea caps NPCs and cars together at MaxNPCCount.
* Map objects with the property Generator (Omni/NPC "NPCGenerator", Omni/CAR
  "CarGenerator", boats ...) are the spawn points. About once a second every
  generator under its caps makes one entity of a random generated type with
  a random costume of that type.
* Civilians walk from beacon to beacon on the wire of BasicBeacons (Omni/NAV,
  radius r feet): two beacons link when their XZ distance is under
  max(r1, r2) + 3 ft and nothing blocks the way. Each step picks a random
  linked beacon (not the one it came from) and aims a random point up to
  NPCBeaconRadius (3 ft) around it. With nowhere to go they are removed.
  They walk (run speed / 4.8, the walk cycle) and run only when scared:
  ScaredType 1 stops, faces the danger for 1 s, turns back and walks away
  (5 s); ScaredType 0 cowers and runs for 20 s.
* Cars drive TrafficBeacons (lane arrows built into road pieces, facing
  their local Z): source -> target when the target is within the source's
  radius, under 20 ft higher or lower, ahead of it (80 deg), facing a
  similar way (120 deg) and reached from behind (90 deg); BeaconGroup digits
  restrict curve heads ("0" in the group) to matching groups, TypeNumber must
  match (boats, the monorail). A KillerBeacon removes the car.

    <zone>.json: {"zone": "city_02_01", "name": "Steel Canyon", "offset_cm": [x, y],
        "area": {"max_npc": 600},
        "types": {"NPC_Male_Buisness": {"kind": "npc", "costumes": [...],
                  "max": 600, "run": 0.7, "run_var": 0.3, "scared": 1, "typenum": 0}},
        "generators": {"NPCGenerator": {"max": 10, "spawn_max": -1, "types": [...]}},
        "spawns": [{"gen": "NPCGenerator", "p": [x, y, z], "yaw": deg}],
        "wire": {"p": [[x, y, z] ...], "r": [cm ...], "links": [[i, j] ...]},
        "traffic": {"p": [...], "yaw": [...], "kill": [i ...], "typenum": [...], "next": [[j ...] ...]}}
"""
import json
import math
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "coh2unreal"))
from coh2unreal.pigg import AssetStore  # noqa: E402
from coh2unreal import maplayout as ml  # noqa: E402

FT = 30.48
# seasonal / event / test layers: the everyday city only
SKIP = re.compile(r"halloween|winter|valentine|holiday|anniversary|beta|event|invasion|"
                  r"shutdown|kraken|zowie|_i\d+_prep|temp_", re.I)
ENT_KINDS = {"npc": "npc", "car": "car", "critter": "critter"}


# ---------------------------------------------------------------- spawn areas
def parse_spawnarea(text, into=None):
    """{types, generators, area} from a spawnarea file, over `into`."""
    res = into or {"types": {}, "generators": {}, "area": {}}
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    cur, kind, depth = None, None, 0
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].split("#", 1)[0].strip()
        if not line:
            continue
        tok = line.split(None, 1)
        key, rest = tok[0], (tok[1] if len(tok) > 1 else "")
        k = key.lower()
        if k == "spawnarea":
            depth = 1
            continue
        if k in ("endspawnarea",):
            depth = 0
            continue
        if k == "end" or k.startswith("end/"):
            if cur is not None:
                cur = None
            else:
                depth = 0
            continue
        if depth == 0:
            continue
        if cur is None:
            if k in ENT_KINDS or k in ("door", "autodoor", "maptransferdoor", "deliverytarget"):
                name = rest.strip()
                cur = res["types"].setdefault(name, {})
                cur.clear()
                cur.update({"kind": ENT_KINDS.get(k, "door"), "costumes": []})
                kind = "type"
            elif k in ("generator", "generatorgroup", "spawngroup"):
                name = rest.strip()
                cur = res["generators"].setdefault(name, {})
                cur.clear()
                cur.update({"types": []})
                kind = "gen"
            else:
                res["area"][k] = rest.strip()
            continue
        vals = [v.strip() for v in rest.split(",") if v.strip()]
        if kind == "type":
            if k == "type":
                cur["costumes"] += vals
            elif k == "maxactiveentities":
                cur["max"] = _int(rest)
            elif k == "runspeed":
                cur["run"] = float(rest.split()[0])
            elif k == "runspeedvariation":
                cur["run_var"] = float(rest.split()[0])
            elif k == "scaredtype":
                cur["scared"] = _int(rest)
            elif k == "beacontypenumber":
                cur["typenum"] = _int(rest)
            elif k == "groundoffset":
                cur["ground"] = float(rest.split()[0])
        else:
            if k == "generatedtypes":
                cur["types"] += vals
            elif k == "maxactiveentities":
                cur["max"] = _int(rest)
            elif k == "maxspawncount":
                cur["spawn_max"] = _int(rest)
            elif k == "activationinterval":
                cur["interval"] = _int(rest)
    return res


def _int(s):
    s = s.strip().split()[0] if s.strip() else "0"
    return -1 if s.lower() == "infinite" else int(float(s))


def spawn_rules(data, zone):
    base = os.path.join(data, "server", "spawnarea")
    files = {f.lower(): f for f in os.listdir(base)}
    res = parse_spawnarea(open(os.path.join(base, files["globals.txt"]), encoding="latin-1").read())
    res = json.loads(json.dumps(res))
    own = files.get(zone.lower() + ".txt")
    if own:
        parse_spawnarea(open(os.path.join(base, own), encoding="latin-1").read(), res)
    return res, bool(own)


# ---------------------------------------------------------------- beacons
class Collector:
    """Walks a zone's layers, memoising each definition's beacons and
    generator points relative to the definition (a road piece holds the
    same dozen arrows wherever it is placed)."""

    def __init__(self, lib):
        self.lib = lib
        self.memo = {}

    def items(self, df, local, depth=0):
        key = id(df)
        if key in self.memo:
            return self.memo[key]
        out = []
        self.memo[key] = out          # cycles: empty while being built
        if depth > 40:
            return out
        if df.beacon:
            out.append(("beacon", ml.IDENTITY, df))
        gen = df.props.get("generator")
        if gen:
            out.append(("gen", ml.IDENTITY, df))
        for child, pos, pyr in df.groups:
            cd = local.get(ml.short_name(child)) or self.lib.defs.get(ml.short_name(child))
            if cd is None:
                continue
            sub = self.items(cd, local, depth + 1)
            if sub:
                m = ml.mat_from_pyr(pos, pyr)
                out += [(k, ml.mat_mul(m, mm), d) for k, mm, d in sub]
        return out


def ue_pos(m):
    x, y, z = m[3]
    return [round(x * FT, 1), round(-z * FT, 1), round(y * FT, 1)]


def ue_yaw(m):
    """Unreal yaw (deg) of a matrix's local Z (the way CoH beacons face)."""
    x, _y, z = m[2]
    return round(math.degrees(math.atan2(-z, x)), 2)


def coh_yaw(m):
    x, _y, z = m[2]
    return math.atan2(x, z)


def zone_points(store, lib, data, zone):
    d = os.path.join(data, "maps", "city_zones", zone)
    layers = sorted(f for f in os.listdir(d) if f.lower().endswith(".txt") and f.lower() != zone + ".txt"
                    and not SKIP.search(f))
    col = Collector(lib)
    basic, traffic, gens = [], [], []
    seen = set()
    for layer in layers:
        rel = "maps/city_zones/%s/%s" % (zone, layer)
        local, refs = ml.load_map(store, lib, rel)
        col.memo.clear()
        for name, pos, pyr in refs:
            df = local.get(ml.short_name(name)) or lib.defs.get(ml.short_name(name))
            if df is None:
                continue
            top = ml.mat_from_pyr(pos, pyr)
            for kind, mm, bd in col.items(df, local):
                m = ml.mat_mul(top, mm)
                key = (kind, bd.name.lower(), tuple(round(v, 1) for v in m[3]))
                if key in seen:
                    continue
                seen.add(key)
                if kind == "gen":
                    gens.append((bd.props["generator"], m))
                elif bd.beacon[0].lower() == "basicbeacon":
                    basic.append((m, math.ceil(bd.beacon[1]), "npcnoautoconnect" in bd.props))
                elif bd.beacon[0].lower() == "trafficbeacon":
                    traffic.append((m, math.ceil(bd.beacon[1]), bd.props))
    return basic, traffic, gens


def grid_pairs(points, cell):
    """Yields (i, j), i < j, for points within neighbouring cells (XZ feet)."""
    g = defaultdict(list)
    for i, (x, z) in enumerate(points):
        g[(int(x // cell), int(z // cell))].append(i)
    for (cx, cz), idx in g.items():
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for j in g.get((cx + dx, cz + dz), ()):
                    for i in idx:
                        if i < j:
                            yield i, j


def wire_links(basic):
    """Original BasicBeacon links (beaconConnection.c BEACONTYPE_BASIC); the
    game checks the line of sight the original also needed."""
    pts = [(m[3][0], m[3][2]) for m, _r, _n in basic]
    cell = max([r for _m, r, _n in basic] + [1]) + 3
    links = []
    for i, j in grid_pairs(pts, cell):
        (mi, ri, _), (mj, rj, _) = basic[i], basic[j]
        maxd = max(ri, rj) + 3
        if (mi[3][0] - mj[3][0]) ** 2 + (mi[3][2] - mj[3][2]) ** 2 < maxd * maxd and abs(mi[3][1] - mj[3][1]) < 20:
            links.append([i, j])
    return links


def sub_angle(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return d


def group_flags(s):
    f = 0
    for ch in (s or "").lower():
        if "0" <= ch <= "9":
            f |= 1 << (ord(ch) - 48)
        elif "a" <= ch <= "f":
            f |= 1 << (10 + ord(ch) - 97)
    return f


def traffic_links(traffic):
    """beaconCanConnectToTrafficBeacon, then the contingency rule for arrows
    with no way on (turned round, the nearest suitable arrow)."""
    n = len(traffic)
    pos = [m[3] for m, _r, _p in traffic]
    yaw = [coh_yaw(m) for m, _r, _p in traffic]
    flags = [group_flags(p.get("beacongroup")) for _m, _r, p in traffic]
    tnum = [int(float(p.get("typenumber") or 0)) for _m, _r, p in traffic]
    rad = [r for _m, r, _p in traffic]
    cell = max(rad + [1])
    g = defaultdict(list)
    for i, p in enumerate(pos):
        g[(int(p[0] // cell), int(p[2] // cell))].append(i)

    def near(i):
        cx, cz = int(pos[i][0] // cell), int(pos[i][2] // cell)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                yield from g.get((cx + dx, cz + dz), ())

    nxt = []
    for s in range(n):
        out = []
        for t in near(s):
            if t == s:
                continue
            d = [pos[t][k] - pos[s][k] for k in range(3)]
            if d[0] ** 2 + d[1] ** 2 + d[2] ** 2 >= rad[s] ** 2 or abs(d[1]) >= 20:
                continue
            if flags[s] & 1 and ((flags[t] & 1) or not ((flags[t] & ~1) & flags[s])):
                continue
            if tnum[s] != tnum[t]:
                continue
            head = math.atan2(d[0], d[2])
            if (abs(sub_angle(yaw[s], head)) < math.radians(80) and
                    abs(sub_angle(yaw[s], yaw[t])) < math.radians(120) and
                    abs(sub_angle(head, yaw[t])) < math.radians(90)):
                out.append(t)
        if not out:
            back = yaw[s] + math.pi
            best, bd = None, 0
            for t in range(n):
                if t == s:
                    continue
                d = [pos[t][k] - pos[s][k] for k in range(3)]
                head = math.atan2(d[0], d[2])
                if abs(sub_angle(back, yaw[t])) < math.radians(120) and abs(sub_angle(head, yaw[t])) < math.radians(120):
                    dd = d[0] ** 2 + d[1] ** 2 + d[2] ** 2
                    if best is None or dd < bd:
                        best, bd = t, dd
            if best is not None:
                out.append(best)
        nxt.append(out)
    return nxt, tnum


# ---------------------------------------------------------------- main
def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    data, out = sys.argv[1], sys.argv[2]
    offsets = json.load(open(os.path.join(REPO, "docs", "zones", "zone_offsets.json")))["zones"]
    city = os.path.join(data, "maps", "city_zones")
    zones = sys.argv[3:] or sorted(z for z in os.listdir(city) if os.path.isdir(os.path.join(city, z)))
    store = AssetStore(data_dirs=[data], pigg_paths=[])
    lib = ml.Library(store)
    result = {"units": "Unreal cm, zone local; world = local + offset_cm (X, Y)",
              "files": "<zone>.json beside this index", "zones": {}}
    costumes = set()
    for zone in zones:
        if not os.path.isdir(os.path.join(city, zone)):
            continue
        rules, own = spawn_rules(data, zone)
        basic, traffic, gens = zone_points(store, lib, data, zone)
        types, generators = rules["types"], rules["generators"]
        live = {}
        spawns = []
        for gname, m in gens:
            gd = generators.get(gname)
            if not gd:
                continue
            kinds = {types.get(t, {}).get("kind") for t in gd["types"]}
            if not kinds & {"npc", "car"}:
                continue                           # doors and critter spawners
            live[gname] = gd
            spawns.append({"gen": gname, "p": ue_pos(m), "yaw": ue_yaw(m)})
        if not spawns and not basic:
            continue
        used = {t: dict(types[t]) for gd in live.values() for t in gd["types"] if t in types}
        for t in used.values():
            costumes.update(t["costumes"])
        off = offsets.get(zone, {}).get("offset_m")
        nxt, tnum = traffic_links(traffic) if traffic else ([], [])
        z = {"zone": zone, "name": offsets.get(zone, {}).get("name", zone),
             "offset_cm": [round(off[0] * 100.0, 1), round(-off[1] * 100.0, 1)] if off else None,
             "own_rules": own,
             "area": {"max_npc": _int(rules["area"].get("maxnpccount", "600")),
                      "max_active": _int(rules["area"].get("maxactiveentities", "1000000"))},
             "types": used, "generators": live, "spawns": spawns,
             "wire": {"p": [ue_pos(m) for m, _r, _n in basic],
                      "r": [round(r * FT, 1) for _m, r, _n in basic],
                      "noauto": [i for i, (_m, _r, n) in enumerate(basic) if n],
                      "links": wire_links(basic)},
             "traffic": {"p": [ue_pos(m) for m, _r, _p in traffic],
                         "yaw": [ue_yaw(m) for m, _r, _p in traffic],
                         "kill": [i for i, (_m, _r, p) in enumerate(traffic) if p.get("killerbeacon")],
                         "typenum": tnum, "next": nxt}}
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, zone + ".json"), "w") as f:
            json.dump(z, f, separators=(",", ":"))
        result["zones"][zone] = {"name": z["name"], "offset_cm": z["offset_cm"], "spawns": len(spawns),
                                 "wire": len(basic), "traffic": len(traffic)}
        by = defaultdict(int)
        for s in spawns:
            by[s["gen"]] += 1
        print("%-16s %4d wire beacons %5d links, %5d lane arrows, spawns %s" % (
            zone, len(basic), len(z["wire"]["links"]), len(traffic),
            ", ".join("%s %d" % kv for kv in sorted(by.items())) or "none"), flush=True)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "civilians.json"), "w") as f:
        json.dump(result, f, indent=1)
    with open(os.path.join(out, "models.json"), "w") as f:
        json.dump(sorted(costumes), f, indent=0)
    print("civilians.json: %d zones, %d civilian and vehicle costumes" % (len(result["zones"]), len(costumes)))


if __name__ == "__main__":
    main()

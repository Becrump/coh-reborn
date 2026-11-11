"""Original enemy encounters for every zone, in the format the game reads.

For each zone this writes two files into <out>/<zone>/:

  encounters.json  the zone's spawn definitions, same schema as Atlas Park's
                   (tools/ai/coh_encounters.py; read by UCoHGameRules): level
                   band, team size, respawn, actors with group/rank/villain,
                   idle/alerted behavior and the villain defs each slot can
                   roll per level.
  sites.json       every original encounter spot: which spawn definitions it
                   can use (CanSpawnN), its slot positions, and transforms in
                   Unreal cm, both zone-local and world (zone_offsets.json).

Sites come from all of a zone's spawn layers (*spawndefs*, *spawns*), so
Kings Row's per-district layers are included. Spawn definitions from
seasonal/zone-event folders (ZoneEvents, Halloween, Winter ...) are marked
"event": true so the normal city population can leave them out.

    python tools/zones/encounters.py <i24>/data <out_dir> [zone ...]

Needs the i24 sparse paths data/maps/city_zones, data/object_library,
data/defs and data/scripts.loc/spawndefs.
"""
import collections
import hashlib
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "coh2unreal"))
sys.path.insert(0, os.path.join(REPO, "tools", "ai"))
sys.path.insert(0, os.path.join(REPO, "tools", "rules"))
from coh2unreal.pigg import AssetStore  # noqa: E402
from coh2unreal import maplayout as ml  # noqa: E402
from coh2unreal.export import ue_transform  # noqa: E402
import coh_encounters as ce  # noqa: E402
import coh_rules  # noqa: E402

# Property "Name" "Value" 0  or, in older files, Property Name Value 0
PROP = re.compile(r'^\s*Property\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]*)"|(\S+))', re.I)
EVENT = re.compile(r"zoneevent|halloween|winter|valentine|rikti_?invasion|"
                   r"beta_?event|anniversary|spring|summer|event", re.I)


def props_of(text):
    """{def name (lower): {property: value}} for top-level properties."""
    out, cur, depth = {}, None, 0
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^(Def|RootMod)\s", line):
            cur, depth = s.split()[1].lower(), 0
            continue
        if cur is None:
            continue
        if s.startswith("Group "):
            depth += 1
        elif s == "End":
            if depth:
                depth -= 1
            else:
                cur = None
        elif depth == 0:
            m = PROP.match(line)
            if m:
                out.setdefault(cur, {})[m.group(1) or m.group(2)] = \
                    m.group(3) if m.group(3) is not None else m.group(4)
    return out


def norm_ref(ref):
    """CanSpawn value -> spawndef key relative to scripts.loc, lower case."""
    r = ref.replace("\\", "/").strip().lower()
    if not r.startswith("spawndefs/"):
        r = "spawndefs/" + r
    return r


def zone_layers(data, zone):
    d = os.path.join(data, "maps", "city_zones", zone)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d)
                  if "spawn" in f.lower() and f.lower().endswith(".txt"))


def collect_sites(store, lib, data, zone, omni_props):
    props = dict(omni_props)
    sites = []
    for layer in zone_layers(data, zone):
        rel = "maps/city_zones/%s/%s" % (zone, layer)
        with open(os.path.join(data, rel), encoding="latin-1") as f:
            props.update(props_of(f.read()))
        local, refs = ml.load_map(store, lib, rel)

        def find(name):
            k = ml.short_name(name)
            return local.get(k) or lib.defs.get(k)

        def walk(name, mat, path, depth, site, layout):
            d = find(name)
            if d is None or depth > 48:
                return
            p = props.get(d.name.lower(), {})
            starts = "EncounterGroup" in p or (site is None and (
                "EncounterSpawn" in p or any(k.lower().startswith("canspawn") for k in p)))
            if starts:  # older zones (Skyway) have bare ES_ defs, no group
                loc, rot, _s = ue_transform(mat)
                site = {"id": hashlib.sha1((layer + path).encode()).hexdigest()[:12],
                        "layer": layer, "group_def": d.name,
                        "probability": p.get("SpawnProbability"),
                        "local_cm": [round(v, 1) for v in loc],
                        "yaw_deg": round(rot[1], 1),
                        "spawndefs": [], "layouts": []}
                sites.append(site)
                layout = None
            if site is not None:
                cans = [norm_ref(v) for k, v in sorted(p.items())
                        if k.lower().startswith("canspawn") and v.strip()]
                for c in cans:
                    if c not in site["spawndefs"]:
                        site["spawndefs"].append(c)
                if "EncounterSpawn" in p:
                    loc, rot, _s = ue_transform(mat)
                    layout = {"spawn": p["EncounterSpawn"], "def": d.name,
                              "local_cm": [round(v, 1) for v in loc],
                              "yaw_deg": round(rot[1], 1), "positions": []}
                    site["layouts"].append(layout)
                if "EncounterPosition" in p and layout is not None:
                    loc, rot, _s = ue_transform(mat)
                    layout["positions"].append(
                        {"slot": p["EncounterPosition"],
                         "local_cm": [round(v, 1) for v in loc],
                         "yaw_deg": round(rot[1], 1)})
            for n, (child, pos, pyr) in enumerate(d.groups):
                walk(child, ml.mat_mul(mat, ml.mat_from_pyr(pos, pyr)),
                     "%s/%d:%s" % (path, n, ml.short_name(child)), depth + 1,
                     site, layout)

        for name, pos, pyr in refs:
            walk(name, ml.mat_from_pyr(pos, pyr), name, 0, None, None)
    return [s for s in sites if s["spawndefs"] or s["layouts"]]


def build_encounters(index, roller, villains, refs):
    """Same records as coh_encounters.build, for the given spawndef refs."""
    encounters, missing = {}, []
    for ref, spots in sorted(refs.items()):
        path = index.get(ref)
        sd = ce.parse_spawndef(path) if path else None
        if sd is None:
            missing.append(ref)
            continue
        sd["kind"] = ce.kind_of(ref)
        sd["spots"] = {"base": spots}
        sd["file"] = ref
        sd["event"] = bool(EVENT.search(ref))
        groups = set()
        for act in sd["actors"]:
            if act["type"] != "villain":
                continue
            rolls = {}
            if act.get("villain"):
                v = act["villain"]
                rolls = {str(l): [v] for l in range(max(sd["min_level"], 1),
                                                    max(sd["max_level"], 1) + 1)}
                if v in villains:
                    groups.add(villains[v].get("VillainGroup"))
            elif act.get("group") and act.get("rank"):
                groups.add(act["group"])
                lo = max(sd["min_level"], 1)
                hi = max(min(sd["max_level"], 54), lo)
                for lvl in range(lo, hi + 1):
                    c, _l = roller.candidates(act["group"], act["rank"],
                                              lvl + ce._int(act.get("level_mod")))
                    rolls[str(lvl)] = c
            act["rolls"] = rolls
        sd["groups"] = sorted(g for g in groups if g)
        name = os.path.basename(ref).rsplit(".", 1)[0]
        if name in encounters:          # same file name in two folders
            name = ref.rsplit(".", 1)[0].replace("spawndefs/", "").replace("/", "__")
        encounters[name] = sd
    return encounters, missing


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    data, out = sys.argv[1], sys.argv[2]
    offsets = json.load(open(os.path.join(REPO, "docs", "zones",
                                          "zone_offsets.json")))["zones"]
    zones = sys.argv[3:] or sorted(
        z for z in os.listdir(os.path.join(data, "maps", "city_zones"))
        if zone_layers(data, z) and re.match(r"^(city|hazard|trial|war)_\d", z))
    store = AssetStore(data_dirs=[data], pigg_paths=[])
    lib = ml.Library(store)
    omni = {}
    for n in store.names():
        if n.startswith("object_library/omni/") and n.endswith(".txt"):
            omni.update(props_of(store.read(n).decode("latin-1")))
    villains = coh_rules.load_villains(os.path.join(data, "defs"))
    roller = ce.Roller(villains)
    root = os.path.join(data, "scripts.loc")
    index = {}
    for d, _s, files in os.walk(os.path.join(root, "spawndefs")):
        for fn in files:
            full = os.path.join(d, fn)
            index[os.path.relpath(full, root).replace("\\", "/").lower()] = full
    summary = {}
    for zone in zones:
        sites = collect_sites(store, lib, data, zone, omni)
        refs = collections.Counter(r for s in sites for r in s["spawndefs"])
        enc, missing = build_encounters(index, roller, villains, refs)
        by_file = {sd["file"]: name for name, sd in enc.items()}
        off = offsets.get(zone, {}).get("offset_m")
        for s in sites:
            s["encounters"] = [by_file[r] for r in s["spawndefs"] if r in by_file]
            s["event"] = bool(s["encounters"]) and all(enc[n]["event"] for n in s["encounters"])
            if off:
                # game x,z offset in meters -> Unreal cm: X = x, Y = -z
                dx, dy = off[0] * 100.0, -off[1] * 100.0
                s["world_cm"] = [round(s["local_cm"][0] + dx, 1),
                                 round(s["local_cm"][1] + dy, 1), s["local_cm"][2]]
        zdir = os.path.join(out, zone)
        os.makedirs(zdir, exist_ok=True)
        with open(os.path.join(zdir, "encounters.json"), "w") as f:
            json.dump({"zone": zone, "encounters": enc, "missing": missing}, f)
        with open(os.path.join(zdir, "sites.json"), "w") as f:
            json.dump({"zone": zone, "units": "Unreal cm; local = zone origin, "
                       "world = after zone_offsets.json", "world_offset_m": off,
                       "sites": sites}, f)
        groups = collections.Counter()
        for s in sites:
            if s["event"]:
                continue
            for n in s["encounters"]:
                for g in enc[n]["groups"]:
                    groups[g] += 1
        lv = [l for n, sd in enc.items() if not sd["event"]
              for l in (sd["min_level"], sd["max_level"]) if l > 0]
        summary[zone] = {"sites": len(sites),
                         "event_sites": sum(1 for s in sites if s["event"]),
                         "spawn_definitions": len(enc), "missing": len(missing),
                         "levels": [min(lv), max(lv)] if lv else None,
                         "top_groups": groups.most_common(6),
                         "placed": bool(off)}
        print("%-13s sites %4d (events %3d)  defs %4d  missing %3d  levels %s  %s" % (
            zone, len(sites), summary[zone]["event_sites"], len(enc), len(missing),
            summary[zone]["levels"], ", ".join(g for g, _ in groups.most_common(4))),
            flush=True)
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main()

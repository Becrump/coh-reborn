"""Story places of every city-map zone, from the original zone maps: where
the contacts stand (PersistentNPC), the mission doors (LairType markers),
visit-location markers and player spawn points, as Unreal world positions.

    python tools/story/world_points.py <i24>/data <out_dir>/story [zone ...]

Writes <out_dir>/story/world_points.json:

  {"zones": {"city_01_01": {
      "npcs":   [{"npc": "contacts/level_1/azuria.npc", "local_cm": [...],
                  "world_cm": [...], "yaw_deg": 0}],
      "doors":  [{"lair": ["sewers", "ap_pp_sewers"], ...}],
      "visits": [{"name": "statue1", ...}],
      "spawns": [{"name": "newplayer", ...}]}}}

world_cm = local_cm + the zone's offset (docs/zones/zone_offsets.json),
X = game x, Y = -game z, as place_world.py places the zones. Atlas Park was
rebuilt, so its points are the original layout's: the game drops them to the
ground (and onto the nav mesh) where it spawns them.

Needs the i24 sparse paths data/maps/city_zones and data/object_library.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "coh2unreal"))
sys.path.insert(0, os.path.join(REPO, "tools", "zones"))
from coh2unreal.pigg import AssetStore  # noqa: E402
from coh2unreal import maplayout as ml  # noqa: E402
from coh2unreal.export import ue_transform  # noqa: E402
from encounters import props_of  # noqa: E402

KEYS = {"persistentnpc": "npcs", "lairtype": "doors", "visitlocation": "visits",
        "spawnlocation": "spawns"}
SKIP_LAYER = re.compile(r"halloween|winter|valentine|rikti_?invasion|betaevent|"
                        r"shadowshardinvasion|zombie|pvp|event|gc_shutdown|i8_prep",
                        re.I)


def zone_points(store, lib, data, zone, omni):
    d = os.path.join(data, "maps", "city_zones", zone)
    out = {v: [] for v in KEYS.values()}
    props = dict(omni)
    layers = sorted(f for f in os.listdir(d) if f.lower().endswith(".txt")
                    and f.lower() != zone + ".txt" and not SKIP_LAYER.search(f))
    for layer in layers:
        rel = "maps/city_zones/%s/%s" % (zone, layer)
        with open(os.path.join(data, rel), encoding="latin-1") as f:
            text = f.read()
        local_props = props_of(text)
        if not any(k.lower() in KEYS for p in local_props.values() for k in p):
            continue
        props.update(local_props)
        local, refs = ml.load_map(store, lib, rel)

        def find(name):
            k = ml.short_name(name)
            return local.get(k) or lib.defs.get(k)

        def walk(name, mat, depth):
            df = find(name)
            if df is None or depth > 48:
                return
            p = {k.lower(): v for k, v in props.get(df.name.lower(), {}).items()}
            for key, kind in KEYS.items():
                if key in p and p[key].strip():
                    loc, rot, _s = ue_transform(mat)
                    rec = {"layer": layer, "local_cm": [round(v, 1) for v in loc],
                           "yaw_deg": round(rot[1], 1)}
                    v = p[key].strip()
                    if kind == "npcs":
                        rec["npc"] = v.replace("\\", "/").lower()
                    elif kind == "doors":
                        rec["lair"] = [t.lower() for t in v.split()]
                        if p.get("locationname"):
                            rec["location"] = p["locationname"]
                    else:
                        rec["name"] = v.lower()
                    out[kind].append(rec)
            for child, pos, pyr in df.groups:
                walk(child, ml.mat_mul(mat, ml.mat_from_pyr(pos, pyr)), depth + 1)

        for name, pos, pyr in refs:
            walk(name, ml.mat_from_pyr(pos, pyr), 0)
    return out


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    data, out = sys.argv[1], sys.argv[2]
    offsets = json.load(open(os.path.join(REPO, "docs", "zones", "zone_offsets.json")))["zones"]
    zones = sys.argv[3:] or sorted(offsets)
    store = AssetStore(data_dirs=[data], pigg_paths=[])
    lib = ml.Library(store)
    omni = {}
    for n in store.names():
        if n.startswith("object_library/omni/") and n.endswith(".txt"):
            omni.update(props_of(store.read(n).decode("latin-1")))
    result = {"units": "Unreal cm; world = local + zone offset (X = game x, Y = -game z)",
              "zones": {}}
    for zone in zones:
        if not os.path.isdir(os.path.join(data, "maps", "city_zones", zone)):
            print("%-13s no map" % zone)
            continue
        pts = zone_points(store, lib, data, zone, omni)
        off = offsets.get(zone, {}).get("offset_m")
        for kind in pts.values():
            for r in kind:
                if off:
                    r["world_cm"] = [round(r["local_cm"][0] + off[0] * 100.0, 1),
                                     round(r["local_cm"][1] - off[1] * 100.0, 1),
                                     r["local_cm"][2]]
        # one contact can be placed in two layers (old and new): keep the last
        seen = {}
        for r in pts["npcs"]:
            seen[r["npc"]] = r
        pts["npcs"] = list(seen.values())
        result["zones"][zone] = pts
        print("%-13s npcs %3d  doors %3d  visits %3d  spawns %3d" % (
            zone, len(pts["npcs"]), len(pts["doors"]), len(pts["visits"]),
            len(pts["spawns"])), flush=True)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "world_points.json"), "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()

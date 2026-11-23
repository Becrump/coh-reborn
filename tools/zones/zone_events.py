"""Zone events of the city-map zones, from the original data: the scripted
events that start now and then in a zone (Hellions setting fires, the Troll
rave, the Croatoa battle) and the city-wide invasions (Rikti, zombies).

    python tools/zones/zone_events.py <i24>/data <out_dir>/zone_encounters [zone ...]

Writes <out_dir>/zone_encounters/zone_events.json:

  {"zone": {"city_02_01": [{"script": "HellionsFire", "def": "hellionsfire",
              "marker": "HellionFire_1", "every_h": 1, "range_min": 10,
              "local_cm": [...], "world_cm": [...],
              "vars": {"SpawnLevel": "10", "BossName": "Hellions_Arson_Boss", ...},
              "text": {"AlertMessage": "The Hellions are setting fires...", ...},
              "villains": {"Hellions": ["Hellions_Arson_Axe_Thug", ...], "FireSpawnWall": [...]}}]},
   "targets": {"city_02_02": {"troll_rave_target_1": [x, y, z]}},     named markers (run-to spots)
   "city": [{"script": "RiktiInvasion", "def": "rikti_invasion", "vars": {...}, "text": {...}},
            {"script": "ZombieApocalypse", ...}]}

Script markers are Omni/MissionBeacons/Marker_Script groups with the
properties Name, RunEvery (hours), RunEveryRange (minutes) and ScriptLocation
(scripts.loc/ScriptDefs/<def>.scriptdef). The scriptdef names the server's
script (ScriptName) and its variables; message variables (P1234...) are
looked up in texts/english. The scripts themselves were C code in the
server, so the game runs its own version of each (CoHZoneEvents.cpp).
Seasonal, PvP and beta scripts are left out.

Needs the i24 sparse paths data/maps/city_zones, data/object_library,
data/scripts.loc/scriptdefs and data/texts/english.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "coh2unreal"))
sys.path.insert(0, os.path.join(REPO, "tools", "story"))
sys.path.insert(0, HERE)
from coh2unreal.pigg import AssetStore  # noqa: E402
from coh2unreal import maplayout as ml  # noqa: E402
from coh2unreal.export import ue_transform  # noqa: E402
from encounters import props_of  # noqa: E402
from coh_story import load_strings  # noqa: E402

SKIP = re.compile(r"halloween|winter|valentine|pvp|beta|covbeta|leveler|holiday|anniversary|"
                  r"heavypet|tutorial", re.I)
CITY_WIDE = ["rikti_invasion", "zombie_apocalypse_hero"]
PSTR = re.compile(r"^P\d+$")


# spawn defs the server's scripts used without naming them in a var
IMPLIED = {"HellionsFire": {"Hellions": "scripts.loc/SpawnDefs/ZoneEvents/Expansion5/HellionsGround_D01_V0.spawndef"}}


def spawndef_villains(data, rel):
    """Every villain a spawn def can roll (its var lists and literal Villain lines)."""
    p = os.path.join(data, rel.replace("\\", "/"))
    if not os.path.exists(p):
        d, f = os.path.split(p)
        alt = [os.path.join(dp, x) for dp, _dn, fs in os.walk(os.path.join(data, "scripts.loc", "spawndefs"))
               for x in fs if x.lower() == f.lower()]
        if not alt:
            return []
        p = alt[0]
    text = open(p, encoding="latin-1").read()
    var = {k: [x.strip() for x in v.split(",") if x.strip()]
           for k, v in re.findall(r"(?m)^\s*var\s+(\w+)\s*=\s*(.*?)\s*$", text)}
    out = []
    for v in re.findall(r"(?m)^\s*Villain\s+(\S+)", text):
        for n in var.get(v, [v]):
            if n not in out:
                out.append(n)
    return out


def read_scriptdef(data, name, strings):
    p = os.path.join(data, "scripts.loc", "scriptdefs", name.lower() + ".scriptdef")
    if not os.path.exists(p):
        return None
    text = open(p, encoding="latin-1").read()
    m = re.search(r"ScriptName\s+(\S+)", text)
    var = {}
    for k, v in re.findall(r"(?m)^\s*var\s+(\w+)\s*=\s*(.*?)\s*$", text):
        var[k] = v.strip().strip('"')
    txt = {}
    for k, v in var.items():
        parts = [x.strip() for x in v.split(",")]
        if parts and all(PSTR.match(x) for x in parts):
            lines = [strings.get(x, "") for x in parts]
            txt[k] = [x for x in lines if x] if len(lines) > 1 else (lines[0] or "")
    script = m.group(1) if m else ""
    vill = {}
    for k, v in list(var.items()) + list(IMPLIED.get(script, {}).items()):
        if v.lower().endswith(".spawndef"):
            vl = spawndef_villains(data, v)
            if vl:
                vill[k] = vl
        elif k.startswith("InvaderList"):
            vill[k] = [x.strip() for x in v.split(";") if x.strip()]
    return {"script": script, "def": name.lower(), "vars": var, "text": txt, "villains": vill}


def zone_markers(store, lib, data, zone, omni):
    """(script markers, named markers) of a zone, local cm."""
    d = os.path.join(data, "maps", "city_zones", zone)
    scripts, named = [], {}
    props = dict(omni)
    layers = sorted(f for f in os.listdir(d) if f.lower().endswith(".txt") and f.lower() != zone + ".txt"
                    and not SKIP.search(f))
    for layer in layers:
        rel = "maps/city_zones/%s/%s" % (zone, layer)
        with open(os.path.join(data, rel), encoding="latin-1") as f:
            text = f.read()
        if "ScriptLocation" not in text and "marker" not in text.lower():
            continue
        props.update(props_of(text))
        local, refs = ml.load_map(store, lib, rel)

        def find(name):
            k = ml.short_name(name)
            return local.get(k) or lib.defs.get(k)

        def walk(name, mat, depth):
            df = find(name)
            if df is None or depth > 48:
                return
            p = {k.lower(): v for k, v in props.get(df.name.lower(), {}).items()}
            loc = None
            if "scriptlocation" in p or "name" in p or "scriptmarker" in p:
                loc, _rot, _s = ue_transform(mat)
                loc = [round(v, 1) for v in loc]
            if "scriptlocation" in p:
                sd = os.path.splitext(os.path.basename(p["scriptlocation"].replace("\\", "/")))[0]
                scripts.append({"def": sd.lower(), "marker": p.get("name", ""), "layer": layer,
                                "every_h": float(p.get("runevery") or 1), "range_min": float(p.get("runeveryrange") or 0),
                                "local_cm": loc})
            elif p.get("scriptmarker") or p.get("name"):
                named[(p.get("scriptmarker") or p["name"]).lower()] = loc
            for child, pos, pyr in df.groups:
                walk(child, ml.mat_mul(mat, ml.mat_from_pyr(pos, pyr)), depth + 1)

        for name, pos, pyr in refs:
            walk(name, ml.mat_from_pyr(pos, pyr), 0)
    return scripts, named


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    data, out = sys.argv[1], sys.argv[2]
    offsets = json.load(open(os.path.join(REPO, "docs", "zones", "zone_offsets.json")))["zones"]
    zones = sys.argv[3:] or sorted(offsets)
    strings = load_strings(os.path.join(data, "texts", "english"))
    store = AssetStore(data_dirs=[data], pigg_paths=[])
    lib = ml.Library(store)
    omni = {}
    for n in store.names():
        if n.startswith("object_library/omni/") and n.endswith(".txt"):
            omni.update(props_of(store.read(n).decode("latin-1")))
    result = {"units": "Unreal cm; world = local + zone offset (X = game x, Y = -game z)",
              "names": {z: o.get("name", z) for z, o in offsets.items()},
              "zone": {}, "targets": {}, "city": []}

    def world(zone, loc):
        off = offsets.get(zone, {}).get("offset_m")
        return [round(loc[0] + off[0] * 100.0, 1), round(loc[1] - off[1] * 100.0, 1), loc[2]] if off and loc else None

    defs = {}
    for zone in zones:
        if not os.path.isdir(os.path.join(data, "maps", "city_zones", zone)):
            continue
        scripts, named = zone_markers(store, lib, data, zone, omni)
        events = []
        for s in scripts:
            if SKIP.search(s["def"]):
                continue
            sd = defs.get(s["def"]) or read_scriptdef(data, s["def"], strings)
            if not sd:
                continue
            defs[s["def"]] = sd
            ev = dict(sd)
            ev.update({k: s[k] for k in ("marker", "every_h", "range_min", "local_cm")})
            ev["world_cm"] = world(zone, s["local_cm"])
            events.append(ev)
        wanted = set()
        for ev in events:
            for v in ev["vars"].values():
                wanted |= {m.lower() for m in re.findall(r"marker:(\w+)", v)}
        if events:
            result["zone"][zone] = events
        tg = {k: world(zone, v) for k, v in named.items() if k in wanted and v}
        if tg:
            result["targets"][zone] = tg
        print("%-13s %d events %s, %d run-to markers" % (zone, len(events),
              ", ".join(sorted({e["script"] for e in events})), len(tg)), flush=True)
    for name in CITY_WIDE:
        sd = read_scriptdef(data, name, strings)
        if sd:
            result["city"].append(sd)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "zone_events.json"), "w") as f:
        json.dump(result, f, indent=1)
    print("city-wide: %s; zone_events.json written" % ", ".join(e["script"] for e in result["city"]))


if __name__ == "__main__":
    main()

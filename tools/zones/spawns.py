"""Export a zone's original enemy encounter points (EncounterGroup / EncounterSpawn /
EncounterPosition) with zone-local transforms, from i24 spawndefs layers.
Usage: python3 spawns.py <i24/data> <zone id e.g. city_01_03> <out.json>"""
import sys, os, re, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "coh2unreal"))
from coh2unreal.pigg import AssetStore
from coh2unreal import maplayout as ml

data, zone, outp = sys.argv[1:4]
store = AssetStore(data_dirs=[data], pigg_paths=[])
lib = ml.Library(store)
PROP = re.compile(r'^\s*Property\s+"([^"]+)"\s+"([^"]*)"', re.I)

def props_of(text):
    out, cur = {}, None; depth = 0
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^(Def|RootMod)\s", line): cur = s.split()[1].lower(); depth = 0; continue
        if cur is None: continue
        if s.startswith("Group "): depth += 1
        elif s == "End":
            if depth: depth -= 1
            else: cur = None
        elif depth == 0:
            m = PROP.match(line)
            if m: out.setdefault(cur, {})[m.group(1)] = m.group(2)
    return out

props = {}
for n in store.names():
    if n.startswith("object_library/omni/") and n.endswith(".txt"):
        props.update(props_of(store.read(n).decode("latin-1")))
zdir = os.path.join(data, "maps/city_zones", zone)
layers = [f for f in os.listdir(zdir) if "spawndef" in f.lower() and f.endswith(".txt")]
res = []
for f in layers:
    rel = "maps/city_zones/%s/%s" % (zone, f)
    text = store.read(rel.lower()).decode("latin-1") if rel.lower() in store else open(os.path.join(zdir, f), errors="replace").read()
    props.update(props_of(text))
    local, refs = ml.load_map(store, lib, rel)
    def find(name):
        k = ml.short_name(name); return local.get(k) or lib.defs.get(k)
    def walk(name, mat, path, depth, group, layout):
        d = find(name)
        if d is None or depth > 32: return
        p = props.get(d.name.lower(), {})
        here = [round(mat[3][0], 1), round(mat[3][1], 1), round(mat[3][2], 1)]
        if "EncounterGroup" in p:
            group = {"layer": f, "name": d.name, "probability": p.get("SpawnProbability"), "pos_ft": here, "layouts": []}
            res.append(group); layout = None
        if "EncounterSpawn" in p and group is not None:
            layout = {"spawn": p["EncounterSpawn"], "def": d.name, "pos_ft": here,
                      "yaw_deg": round(__import__("math").degrees(__import__("math").atan2(mat[2][0], mat[0][0])), 1), "positions": []}
            group["layouts"].append(layout)
        if "EncounterPosition" in p and layout is not None:
            layout["positions"].append({"slot": p["EncounterPosition"], "pos_ft": here})
        for child, pos, pyr in d.groups:
            walk(child, ml.mat_mul(mat, ml.mat_from_pyr(pos, pyr)), path + "/" + child, depth + 1, group, layout)
    for name, pos, pyr in refs:
        walk(name, ml.mat_mul(ml.IDENTITY, ml.mat_from_pyr(pos, pyr)), name, 0, None, None)
json.dump({"zone": zone, "units": "game feet, zone-local", "encounters": res}, open(outp, "w"), indent=1)
from collections import Counter
print(len(res), "encounter groups;", sum(len(g["layouts"]) for g in res), "layouts;", sum(len(l["positions"]) for g in res for l in g["layouts"]), "positions")
print(Counter(l["spawn"] for g in res for l in g["layouts"]).most_common(12))
print(Counter(l["def"] for g in res for l in g["layouts"]).most_common(8))

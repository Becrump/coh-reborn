import sys, os, re, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "coh2unreal"))
from coh2unreal.pigg import AssetStore
from coh2unreal import maplayout as ml
store = AssetStore(data_dirs=[os.environ.get("I24_DATA", "i24/data")], pigg_paths=[])
lib = ml.Library(store)
base = os.path.join(os.environ.get("I24_DATA", "i24/data"), "maps/city_zones")
SKIP = re.compile(r"UNIV_|INFO|^$")
out = {}
for z in sys.argv[1:]:
    d = os.path.join(base, z)
    c = [f for f in os.listdir(d) if f.lower() == z + "_layer_geometry.txt"]
    fn = c[0] if c else z + ".txt"
    defs = {}; cur = None
    for line in open(os.path.join(d, fn), errors="replace"):
        if line.startswith("Def "): cur = line.split()[1]
        m = re.search(r'TexWordLayout"\s+"([^"]*)"', line)
        if m and cur and not SKIP.search(m.group(1)): defs[cur] = m.group(1)
    local, refs = ml.load_map(store, lib, "maps/city_zones/%s/%s" % (z, fn))
    insts, _ = ml.resolve(lib, local, refs)
    xs = sorted(i.matrix[3][0] for i in insts); zs = sorted(i.matrix[3][2] for i in insts); n = len(xs)
    res = {"bounds_ft": [xs[int(.01*n)], zs[int(.01*n)], xs[int(.99*n)], zs[int(.99*n)]], "signs": {}}
    for i in insts:
        parts = i.path.split("/") if isinstance(i.path, str) else list(i.path)
        for p in parts:
            if p in defs:
                res["signs"].setdefault(defs[p], [round(i.matrix[3][0]), round(i.matrix[3][2])])
    out[z] = res
    print(z, json.dumps(res), flush=True)
json.dump(out, open("gates.json", "w"), indent=1)

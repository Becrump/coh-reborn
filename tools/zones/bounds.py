import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "coh2unreal"))
from coh2unreal.pigg import AssetStore
from coh2unreal import maplayout as ml
store = AssetStore(data_dirs=[os.environ.get("I24_DATA", "i24/data")], pigg_paths=[])
lib = ml.Library(store)
base = os.path.join(os.environ.get("I24_DATA", "i24/data"), "maps/city_zones")
for z in sys.argv[1:]:
    d = os.path.join(base, z)
    cands = [f for f in os.listdir(d) if f.lower() == z + "_layer_geometry.txt"]
    rel = "maps/city_zones/%s/%s" % (z, cands[0] if cands else z + ".txt")
    try:
        local, refs = ml.load_map(store, lib, rel)
        insts, missing = ml.resolve(lib, local, refs)
        xs = [i.matrix[3][0] for i in insts]; zs = [i.matrix[3][2] for i in insts]
        # robust bounds: 1st/99th percentile
        xs.sort(); zs.sort(); n=len(xs)
        p=lambda a,q: a[int(q*(n-1))]
        print("%-12s n=%6d  x %6.0f..%6.0f z %6.0f..%6.0f ft  core(1-99%%) %.2f x %.2f km" % (
            z, n, xs[0], xs[-1], zs[0], zs[-1],
            (p(xs,.99)-p(xs,.01))*0.0003048, (p(zs,.99)-p(zs,.01))*0.0003048), flush=True)
    except Exception as e:
        print(z, "ERR", e, flush=True)

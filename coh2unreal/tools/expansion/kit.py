import sys, glob, os, pickle, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from coh2unreal.pigg import AssetStore
from coh2unreal import maplayout as ml
from coh2unreal.export import Exporter
D = r"C:/Users/rtcru/CoHReborn"
def load():
    store = AssetStore(data_dirs=[D + "/i24/data"], pigg_paths=glob.glob(D + "/piggs/*.pigg"))
    lib = ml.Library(store)
    ex = Exporter(store, lib, D + "/expansion/tmp")
    return store, lib, ex
def bounds(lib, ex, name, verbose=False):
    insts, miss = ml.resolve(lib, {}, [(name, (0, 0, 0), (0, 0, 0))])
    lo = [1e9]*3; hi = [-1e9]*3; names = []
    skip = ex.plan_lods(insts)
    for i in insts:
        res = ex._model(i.geo, i.model)
        if not isinstance(res, tuple) or id(i) in skip: continue
        mesh = res[1]; m = i.matrix; p = mesh["positions"]
        names.append(i.model)
        for k in range(0, len(p), 3):
            x, y, z = p[k], p[k+1], p[k+2]
            w = [x*m[0][j] + y*m[1][j] + z*m[2][j] + m[3][j] for j in range(3)]
            for j in range(3):
                lo[j] = min(lo[j], w[j]); hi[j] = max(hi[j], w[j])
    return lo, hi, names, miss
if __name__ == "__main__":
    store, lib, ex = load()
    for n in sys.argv[1:]:
        lo, hi, names, miss = bounds(lib, ex, n)
        print("%-40s x %7.1f..%7.1f  y %6.1f..%6.1f  z %7.1f..%7.1f  n=%d %s %s" % (n, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2], len(names), sorted(set(names))[:8], list(miss)[:3]))

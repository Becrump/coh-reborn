"""Diagnostics for missing tree foliage. Run from the coh2unreal folder:
python tools/diag_trees.py <i24 data> <pigg folder>"""
import sys, glob, io, collections
sys.path.insert(0, ".")
from coh2unreal.pigg import AssetStore
from coh2unreal import maplayout as ml, geo as geomod, texture as texmod
from PIL import Image
store = AssetStore([sys.argv[1]], glob.glob(sys.argv[2] + "/*.pigg"))
lib = ml.Library(store)
local, refs = ml.load_map(store, lib, "maps/city_zones/city_01_01/city_01_01_layer_geometry.txt")
inst, _ = ml.resolve(lib, local, refs)
near = [i for i in inst if -300 <= i.matrix[3][0] <= 550 and -1100 <= i.matrix[3][2] <= -250]
c = collections.Counter((i.geo, i.model) for i in near if "tree" in i.geo.lower() or "tree" in i.model.lower())
for (g, m), n in c.most_common(6):
    geo = geomod.Geo(store.read(g), g)
    want = ml.short_name(m)
    for mm in geo.models:
        if mm.name.lower().split("__")[0] == want:
            print(n, g, mm.name, "trick:", lib.trick_for(mm.name) or lib.trick_for(want))
            for t, cnt in mm.tex_ids:
                b = t.rsplit(".", 1)[0]
                mat = lib.materials.get(b.lower())
                cands = store.find_basename(b + ".texture") or (mat and store.find_basename(mat.get("base", "").rsplit(".", 1)[0] + ".texture")) or []
                info = ""
                if cands:
                    name, payload = texmod.unwrap(store.read(cands[0]))
                    im = Image.open(io.BytesIO(payload)); im.load()
                    info = "%s %s %s" % (name, im.mode, im.format)
                    if "A" in im.mode:
                        a = im.getchannel("A"); h = a.histogram()
                        info += " alpha>=128: %.2f, >=32: %.2f" % (sum(h[128:]) / sum(h), sum(h[32:]) / sum(h))
                print("   tex", t, cnt, "mat:", mat, "->", info)

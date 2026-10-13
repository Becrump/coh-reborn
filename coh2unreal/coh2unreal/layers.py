"""Exports the extra texture layers CoH draws on top of a base texture.

The glTF holds one base texture per material. CoH adds more, from two
places in tricks/*.txt:

- "Texture <name>" trick blocks for plain textures: Blend <detail>,
  BlendType (Multiply / AddGlow / ColorBlendDual / ...), ScaleST0/ScaleST1.
- Composite material blocks: Multiply1 (+ Multiply1Scale) and AddGlow1.

This writes <name>_layers.json and the layer textures as PNG so the Unreal
setup can add them without re-importing the zone:

    python -m coh2unreal.layers --data i24/data --piggs piggs \
        --gltf out/atlas_park/atlas_park.gltf

JSON: {material name as Unreal names it: {"detail": png, "detail_scale":
[u, v], "glow": png, "glow_scale": [u, v], "glow_mask": png,
"glow_mask_alpha": bool, "glow_mask_invert": bool}} ("detail" multiplies
the colour, "glow" is light emitted at night, tiled by glow_scale and
limited to where glow_mask says its material shows: CoH's AddGlowMat2 puts
the glow on the masked second material, e.g. only the windows of a brick
wall).
"""
import argparse
import glob
import json
import os

from .pigg import AssetStore
from . import maplayout as ml
from . import texture as texmod

SKIP = {"none", "white", "grey", "gray", "black"}


def _bare(name):
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] if "." in base else base


def parse_texture_tricks(store):
    """{texture name lower: {blend, blendtype, scale}} from Texture blocks
    that set Blend (plain textures; composites are in Library.materials)."""
    out = {}
    for rel in sorted(n for n in store.names()
                      if n.startswith("tricks/") and n.endswith(".txt")):
        cur = None
        for tok in ml._lines(store.read(rel).decode("latin-1")):
            k = tok[0].lower()
            if k == "texture" and len(tok) > 1:
                cur = {}
                out[_bare(tok[1]).lower()] = cur
            elif cur is None:
                continue
            elif k == "end":
                cur = None
            elif k == "blend" and len(tok) > 1:
                cur["blend"] = tok[1]
            elif k == "blendtype" and len(tok) > 1:
                cur["blendtype"] = tok[1].lower()
            elif k in ("scalest1", "scalest0") and len(tok) >= 3:
                try:
                    cur.setdefault("scale", (float(tok[1]), float(tok[2])))
                except ValueError:
                    pass
    return out


def parse_composite_layers(store):
    """{material lower: {multiply, multiply_scale, addglow}}."""
    out = {}
    for rel in sorted(n for n in store.names()
                      if n.startswith("tricks/") and n.endswith(".txt")):
        cur = None
        for tok in ml._lines(store.read(rel).decode("latin-1")):
            k = tok[0].lower()
            if k == "texture" and len(tok) > 1:
                cur = {}
                out[tok[1].lower()] = cur
            elif cur is None:
                continue
            elif k == "end":
                cur = None
            elif k == "multiply1" and len(tok) > 1:
                cur["multiply"] = tok[1]
            elif k == "multiply1scale" and len(tok) >= 3:
                try:
                    cur["multiply_scale"] = (float(tok[1]), float(tok[2]))
                except ValueError:
                    pass
            elif k == "addglow1" and len(tok) > 1:
                cur["addglow"] = tok[1]
            elif k == "addglow1scale" and len(tok) >= 3:
                try:
                    cur["addglow_scale"] = (float(tok[1]), float(tok[2]))
                except ValueError:
                    pass
            elif k == "addglowmat2" and len(tok) > 1:
                cur["addglow_mat2"] = tok[1] not in ("0", "0.0")
            elif k == "mask" and len(tok) > 1:
                cur["mask"] = tok[1]
            elif k == "alphamask" and len(tok) > 1:
                cur["alpha_mask"] = tok[1] not in ("0", "0.0")
    return out


class Writer:
    def __init__(self, store, out_dir):
        self.store, self.out_dir, self.done = store, out_dir, {}

    def png(self, texname):
        key = _bare(texname).lower()
        if key in SKIP:
            return None
        if key in self.done:
            return self.done[key]
        cands = self.store.find_basename(_bare(texname) + ".texture")
        cands.sort(key=lambda p: (not p.startswith("texture_library/"), p))
        rel = None
        if cands:
            data, _alpha = texmod.to_png(self.store.read(cands[0]))
            if data:
                rel = "layers/%s.png" % _bare(texname)
                path = os.path.join(self.out_dir, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)
        self.done[key] = rel
        return rel


def build(store, gltf_path):
    out_dir = os.path.dirname(os.path.abspath(gltf_path))
    g = json.load(open(gltf_path))
    texs = parse_texture_tricks(store)
    comps = parse_composite_layers(store)
    w = Writer(store, out_dir)
    result = {}
    for m in g["materials"]:
        name = m["name"]
        base = name.split("__", 1)[0]               # drop __ADD/__GLOW...
        key = _bare(base).lower()
        entry = {}
        t = texs.get(key)
        if t and t.get("blend") and _bare(t["blend"]).lower() not in SKIP:
            kind = t.get("blendtype", "multiply")
            png = w.png(t["blend"])
            if png and kind == "multiply":
                entry["detail"] = png
                entry["detail_scale"] = list(t.get("scale", (1.0, 1.0)))
            elif png and kind == "addglow":
                entry["glow"] = png
        c = comps.get(base.lower())
        if c:
            mul = c.get("multiply")
            if mul and _bare(mul).lower() not in SKIP and "reflect" not in \
                    mul.lower():
                png = w.png(mul)
                if png:
                    entry["detail"] = png
                    entry["detail_scale"] = list(c.get("multiply_scale",
                                                       (1.0, 1.0)))
            if c.get("addglow") and _bare(c["addglow"]).lower() not in SKIP:
                png = w.png(c["addglow"])
                if png:
                    entry["glow"] = png
                    entry["glow_scale"] = list(c.get("addglow_scale",
                                                     (1.0, 1.0)))
                    # the glow lights one of the two blended materials; the
                    # mask says where material 2 shows (e.g. only windows)
                    mask = c.get("mask")
                    if mask and _bare(mask).lower() not in SKIP:
                        mpng = w.png(mask)
                        if mpng:
                            entry["glow_mask"] = mpng
                            entry["glow_mask_alpha"] = c.get("alpha_mask",
                                                             False)
                            # mask 1 = material 1 (e.g. the brick), so a
                            # glow on material 2 uses the inverted mask
                            entry["glow_mask_invert"] = c.get(
                                "addglow_mat2", False)
        if entry:
            result[name.replace(".", "_")] = entry
    name = os.path.splitext(os.path.basename(gltf_path))[0]
    with open(os.path.join(out_dir, name + "_layers.json"), "w") as f:
        json.dump(result, f, indent=1)
    return result


def main():
    ap = argparse.ArgumentParser(prog="coh2unreal.layers")
    ap.add_argument("--data", action="append", default=[])
    ap.add_argument("--piggs", action="append", default=[])
    ap.add_argument("--gltf", required=True)
    args = ap.parse_args()
    piggs = []
    for d in args.piggs:
        piggs += glob.glob(os.path.join(d, "*.pigg"))
    store = AssetStore(data_dirs=args.data, pigg_paths=piggs)
    res = build(store, args.gltf)
    det = sum("detail" in v for v in res.values())
    glow = sum("glow" in v for v in res.values())
    print("layers: %d materials with a detail texture, %d with a night glow"
          % (det, glow))


if __name__ == "__main__":
    main()

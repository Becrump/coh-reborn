"""Exports a resolved City of Heroes map to glTF 2.0 for Unreal.

The map is merged into square tiles so a zone imports as a few hundred
actors instead of hundreds of thousands. Each tile holds one primitive per
texture. Units are converted from feet to meters; axes stay Y-up like the
game and glTF.
"""
import array
import json
import math
import os
import struct
import sys

from . import geo as geomod
from . import maplayout as ml
from . import texture as texmod

FEET_TO_METERS = 0.3048


class _Prim:
    __slots__ = ("pos", "nrm", "uv", "idx")

    def __init__(self):
        self.pos = array.array("f")
        self.nrm = array.array("f")
        self.uv = array.array("f")
        self.idx = array.array("I")


class Exporter:
    def __init__(self, store, library, out_dir, tile_size_ft=400.0,
                 log=print):
        self.store = store
        self.lib = library
        self.out_dir = out_dir
        self.tile = tile_size_ft
        self.log = log
        self.geos = {}
        self.mesh_cache = {}
        self.tiles = {}            # (tx, tz) -> {texname: _Prim}
        self.textures = {}         # texname -> (png rel path or None, alpha)
        self.stats = {"instances": 0, "placed": 0, "hidden": 0, "lod": 0,
                      "missing_geo": set(), "missing_model": set(),
                      "missing_tex": set(), "bad_geo": set()}

    # ------------------------------------------------------------ loading
    def _geo(self, path):
        if path not in self.geos:
            g = None
            if path in self.store:
                try:
                    g = geomod.Geo(self.store.read(path), path)
                except Exception as e:  # keep going, report at the end
                    self.stats["bad_geo"].add("%s: %s" % (path, e))
            else:
                self.stats["missing_geo"].add(path)
            self.geos[path] = g
        return self.geos[path]

    def _model(self, geo_path, obj):
        key = (geo_path, obj.lower())
        if key in self.mesh_cache:
            return self.mesh_cache[key]
        g = self._geo(geo_path)
        result = None
        if g is not None:
            want = ml.short_name(obj)
            exact = [m for m in g.models if m.name.lower() == want]
            loose = [m for m in g.models
                     if m.name.lower().split("__", 1)[0] == want]
            found = (exact or loose or [None])[0]
            if found is None:
                self.stats["missing_model"].add("%s:%s" % (geo_path, obj))
            else:
                trick = self.lib.trick_for(found.name) or \
                    self.lib.trick_for(want)
                if trick and trick["hidden"]:
                    result = "hidden"
                elif trick and trick["lod_near"] > 0:
                    result = "lod"
                else:
                    result = (found.name, g.mesh(found))
        self.mesh_cache[key] = result
        return result

    # ------------------------------------------------------------- placing
    def add(self, inst):
        self.stats["instances"] += 1
        res = self._model(inst.geo, inst.model)
        if res is None:
            return
        if res in ("hidden", "lod"):
            self.stats[res] += 1
            return
        _name, mesh = res
        m = inst.matrix
        pos = mesh["positions"]
        nrm = mesh["normals"]
        uv = mesh["uvs"]
        nverts = len(pos) // 3
        if not nverts:
            return
        # world-space positions
        wp = [0.0] * (nverts * 3)
        cx = cz = 0.0
        for v in range(nverts):
            x, y, z = pos[v * 3], pos[v * 3 + 1], pos[v * 3 + 2]
            for k in range(3):
                wp[v * 3 + k] = (x * m[0][k] + y * m[1][k] + z * m[2][k]
                                 + m[3][k])
        cx, cz = m[3][0], m[3][2]
        tile = (math.floor(cx / self.tile), math.floor(-cz / self.tile))
        prims = self.tiles.setdefault(tile, {})
        for texname, tris in mesh["groups"]:
            if not tris:
                continue
            prim = prims.get(texname)
            if prim is None:
                prim = prims[texname] = _Prim()
            base = len(prim.pos) // 3
            used = sorted(set(tris))
            remap = {}
            for vi in used:
                remap[vi] = base + len(remap)
                # The game is left-handed; negate Z for right-handed glTF.
                prim.pos.extend((wp[vi * 3] * FEET_TO_METERS,
                                 wp[vi * 3 + 1] * FEET_TO_METERS,
                                 -wp[vi * 3 + 2] * FEET_TO_METERS))
                if nrm:
                    nx, ny, nz = nrm[vi * 3:vi * 3 + 3]
                    n = [nx * m[0][k] + ny * m[1][k] + nz * m[2][k]
                         for k in range(3)]
                    ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
                    prim.nrm.extend((n[0] / ln, n[1] / ln, -n[2] / ln))
                else:
                    prim.nrm.extend((0.0, 1.0, 0.0))
                if uv:
                    # The game's t axis runs the other way from glTF's v.
                    prim.uv.extend((uv[vi * 2], 1.0 - uv[vi * 2 + 1]))
                else:
                    prim.uv.extend((0.0, 0.0))
            # Mirroring Z flips triangle winding, so swap two corners.
            for t in range(0, len(tris) - 2, 3):
                prim.idx.extend((remap[tris[t]], remap[tris[t + 2]],
                                 remap[tris[t + 1]]))
        self.stats["placed"] += 1

    # -------------------------------------------------------------- output
    def _png(self, texname):
        """Converts one game texture to PNG. Returns (rel path, alpha)."""
        key = "png:" + texname.lower()
        if key in self.textures:
            return self.textures[key]
        base = _bare(texname)
        rel, alpha = None, False
        cands = self.store.find_basename(base + ".texture")
        cands.sort(key=lambda p: (not p.startswith("texture_library/"), p))
        if cands:
            try:
                png, alpha = texmod.to_png(self.store.read(cands[0]))
            except ImportError:
                png = None
                self.log("Pillow is not installed; textures are skipped. "
                         "Run: python -m pip install pillow")
            if png:
                rel = "textures/%s.png" % _safe(base)
                path = os.path.join(self.out_dir, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(png)
        self.textures[key] = (rel, alpha)
        return rel, alpha

    def _find_texture(self, texname):
        cands = self.store.find_basename(_bare(texname) + ".texture")
        cands.sort(key=lambda p: (not p.startswith("texture_library/"), p))
        return cands[0] if cands else None

    def _leaf(self, base, mask):
        """Base colour with the companion _a texture as cutout opacity."""
        cpath, mpath = self._find_texture(base), self._find_texture(mask)
        if not (cpath and mpath):
            return None
        png = texmod.combine_alpha(self.store.read(cpath),
                                   self.store.read(mpath))
        if not png:
            return None
        rel = "textures/%s__%s.png" % (_safe(_bare(base)), _safe(_bare(mask)))
        path = os.path.join(self.out_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(png)
        return rel, True

    def _texture(self, texname):
        """Returns (base color png, alpha, normal map png or None)."""
        if texname in self.textures:
            return self.textures[texname]
        rel, alpha = self._png(texname)
        normal = None
        mat = self.lib.materials.get(_bare(texname).lower())
        if mat:
            # Composite material: use its base layer (and bump map).
            if rel is None and mat.get("base"):
                rel, alpha = self._png(mat["base"])
                dual = mat.get("dual", "")
                if rel and _bare(dual).lower().endswith("_a"):
                    rel, alpha = self._leaf(mat["base"], dual) or (rel, alpha)
            if mat.get("bump"):
                normal = self._png(mat["bump"])[0]
        if rel is None:
            self.stats["missing_tex"].add(texname)
        self.textures[texname] = (rel, alpha, normal)
        return self.textures[texname]

    def write(self, name):
        os.makedirs(self.out_dir, exist_ok=True)
        bin_name = name + ".bin"
        gl = {"asset": {"version": "2.0", "generator": "coh2unreal"},
              "scene": 0, "scenes": [{"name": name, "nodes": []}],
              "nodes": [], "meshes": [], "materials": [], "textures": [],
              "images": [], "samplers": [{"wrapS": 10497, "wrapT": 10497}],
              "accessors": [], "bufferViews": [],
              "buffers": [{"uri": bin_name, "byteLength": 0}]}
        mat_index = {}
        blob = open(os.path.join(self.out_dir, bin_name), "wb")
        offset = 0

        def view(data, target):
            nonlocal offset
            raw = data.tobytes()
            if sys.byteorder != "little":
                swapped = array.array(data.typecode, data)
                swapped.byteswap()
                raw = swapped.tobytes()
            blob.write(raw)
            pad = (4 - len(raw) % 4) % 4
            blob.write(b"\0" * pad)
            gl["bufferViews"].append({"buffer": 0, "byteOffset": offset,
                                      "byteLength": len(raw),
                                      "target": target})
            offset += len(raw) + pad
            return len(gl["bufferViews"]) - 1

        def accessor(data, comps, ctype, target, minmax=False):
            v = view(data, target)
            acc = {"bufferView": v, "componentType": ctype,
                   "count": len(data) // comps,
                   "type": {1: "SCALAR", 2: "VEC2", 3: "VEC3"}[comps]}
            if minmax:
                acc["min"] = [min(data[i::comps]) for i in range(comps)]
                acc["max"] = [max(data[i::comps]) for i in range(comps)]
            gl["accessors"].append(acc)
            return len(gl["accessors"]) - 1

        def material(texname):
            if texname in mat_index:
                return mat_index[texname]
            rel, alpha, normal = self._texture(texname)
            mat = {"name": texname,
                   "pbrMetallicRoughness": {"metallicFactor": 0.0,
                                            "roughnessFactor": 0.9}}
            if rel:
                gl["images"].append({"uri": rel})
                gl["textures"].append({"source": len(gl["images"]) - 1,
                                       "sampler": 0})
                mat["pbrMetallicRoughness"]["baseColorTexture"] = {
                    "index": len(gl["textures"]) - 1}
            if normal:
                gl["images"].append({"uri": normal})
                gl["textures"].append({"source": len(gl["images"]) - 1,
                                       "sampler": 0})
                mat["normalTexture"] = {"index": len(gl["textures"]) - 1}
            if alpha:
                mat["alphaMode"] = "MASK"
                mat["alphaCutoff"] = 0.3
                mat["doubleSided"] = True
            gl["materials"].append(mat)
            mat_index[texname] = len(gl["materials"]) - 1
            return mat_index[texname]

        for (tx, tz) in sorted(self.tiles):
            prims = []
            for texname, p in sorted(self.tiles[(tx, tz)].items()):
                if not p.idx:
                    continue
                attrs = {
                    "POSITION": accessor(p.pos, 3, 5126, 34962, True),
                    "NORMAL": accessor(p.nrm, 3, 5126, 34962),
                    "TEXCOORD_0": accessor(p.uv, 2, 5126, 34962),
                }
                prims.append({"attributes": attrs,
                              "indices": accessor(p.idx, 1, 5125, 34963),
                              "material": material(texname)})
            if not prims:
                continue
            gl["meshes"].append({"name": "tile_%d_%d" % (tx, tz),
                                 "primitives": prims})
            gl["nodes"].append({"name": "tile_%d_%d" % (tx, tz),
                                "mesh": len(gl["meshes"]) - 1})
            gl["scenes"][0]["nodes"].append(len(gl["nodes"]) - 1)
        blob.close()
        gl["buffers"][0]["byteLength"] = offset
        for k in ("textures", "images"):
            if not gl[k]:
                del gl[k]
        with open(os.path.join(self.out_dir, name + ".gltf"), "w") as f:
            json.dump(gl, f)
        return os.path.join(self.out_dir, name + ".gltf")


def _bare(name):
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] if "." in base else base


def _safe(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def write_instances(instances, path):
    """Saves every placed model with its 4x4 game-space matrix (feet)."""
    rows = [{"geo": i.geo, "model": i.model, "path": i.path,
             "matrix": i.matrix} for i in instances]
    with open(path, "w") as f:
        json.dump(rows, f)

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

# How a model draws, from its trick's TrickFlags/ObjFlags. Each mode gets
# its own material so Unreal can set the matching blend mode:
#   ""      normal
#   "glow"  FullBright: self-lit (signs, lamp bulbs)
#   "night" NightLight: glows only at night (lit windows); exported into
#           separate *_night tile actors so a day/night cycle can toggle them
#   "add"   Additive: light added on top (lamp pools, beams, glints)
#   "glass" ReflectTex on its own: real window panes (shop fronts) that the
#           old renderer drew with an environment map; exported glossy into
#           separate *_glass tile actors so they can be hidden if needed
# ReflectTex+Additive layers and Subtractive ones are fake reflections and
# shadows; Lumen does those for real, so they are skipped.
MAT_SUFFIX = {"": "", "glow": "__GLOW", "night": "__NIGHT", "add": "__ADD",
              "addnight": "__ADD__NIGHT", "glass": "__GLASS",
              "water": "__WATERTOP"}
# CoH water volumes are invisible boxes; where no water model sits on one
# (some canal stretches) the export adds the box's top face in this texture
WATER_TOP_TEX = "newwater4.tga"
VISIBLE_WATER = ("_outsdewater_smooth", "_calmwater_")


def draw_mode(flags):
    """Returns the draw mode for a trick's flags, or None to skip it."""
    if not flags:
        return ""
    reflect = bool(flags & {"reflecttex0", "reflecttex1"})
    if "subtractive" in flags or (reflect and "additive" in flags):
        return None
    night = "nightlight" in flags
    if reflect and not night:
        return "glass"
    if "additive" in flags:
        return "addnight" if night else "add"
    if night:
        return "night"
    if "fullbright" in flags:
        return "glow"
    return ""


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
        self.tiles = {}            # (tx, tz) -> {(texname, mode): _Prim}
        self.lights = []           # maplayout.Light, set by the caller
        # instanced mode: one mesh per model in its own space + placements
        self.library = False
        self.placements = []       # (mesh name, has night part, matrix)
        self.khr_lights = False    # also put them in the glTF
        self.textures = {}         # texname -> (png rel path or None, alpha)
        self.stats = {"instances": 0, "placed": 0, "hidden": 0, "lod": 0,
                      "fake_fx": 0, "modes": {},
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
                mode = draw_mode(trick["flags"]) if trick else ""
                if trick and trick["hidden"]:
                    result = "hidden"
                elif mode is None:
                    result = "fake_fx"
                else:
                    # far-only detail level: plan_lods decides if it's needed
                    far = bool(trick and trick["lod_near"] > 0)
                    result = (found.name, g.mesh(found), mode, far)
        self.mesh_cache[key] = result
        return result

    # ------------------------------------------------------------- placing
    def plan_lods(self, instances):
        """CoH places detail levels of one object together (X_hi, X_lo,
        X_LOD...), showing one at a time by distance. Returns the ids of
        the instances to skip: the low-detail ones where a full-detail
        twin sits at the same spot. A low-detail model with no twin is the
        only version there and is kept (otherwise it leaves a hole).

        The twin is often in another sub-group or has another name (a road
        intersection's far version is a plain _6_strt_lo under the
        _6_4wayA_hi), so far-only models (LodNear set) also go when any
        full-detail model has its origin within a foot of theirs."""
        def is_low(name, res):
            low = name.lower()
            return res[3] or low.endswith(("_lo", "lod")) or "_lo_" in low
        groups = {}
        full = set()
        for inst in instances:
            res = self._model(inst.geo, inst.model)
            if not isinstance(res, tuple):
                continue
            key = (inst.path.rsplit("/", 1)[0],
                   tuple(round(v, 1) for v in inst.matrix[3]))
            low = is_low(inst.model, res)
            groups.setdefault(key, []).append((inst, low, res[3]))
            if not low:
                full.add(tuple(round(v) for v in inst.matrix[3]))
        skip = set()
        for members in groups.values():
            if any(not low for _i, low, _far in members):
                skip.update(id(i) for i, low, _far in members if low)
        for members in groups.values():
            for inst, _low, far in members:
                if not far or id(inst) in skip:
                    continue
                x, y, z = (round(v) for v in inst.matrix[3])
                if any((x + dx, y + dy, z + dz) in full
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                       for dz in (-1, 0, 1)):
                    skip.add(id(inst))
        return skip

    def add(self, inst, skip=False):
        self.stats["instances"] += 1
        res = self._model(inst.geo, inst.model)
        if res is None:
            return
        if res in ("hidden", "fake_fx"):
            self.stats[res] += 1
            return
        if skip:
            self.stats["lod"] += 1
            return
        _name, mesh, mode, _far = res
        self.stats["modes"][mode] = self.stats["modes"].get(mode, 0) + 1
        m = inst.matrix
        if self.library:
            key = _safe(_name)
            if key not in self.tiles:
                self._fill(self.tiles.setdefault(key, {}), mesh, mode,
                           [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0], [0, 0, 0]])
            elif not any(k[1] == mode for k in self.tiles[key]):
                self._fill(self.tiles[key], mesh, mode,
                           [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0], [0, 0, 0]])
            self.placements.append((key, m))
            self.stats["placed"] += 1
            return
        cx, cz = m[3][0], m[3][2]
        tile = (math.floor(cx / self.tile), math.floor(-cz / self.tile))
        self._fill(self.tiles.setdefault(tile, {}), mesh, mode, m)
        self.stats["placed"] += 1

    def add_water_tops(self, instances):
        """Top faces for water_coll_<size> volumes with no visible water
        model at the same spot. Returns how many were added."""
        def spot(inst):
            return tuple(round(v, 1) for v in inst.matrix[3])
        seen = {spot(i) for i in instances
                if i.model.lower().startswith(VISIBLE_WATER)}
        n = 0
        for inst in instances:
            name = inst.model.lower()
            if not name.startswith("water_coll_") or spot(inst) in seen:
                continue
            try:
                h = float(name.rsplit("_", 1)[1]) / 2
            except ValueError:
                continue
            mesh = {"positions": array.array(
                        "f", [-h, 0, -h, h, 0, -h, h, 0, h, -h, 0, h]),
                    "normals": array.array("f", [0, 1, 0] * 4),
                    "uvs": array.array("f", [0, 0, 1, 0, 1, 1, 0, 1]),
                    "groups": [(WATER_TOP_TEX, [0, 2, 1, 0, 3, 2])]}
            m = inst.matrix
            tile = (math.floor(m[3][0] / self.tile),
                    math.floor(-m[3][2] / self.tile))
            self._fill(self.tiles.setdefault(tile, {}), mesh, "water", m)
            n += 1
        return n

    def _fill(self, prims, mesh, mode, m):
        """Appends a model's triangles, transformed by game matrix m, to the
        primitives of one output mesh (keyed by texture and draw mode)."""
        pos = mesh["positions"]
        nrm = mesh["normals"]
        uv = mesh["uvs"]
        nverts = len(pos) // 3
        if not nverts:
            return
        # positions transformed by m (world space, or local for the library)
        wp = [0.0] * (nverts * 3)
        for v in range(nverts):
            x, y, z = pos[v * 3], pos[v * 3 + 1], pos[v * 3 + 2]
            for k in range(3):
                wp[v * 3 + k] = (x * m[0][k] + y * m[1][k] + z * m[2][k]
                                 + m[3][k])
        for texname, tris in mesh["groups"]:
            if not tris:
                continue
            prim = prims.get((texname, mode))
            if prim is None:
                prim = prims[(texname, mode)] = _Prim()
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
        """Returns (base color png, alpha, normal map png or None,
        (u, v) tiling scale or None)."""
        if texname in self.textures:
            return self.textures[texname]
        rel, alpha = self._png(texname)
        normal = scale = None
        mat = self.lib.materials.get(_bare(texname).lower())
        if mat:
            # Composite material: use its base layer (and bump map). Its
            # base texture's alpha is a shine mask, not opacity, unless the
            # material has a leaf-shape (_a) layer.
            if rel is None and mat.get("base"):
                rel, base_alpha = self._png(mat["base"])
                alpha = False
                dual = mat.get("dual", "")
                if rel and _bare(dual).lower().endswith("_a"):
                    rel, alpha = self._leaf(mat["base"], dual) or (rel, False)
                elif _bare(dual).lower() == _bare(mat["base"]).lower():
                    # DualColor = Base: the game blends with the base's own
                    # alpha (decals, tree roots, glass, fences)
                    alpha = base_alpha
                if mat.get("scale") and mat["scale"] != (1.0, 1.0):
                    scale = mat["scale"]
            if mat.get("bump"):
                normal = self._png(mat["bump"])[0]
        if rel is None:
            self.stats["missing_tex"].add(texname)
        self.textures[texname] = (rel, alpha, normal, scale)
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

        image_index = {}
        used = set()               # glTF extensions referenced

        def image(rel):
            if rel not in image_index:
                gl["images"].append({"uri": rel})
                gl["textures"].append({"source": len(gl["images"]) - 1,
                                       "sampler": 0})
                image_index[rel] = len(gl["textures"]) - 1
            return image_index[rel]

        def material(texname, mode):
            key = (texname, mode)
            if key in mat_index:
                return mat_index[key]
            rel, alpha, normal, scale = self._texture(texname)
            mat = {"name": texname + MAT_SUFFIX[mode],
                   "pbrMetallicRoughness": {"metallicFactor": 0.0,
                                            "roughnessFactor": 0.9}}

            def texref(path):
                ref = {"index": image(path)}
                if scale:
                    ref["extensions"] = {"KHR_texture_transform": {
                        "scale": list(scale)}}
                    used.add("KHR_texture_transform")
                return ref
            if rel:
                mat["pbrMetallicRoughness"]["baseColorTexture"] = texref(rel)
            if normal:
                mat["normalTexture"] = texref(normal)
            if alpha:
                mat["alphaMode"] = "MASK"
                mat["alphaCutoff"] = 0.3
                mat["doubleSided"] = True
            if mode == "glass":
                mat["pbrMetallicRoughness"]["roughnessFactor"] = 0.08
                mat["doubleSided"] = True
            elif mode and mode != "water" and rel:
                mat["emissiveTexture"] = texref(rel)
                mat["emissiveFactor"] = [1.0, 1.0, 1.0]
            if mode in ("add", "addnight"):
                # Unreal sets these to Additive by the __ADD name suffix.
                mat["pbrMetallicRoughness"]["baseColorFactor"] = [0, 0, 0, 1]
                mat["alphaMode"] = "BLEND"
                mat.pop("alphaCutoff", None)
                mat["doubleSided"] = True
            gl["materials"].append(mat)
            mat_index[key] = len(gl["materials"]) - 1
            return mat_index[key]

        def tile_mesh(mesh_name, items):
            prims = []
            for (texname, mode), p in items:
                if not p.idx:
                    continue
                attrs = {
                    "POSITION": accessor(p.pos, 3, 5126, 34962, True),
                    "NORMAL": accessor(p.nrm, 3, 5126, 34962),
                    "TEXCOORD_0": accessor(p.uv, 2, 5126, 34962),
                }
                prims.append({"attributes": attrs,
                              "indices": accessor(p.idx, 1, 5125, 34963),
                              "material": material(texname, mode)})
            if not prims:
                return
            gl["meshes"].append({"name": mesh_name, "primitives": prims})
            gl["nodes"].append({"name": mesh_name,
                                "mesh": len(gl["meshes"]) - 1})
            gl["scenes"][0]["nodes"].append(len(gl["nodes"]) - 1)

        for key in sorted(self.tiles):
            items = sorted(self.tiles[key].items())
            base = key if self.library else "tile_%d_%d" % key
            # library meshes keep their glass (placements only know _night)
            split = () if self.library else ("glass", "water")
            tile_mesh(base, [i for i in items if "night" not in i[0][1]
                             and i[0][1] not in split])
            tile_mesh(base + "_night", [i for i in items if "night" in i[0][1]])
            for kind in split:
                tile_mesh(base + "_" + kind,
                          [i for i in items if i[0][1] == kind])
        if self.library:
            self._write_placements(name)
        if self.lights:
            self._write_lights(gl, name)
        if used:
            gl["extensionsUsed"] = sorted(set(gl.get("extensionsUsed", []))
                                          | used)
        blob.close()
        gl["buffers"][0]["byteLength"] = offset
        for k in ("textures", "images"):
            if not gl[k]:
                del gl[k]
        with open(os.path.join(self.out_dir, name + ".gltf"), "w") as f:
            json.dump(gl, f)
        # For the Unreal setup script: which imported materials are cutouts.
        masked = sorted(m["name"].replace(".", "_") for m in gl["materials"]
                        if m.get("alphaMode") == "MASK")
        with open(os.path.join(self.out_dir, "masked_materials.json"),
                  "w") as f:
            json.dump(masked, f, indent=0)
        return os.path.join(self.out_dir, name + ".gltf")

    def _write_placements(self, name):
        """<name>_placements.json: every placement as an Unreal transform
        (cm, degrees) of its library mesh, plus whether the mesh has a
        night-only part (<mesh>_night, same transform)."""
        night = {k for k, prims in self.tiles.items()
                 if any("night" in kk[1] for kk in prims)}
        day = {k for k, prims in self.tiles.items()
               if any("night" not in kk[1] for kk in prims)}
        rows = []
        for key, m in self.placements:
            loc, rot, scl = ue_transform(m)
            rows.append({"m": key, "day": key in day, "night": key in night,
                         "l": loc, "r": rot, "s": scl})
        with open(os.path.join(self.out_dir, name + "_placements.json"),
                  "w") as f:
            json.dump(rows, f, separators=(",", ":"))

    def _write_lights(self, gl, name):
        """Writes the CoH Omni lights to <name>_lights.json and, if
        self.khr_lights is set, into the glTF as point lights
        (KHR_lights_punctual).

        They are off in the glTF by default: most are interior fill lights
        standing in for global illumination (Lumen does that now), and
        Unreal creates an actor per light, thousands for one zone.

        The old engine baked these into vertex colours, so values above 255
        (overbright) are common. Colour is normalised by its peak and the
        excess goes into intensity.
        """
        defs, rows = [], []
        parent = {"name": "coh_lights", "children": []}
        for n, lt in enumerate(self.lights):
            r, g, b = lt.color
            peak = max(r, g, b, 1.0)
            radius_m = max(lt.radius * FEET_TO_METERS, 0.5)
            color = [round(r / peak, 4), round(g / peak, 4),
                     round(b / peak, 4)]
            # candela; scaled so a lamp still reads at the edge of its radius
            intensity = round(min(peak / 255.0, 2.0) * radius_m ** 2 * 1.5, 2)
            x, y, z = lt.pos
            pos = [x * FEET_TO_METERS, y * FEET_TO_METERS,
                   -z * FEET_TO_METERS]
            rows.append({"name": "omni_%d" % n, "pos": pos, "color": color,
                         "intensity": intensity, "range": round(radius_m, 2),
                         "path": lt.path})
            if not self.khr_lights:
                continue
            defs.append({"name": "omni_%d" % n, "type": "point",
                         "color": color, "intensity": intensity,
                         "range": round(radius_m, 2)})
            gl["nodes"].append({
                "name": "omni_%d" % n, "translation": pos,
                "extensions": {"KHR_lights_punctual": {"light": n}}})
            parent["children"].append(len(gl["nodes"]) - 1)
        if self.khr_lights:
            gl["nodes"].append(parent)
            gl["scenes"][0]["nodes"].append(len(gl["nodes"]) - 1)
            gl.setdefault("extensions", {})["KHR_lights_punctual"] = {
                "lights": defs}
            gl.setdefault("extensionsUsed", []).append("KHR_lights_punctual")
        with open(os.path.join(self.out_dir, name + "_lights.json"),
                  "w") as f:
            json.dump(rows, f)


def ue_transform(m):
    """CoH game matrix (rows = local axes in feet, row 3 = position) ->
    Unreal location (cm), rotator [pitch, yaw, roll] (deg) and scale, for a
    library mesh exported in its own (glTF) space and imported to Unreal.

    game -> glTF negates Z (and feet -> metres); glTF -> Unreal swaps Y/Z
    (metres -> cm). The two mirrors cancel, so the result is a proper
    rotation: M_ue = P D R D P with D = diag(1,1,-1), P = swap(Y,Z).
    """
    R = [[m[i][j] for j in range(3)] for i in range(3)]
    D = [1, 1, -1]
    A = [[D[i] * R[i][j] * D[j] for j in range(3)] for i in range(3)]
    perm = [0, 2, 1]
    M = [[A[perm[i]][perm[j]] for j in range(3)] for i in range(3)]
    scale = [math.sqrt(sum(c * c for c in row)) or 1.0 for row in M]
    X, Y, Z = ([c / s for c in row] for row, s in zip(M, scale))
    # FMatrix::Rotator(): rows are the X, Y, Z axes
    pitch = math.degrees(math.atan2(X[2], math.hypot(X[0], X[1])))
    yaw = math.degrees(math.atan2(X[1], X[0]))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    sy_axis = [-sy, cy, 0.0]                 # Y axis of (pitch, yaw, 0)
    roll = math.degrees(math.atan2(sum(a * b for a, b in zip(Z, sy_axis)),
                                   sum(a * b for a, b in zip(Y, sy_axis))))
    t = m[3]
    loc = [t[0] * 30.48, -t[2] * 30.48, t[1] * 30.48]
    return ([round(v, 2) for v in loc], [round(pitch, 4), round(yaw, 4),
            round(roll, 4)], [round(scale[0], 5), round(scale[1], 5),
                               round(scale[2], 5)])


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

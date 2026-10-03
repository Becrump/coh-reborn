"""Parses City of Heroes map and object library text files and resolves a
map into a flat list of placed models.

Follows Common/group/groupfileload.c (Def/Group/Ref grammar),
Common/group/groupfilelib.c (library name lookup) and Common/seq/tricks.c.
"""
import math
import os
import re

_LIGHT_KEYS = {"omni", "sound", "fog", "cubemap", "volume", "ambient"}


class Def:
    __slots__ = ("name", "groups", "obj", "flags", "has_editor_only",
                 "source", "lod_far")

    def __init__(self, name, source):
        self.name = name
        self.groups = []          # [(child name, pos, pyr_degrees)]
        self.obj = None
        self.flags = set()
        self.has_editor_only = False
        self.source = source
        self.lod_far = 0.0


def _lines(text):
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].split("//", 1)[0].strip()
        if line:
            yield line.split()


def parse_group_file(text, source=""):
    """Returns (defs, refs, imports). defs keep file order."""
    defs, refs, imports = [], [], []
    it = _lines(text)
    for tok in it:
        key = tok[0].lower()
        if key in ("def", "rootmod") and len(tok) > 1:
            d = Def(tok[1], source)
            d.flags.add("rootmod" if key == "rootmod" else "def")
            _parse_def(it, d)
            defs.append(d)
        elif key == "ref" and len(tok) > 1:
            pos, pyr = _parse_placement(it)
            refs.append((tok[1], pos, pyr))
        elif key == "import" and len(tok) > 1:
            imports.append(tok[1])
    return defs, refs, imports


def _parse_placement(it):
    pos, pyr = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    for tok in it:
        key = tok[0].lower()
        if key == "end":
            break
        if key == "pos":
            pos = tuple(float(v) for v in tok[1:4])
        elif key in ("pyr", "rot"):
            pyr = tuple(float(v) for v in tok[1:4])
    return pos, pyr


def _parse_def(it, d):
    for tok in it:
        key = tok[0].lower()
        if key in ("end", "defend"):
            return
        if key == "group" and len(tok) > 1:
            pos, pyr = _parse_placement(it)
            d.groups.append((tok[1], pos, pyr))
        elif key == "lod":
            for t in it:
                k = t[0].lower()
                if k == "end":
                    break
                if k == "far" and len(t) > 1:
                    d.lod_far = float(t[1])
        elif key == "obj" and len(tok) > 1:
            d.obj = tok[1]
        elif key == "flags":
            d.flags.update(f.lower() for f in tok[1:])
        elif key in _LIGHT_KEYS:
            d.has_editor_only = True


def parse_tricks(text):
    """Returns {trick name lower: dict(hidden=bool, lod_near=float)}."""
    out = {}
    cur = None
    for tok in _lines(text):
        key = tok[0].lower()
        if key == "trick" and len(tok) > 1:
            cur = {"hidden": False, "lod_near": 0.0}
            out[tok[1].lower()] = cur
        elif cur is None:
            continue
        elif key == "end":
            cur = None
        elif key in ("trickflags", "objflags"):
            fl = {f.lower() for f in tok[1:]}
            if "nodraw" in fl or "editorvisible" in fl:
                cur["hidden"] = True
        elif key == "lodnear" and len(tok) > 1:
            try:
                cur["lod_near"] = float(tok[1])
            except ValueError:
                pass
    return out


def parse_materials(text):
    """Returns {name lower: {"base":..., "bump":..., "multiply":...}} from
    the "Texture" blocks in tricks/*.txt (composite materials)."""
    out = {}
    cur = None
    keys = {"base1": "base", "base": "base", "bumpmap1": "bump",
            "multiply1": "multiply", "dualcolor1": "dual"}
    for tok in _lines(text):
        key = tok[0].lower()
        if key == "texture" and len(tok) > 1:
            cur = {}
            out[tok[1].lower()] = cur
        elif cur is None:
            continue
        elif key == "end":
            cur = None
        elif key in keys and len(tok) > 1 and tok[1].lower() != "none":
            cur.setdefault(keys[key], tok[1])
    return out


def short_name(name):
    return name.replace("\\", "/").rsplit("/", 1)[-1].lower()


def mat_from_pyr(pos, pyr_deg):
    """Port of createMat3YPR(): returns rows [x axis, y axis, z axis, pos]."""
    p, y, r = (math.radians(a) for a in pyr_deg)
    sp, cp = math.sin(p), math.cos(p)
    sy, cy = math.sin(y), math.cos(y)
    sr, cr = math.sin(r), math.cos(r)
    m = [[0.0] * 3 for _ in range(3)]
    temp = sy * sp
    m[0][0] = cy * cr + temp * sr
    m[1][0] = cy * sr - temp * cr
    m[2][0] = sy * cp
    m[0][1] = -cp * sr
    m[1][1] = cp * cr
    m[2][1] = sp
    temp = -cy * sp
    m[0][2] = -sy * cr - temp * sr
    m[1][2] = -sy * sr + temp * cr
    m[2][2] = cy * cp
    return [m[0], m[1], m[2], list(pos)]


def mat_mul(parent, child):
    """World matrix of child placed inside parent (game row-vector form)."""
    out = []
    for i in range(3):
        row = child[i]
        out.append([sum(row[k] * parent[k][j] for k in range(3))
                    for j in range(3)])
    cp = child[3]
    out.append([sum(cp[k] * parent[k][j] for k in range(3)) + parent[3][j]
                for j in range(3)])
    return out


IDENTITY = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0], [0, 0, 0]]


class Library:
    """All object library definitions, indexed by short name."""

    def __init__(self, store):
        self.store = store
        self.defs = {}
        self.geo_for = {}    # short obj name -> geo path
        self.tricks = {}
        self.materials = {}
        names = list(store.names())
        for rel in sorted(n for n in names
                          if n.startswith("object_library/")
                          and n.endswith(".rootnames")):
            geo = rel[:-len(".rootnames")] + ".geo"
            text = store.read(rel).decode("latin-1")
            for d in parse_group_file(text, rel)[0]:
                self.geo_for.setdefault(d.name.lower(), geo)
                if d.obj:
                    self.geo_for.setdefault(d.obj.lower(), geo)
                self._add(d)
        for rel in sorted(n for n in names
                          if n.startswith("object_library/")
                          and n.endswith(".txt")):
            geo = rel[:-4] + ".geo"
            text = store.read(rel).decode("latin-1")
            for d in parse_group_file(text, rel)[0]:
                self.geo_for.setdefault(d.name.lower(), geo)
                self._add(d)
        for rel in sorted(n for n in names
                          if n.startswith("tricks/") and n.endswith(".txt")):
            text = store.read(rel).decode("latin-1")
            self.tricks.update(parse_tricks(text))
            self.materials.update(parse_materials(text))

    def _add(self, d):
        key = d.name.lower()
        old = self.defs.get(key)
        if old is None:
            self.defs[key] = d
            return
        # RootMod and later Defs layer on top of the root geometry def.
        old.groups.extend(d.groups)
        old.obj = old.obj or d.obj
        old.flags |= d.flags
        old.has_editor_only |= d.has_editor_only
        old.lod_far = d.lod_far or old.lod_far

    def trick_for(self, model_name):
        n = model_name.lower()
        if "__" in n:
            return self.tricks.get(n.split("__", 1)[1])
        return self.tricks.get(n)


class Instance:
    __slots__ = ("geo", "model", "matrix", "path")

    def __init__(self, geo, model, matrix, path):
        self.geo = geo
        self.model = model
        self.matrix = matrix
        self.path = path


def load_map(store, library, map_path):
    """Loads a map .txt and all its imports. Returns (defs dict, refs)."""
    local = {}
    refs = []
    seen = set()

    def load(rel):
        rel = rel.replace("\\", "/").lower()
        if rel in seen or rel not in store:
            return
        seen.add(rel)
        defs, r, imports = parse_group_file(store.read(rel).decode("latin-1"),
                                            rel)
        for d in defs:
            local[d.name.lower()] = d
        refs.extend(r)
        for imp in imports:
            load(imp)

    load(map_path)
    return local, refs


def resolve(library, local_defs, refs, skip_layers=()):
    """Walks the map tree. Returns (instances, missing names)."""
    out = []
    missing = set()
    skip = tuple(s.lower() for s in skip_layers)

    def find(name):
        key = short_name(name)
        return local_defs.get(key) or library.defs.get(key)

    def walk(name, mat, path, depth):
        if depth > 64:
            return
        d = find(name)
        if d is None:
            missing.add(name)
            return
        if d.source and any(s in d.source for s in skip):
            return
        if d.obj:
            obj = short_name(d.obj)
            geo = library.geo_for.get(obj)
            if geo:
                out.append(Instance(geo, d.obj, mat, path))
            else:
                missing.add(d.obj)
        for child, pos, pyr in d.groups:
            walk(child, mat_mul(mat, mat_from_pyr(pos, pyr)),
                 path + "/" + short_name(child), depth + 1)

    for name, pos, pyr in refs:
        walk(name, mat_mul(IDENTITY, mat_from_pyr(pos, pyr)),
             short_name(name), 0)
    return out, missing

"""Export City of Heroes NPC/villain characters as rigged, animated glTF.

    python -m coh2unreal.character --data i24/data --piggs piggs \\
        --villain Hellions_Brawl_Thug --out out/characters

Chain (see docs/character-export-brief.md):
villain def -> NPC costume (.nd) -> body parts (defs/ui/bodyparts.bp) ->
player_library/<prefix>_<base>.geo model GEO_<bone>_<geometry> + textures,
on the ent type's base skeleton (sequencer TypeDef BaseSkeleton), with
moves (Ready, RunCycle, ...) sampled from the sequencer's .anim files.

Every costume part stays a separate skinned mesh named after its body part
and side (Hand_R, Hand_L, Foot_R, Head, Chest, ...), so pieces such as hands
can be swapped later.

Coordinates: feet -> metres, game Z negated (left-handed -> glTF), triangle
winding swapped and V flipped, as in the zone exporter. CoH applies bone
rotations with row vectors (quatToMat + mulVecMat3), i.e. the conjugate of
the stored quaternion; with the Z mirror that becomes (x, y, -z, w).
"""
import argparse
import array
import glob
import io
import json
import os
import random
import struct
import sys

from . import anim as A
from . import idles as I
from .defs import load_sequencer, parse_braces, parse_kv
from .geo import Geo
from .pigg import AssetStore
from . import texture as T

FT = 0.3048
FPS = 30.0
# clip name -> sequencer moves to try, best first (creature sequencers name
# their melee moves differently)
DEFAULT_MOVES = [("idle", ["Ready"]),
                 ("run", ["RunCycle", "W_RunCycle"]),
                 ("attack", ["Initial_Strike", "ClawSwipe_Right", "clawslash",
                             "clawrake", "A_Initial_Strike"]),
                 ("hit", ["HitQuick", "W_HitQuick", "C_HitQuick"]),
                 ("death", ["Default_Death", "Death_Mid_Air"])]
# costume.c g_BodyTypeInfos: body type -> (ent type, texture prefix)
BODY_TYPES = {0: ("male", "SM"), 1: ("fem", "SF"), 4: ("huge", "SH"),
              5: ("enemy", "EY"), 6: ("enemy", "EY")}
PART_NAMES = {"gloves": "Hand", "boots": "Foot"}
# costume_client.c bodyPartIsLinkedToChest
CHEST_LINKED = {"collar", "capeharness", "broach", "back", "cape"}


def pos3(p):
    return (p[0] * FT, p[1] * FT, -p[2] * FT)


def quat(q):
    return (q[0], q[1], -q[2], q[3])


# ---------------------------------------------------------------- game data
class GameData:
    def __init__(self, data_dir, piggs):
        self.data_dir = data_dir
        self.store = AssetStore([], piggs)
        self.bodyparts = {}
        # BodyPart ... End blocks (BodyPart.c)
        cur = None
        for n in parse_braces(self._text("defs/ui/bodyparts.bp")):
            k = n.key.lower()
            if k == "bodypart":
                cur = n
            elif k == "end":
                if cur is not None:
                    self.bodyparts[(cur.arg("Name") or "").lower()] = cur
                cur = None
            elif cur is not None:
                cur.children.append(n)
        self._npcs = None
        self._seqs = {}
        self._anims = {}
        self._geos = {}
        self._tex = {}

    def composites(self):
        """{composite texture name: Base1 texture} from the trick files."""
        if getattr(self, "_comp", None) is None:
            self._comp = {}
            for path in glob.glob(os.path.join(self.data_dir, "tricks", "**",
                                               "*.txt"), recursive=True):
                cur = None
                with open(path, encoding="latin-1") as f:
                    for line in f:
                        t = line.split("//", 1)[0].split()
                        if not t:
                            continue
                        k = t[0].lower()
                        if k == "texture" and len(t) > 1:
                            cur = t[1].lower().rsplit(".tga", 1)[0]
                        elif k == "end":
                            cur = None
                        elif cur and k == "base1" and len(t) > 1 and                                 t[1].lower() != "none":
                            self._comp.setdefault(
                                cur, t[1].rsplit(".", 1)[0]
                                if t[1].lower().endswith(".tga") else t[1])
        return self._comp

    def chest_links(self, cos):
        """getChestGeoLink: GeoStrings for the chest part's BodySetName,
        else the first entry of defs/chestGeoLink.def."""
        if not hasattr(self, "_links"):
            self._links = [(n.arg("BonesetName") or "", n.get("GeoStrings"))
                           for n in parse_braces(self._text(
                               "defs/chestgeolink.def"))
                           if n.key.lower() == "chestgeolink"]
            self._links = [(b, g.args if g else []) for b, g in self._links]
        if not self._links:
            return []
        for cp in cos.all("CostumePart"):
            if cp.args and cp.args[0].lower() == "chest":
                bs = (cp.arg("BodySetName") or "").lower()
                for b, g in self._links:
                    if bs and b.lower() == bs:
                        return g
        return self._links[0][1]

    def _text(self, rel):
        with open(os.path.join(self.data_dir, rel), encoding="latin-1") as f:
            return f.read()

    def npcs(self):
        if self._npcs is None:
            self._npcs = {}
            for path in glob.glob(os.path.join(self.data_dir, "defs", "**",
                                               "*.nd"), recursive=True):
                with open(path, encoding="latin-1") as f:
                    for n in parse_braces(f.read()):
                        if n.key.lower() == "npc" and n.args:
                            self._npcs.setdefault(n.args[0].lower(), n)
        return self._npcs

    def villains(self):
        out = []
        for path in sorted(glob.glob(os.path.join(self.data_dir, "defs",
                                                  "villains", "*.villain"))):
            with open(path, encoding="latin-1") as f:
                for n in parse_braces(f.read()):
                    if n.key.lower() == "villaindef" and n.args:
                        out.append(n)
        return out

    def ent_type(self, name):
        p = os.path.join(self.data_dir, "ent_types", name.lower() + ".txt")
        if not os.path.exists(p):
            return {}
        return parse_kv(self._text(os.path.relpath(p, self.data_dir)))

    def sequencer(self, name):
        key = name.lower()
        if key not in self._seqs:
            self._seqs[key] = load_sequencer(self.data_dir, name)
        return self._seqs[key]

    def anim(self, name):
        key = name.lower().replace("\\", "/")
        if key not in self._anims:
            rel = "player_library/animations/%s.anim" % key
            self._anims[key] = A.AnimTrack(self.store.read(rel)) \
                if rel in self.store else None
        return self._anims[key]

    def geo(self, rel):
        key = rel.lower()
        if key not in self._geos:
            self._geos[key] = Geo(self.store.read(key), key) \
                if key in self.store else None
        return self._geos[key]

    def texture(self, name):
        """RGBA PIL image for a costume texture base name, or None."""
        from PIL import Image
        key = name.lower()
        if key in self._tex:
            return self._tex[key]
        img = None
        hits = self.store.find_basename(key + ".texture")
        if not hits:
            # composite "trick" textures (tricks/**/*.txt `Texture X_...`)
            base = self.composites().get(key)
            if base:
                hits = self.store.find_basename(base.lower() + ".texture")
        if hits:
            _n, payload = T.unwrap(self.store.read(hits[0]))
            try:
                img = Image.open(io.BytesIO(payload))
                img.load()
                img = img.convert("RGBA")
            except Exception:
                img = None
        self._tex[key] = img
        return img


# ------------------------------------------------------------------ costume
class Part:
    def __init__(self, body_part, side, bone_id, geo_rel, models, tex1, tex2,
                 c1, c2):
        self.body_part = body_part
        self.side = side
        self.bone_id = bone_id
        self.geo_rel = geo_rel
        self.models = models        # candidate model names, best first
        self.tex1 = tex1
        self.tex2 = tex2
        self.c1 = c1
        self.c2 = c2

    @property
    def label(self):
        base = PART_NAMES.get(self.body_part.lower(), self.body_part)
        return "%s_%s" % (base, self.side) if self.side else base


def _color(node, key, default=(255, 255, 255)):
    n = node.get(key)
    if n is None or len(n.args) < 3:
        return default
    return tuple(int(float(v)) for v in n.args[:3])


def _single_or_dual(tex1):
    """calc_tex_types1: (single_texture, dual_pass) from the tex1 suffix."""
    t = (tex1 or "").lower()
    return t.endswith("x"), t.endswith("a")


def resolve_costume(gd, npc, log):
    cos = npc.get("Costume")
    if cos is None:
        raise ValueError("NPC %s has no Costume" % npc.args[0])
    body_type = int(cos.arg("BodyType", "0"))
    ent_name = cos.arg("EntTypeFile") or BODY_TYPES.get(body_type,
                                                        ("male",))[0]
    prefix = cos.arg("CostumeFilePrefix") or ent_name
    gender = BODY_TYPES.get(body_type, ("male", "SM"))[1]
    skin = _color(cos, "SkinColor")
    links = gd.chest_links(cos)
    parts = []
    for cp in cos.all("CostumePart"):
        name = cp.args[0] if cp.args else ""
        bp = gd.bodyparts.get(name.lower())
        if bp is None:
            log("  part %s: no body part def" % name)
            continue
        geom = cp.arg("Geometry") or "None"
        if geom.lower() == "none":
            continue
        tex1 = cp.arg("Texture1") or "None"
        tex2 = cp.arg("Texture2") or "None"
        c1, c2 = _color(cp, "Color1"), _color(cp, "Color2")
        if "skin" in tex1.lower():          # get_color
            c1, c2 = skin, c1
        two = int(bp.arg("BoneCount", "1")) == 2
        geo_name = bp.arg("GeoName")
        sides = ("R", "L") if two else ("",)
        linked = name.lower() in CHEST_LINKED
        for side in sides:
            if ".geo/" in geom.lower():
                cut = geom.lower().index(".geo/")
                f, m = geom[:cut + 4], geom[cut + 5:]
                if two and "*" not in m:
                    # doChangeGeo: an explicit LArmR/LArmL model fills one
                    # side only; anything else goes on both bones as given
                    if "larm" + side.lower() not in m.lower() and                             "larm" in m.lower():
                        continue
                geo_rel = "player_library/" + f
                plain = m.replace("*", side)
                models = ["%s_%s" % (plain, l) for l in links]                     if linked else []
            else:
                geo_rel = "player_library/%s_%s.geo" % (prefix,
                                                        bp.arg("BaseName"))
                head = "GEO_%s%s" % (geo_name, side)
                plain = "%s_%s" % (head, geom)
                models = ["%s_%s_%s" % (head, l, geom) for l in links]                     if linked else []
            models.append(plain)
            bone = A.bone_id_from_text(geo_name + side)
            t1, t2 = texture_names(bp, tex1, tex2, prefix, gender, gd)
            parts.append(Part(name, side, bone, geo_rel, models, t1, t2,
                              c1, c2))
    return ent_name, prefix, parts


def texture_names(bp, tex1, tex2, prefix, gender, gd):
    """determineTextureNames (costume_client.c), returns base names or None
    for 'none'."""
    tex_name = bp.arg("TexName")
    single, dual = _single_or_dual(tex1)

    def full(t):
        if t.startswith("!"):
            return t[1:]
        return "%s_%s" % (tex_name, t)

    def fix(n):
        # gender_prefix_fixup: textures may carry an SM_/SF_/prefix_ prefix
        for p in (gender, prefix):
            cand = "%s_%s" % (p, n)
            if gd.store.find_basename(cand.lower() + ".texture"):
                return cand
        return n

    o1 = None if tex1.lower().lstrip("!") == "none" else full(tex1)
    if tex2.lower().lstrip("!") == "none" or single:
        o2 = None
    elif dual and not tex2.startswith("!") and o1 and \
            o1.lower().endswith("01a"):
        o2 = o1[:-1] + "B"       # villain hack in determineTextureNames
    else:
        o2 = full(tex2)
    if o1 and not tex1.startswith("!"):
        o1 = fix(o1)
    if o2 and not tex2.startswith("!"):
        o2 = fix(o2)
    return o1, o2


TINT_GAIN = 1.0


def tinted_png(gd, part, cache):
    """Bakes the COLORBLEND_DUAL look into one unlit base colour texture:
    C = T2*c1 + (1-T2)*c2, out = T1 * lerp(gain*C, 1, T1.a). The shader
    multiplies by 4*light twice; gain 1 keeps the texture detail closest to
    the game look (2 washes pale colours out to white; tunable)."""
    key = (part.tex1, part.tex2, part.c1, part.c2)
    if key in cache:
        return cache[key]
    import numpy as np
    from PIL import Image
    t1 = gd.texture(part.tex1) if part.tex1 else None
    t2 = gd.texture(part.tex2) if part.tex2 else None
    if t1 is None and t2 is None:
        cache[key] = (None, False)
        return cache[key]
    size = (t1 or t2).size
    a1 = np.asarray(t1, dtype=np.float32) / 255.0 if t1 is not None \
        else np.ones((size[1], size[0], 4), np.float32)
    if t2 is not None:
        if t2.size != size:
            t2 = t2.resize(size)
        t2a = np.asarray(t2, dtype=np.float32) / 255.0
        a2, opacity = t2a[..., :3], t2a[..., 3:4]
    else:
        a2 = np.ones((size[1], size[0], 3), np.float32)
        opacity = None
    c1 = np.array(part.c1, np.float32) / 255.0
    c2 = np.array(part.c2, np.float32) / 255.0
    c = a2 * c1 + (1.0 - a2) * c2
    alpha = a1[..., 3:4]
    rgb = a1[..., :3] * (alpha + (1.0 - alpha) * TINT_GAIN * c)
    # alpha = c1.a * T2.a: emblems and decals cut out with Texture2's alpha
    masked = opacity is not None and float(opacity.min()) < 0.5
    if masked:
        rgba = np.concatenate([rgb, opacity], axis=2)
        img = Image.fromarray((np.clip(rgba, 0, 1) * 255 + 0.5).astype(
            np.uint8), "RGBA")
    else:
        img = Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(
            np.uint8), "RGB")
    out = io.BytesIO()
    img.save(out, "PNG")
    cache[key] = (out.getvalue(), masked)
    return cache[key]


# ----------------------------------------------------------------- skeleton
class Skeleton:
    def __init__(self, base):
        self.base = base
        self.parents = base.parents()
        self.order = []                     # parents before children
        kids = {}
        for b, p in self.parents.items():
            kids.setdefault(p, []).append(b)

        def walk(p):
            for b in sorted(kids.get(p, [])):
                self.order.append(b)
                walk(b)
        walk(-1)
        self.local = {b: (base.tracks[b].poss[0] if b in base.tracks
                          else (0.0, 0.0, 0.0)) for b in self.order}
        self.world = {}
        for b in self.order:
            p = self.parents[b]
            l = self.local[b]
            w = self.world[p] if p >= 0 else (0.0, 0.0, 0.0)
            self.world[b] = (w[0] + l[0], w[1] + l[1], w[2] + l[2])

    def btt(self, b):
        """Bone translation total with HIPS at 0 (seqskeleton.c)."""
        h = self.world.get(A.BONE_IDS["HIPS"], (0.0, 0.0, 0.0))
        w = self.world.get(b, h)
        return (w[0] - h[0], w[1] - h[1], w[2] - h[2])


# ---------------------------------------------------------------- glTF out
class Builder:
    def __init__(self):
        self.buf = bytearray()
        self.gltf = {"asset": {"version": "2.0",
                               "generator": "coh2unreal.character"},
                     "scene": 0, "scenes": [{"nodes": []}], "nodes": [],
                     "meshes": [], "materials": [], "textures": [],
                     "images": [], "samplers": [{"magFilter": 9729,
                                                 "minFilter": 9987}],
                     "accessors": [], "bufferViews": [], "skins": [],
                     "animations": []}

    def view(self, data, target=None):
        while len(self.buf) % 4:
            self.buf.append(0)
        v = {"buffer": 0, "byteOffset": len(self.buf),
             "byteLength": len(data)}
        if target:
            v["target"] = target
        self.buf.extend(data)
        self.gltf["bufferViews"].append(v)
        return len(self.gltf["bufferViews"]) - 1

    def accessor(self, values, ncomp, ctype, target=None, minmax=False):
        fmt = {5126: "f", 5123: "H", 5121: "B", 5125: "I"}[ctype]
        arr = array.array(fmt, values)
        typ = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4",
               16: "MAT4"}[ncomp]
        acc = {"bufferView": self.view(arr.tobytes(), target),
               "componentType": ctype, "count": len(arr) // ncomp,
               "type": typ}
        if minmax:
            acc["min"] = [min(arr[i::ncomp]) for i in range(ncomp)]
            acc["max"] = [max(arr[i::ncomp]) for i in range(ncomp)]
        self.gltf["accessors"].append(acc)
        return len(self.gltf["accessors"]) - 1

    def node(self, d):
        self.gltf["nodes"].append(d)
        return len(self.gltf["nodes"]) - 1


def export_npc(gd, npc_name, out_dir, name=None, moves=DEFAULT_MOVES,
               log=print):
    npc = gd.npcs().get(npc_name.lower())
    if npc is None:
        raise KeyError("NPC costume %s not found" % npc_name)
    name = name or npc_name
    ent_name, prefix, parts = resolve_costume(gd, npc, log)
    et = gd.ent_type(ent_name)
    seq_file = (et.get("sequencer") or ["player.txt"])[0]
    seq_type = (et.get("sequencertype") or [ent_name])[0]
    seq = gd.sequencer(seq_file)
    base_name = seq.base_skeleton(seq_type) or "male/skel_ready2"
    base = gd.anim(base_name)
    if base is None or base.hierarchy is None:
        raise ValueError("base skeleton %s missing" % base_name)
    sk = Skeleton(base)
    log("%s: ent %s, sequencer %s/%s, skeleton %s, %d bones" % (
        name, ent_name, seq_file, seq_type, base_name, len(sk.order)))

    b = Builder()
    g = b.gltf
    joint_index = {}
    for bid in sk.order:
        p = sk.parents[bid]
        joint_index[bid] = b.node({"name": A.BONE_NAMES[bid],
                                   "translation": list(pos3(sk.local[bid]))})
    for bid in sk.order:
        p = sk.parents[bid]
        if p >= 0:
            g["nodes"][joint_index[p]].setdefault("children", []).append(
                joint_index[bid])
    roots = [joint_index[b_] for b_ in sk.order if sk.parents[b_] < 0]
    joints = [joint_index[b_] for b_ in sk.order]
    jslot = {bid: i for i, bid in enumerate(sk.order)}
    ibm = []
    for bid in sk.order:
        w = pos3(sk.world[bid])
        ibm.extend([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0,
                    -w[0], -w[1], -w[2], 1])
    skin = {"name": name + "_skin", "joints": joints,
            "inverseBindMatrices": b.accessor(ibm, 16, 5126),
            "skeleton": roots[0]}
    g["skins"].append(skin)

    scale = 1.0 + float(npc.get("Costume").arg("Scale", "0") or 0) / 100.0
    gscale = [float(v) for v in (et.get("geomscale") or [1, 1, 1])[:3]]
    # The Z mirror leaves the character facing -Z; turn it to face +Z (the
    # glTF forward axis) without changing its handedness.
    root = b.node({"name": name, "children": roots,
                   "rotation": [0.0, 1.0, 0.0, 0.0],
                   "scale": [scale * gscale[0], scale * gscale[1],
                             scale * gscale[2]]})
    g["scenes"][0]["nodes"].append(root)

    tex_cache = {}
    mat_index = {}
    hips_w = sk.world.get(0, (0.0, 0.0, 0.0))
    exported = []
    for part in parts:
        geo = gd.geo(part.geo_rel)
        model = None
        if geo is not None:
            # model names may carry "__trick" suffixes (__dblsided, __alpha)
            byname = {}
            for m in geo.models:
                byname.setdefault(m.name.split("__")[0].lower(), m)
            for want in part.models:
                model = byname.get(want.lower())
                if model is not None:
                    break
        if model is None:
            log("  missing %s in %s" % (part.models[-1], part.geo_rel))
            continue
        attach = A.bone_id_from_text(model.name[4:])
        if attach < 0:
            attach = part.bone_id
        mesh = geo.mesh(model)
        weights = geo.skin(model)
        off = sk.btt(attach)
        pos = mesh["positions"]
        nrm = mesh["normals"]
        uv = mesh["uvs"]
        nv = model.vert_count
        P, N, U, J, W = [], [], [], [], []
        for v in range(nv):
            p = (pos[3 * v] + off[0] + hips_w[0],
                 pos[3 * v + 1] + off[1] + hips_w[1],
                 pos[3 * v + 2] + off[2] + hips_w[2])
            P.extend(pos3(p))
            if nrm:
                N.extend((nrm[3 * v], nrm[3 * v + 1], -nrm[3 * v + 2]))
            U.extend((uv[2 * v], 1.0 - uv[2 * v + 1]) if uv else (0, 0))
            if weights:
                b0, b1, w0 = weights[v]
            else:
                b0, b1, w0 = attach, attach, 1.0
            j0 = jslot.get(b0, jslot.get(attach, 0))
            j1 = jslot.get(b1, j0)
            if j0 == j1 or w0 >= 1.0:
                J.extend((j0, 0, 0, 0))
                W.extend((1.0, 0.0, 0.0, 0.0))
            else:
                J.extend((j0, j1, 0, 0))
                W.extend((w0, 1.0 - w0, 0.0, 0.0))
        attrs = {"POSITION": b.accessor(P, 3, 5126, 34962, True),
                 "TEXCOORD_0": b.accessor(U, 2, 5126, 34962),
                 "JOINTS_0": b.accessor(J, 4, 5123, 34962),
                 "WEIGHTS_0": b.accessor(W, 4, 5126, 34962)}
        if N:
            attrs["NORMAL"] = b.accessor(N, 3, 5126, 34962)
        png, masked = tinted_png(gd, part, tex_cache)
        mkey = (part.tex1, part.tex2, part.c1, part.c2)
        if mkey not in mat_index:
            mat = {"name": "M_%s_%s" % (name, part.label),
                   "pbrMetallicRoughness": {"metallicFactor": 0.0,
                                            "roughnessFactor": 0.8},
                   "doubleSided": False}
            if masked:
                mat["alphaMode"] = "MASK"
                mat["alphaCutoff"] = 0.5
            if png:
                fn = "%s_%s.png" % (name, part.label)
                with open(os.path.join(out_dir, "textures", fn), "wb") as f:
                    f.write(png)
                g["images"].append({"uri": "textures/" + fn})
                g["textures"].append({"source": len(g["images"]) - 1,
                                      "sampler": 0})
                mat["pbrMetallicRoughness"]["baseColorTexture"] = {
                    "index": len(g["textures"]) - 1}
            else:
                mat["pbrMetallicRoughness"]["baseColorFactor"] = [
                    part.c1[0] / 255, part.c1[1] / 255, part.c1[2] / 255, 1]
            g["materials"].append(mat)
            mat_index[mkey] = len(g["materials"]) - 1
        prims = []
        for _tname, tris in mesh["groups"]:
            if not tris:
                continue
            idx = []
            for t in range(0, len(tris), 3):
                idx.extend((tris[t], tris[t + 2], tris[t + 1]))
            prims.append({"attributes": attrs,
                          "indices": b.accessor(idx, 1, 5125, 34963),
                          "material": mat_index[mkey]})
        g["meshes"].append({"name": part.label, "primitives": prims})
        n = b.node({"name": part.label, "mesh": len(g["meshes"]) - 1,
                    "skin": 0,
                    "extras": {"cohBodyPart": part.body_part,
                               "cohBone": A.BONE_NAMES[attach],
                               "cohModel": model.name,
                               "cohGeo": part.geo_rel,
                               "cohTexture1": part.tex1,
                               "cohTexture2": part.tex2}})
        g["nodes"][root]["children"].append(n)
        exported.append(part.label)
    log("  parts: %s" % ", ".join(exported))

    # ------------------------------------------------------------ animations
    clips = []
    for clip_name, cands in moves:
        if isinstance(cands, str):
            cands = [cands]
        a = move = None
        for move in cands:
            a = seq.anim_for(move, seq_type)
            if a:
                break
        if not a:
            log("  clip %s: no move for %s" % (clip_name, seq_type))
            continue
        anim_name, first, last = a
        tr = gd.anim(anim_name)
        if tr is None:
            log("  move %s: %s.anim missing" % (move, anim_name))
            continue
        abase = gd.anim(tr.base_name) if tr.base_name else None
        if not last:
            last = int(tr.length)
        frames = list(range(first, last + 1))
        times = [(f - first) / FPS for f in frames]
        tacc = b.accessor(times, 1, 5126, minmax=True)
        channels, samplers = [], []
        for bid in sk.order:
            bt = tr.tracks.get(bid)
            if bt is None and abase is not None:
                bt = abase.tracks.get(bid)
            if bt is None:
                continue
            # animDelta: animPos - (animBasePos - basePos)
            ab = bt.poss[0]
            bp = sk.local[bid]
            delta = (ab[0] - bp[0], ab[1] - bp[1], ab[2] - bp[2])
            R, Pp = [], []
            prev = None
            for f in frames:
                r, p = A.sample(bt, f)
                q = quat(r)
                if prev is not None and sum(x * y for x, y in
                                            zip(q, prev)) < 0:
                    q = tuple(-x for x in q)
                prev = q
                R.extend(q)
                Pp.extend(pos3((p[0] - delta[0], p[1] - delta[1],
                                p[2] - delta[2])))
            si = len(samplers)
            samplers.append({"input": tacc,
                             "output": b.accessor(R, 4, 5126),
                             "interpolation": "LINEAR"})
            channels.append({"sampler": si, "target": {
                "node": joint_index[bid], "path": "rotation"}})
            samplers.append({"input": tacc,
                             "output": b.accessor(Pp, 3, 5126),
                             "interpolation": "LINEAR"})
            channels.append({"sampler": si + 1, "target": {
                "node": joint_index[bid], "path": "translation"}})
        g["animations"].append({"name": clip_name, "channels": channels,
                                "samplers": samplers,
                                "extras": {"cohMove": move,
                                           "cohAnim": anim_name,
                                           "frames": [first, last]}})
        clips.append(clip_name)
    log("  clips: %s" % ", ".join(clips))

    for k in ("textures", "images", "materials", "animations"):
        if not g[k]:
            del g[k]
    g["buffers"] = [{"uri": name + ".bin", "byteLength": len(b.buf)}]
    with open(os.path.join(out_dir, name + ".bin"), "wb") as f:
        f.write(b.buf)
    path = os.path.join(out_dir, name + ".gltf")
    with open(path, "w") as f:
        json.dump(g, f, indent=1)
    return {"gltf": path, "parts": exported, "clips": clips,
            "skeleton": base_name}


def villain_info(v):
    levels = []
    costumes = []
    for lv in v.all("Level"):
        try:
            levels.append(int(lv.args[0]))
        except (IndexError, ValueError):
            pass
        c = lv.get("Costumes")
        if c:
            for n in c.args:
                if n not in costumes:
                    costumes.append(n)
    return {"name": v.args[0], "group": v.arg("VillainGroup"),
            "rank": v.arg("Rank"), "levels": levels, "costumes": costumes}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", required=True, help="i24/data folder")
    ap.add_argument("--piggs", required=True, help="folder of .pigg files")
    ap.add_argument("--out", required=True)
    ap.add_argument("--villain", action="append", default=[],
                    help="VillainDef name (repeatable)")
    ap.add_argument("--group", help="export every villain of this group")
    ap.add_argument("--npc", action="append", default=[],
                    help="NPC costume name (repeatable)")
    ap.add_argument("--all-costumes", action="store_true",
                    help="export every costume variant, not just the first")
    ap.add_argument("--max-level", type=int,
                    help="only villains spawning at or below this level")
    ap.add_argument("--idles", help="idle graph JSON from coh2unreal.idles: "
                    "also export each idle/pose state as a clip and copy "
                    "the graph to <out>/idles.json")
    ap.add_argument("--tint-gain", type=float, default=TINT_GAIN,
                    help="brightness of the baked colour tint (default 1)")
    args = ap.parse_args(argv)
    globals()["TINT_GAIN"] = args.tint_gain

    gd = GameData(args.data, glob.glob(os.path.join(args.piggs, "*.pigg")))
    moves = DEFAULT_MOVES
    if args.idles:
        moves = DEFAULT_MOVES + I.clip_moves(args.idles)
        os.makedirs(args.out, exist_ok=True)
        import shutil
        shutil.copyfile(args.idles, os.path.join(args.out, "idles.json"))
    jobs = []      # (npc costume, out name, info)
    vil = {v.args[0].lower(): v for v in gd.villains()}
    picks = [vil[n.lower()] for n in args.villain if n.lower() in vil]
    for n in args.villain:
        if n.lower() not in vil:
            print("unknown villain %s" % n, file=sys.stderr)
    if args.group:
        picks += [v for v in vil.values()
                  if (v.arg("VillainGroup") or "").lower() ==
                  args.group.lower()]
    for v in picks:
        info = villain_info(v)
        if args.max_level and (not info["levels"] or
                               min(info["levels"]) > args.max_level):
            continue
        cos = info["costumes"] if args.all_costumes else info["costumes"][:1]
        for c in cos:
            jobs.append((c, c, info))
    for n in args.npc:
        jobs.append((n, n, None))

    index_path = os.path.join(args.out, "index.json")
    index = []
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)
    done = {e["costume"].lower(): e for e in index}
    skipped = set()
    for costume, oname, info in jobs:
        if costume.lower() in skipped:
            continue
        prev = done.get(costume.lower())
        if prev is not None:
            if info and info["name"] not in prev.setdefault("villains", []):
                prev["villains"].append(info["name"])
                if info["rank"] and info["rank"] not in prev["ranks"]:
                    prev["ranks"].append(info["rank"])
                if info["levels"]:
                    prev["level_min"] = min(prev["level_min"],
                                            min(info["levels"]))
                    prev["level_max"] = max(prev["level_max"],
                                            max(info["levels"]))
                with open(index_path, "w") as f:
                    json.dump(index, f, indent=1)
            continue
        group = (info or {}).get("group") or "misc"
        odir = os.path.join(args.out, group.lower(), oname)
        os.makedirs(os.path.join(odir, "textures"), exist_ok=True)
        try:
            res = export_npc(gd, costume, odir, oname, moves)
        except Exception as e:      # keep the batch going
            print("FAILED %s: %s" % (costume, e), file=sys.stderr)
            continue
        if not res["parts"]:
            # FX-only critters (fire puddles, runes) have no body to export
            print("SKIPPED %s: no geometry" % costume, file=sys.stderr)
            import shutil
            shutil.rmtree(odir, ignore_errors=True)
            skipped.add(costume.lower())
            continue
        entry = {"costume": costume,
                 "gltf": os.path.relpath(res["gltf"], args.out).replace(
                     "\\", "/"),
                 "parts": res["parts"], "clips": res["clips"],
                 "skeleton": res["skeleton"]}
        if info:
            entry.update({"villains": [info["name"]],
                          "group": info["group"],
                          "ranks": [info["rank"]] if info["rank"] else [],
                          "level_min": min(info["levels"] or [0]),
                          "level_max": max(info["levels"] or [0])})
        index.append(entry)
        done[costume.lower()] = entry
        with open(index_path, "w") as f:
            json.dump(index, f, indent=1)
    print("%d characters in %s" % (len(index), index_path))


if __name__ == "__main__":
    main()

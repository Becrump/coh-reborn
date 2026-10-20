"""Export the original power effects (.fx, .part, .bhvr) for Unreal.

    python -m coh2unreal.fx --data i24/data --piggs piggs --out out/fx export \
        --powers-json out/powers/power_anims.json --set Blaster_Ranged.Fire_Blast
    python -m coh2unreal.fx ... export --fx powers/firecontrol/firebolt.fx
    python -m coh2unreal.fx ... export --powers-json ... --all

An effect (.fx, data/fx) is a timeline of conditions ("at tick 16", "when the
projectile hits") that fire events. An event places a node on a bone of the
caster or target (At WepR, T_Chest), optionally moving by a behavior (.bhvr:
velocity, gravity, tracking toward a magnet such as the target), and starts
particle systems (.part) on it, child effects, sounds or geometry.

The export keeps the original parameters, typed and with the engine's
defaults filled in (Game/src/graphics/FX/particle.c, Common/fxinfo.c and
fxbhvr.c in Thunderspies/CityOfHeroes), so the Unreal side can map them onto
a parametric Niagara emitter:

    fx_library.json  {"fx": {path: fx}, "parts": {path: part},
                      "behaviors": {path: bhvr}, "textures": {name: png},
                      "missing": [...]}
    geoms/*.gltf     visible effect models (Blazing Bolt's flame cone...)
    sounds/*.wav     effect sounds (Sound lines), converted with ffmpeg
    power_fx.json    {power: {"AttackFX": path, "HitFX": ..., "ProjectileSpeed",
                      "FramesBeforeHit", "themes": [...]}}
    textures/*.png

Units are the game's: feet, and ticks of 1/30 s. Velocities are feet per tick,
spin is 1/256 turns, colors are 0-255. Paths are lower case, relative to
data/fx.
"""
import argparse
import glob
import json
import os
import re
import sys

FPS = 30
FX_BLOCKS = {"fxinfo", "input", "condition", "event", "bhvroverride"}

# (keyword, kind, default). Kinds: f float, i int, s string, v3 vec3,
# fN / iN float or int array expanded to N (missing values copy the first,
# like ExpandF32Params), flags list of names.
PART_FIELDS = [
    ("FrontOrLocalFacing", "i", 0), ("WorldOrLocalPosition", "i", 0),
    ("TimeToFull", "f", 0), ("KickStart", "i", 0),
    ("NewPerFrame", "f2", 0), ("Burst", "i2", 0),
    ("BurbleAmplitude", "f2", 0), ("BurbleType", "i", 0),
    ("BurbleFrequency", "f", 0), ("BurbleThreshold", "f", 0),
    ("MoveScale", "f", 0),
    ("EmissionType", "i", 0), ("EmissionStartJitter", "f6", 0),
    ("EmissionRadius", "f", 0), ("EmissionHeight", "f", 0),
    ("EmissionLifeSpan", "f", 0), ("EmissionLifeSpanJitter", "f", 0),
    ("Spin", "i", 0), ("SpinJitter", "i", 0), ("OrientationJitter", "i", 0),
    ("Magnetism", "f", 0), ("Gravity", "f", 0), ("KillOnZero", "i", 0),
    ("Terrain", "i", 0),
    ("InitialVelocity", "f6", 0), ("InitialVelocityJitter", "f6", 0),
    ("VelocityJitter", "v3", 0), ("TightenUp", "f", 0), ("SortBias", "f", 0),
    ("Drag", "f", 0), ("Stickiness", "f", 0),
    ("ColorOffset", "v3", 0), ("ColorOffsetJitter", "v3", 0),
    ("Alpha", "i2", 0), ("ColorChangeType", "i", 0),
    ("FadeInBy", "f", 0), ("FadeOutStart", "f", 0), ("FadeOutBy", "f", 0),
    ("DieLikeThis", "s", ""), ("DeathAgeToZero", "i", 0),
    ("StartSize", "f2", 0), ("StartSizeJitter", "f", 0),
    ("EndSize", "f2", 0), ("ExpandRate", "f", 0), ("ExpandType", "i", 0),
    ("Blend_mode", "blend", 0),
    ("TextureName", "s", "white"), ("TextureName2", "s", "white"),
    ("TexScroll1", "v3", 0), ("TexScroll2", "v3", 0),
    ("TexScrollJitter1", "v3", 0), ("TexScrollJitter2", "v3", 0),
    ("AnimFrames1", "f", 0), ("AnimFrames2", "f", 0),
    ("AnimPace1", "f", 0), ("AnimPace2", "f", 0),
    ("AnimType1", "i", 0), ("AnimType2", "i", 0),
    ("StreakType", "i", 0), ("StreakScale", "f", 0),
    ("StreakOrient", "i", 0), ("StreakDirection", "i", 0),
    ("VisRadius", "f", 0), ("VisDist", "f", 0),
    ("Flags", "flags", []),
]
BHVR_FIELDS = [
    ("StartJitter", "v3", 0), ("InitialVelocity", "v3", 0),
    ("InitialVelocityJitter", "v3", 0), ("InitialVelocityAngle", "f", 0),
    ("Gravity", "f", 0), ("Physics", "i", 0), ("PhysRadius", "f", 0),
    ("PhysGravity", "f", 1.0), ("PhysRestitution", "f", 0),
    ("PhysSFriction", "f", 0), ("PhysDFriction", "f", 0),
    ("PhysKillBelowSpeed", "f", 0), ("PhysDensity", "f", 1.0),
    ("PhysForceRadius", "f", 0), ("PhysForcePower", "f", 0),
    ("PhysForcePowerJitter", "f", 0), ("PhysForceCentripetal", "f", 2.0),
    ("PhysForceSpeedScaleMax", "f", 0), ("PhysScale", "v3", 0),
    ("PhysForceType", "s", "None"), ("PhysDebris", "s", "None"),
    ("Spin", "v3", 0), ("SpinJitter", "v3", 0),
    ("FadeInLength", "f", 0), ("FadeOutLength", "f", 0),
    ("Shake", "f", 0), ("ShakeFallOff", "f", 0), ("ShakeRadius", "f", 0),
    ("Blur", "f", 0), ("BlurFallOff", "f", 0), ("BlurRadius", "f", 0),
    ("Scale", "v3", 0), ("ScaleRate", "v3", 0), ("ScaleTime", "v3", 0),
    ("EndScale", "v3", 0), ("Stretch", "i", 0), ("Drag", "f", 0),
    ("PyrRotate", "v3", 0), ("PyrRotateJitter", "v3", 0),
    ("PositionOffset", "v3", 0), ("UseShieldOffset", "i", 0),
    ("TrackRate", "f", 0), ("TrackMethod", "i", 0), ("Collides", "i", 0),
    ("LifeSpan", "i", 0), ("AnimScale", "f", 0), ("Alpha", "i", 0),
    ("PulsePeakTime", "f", 0), ("PulseBrightness", "f", 0),
    ("PulseClamp", "f", 0), ("HueShift", "f", 0), ("HueShiftJitter", "f", 0),
]
BLEND_MODES = ["Normal", "Additive", "Subtractive", "PremultipliedAlpha",
               "Multiply", "SubtractiveInverse"]
# color nav points: (rgb key, alt key, time key, alt time key)
NAV_KEYS = [("startcolor", "rgb0", None, None),
            ("becolor1", "rgb1", "bytime1", "rgb0time"),
            ("becolor2", "rgb2", "bytime2", "rgb1time"),
            ("becolor3", "rgb3", "bytime3", "rgb2time"),
            ("becolor4", "rgb4", "bytime4", "rgb3time")]
# power fields that name effects
POWER_FX_KEYS = ("ActivationFX", "WindUpFX", "InitialAttackFX", "AttackFX",
                 "SecondaryAttackFX", "HitFX", "BlockFX", "DeathFX",
                 "ContinuingFX", "ContinuingFX1", "ContinuingFX2",
                 "ContinuingFX3", "ConditionalFX", "ConditionalFX1",
                 "ConditionalFX2", "ConditionalFX3", "ActivationFX",
                 "DeactivationFX", "InitialFX", "AttackFX1", "AttackFX2")
POWER_TIMING_KEYS = ("FramesBeforeHit", "AttackFrames", "ProjectileSpeed",
                     "DelayedHit", "FramesBeforeSecondaryHit",
                     "InitialFramesBeforeHit", "Palette")


class Block:
    """A keyword block: items are (keyword_lower, args) lines and sub-blocks
    (keyword_lower, Block), in file order."""

    def __init__(self, key):
        self.key = key
        self.items = []

    def lines(self, key):
        return [a for k, a in self.items if k == key and isinstance(a, list)]

    def first(self, key, default=None):
        for k, a in self.items:
            if k == key and isinstance(a, list):
                return a
        return default

    def blocks(self, key):
        return [b for k, b in self.items if k == key and isinstance(b, Block)]


def _tokens(line):
    line = re.split(r"#|//", line, maxsplit=1)[0]
    return [t.strip('"') for t in re.findall(r'"[^"]*"|\S+', line)]


def parse_blocks(text, block_keys):
    """Parses the game's keyword/End text format into a root Block."""
    root = Block("root")
    stack = [root]
    for raw in text.splitlines():
        toks = _tokens(raw)
        if not toks:
            continue
        key = toks[0].lower()
        if key == "end":
            if len(stack) > 1:
                stack.pop()
            continue
        if key in block_keys:
            b = Block(key)
            b.args = toks[1:]
            stack[-1].items.append((key, b))
            stack.append(b)
        else:
            stack[-1].items.append((key, toks[1:]))
    return root


def _num(s):
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s


def _typed(block, fields):
    out = {}
    for name, kind, default in fields:
        args = block.first(name.lower())
        if kind in ("f", "i"):
            v = default
            if args:
                try:
                    v = float(args[0]) if kind == "f" else int(float(args[0]))
                except ValueError:
                    pass
        elif kind == "s":
            v = args[0] if args else default
        elif kind == "v3":
            v = [0.0, 0.0, 0.0]
            for i, a in enumerate((args or [])[:3]):
                try:
                    v[i] = float(a)
                except ValueError:
                    pass
        elif kind == "blend":
            v = 0
            if args:
                a = args[0]
                if a.lstrip("-").isdigit():
                    v = int(a)
                else:
                    low = [m.lower() for m in BLEND_MODES]
                    v = low.index(a.lower()) if a.lower() in low else 0
            v = BLEND_MODES[v] if 0 <= v < len(BLEND_MODES) else "Normal"
        elif kind == "flags":
            v = list(args or [])
        else:  # arrays
            n = int(kind[1:])
            vals = []
            for a in args or []:
                try:
                    vals.append(float(a) if kind[0] == "f" else int(float(a)))
                except ValueError:
                    pass
            if not vals:
                vals = [default] * (3 if n == 6 else 1)
            if n == 2:
                vals = (vals + vals[:1])[:2]
            elif n == 6:  # two vec3s: full power, low power
                vals = (vals + [0] * 3)[:3] + ((vals[3:6] + [0] * 3)[:3]
                                              if len(vals) > 3 else vals[:3])
            v = vals
        out[name] = v
    return out


def color_nav(block):
    """The color nav points [[time, r, g, b, primaryTint, secondaryTint]...]
    in effect order (the path stops at the first time that doesn't rise)."""
    pts = []
    for i, (ck, ak, tk, atk) in enumerate(NAV_KEYS):
        rgb = block.first(ck) or block.first(ak)
        t = block.first(tk) if tk else ["0"]
        if t is None and atk:
            t = block.first(atk)
        rgb = [int(float(x)) for x in (rgb or [])[:3]] + [0, 0, 0]
        pt = ("primarytint%d" % i) if i else "primarytint"
        st = ("secondarytint%d" % i) if i else "secondarytint"
        pts.append([int(float((t or ["0"])[0])), rgb[0], rgb[1], rgb[2],
                    float((block.first(pt) or ["0"])[0]),
                    float((block.first(st) or ["0"])[0])])
    if pts[0][1:4] == [0, 0, 0]:
        pts[0][1:4] = [255, 255, 255]
    pts[0][0] = 0
    out = [pts[0]]
    for p in pts[1:]:
        if p[0] > out[-1][0]:
            out.append(p)
        else:
            break
    return out


def tinted(pt, custom):
    """A nav point's color with the player's power colors mixed in by its
    PrimaryTint / SecondaryTint percents (calculateCustomColor)."""
    rgb = list(pt[1:4])
    if not custom or (not pt[4] and not pt[5]):
        return rgb
    p, s = pt[4] * 0.01, pt[5] * 0.01
    b = min(max(1.0 - p - s, 0.0), 1.0)
    p, s = min(max(p, 0.0), 1.0), min(max(s, 0.0), 1.0)
    tot = p + s + b
    if tot == 0:
        p, s, b = 0.0, 0.0, 1.0
    else:
        p, s, b = p / tot, s / tot, b / tot
    pr, se = custom
    return [p * pr[k] + s * se[k] + b * rgb[k] for k in range(3)]


def color_path(nav, custom=None):
    """One rgb per tick, as partBuildColorPath builds it. custom is the
    player's (primary, secondary) power colors for tintable systems."""
    nav = [[p[0]] + tinted(p, custom) + list(p[4:]) for p in nav]
    length = max(p[0] for p in nav) + 1
    path = []
    cur = list(nav[0][1:4])
    for a, b in zip(nav, nav[1:]):
        dt = float(b[0] - a[0])
        dv = [(b[k] - a[k]) / dt for k in (1, 2, 3)]
        cur = list(a[1:4])
        path.append(list(cur))
        t = a[0] + 1
        while t <= b[0]:
            cur = [cur[k] + dv[k] for k in range(3)]
            path.append(list(cur))
            t += 1
    while len(path) < length:
        path.append(list(nav[-1][1:4]))
    return [[int(round(c)) for c in p] for p in path[:length]]


def part_info(block):
    p = _typed(block, PART_FIELDS)
    if not p["Alpha"][0]:
        p["Alpha"][0] = 255
    if not p["Alpha"][1]:
        p["Alpha"][1] = 255
    if not p["VisDist"]:
        p["VisDist"] = 10000.0
    if p["FadeOutBy"] - p["FadeOutStart"] > 256:
        p["FadeOutBy"] = p["FadeOutStart"] + 256
    if not p["BurbleFrequency"]:
        p["BurbleFrequency"] = 1.0
    p["ColorNav"] = color_nav(block)
    return p


def bhvr_info(block, partial=False):
    """A behavior; with partial, only the keys the block names (an
    override)."""
    b = _typed(block, BHVR_FIELDS)
    if partial:
        named = {k for k, a in block.items if isinstance(a, list)}
        b = {k: v for k, v in b.items() if k.lower() in named}
    if any(k in ("startcolor", "rgb0") for k, _ in block.items):
        b["ColorNav"] = color_nav(block)
    return b


def norm_path(name, fx_dir=None):
    """Event file names: ':X.part' is next to the effect, others are
    relative to data/fx."""
    if not name:
        return None
    n = name.replace("\\", "/").strip()
    if n.startswith(":"):
        n = (fx_dir + "/" if fx_dir else "") + n[1:]
    n = n.lower().lstrip("/")
    if n.startswith("fx/"):
        n = n[3:]
    return re.sub(r"/+", "/", n)


EVENT_STRINGS = {"ename": "name", "type": "type", "at": "at",
                 "magnet": "magnet", "lookat": "lookat", "pmagnet": "pmagnet",
                 "pother": "pother", "anim": "anim", "animpiv": "animpiv",
                 "setstate": "setstate", "worldgroup": "worldgroup",
                 "atrayfx": "atrayfx"}
EVENT_FILES = {"bhvr": "bhvr", "childfx": "childfx", "cevent": "cevent",
               "jevent": "jevent"}
EVENT_NUMBERS = {"lifespan": "lifespan", "lifespanjitter": "lifespanjitter",
                 "altpiv": "altpiv", "cdestroy": "cdestroy",
                 "jdestroy": "jdestroy", "cthresh": "cthresh",
                 "raylength": "raylength", "soundnorepeat": "soundnorepeat",
                 "parentvelocityfraction": "parentvelocityfraction"}


def fx_info(root, path):
    fx_dir = path.rsplit("/", 1)[0] if "/" in path else ""
    info = root.blocks("fxinfo")
    info = info[0] if info else root
    fx = {"lifespan": int(float((info.first("lifespan") or ["0"])[0])),
          "lighting": int(float((info.first("lighting") or ["0"])[0])),
          "flags": info.first("flags") or [],
          "inputs": [((i.first("inpname") or [""])[0]).lower()
                     for i in info.blocks("input")],
          "conditions": []}
    for c in info.blocks("condition"):
        cond = {"on": ((c.first("on") or ["Time"])[0]).lower(),
                "time": float((c.first("time") or ["0"])[0])}
        for k in ("repeat", "repeatjitter", "domany", "random", "chance",
                  "dist", "daystart", "dayend", "forcethreshold"):
            a = c.first(k)
            if a:
                cond[k] = _num(a[0])
        tb = c.first("triggerbits")
        if tb:
            cond["triggerbits"] = [t.upper() for t in tb]
        cond["events"] = [fx_event(e, fx_dir) for e in c.blocks("event")]
        fx["conditions"].append(cond)
    return fx


def fx_event(e, fx_dir):
    ev = {"type": "create", "at": "origin"}
    parts, sounds, geoms, splats = [], [], [], []
    for k, a in e.items:
        if isinstance(a, Block):
            if k == "bhvroverride":
                ev["bhvroverride"] = bhvr_info(a, partial=True)
            continue
        if k in ("part", "part1", "part2", "part3", "part4", "part5"):
            if a:
                parts.append(norm_path(a[0], fx_dir) if a[0].lower().endswith(
                    ".part") or a[0].startswith(":") else norm_path(a[0]))
        elif k == "sound" and a:
            nums = [float(x) for x in a[1:4] if _is_num(x)]
            nums += [100.0, 20.0, 1.0][len(nums):]
            sounds.append({"name": a[0], "radius": nums[0], "fade": nums[1],
                           "volume": nums[2]})
        elif k == "geom" and a:
            geoms.append(a[0])
        elif k == "splat" and a:
            splats.append(a[:2])
        elif k in EVENT_STRINGS and a:
            ev[EVENT_STRINGS[k]] = a[0].lower() if k in (
                "type", "at", "magnet", "lookat", "pmagnet", "pother") else a[0]
        elif k in EVENT_FILES and a:
            ev[EVENT_FILES[k]] = norm_path(a[0], fx_dir)
        elif k in EVENT_NUMBERS and a:
            ev[EVENT_NUMBERS[k]] = _num(a[0])
        elif k in ("inherit", "update", "flags", "while", "until", "power",
                   "cape", "tintgeom", "crotation"):
            ev[k] = a
        elif k in ("hardwareonly", "softwareonly", "physicsonly",
                   "cameraspace"):
            ev[k] = True
        else:
            ev.setdefault("other", {})[k] = [_num(x) for x in a]
    if parts:
        ev["parts"] = parts
    if sounds:
        ev["sounds"] = sounds
    if geoms:
        ev["geoms"] = geoms
    if splats:
        ev["splats"] = splats
    return ev


def _is_num(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


class FxLibrary:
    """Loads effect files from data/fx (text) with the archives as a
    fallback, and the particle textures from the archives."""

    def __init__(self, data_dir, store=None):
        self.fx_dir = os.path.join(data_dir, "fx")
        self.store = store
        self.index = {}
        for root, _d, files in os.walk(self.fx_dir):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, self.fx_dir).replace("\\", "/")
                self.index[rel.lower()] = full
        self.fx, self.parts, self.bhvrs = {}, {}, {}
        self.geoms = {}
        self._geom_objs = {}
        self._geom_index = None
        self.missing = set()

    def text(self, rel):
        full = self.index.get(rel)
        if full:
            with open(full, encoding="latin-1") as f:
                return f.read()
        if self.store is not None and ("fx/" + rel) in self.store:
            return self.store.read("fx/" + rel).decode("latin-1")
        self.missing.add(rel)
        return None

    def load_fx(self, rel):
        rel = norm_path(rel)
        if rel and not rel.endswith(".fx"):
            rel += ".fx"
        if rel in self.fx:
            return self.fx[rel]
        t = self.text(rel)
        self.fx[rel] = fx = fx_info(parse_blocks(t, FX_BLOCKS), rel) \
            if t is not None else None
        if fx is None:
            return None
        for c in fx["conditions"]:
            for e in c["events"]:
                for p in e.get("parts", []):
                    self.load_part(p)
                if e.get("bhvr"):
                    self.load_bhvr(e["bhvr"])
                for k in ("childfx", "cevent", "jevent"):
                    if e.get(k):
                        self.load_fx(e[k])
        return fx

    def load_part(self, rel):
        if rel in self.parts:
            return self.parts[rel]
        t = self.text(rel)
        p = None
        if t is not None:
            systems = parse_blocks(t, {"system"}).blocks("system")
            if systems:
                p = part_info(systems[0])
        self.parts[rel] = p
        return p

    def load_bhvr(self, rel):
        if rel in self.bhvrs:
            return self.bhvrs[rel]
        t = self.text(rel)
        b = None
        if t is not None:
            blocks = parse_blocks(t, {"behavior"}).blocks("behavior")
            if blocks:
                b = bhvr_info(blocks[0])
        self.bhvrs[rel] = b
        return b

    def geom_index(self):
        """Model name -> archive .geo path, for the effect models
        (object_library/fx and player_library)."""
        if self._geom_index is None:
            self._geom_index = {}
            self._indexed = set()
            self._index_geos(lambda n: n.startswith(
                ("object_library/fx/", "player_library/"))
                and n.endswith(".geo"))
        return self._geom_index

    def _index_geos(self, want):
        from .geo import Geo
        names = [n for n in (self.store.names() if self.store else [])
                 if want(n) and n not in self._indexed]
        for n in sorted(names):
            self._indexed.add(n)
            try:
                g = Geo(self.store.read(n), n)
            except Exception:
                continue
            for m in g.models:
                low = m.name.lower()
                self._geom_index.setdefault(low, (n, g, m))
                # "FireBlast1__FireBlast1": model name, then its trick
                self._geom_index.setdefault(low.split("__")[0], (n, g, m))

    def load_geoms(self):
        """The models effect events name (Geom): file, size and alternate
        pivots. Most are invisible pivots (CenterDummy, LocalPivot01) that
        give events an offset and direction through AltPiv."""
        names = set()
        for fx in self.fx.values():
            for c in (fx or {}).get("conditions", []):
                for e in c["events"]:
                    names.update(g.lower() for g in e.get("geoms", []))
        idx = self.geom_index()
        if any(n not in idx for n in names):
            self._index_geos(lambda n: n.endswith(".geo"))
        for name in sorted(names):
            hit = idx.get(name)
            if not hit:
                self.missing.add("geom:" + name)
                continue
            path, g, m = hit
            self.geoms[name] = {"file": path, "model": m.name,
                                "tris": m.tri_count,
                                "textures": [t for t, _c in m.tex_ids],
                                "min": list(m.min), "max": list(m.max),
                                "alt_pivots": g.alt_pivots(m)}
            self._geom_objs[name] = (g, m)
        return self.geoms

    def export_geom_meshes(self, out_dir):
        """Visible effect models (more than a pivot's few triangles) as
        glTF, converted like the character exports (feet to meters, z
        negated). Materials name the particle-style texture PNGs."""
        from .character import Builder, pos3
        os.makedirs(out_dir, exist_ok=True)
        for name, (g, m) in sorted(self._geom_objs.items()):
            info = self.geoms[name]
            textures = [t.lower() for t in info["textures"]]
            if m.tri_count <= 12 or all(t in ("white", "invisible")
                                        for t in textures):
                continue
            mesh = g.mesh(m)
            b = Builder()
            b.gltf["asset"]["generator"] = "coh2unreal.fx"
            pos = [c for i in range(m.vert_count)
                   for c in pos3(mesh["positions"][i * 3:i * 3 + 3])]
            nrm = [c for i in range(m.vert_count) for c in (
                mesh["normals"][i * 3], mesh["normals"][i * 3 + 1],
                -mesh["normals"][i * 3 + 2])] if mesh["normals"] else None
            attrs = {"POSITION": b.accessor(pos, 3, 5126, minmax=True)}
            if nrm:
                attrs["NORMAL"] = b.accessor(nrm, 3, 5126)
            if mesh["uvs"]:
                attrs["TEXCOORD_0"] = b.accessor(mesh["uvs"], 2, 5126)
            prims = []
            for tname, tris in mesh["groups"]:
                if not tris:
                    continue
                idx = []
                for t in range(0, len(tris), 3):  # flip winding for -z
                    idx += [tris[t], tris[t + 2], tris[t + 1]]
                b.gltf["materials"].append({"name": tname,
                                            "extras": {"texture": tname}})
                prims.append({"attributes": attrs,
                              "indices": b.accessor(idx, 1, 5125),
                              "material": len(b.gltf["materials"]) - 1})
            b.gltf["meshes"].append({"name": m.name, "primitives": prims})
            b.gltf["scenes"][0]["nodes"].append(b.node({"name": m.name,
                                                        "mesh": 0}))
            for k in ("skins", "animations", "textures", "images"):
                if not b.gltf[k]:
                    del b.gltf[k]
            fn = re.sub(r"[^a-z0-9_]+", "_", name)
            b.gltf["buffers"] = [{"uri": fn + ".bin",
                                  "byteLength": len(b.buf)}]
            with open(os.path.join(out_dir, fn + ".bin"), "wb") as f:
                f.write(b.buf)
            with open(os.path.join(out_dir, fn + ".gltf"), "w") as f:
                json.dump(b.gltf, f)
            info["mesh"] = "geoms/" + fn + ".gltf"

    def tricks(self):
        """Trick and Texture blocks of data/tricks: per-model scrolling,
        blend and flags (Trick NAME, matched by the "__NAME" model suffix)
        and composite materials (Texture X_NAME: Base1, Multiply1, DualColor1
        ... layers)."""
        if getattr(self, "_tricks", None) is None:
            self._tricks = ({}, {})
            root = os.path.join(os.path.dirname(self.fx_dir), "tricks")
            for d, _s, files in os.walk(root):
                for fn in sorted(files):
                    if not fn.lower().endswith(".txt"):
                        continue
                    with open(os.path.join(d, fn), encoding="latin-1") as f:
                        tree = parse_blocks(f.read(), {"trick", "texture"})
                    for k, b in tree.items:
                        if isinstance(b, Block) and b.args:
                            dest = self._tricks[0 if k == "trick" else 1]
                            dest.setdefault(b.args[0].lower(), {
                                kk: [_num(x) for x in a]
                                for kk, a in b.items if isinstance(a, list)})
        return self._tricks

    def resolve_materials(self):
        """Fills each geom's trick and its composite (X_) textures."""
        tricks, textures = self.tricks()
        self.materials = {}
        for g in self.geoms.values():
            if "__" in g["model"]:
                t = tricks.get(g["model"].split("__", 1)[1].lower())
                if t:
                    g["trick"] = t
            for tex in g.get("textures", []):
                low = os.path.splitext(tex.lower())[0]
                if low in textures:
                    layers = {}
                    for k, v in textures[low].items():
                        m = re.match(r"(base|multiply|dualcolor|addglow|mask|"
                                     r"bumpmap)(\d?)(.*)", k)
                        if m:
                            layer = m.group(1) + m.group(2)
                            layers.setdefault(layer, {})[
                                m.group(3) or "texture"] = v
                    layers = {k: v for k, v in layers.items() if str(
                        (v.get("texture") or ["none"])[0]).lower() != "none"}
                    self.materials[low] = layers
        return self.materials

    def texture_names(self):
        names = set(t.lower() for g in self.geoms.values()
                    for t in g.get("textures", [])
                    if not t.lower().startswith("x_"))
        for layers in getattr(self, "materials", {}).values():
            for v in layers.values():
                names.add(str(v["texture"][0]).lower())
        for p in self.parts.values():
            if p:
                for k in ("TextureName", "TextureName2"):
                    names.add(p[k].lower())
        return sorted(names)

    def find_texture(self, name):
        """Archive path of a particle texture ("mist2.tga"), preferring the
        fx texture folders."""
        if self.store is None:
            return None
        base = os.path.splitext(os.path.basename(name.replace("\\", "/")))[0]
        hits = self.store.find_basename(base + ".texture")
        if not hits:
            return None
        hits.sort(key=lambda h: (not h.startswith("texture_library/fx/"), h))
        return hits[0]

    def export_textures(self, out_dir):
        from .texture import to_png
        os.makedirs(out_dir, exist_ok=True)
        done = {}
        for name in self.texture_names():
            src = self.find_texture(name)
            if not src:
                if name not in ("white", "white.tga", "0", "none"):
                    self.missing.add("texture:" + name)
                continue
            try:
                png, alpha = to_png(self.store.read(src))
            except ValueError:
                png = None
            if png is None:
                self.missing.add("texture:" + name)
                continue
            fn = os.path.splitext(os.path.basename(name))[0].lower() + ".png"
            with open(os.path.join(out_dir, fn), "wb") as f:
                f.write(png)
            done[name] = {"png": "textures/" + fn, "alpha": alpha,
                          "source": src}
        return done

    def sound_names(self):
        names = set()
        for fx in self.fx.values():
            for c in (fx or {}).get("conditions", []):
                for e in c["events"]:
                    names.update(x["name"].lower() for x in e.get("sounds", []))
        return sorted(names)

    def export_sounds(self, out_dir, wav=True):
        """Effect sounds (sound/ogg/**/<name>.ogg), as .wav for Unreal when
        ffmpeg is available, else the original .ogg."""
        import shutil
        import subprocess
        os.makedirs(out_dir, exist_ok=True)
        ffmpeg = shutil.which("ffmpeg") if wav else None
        done = {}
        for name in self.sound_names():
            hits = [h for h in self.store.find_basename(name + ".ogg")
                    if h.startswith("sound/")]
            if not hits:
                self.missing.add("sound:" + name)
                continue
            src = sorted(hits)[0]
            try:
                data = self.store.read(src)
            except ValueError:  # damaged archive entry
                self.missing.add("sound:" + name)
                continue
            ogg = os.path.join(out_dir, name + ".ogg")
            with open(ogg, "wb") as f:
                f.write(data)
            rel = "sounds/" + name + ".ogg"
            if ffmpeg:
                out = os.path.join(out_dir, name + ".wav")
                r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i",
                                    ogg, out])
                if r.returncode == 0:
                    os.remove(ogg)
                    rel = "sounds/" + name + ".wav"
            done[name] = {"file": rel, "source": src}
        return done

    def to_json(self, textures, sounds=None):
        return {"format": 1, "units": {"distance": "feet", "time": "1/30 s"},
                "fx": {k: v for k, v in sorted(self.fx.items()) if v},
                "parts": {k: v for k, v in sorted(self.parts.items()) if v},
                "behaviors": {k: v for k, v in sorted(self.bhvrs.items()) if v},
                "geoms": self.geoms,
                "materials": getattr(self, "materials", {}),
                "textures": textures,
                "sounds": sounds or {},
                "missing": sorted(self.missing)}


def power_fx(power):
    """The effect files and timing of one power_anims.json entry."""
    out = {}
    for k in POWER_TIMING_KEYS:
        if k in power:
            out[k] = power[k]
    for k, v in power.items():
        if k.endswith("FX") or k in POWER_FX_KEYS:
            if isinstance(v, str):
                out[k] = norm_path(v)
            elif isinstance(v, list):
                out[k] = [norm_path(x) for x in v if isinstance(x, str)]
    if "theme" not in power:
        # the game's defaults (powers_load.c power_FixupForBinFX)
        out.setdefault("FramesBeforeHit", 15)
        out.setdefault("InitialFramesBeforeHit", out["FramesBeforeHit"])
        if out.get("DelayedHit") and not out.get("ProjectileSpeed"):
            out["ProjectileSpeed"] = 60.0
    if power.get("themes"):
        out["themes"] = []
        for th in power["themes"]:
            t = power_fx({k: v for k, v in th.items() if k != "themes"})
            t["theme"] = th.get("theme")
            out["themes"].append(t)
    return out


def fx_paths(pfx):
    for k, v in pfx.items():
        if k == "themes":
            for t in v:
                yield from fx_paths(t)
        elif isinstance(v, str) and v.endswith(".fx"):
            yield v
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str) and x.endswith(".fx"):
                    yield x


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", required=True, help="i24/data folder")
    ap.add_argument("--piggs", help="folder of .pigg files (textures)")
    ap.add_argument("--out", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    se = sub.add_parser("export")
    se.add_argument("--powers-json", help="power_anims.json from powanim")
    se.add_argument("--set", action="append", default=[],
                    help="power set, e.g. Blaster_Ranged.Fire_Blast")
    se.add_argument("--power", action="append", default=[])
    se.add_argument("--all", action="store_true", help="every player power")
    se.add_argument("--fx", action="append", default=[],
                    help="effect file relative to data/fx")
    se.add_argument("--no-sounds", action="store_true")
    se.add_argument("--no-themes", action="store_true",
                    help="skip the customizable power themes")
    args = ap.parse_args(argv)

    store = None
    if args.piggs:
        from .pigg import AssetStore
        store = AssetStore(pigg_paths=glob.glob(os.path.join(args.piggs,
                                                             "*.pigg")))
    lib = FxLibrary(args.data, store)
    os.makedirs(args.out, exist_ok=True)
    powers = {}
    if args.powers_json:
        with open(args.powers_json, encoding="utf-8") as f:
            allp = json.load(f)
        sets = [s.lower() for s in args.set]
        names = {p.lower() for p in args.power}
        for name, p in allp.items():
            low = name.lower()
            if args.all or low in names or low.rsplit(".", 1)[0] in sets:
                pf = power_fx(p)
                if args.no_themes:
                    pf.pop("themes", None)
                powers[name] = pf
    for name, pf in powers.items():
        for path in fx_paths(pf):
            lib.load_fx(path)
    for path in args.fx:
        lib.load_fx(path)
    if store:
        lib.load_geoms()
        lib.resolve_materials()
        lib.export_geom_meshes(os.path.join(args.out, "geoms"))
    textures = lib.export_textures(os.path.join(args.out, "textures")) \
        if store else {}
    sounds = lib.export_sounds(os.path.join(args.out, "sounds")) \
        if store and not args.no_sounds else {}
    with open(os.path.join(args.out, "fx_library.json"), "w") as f:
        json.dump(lib.to_json(textures, sounds), f, indent=1)
    if powers:
        with open(os.path.join(args.out, "power_fx.json"), "w") as f:
            json.dump(powers, f, indent=1)
    print("%d powers, %d effects, %d particle systems, %d behaviors, "
          "%d textures, %d sounds, %d missing" % (
              len(powers), sum(1 for v in lib.fx.values() if v),
              sum(1 for v in lib.parts.values() if v),
              sum(1 for v in lib.bhvrs.values() if v), len(textures),
              len(sounds), len(lib.missing)))
    for m in sorted(lib.missing)[:40]:
        print("  missing", m)
    return 0


if __name__ == "__main__":
    sys.exit(main())

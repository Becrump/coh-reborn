"""Preview of the original power effects: a port of the game's particle
update (partUpdateSystem in Game/src/graphics/FX/particle.c) and of the
effect timeline (conditions, events, behaviors, projectile tracking), drawn
from the side. It checks fx_library.json before the Unreal side maps it onto
Niagara, and shows what each power should look like.

    python -m coh2unreal.fxsim --lib out/fx --power Blaster_Ranged.Fire_Blast.Fire_Blast \
        --out fire_blast.png [--ticks 0,10,20,30,40,50]
    python -m coh2unreal.fxsim --lib out/fx --set Blaster_Ranged.Fire_Blast --out sheet.png

The caster stands at z=0 facing +z, the target at --distance feet (30). Bones
are fixed points of a standing body (no animation). The power's effects
start as the game starts them: ActivationFX and AttackFX at tick 0, HitFX
when the hit lands (FramesBeforeHit, plus the projectile's travel at
ProjectileSpeed feet per second for DelayedHit powers).
"""
import argparse
import json
import math
import os
import random
import sys

import numpy as np

# standing body, feet, caster facing +z (x to its left)
BONES = {"origin": (0, 0, 0), "hips": (0, 3.1, 0), "waist": (0, 3.6, 0),
         "chest": (0, 4.7, 0.2), "neck": (0, 5.4, 0.1), "head": (0, 5.9, 0.2),
         "wepr": (-0.7, 4.4, 1.3), "wepl": (0.7, 4.4, 1.3),
         "handr": (-0.7, 4.4, 1.3), "handl": (0.7, 4.4, 1.3),
         "footr": (-0.4, 0.2, 0), "footl": (0.4, 0.2, 0),
         "fore_r": (-0.6, 4.2, 0.8), "fore_l": (0.6, 4.2, 0.8),
         "uarmr": (-0.8, 4.9, 0.2), "uarml": (0.8, 4.9, 0.2),
         "col_r": (-0.4, 5.1, 0), "col_l": (0.4, 5.1, 0),
         "thighr": (-0.4, 2.6, 0), "thighl": (0.4, 2.6, 0)}


def rnd():
    return random.uniform(-1.0, 1.0)


def jitter(v, j):
    return np.array([v[0] + j[0] * rnd(), v[1] + j[1] * rnd(),
                     v[2] + j[2] * rnd()])


class Entity:
    def __init__(self, pos, facing):
        self.pos = np.array(pos, float)
        self.facing = facing  # +1 faces +z, -1 faces -z

    def bone(self, name):
        name = (name or "origin").lower()
        b = BONES.get(name)
        if b is None:
            b = BONES["chest"]
        return self.pos + np.array([b[0] * self.facing, b[1],
                                    b[2] * self.facing])


class PartSystem:
    """One .part system, following partUpdateSystem with power 10."""

    def __init__(self, info, geo):
        self.i = info
        self.geo = geo
        self.age = 0.0
        self.dying = False
        self.new_buffer = 0.0
        self.npf = info["NewPerFrame"][0]
        self.burst = info["Burst"][0]
        self.alpha = info["Alpha"][0]
        self.startsize = info["StartSize"][0]
        self.endsize = info["EndSize"][0]
        self.burble = info["BurbleAmplitude"][0]
        self.kill_on_zero = info["KillOnZero"]
        self.local = info["WorldOrLocalPosition"] == 1
        self.max = min(int(self.burst + self.npf * info["FadeOutBy"] + 10)
                       + (200 if info["MoveScale"] or self.burble else 0), 1500)
        life = info["EmissionLifeSpan"] + rnd() * info["EmissionLifeSpanJitter"]
        self.emission_life = max(life, 0.0)
        self.path = color_path(info["ColorNav"], CUSTOM_COLORS)
        self.p = []  # [pos, vel, age, size, theta, spin, pulsedir]
        self.prev = None
        self.frame = 0.0

    def soft_kill(self):
        self.dying = True
        self.npf = 0
        self.burble = 0
        self.kill_on_zero = 1
        if "FadeImmediatelyOnDeath" in self.i["Flags"]:
            for p in self.p:
                p[2] = max(p[2], self.i["FadeOutStart"])

    def update(self, dt=1.0):
        i = self.i
        start = self.geo.pos.copy()
        if self.prev is None:
            self.prev = start.copy()
        change = start - self.prev
        if self.local:
            emit = np.zeros(3)
        else:
            emit = start
        nb = 0.0
        if not i["MoveScale"] or not self.age:
            nb = self.npf * dt
        elif not self.dying:
            ln = float(np.linalg.norm(change))
            if i["MoveScale"] > 0:
                nb = self.npf * i["MoveScale"] * ln
            else:
                nb = self.npf * dt
                nb += max(-nb, i["MoveScale"] * ln)
        if self.age == 0:
            nb += self.burst
        if self.burble:
            x = self.age / i["BurbleFrequency"]
            y = math.sin(x / 64.0 * 2 * math.pi) if i["BurbleType"] else \
                math.sin(x * 0.37) * math.cos(x * 0.11)
            if y >= i["BurbleThreshold"] * 2 - 1:
                nb += (y + 1) * self.burble * dt
        self.new_buffer += nb
        num = int(self.new_buffer)
        self.new_buffer -= num
        if len(self.p) + num > self.max:
            num = max(self.max - len(self.p), 0)
        if self.emission_life > 0 and self.age > self.emission_life:
            num = 0
        iv = self.geo.rot @ np.array(i["InitialVelocity"][:3])
        ivj = np.array(i["InitialVelocityJitter"][:3])
        esj = np.array(i["EmissionStartJitter"][:3])
        other = self.geo.other if self.geo.other is not None else start
        for n in range(num):
            size = self.startsize + (rnd() * i["StartSizeJitter"]
                                     if i["StartSizeJitter"] else 0)
            spin = i["Spin"] + (random.randint(0, i["SpinJitter"])
                                if i["SpinJitter"] else 0)
            theta = random.randint(0, i["OrientationJitter"]) \
                if i["OrientationJitter"] else 0
            vel = jitter(iv, ivj)
            et = i["EmissionType"]
            if et == 1:
                pos = emit + (other - start) * random.random()
            elif et == 2:
                a = random.uniform(0, 2 * math.pi)
                pos = emit + np.array([math.cos(a) * i["EmissionRadius"],
                                       random.random() * i["EmissionHeight"],
                                       math.sin(a) * i["EmissionRadius"]])
            elif et == 4:
                d = np.random.normal(size=3)
                d /= np.linalg.norm(d) or 1
                pos = emit + d * i["EmissionRadius"]
            elif et == 3:
                pos = emit - change * (1.0 - n / float(num))
            elif et == 5:
                pos = emit + (other - start) / num * n
            else:
                pos = emit.copy()
            pos = jitter(pos, esj)
            self.p.append([pos, vel, 0.0, size, theta, spin, 1])
        grav = i["Gravity"] * dt
        drag = i["Drag"] * dt
        mag = i["Magnetism"] * dt
        vj = np.array(i["VelocityJitter"])
        stick = change * i["Stickiness"]
        keep = []
        for p in self.p:
            if p[2] >= i["FadeOutBy"]:
                continue
            if vj.any():
                p[1] = jitter(p[1], vj)
            p[1][1] -= grav
            if drag:
                p[1] = p[1] - p[1] * drag
            p[0] = p[0] + p[1] * dt
            if mag and self.geo.magnet is not None:
                m = self.geo.magnet - (start if self.local else 0)
                p[1] = p[1] + np.where(p[0] < m, mag, -mag)
            if i["Stickiness"] and p[2]:
                p[0] = p[0] + stick
            er = i["ExpandRate"] * dt
            if er:
                if i["ExpandType"] == 0:
                    p[3] += er
                elif i["ExpandType"] == 1:
                    p[3] += er
                    p[3] = max(p[3], self.endsize) if er < 0 else \
                        min(p[3], self.endsize)
                else:
                    old = p[3]
                    p[3] += er if p[6] else -er
                    lo, hi = sorted((self.startsize, self.endsize))
                    if p[3] > hi or p[3] < lo:
                        p[3] = old
                        p[6] = 0 if p[6] else 1
            p[2] += dt
            keep.append(p)
        self.p = keep
        self.prev = start.copy()
        for k in (1, 2):
            if i["AnimFrames%d" % k] > 1 and k == 1:
                self.frame = (self.frame + i["AnimPace1"] * dt) % \
                    i["AnimFrames1"]
        self.age += dt
        alive = True
        if self.dying or (not self.npf and not i["MoveScale"]
                          and not self.burble):
            if not self.p:
                alive = False
        if not self.p and self.kill_on_zero and nb <= 0 and not (
                not self.dying and (self.burble or i["MoveScale"])):
            alive = False
        return alive

    def alpha_of(self, p):
        i = self.i
        a = p[2] - 1  # age before this tick's step, as drawn by the game
        if a >= i["FadeOutStart"]:
            span = (i["FadeOutBy"] - i["FadeOutStart"]) or 1
            f = 1.0 - (a - i["FadeOutStart"]) / span
        elif a < i["FadeInBy"]:
            f = a / i["FadeInBy"]
        else:
            f = 1.0
        return max(1, round(self.alpha * max(f, 0))) / 255.0

    def color_of(self, p):
        idx = int(round(p[2] - 1))
        if self.i["ColorChangeType"] == 1:
            idx %= len(self.path)
        idx = max(0, min(idx, len(self.path) - 1))
        return np.array(self.path[idx], float) / 255.0


# the player's power colors (primary, secondary) for tintable effects
CUSTOM_COLORS = None


def color_path(nav, custom=None):
    from .fx import color_path as cp
    return cp(nav, custom)


class Geo:
    """An event's node: on a bone, on another node, or moving by its
    behavior (projectiles track the magnet at TrackRate feet per tick)."""

    def __init__(self, fx, ev, bhvr):
        self.fx = fx
        self.ev = ev
        self.name = (ev.get("name") or "").lower()
        self.b = bhvr
        self.alive = True
        self.age = 0
        self.systems = []
        self.hit = False
        self.follow = None
        geoms = ev.get("geoms") or []
        self.geom = fx.lib.get("geoms", {}).get(geoms[0].lower()) \
            if geoms else None
        # an alternate pivot of the model of the node this one is on
        self.piv_rot, self.piv_pos = np.eye(3), np.zeros(3)
        at = ev.get("at", "origin")
        if at in fx.geos:
            self.follow = fx.geos[at]
            ap = ev.get("altpiv", 0) or 0
            pivots = (self.follow.geom or {}).get("alt_pivots", [])
            if 0 < ap <= len(pivots):
                m = pivots[ap - 1]
                self.piv_rot = np.array(m[:3], float).T
                self.piv_pos = np.array(m[3], float)
            self.place_on_follow()
        else:
            f = fx.entity.facing
            self.rot = np.diag([float(f), 1.0, float(f)])
            self.pos = fx.bone(at)
        off = np.array(bhvr.get("PositionOffset", [0, 0, 0]))
        sj = np.array(bhvr.get("StartJitter", [0, 0, 0]))
        self.pos = self.pos + self.rot @ jitter(off, sj)
        self.vel = self.rot @ jitter(
            np.array(bhvr.get("InitialVelocity", [0, 0, 0])),
            np.array(bhvr.get("InitialVelocityJitter", [0, 0, 0])))
        self.moving = ev.get("type") in ("start", "startpositonly") or \
            bool(ev.get("bhvr"))
        self.magnet = fx.point(ev.get("magnet")) if ev.get("magnet") else None
        self.other = fx.point(ev.get("pother")) if ev.get("pother") else None
        if ev.get("pmagnet"):
            self.magnet = fx.point(ev.get("pmagnet"))
        life = ev.get("lifespan", 0) or 0
        if life:
            life += rnd() * (ev.get("lifespanjitter", 0) or 0)
        self.life = life

    def place_on_follow(self):
        f = self.follow
        self.rot = f.rot @ self.piv_rot
        self.pos = f.pos + f.rot @ self.piv_pos

    def update(self, dt=1.0):
        self.age += dt
        if self.follow is not None:
            self.place_on_follow()
        elif self.moving:
            tr = self.b.get("TrackRate", 0)
            target = self.fx.point(self.ev.get("magnet")) \
                if self.ev.get("magnet") else None
            if target is not None and tr:
                if self.hit:
                    self.pos = target.copy()
                else:
                    d = target - self.pos
                    dist = float(np.linalg.norm(d))
                    step = tr * dt
                    if dist <= step or dist < 0.001:
                        self.pos = target.copy()
                        self.hit = True
                    else:
                        self.pos = self.pos + d / dist * step
            else:
                self.vel[1] -= self.b.get("Gravity", 0) * dt
                if self.b.get("Drag"):
                    self.vel = self.vel - self.vel * self.b["Drag"] * dt
                self.pos = self.pos + self.vel * dt
        if self.life and self.age >= self.life:
            self.kill()

    def kill(self):
        if self.alive:
            self.alive = False
            for s in self.systems:
                s.soft_kill()


class FxRun:
    """One playing effect on an entity, with an optional target."""

    def __init__(self, lib, path, entity, target=None, at=None, parent=None):
        self.lib = lib
        self.path = path
        self.d = lib["fx"].get(path)
        self.entity = entity
        self.target = target
        self.at = at
        self.parent = parent
        self.age = 0.0
        self.geos = {}
        self.all_geos = []
        self.fired = set()
        self.children = []
        self.systems = []
        self.alive = self.d is not None
        self.sounds = []

    def bone(self, name):
        name = (name or "origin").lower()
        if self.at is not None and name in ("origin", "root"):
            return self.at.pos.copy()
        if name.startswith("t_") and self.target is not None:
            return self.target.bone(name[2:])
        if name in ("target", "t_origin") and self.target is not None:
            return self.target.bone("chest")
        if self.at is not None:
            return self.at.pos.copy()
        return self.entity.bone(name)

    def point(self, name):
        name = (name or "").lower()
        if name in ("target", "t_target") and self.target is not None:
            return self.target.bone("chest")
        if name in self.geos:
            return self.geos[name].pos.copy()
        return self.bone(name)

    def fire(self, ev):
        typ = ev.get("type", "create")
        name = (ev.get("name") or "").lower()
        if typ == "destroy":
            for g in list(self.all_geos):
                if name == "all" or g.name == name:
                    g.kill()
            return
        if typ in ("setstate", "setlight"):
            return
        bh = dict(self.lib["behaviors"].get(ev.get("bhvr") or "", {}) or {})
        bh.update(ev.get("bhvroverride", {}))
        g = Geo(self, ev, bh)
        if name:
            self.geos[name] = g
        self.all_geos.append(g)
        for p in ev.get("parts", []):
            info = self.lib["parts"].get(p)
            if info:
                s = PartSystem(info, g)
                g.systems.append(s)
                self.systems.append(s)
        for s in ev.get("sounds", []):
            self.sounds.append((self.age, s["name"]))
        if ev.get("childfx") and ev["childfx"] in self.lib["fx"]:
            self.children.append(FxRun(self.lib, ev["childfx"], self.entity,
                                       self.target, at=g, parent=self))

    def update(self, dt=1.0):
        if self.d is None:
            return False
        if self.alive:
            for ci, c in enumerate(self.d["conditions"]):
                on = c["on"]
                due = False
                if on == "time" and ci not in self.fired and \
                        self.age >= c["time"]:
                    due = True
                elif on.startswith("prime") and on.endswith("hit") and \
                        ci not in self.fired:
                    g = self.geos.get(on[:-3])
                    due = g is not None and g.hit
                if not due:
                    continue
                self.fired.add(ci)
                if c.get("chance") and random.random() * 100 > c["chance"]:
                    continue
                times = 1 + int(c.get("repeat", 0) or 0)
                evs = c["events"]
                if c.get("random") and evs:
                    evs = [random.choice(evs)]
                for _ in range(times):
                    for ev in evs:
                        self.fire(ev)
            life = self.d["lifespan"]
            if life and self.age >= life:
                self.alive = False
                for g in self.all_geos:
                    g.kill()
        for g in self.all_geos:
            if g.alive:
                g.update(dt)
        self.systems = [s for s in self.systems if s.update(dt)]
        self.children = [c for c in self.children if c.update(dt)]
        self.age += dt
        return self.alive or bool(self.systems) or bool(self.children)

    def all_systems(self):
        out = list(self.systems)
        for c in self.children:
            out += c.all_systems()
        return out


class Canvas:
    """Side view: screen x is world z, screen y is world y."""

    def __init__(self, lib_dir, z0=-4.0, z1=40.0, y0=-0.5, y1=10.0, ppf=20):
        self.lib_dir = lib_dir
        self.z0, self.y1, self.ppf = z0, y1, ppf
        self.w = int((z1 - z0) * ppf)
        self.h = int((y1 - y0) * ppf)
        self.tex = {}

    def texture(self, lib, name):
        name = (name or "").lower()
        if name in self.tex:
            return self.tex[name]
        t = None
        info = lib["textures"].get(name)
        if info:
            from PIL import Image
            img = Image.open(os.path.join(self.lib_dir, info["png"]))
            img = img.convert("RGBA")
            img.thumbnail((64, 64))
            t = np.asarray(img, dtype=np.float32) / 255.0
        if t is None:
            t = np.ones((8, 8, 4), np.float32)
        self.tex[name] = t
        return t

    def to_px(self, p):
        return np.array([(p[2] - self.z0) * self.ppf,
                         (self.y1 - p[1]) * self.ppf])

    def blank(self):
        img = np.zeros((self.h, self.w, 3), np.float32)
        img[:] = (0.09, 0.10, 0.12)
        gy = int(self.y1 * self.ppf)
        img[gy:] = (0.16, 0.16, 0.17)
        return img

    def body(self, img, ent):
        """A grey silhouette for an entity."""
        c = self.to_px(ent.pos)
        x0 = int(c[0] - 0.7 * self.ppf)
        x1 = int(c[0] + 0.7 * self.ppf)
        y0 = int(c[1] - 6.0 * self.ppf)
        y1 = int(c[1])
        img[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)] = (0.3, 0.3, 0.33)

    def draw_system(self, img, lib, s):
        i = s.i
        tex = self.texture(lib, i["TextureName"])
        th, tw = tex.shape[:2]
        frames = i["AnimFrames1"]
        fw, sx, sy = 1, 1.0, 1.0
        if frames > 1:
            fw, sx, sy = {2: (2, .5, 1), 4: (2, .5, .5), 8: (4, .25, .5),
                          16: (4, .25, .25), 32: (8, .125, .25)}[
                next(n for n in (2, 4, 8, 16, 32) if frames <= n)]
        fr = int(s.frame)
        u0, v0 = (fr % fw) * sx, (fr // fw) * sy
        base = s.geo.pos if s.local else np.zeros(3)
        blend = i["Blend_mode"]
        for k, p in enumerate(s.p):
            pos = p[0] + base
            st = i["StreakType"]
            pos2 = pos
            if st == 1:
                v = p[1] * i["StreakScale"]
                pos2 = pos - v if i["StreakDirection"] == 0 else pos + v
            elif st == 2:
                pos2 = pos + np.array([0, i["Gravity"] * i["StreakScale"], 0])
            elif st == 3:
                pos2 = s.geo.pos
            elif st == 4 and s.geo.magnet is not None:
                pos2 = s.geo.magnet
            elif st == 5 and s.geo.other is not None:
                pos2 = s.geo.other
            elif st == 7:
                pos2 = s.p[k + 1][0] + base if k + 1 < len(s.p) else s.geo.pos
            a = self.to_px(pos)
            b = self.to_px(pos2)
            if st and i["StreakOrient"] == 1:
                if i["StreakDirection"] == 1:
                    a, b = b, a
                theta = math.atan2(-(a[1] - b[1]), a[0] - b[0]) - math.pi / 2
            else:
                theta = p[4] / 256.0 * 2 * math.pi
                if p[5]:
                    p[4] = (p[4] + abs(p[5]) * 0.1) % 256
            size = max(p[3], 0) * self.ppf

            def corner(ang):
                return np.array([math.cos(ang), -math.sin(ang)]) * size
            ul = a + corner(theta + 96 / 256.0 * 2 * math.pi)
            ur = a + corner(theta + 32 / 256.0 * 2 * math.pi)
            ll = b + corner(theta + 160 / 256.0 * 2 * math.pi)
            U = ur - ul
            V = ll - ul
            pts = np.array([ul, ur, ll, ur + V])
            x0, y0 = np.floor(pts.min(0)).astype(int)
            x1, y1 = np.ceil(pts.max(0)).astype(int)
            x0, y0 = max(x0, 0), max(y0, 0)
            x1, y1 = min(x1, self.w), min(y1, self.h)
            if x1 <= x0 or y1 <= y0:
                continue
            m = np.array([[U[0], V[0]], [U[1], V[1]]])
            det = np.linalg.det(m)
            if abs(det) < 1e-6:
                continue
            inv = np.linalg.inv(m)
            ys, xs = np.mgrid[y0:y1, x0:x1]
            dx = xs + 0.5 - ul[0]
            dy = ys + 0.5 - ul[1]
            u = inv[0, 0] * dx + inv[0, 1] * dy
            v = inv[1, 0] * dx + inv[1, 1] * dy
            inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
            if not inside.any():
                continue
            tu = ((u0 + np.clip(u, 0, .999) * sx) * tw).astype(int) % tw
            tv = ((v0 + np.clip(v, 0, .999) * sy) * th).astype(int) % th
            smp = tex[tv, tu]
            col = s.color_of(p)
            al = s.alpha_of(p) * smp[..., 3] * inside
            rgb = smp[..., :3] * col
            region = img[y0:y1, x0:x1]
            a3 = al[..., None]
            if blend == "Additive":
                region += rgb * a3
            elif blend in ("Subtractive", "SubtractiveInverse"):
                region -= rgb * a3
            elif blend == "Multiply":
                region *= (1 - a3) + rgb * a3
            elif blend == "PremultipliedAlpha":
                region *= (1 - a3)
                region += rgb * inside[..., None]
            else:
                region *= (1 - a3)
                region += rgb * a3


def hit_tick(pfx, distance):
    hit = pfx.get("FramesBeforeHit", 0) or 0
    if pfx.get("DelayedHit") and pfx.get("ProjectileSpeed"):
        hit += distance / float(pfx["ProjectileSpeed"]) * 30
    return int(round(hit))


def simulate(lib, lib_dir, pfx, ticks, distance=30.0, seed=1):
    """Frames (float RGB arrays) of one power at the given ticks."""
    random.seed(seed)
    np.random.seed(seed)
    caster = Entity((0, 0, 0), 1)
    target = Entity((0, 0, distance), -1)
    cv = Canvas(lib_dir, z1=distance + 5)
    runs = []
    for k in ("WindUpFX", "ActivationFX", "AttackFX", "InitialAttackFX"):
        if pfx.get(k):
            runs.append(FxRun(lib, pfx[k], caster, target))
    hit_at = hit_tick(pfx, distance)
    hits = [k for k in ("HitFX",) if pfx.get(k)]
    frames = {}
    last = max(ticks)
    for t in range(last + 1):
        if t == hit_at:
            for k in hits:
                runs.append(FxRun(lib, pfx[k], target, caster))
        runs = [r for r in runs if r.update(1.0)]
        if t in ticks:
            img = cv.blank()
            cv.body(img, caster)
            cv.body(img, target)
            for r in runs:
                for s in r.all_systems():
                    cv.draw_system(img, lib, s)
            frames[t] = np.clip(img, 0, 1)
    return frames, hit_at


def sheet(rows, path, label_w=180):
    """rows: [(label, {tick: frame})] -> one PNG, a row per power."""
    from PIL import Image, ImageDraw
    first = next(iter(rows[0][1].values()))
    h, w = first.shape[:2]
    scale = 0.6
    fw, fh = int(w * scale), int(h * scale)
    ncol = max(len(f) for _l, f in rows)
    out = Image.new("RGB", (label_w + ncol * (fw + 4), len(rows) * (fh + 18)),
                    (20, 20, 24))
    dr = ImageDraw.Draw(out)
    for r, (label, frames) in enumerate(rows):
        y = r * (fh + 18)
        dr.text((6, y + fh // 2), label, fill=(230, 230, 230))
        for c, (t, img) in enumerate(sorted(frames.items())):
            im = Image.fromarray((img * 255).astype(np.uint8)).resize((fw, fh))
            x = label_w + c * (fw + 4)
            out.paste(im, (x, y))
            dr.text((x + 4, y + fh + 2), "tick %d (%.2fs)" % (t, t / 30.0),
                    fill=(160, 160, 170))
    out.save(path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lib", required=True, help="folder with fx_library.json"
                    " and power_fx.json")
    ap.add_argument("--power", action="append", default=[])
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--theme", help="customizable power theme name")
    ap.add_argument("--colors", help="power colors for --theme, as "
                    "r,g,b,r,g,b (primary, secondary); default 255,110,0,"
                    "255,220,80")
    ap.add_argument("--ticks", default="5,15,20,25,30,40,55")
    ap.add_argument("--distance", type=float, default=30.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    with open(os.path.join(args.lib, "fx_library.json")) as f:
        lib = json.load(f)
    with open(os.path.join(args.lib, "power_fx.json")) as f:
        pfx_all = json.load(f)
    names = list(args.power)
    for s in args.set:
        names += sorted(n for n in pfx_all if n.rsplit(".", 1)[0] == s)
    ticks = sorted(int(t) for t in args.ticks.split(","))
    global CUSTOM_COLORS
    if args.theme:
        c = [float(x) for x in (args.colors or
                                "255,110,0,255,220,80").split(",")]
        CUSTOM_COLORS = (c[0:3], c[3:6])
    rows = []
    for n in names:
        pfx = pfx_all[n]
        if args.theme:
            th = [t for t in pfx.get("themes", []) if t.get("theme") ==
                  args.theme]
            if th:
                pfx = th[0]
        frames, hit = simulate(lib, args.lib, pfx, ticks, args.distance)
        rows.append(("%s\nhit at tick %d" % (n.rsplit(".", 1)[-1], hit),
                     frames))
        print(n, "hit at", hit)
    sheet(rows, args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

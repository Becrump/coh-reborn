"""Match every power to its original animation moves and FX.

    python -m coh2unreal.powanim --data i24/data --out out/powers

A power's animation lives in its .pfx file (included from the power def):
AttackBits, ActivationBits, HitBits ... are sequencer state bits. The
player sequencer (sequencers/player.txt and its includes) picks the move to
play the way seqSearchInterrupts (Common/seq/seqsequence.c) does: among the
moves that interrupt the current move (Interrupts names one of its Member
groups, or the move itself), whose Requires bits are all set, the highest
Priority wins; equal priorities rotate. The move then runs through its
NextMove chain back to a ready (a Cycle move). Each move gives the anim and
frame range per body type (male, fem, huge; a type without its own Anim
falls back to its ParentType, so fem and huge often play the male anim).

Writes:
  power_anims.json  power -> bits, timing (FramesBeforeHit, AttackFrames,
                    ...), FX file names, and per body type the move chain
                    as [move, anim, first, last] segments; the same for
                    each CustomFX theme (alternate animations and palettes)
  anim_list.json    every anim a player power or a core move uses, per body
                    type, for the animation library export
"""
import argparse
import glob
import json
import os
import re
import sys

BODIES = ("male", "fem", "huge")
# fields of a power's .pfx that name sequencer bits; the state a move is
# picked from is ModeBits plus these
BIT_FIELDS = ("ActivationBits", "InitialAttackBits", "AttackBits",
              "WindupBits", "HitBits", "BlockBits", "DeathBits")
TIMING = ("FramesBeforeHit", "AttackFrames", "InitialFramesBeforeHit",
          "InitialAttackFXFrameDelay", "FramesBeforeBlock",
          "InitialFramesBeforeBlock", "ProjectileSpeed", "DelayedHit")
FX_FIELDS = ("ActivationFX", "InitialAttackFX", "AttackFX", "WindUpFX",
             "HitFX", "BlockFX", "ContinuingFX", "ContinuingFX2",
             "ContinuingFX3", "ConditionalFX", "DeathFX")
# moves every hero needs whatever powers they have
CORE_MOVES = ("Ready", "CombatReady", "RunCycle", "WalkCycle", "BackRun",
              "JumpUp", "Fall", "Land", "FlyCycle", "Fly_Forward", "Hover",
              "HitQuick", "HitBack", "Default_Death", "KnockBack",
              "KnockDown", "GetUp", "Held", "Sleep", "Stunned", "Afraid")


class PathIndex:
    """Case-insensitive file lookup under the data folder (the game is
    Windows-made: includes say sequencers\\Members\\x.inc, the folder is
    members)."""

    def __init__(self, root):
        self.root = root
        self.map = {}
        for d, _dirs, files in os.walk(root):
            for f in files:
                full = os.path.join(d, f)
                rel = os.path.relpath(full, root).replace("\\", "/").lower()
                self.map[rel] = full

    def find(self, rel):
        return self.map.get(rel.replace("\\", "/").lower().lstrip("/"))


def _tokens(line):
    line = line.split("//", 1)[0].split("#", 1)[0]
    return [t.strip('"') for t in re.findall(r'"[^"]*"|\S+', line)]


# ---------------------------------------------------------------- sequencer
class Move:
    def __init__(self, name, order):
        self.name = name
        self.order = order
        self.requires = set()
        self.priority = 0
        self.member = set()
        self.interrupts = set()
        self.next_move = None
        self.cycle_move = None
        self.flags = set()
        self.sets = set()
        self.types = {}
        self.fx = []


class Sequencer:
    def __init__(self):
        self.typedefs = {}
        self.moves = {}
        self.order = []

    def type_chain(self, seqtype):
        out, t = [], (seqtype or "").lower()
        while t and t != "none" and t not in out:
            out.append(t)
            t = (self.typedefs.get(t, {}).get("parenttype") or "").lower()
        return out

    def anim_for(self, move, body):
        for t in self.type_chain(body):
            if t in move.types:
                return move.types[t]
        return None

    def interrupts(self, a, b):
        """seqAInterruptsB: a's Interrupts names a group b is a Member of,
        or b itself."""
        return bool(a.interrupts & (b.member | {b.name.lower()}))

    def pick(self, bits, current):
        best, found = 0, []
        for m in self.order:
            if not m.requires or not m.requires <= bits:
                continue
            if not self.interrupts(m, current):
                continue
            if m.priority > best:
                best, found = m.priority, [m]
            elif m.priority == best:
                found.append(m)
        return found

    def chain(self, move, limit=12):
        """move plus its NextMove chain, stopping at a cycling ready."""
        out, seen = [], set()
        m = move
        while m is not None and m.name.lower() not in seen and len(out) < limit:
            seen.add(m.name.lower())
            out.append(m)
            if "cycle" in m.flags and m is not move:
                out.pop()
                break
            m = self.moves.get((m.next_move or "").lower())
        return out


def load_sequencer(paths, name):
    seq = Sequencer()

    def read(rel, depth=0):
        path = paths.find(rel if rel.lower().startswith("sequencers/") or
                          rel.lower().startswith("sequencers\\")
                          else "sequencers/" + rel)
        if path is None or depth > 8:
            return []
        out = []
        with open(path, encoding="latin-1") as f:
            for line in f:
                t = _tokens(line)
                if t and t[0].lower() == "include" and len(t) > 1:
                    out.extend(read(t[1], depth + 1))
                elif t:
                    out.append(t)
        return out

    td = mv = ty = None
    for t in read(name):
        k = t[0].lower()
        if k == "typedef" and len(t) > 1:
            td = seq.typedefs.setdefault(t[1].lower(), {})
        elif k == "typedefend":
            td = None
        elif td is not None and len(t) > 1:
            td[k] = t[1]
        elif k == "move" and len(t) > 1:
            mv = Move(t[1], len(seq.order))
            if t[1].lower() not in seq.moves:
                seq.moves[t[1].lower()] = mv
                seq.order.append(mv)
            ty = None
        elif k == "mend":
            mv = ty = None
        elif mv is None:
            continue
        elif k == "type" and len(t) > 1:
            ty = t[1].lower()
        elif k == "tend":
            ty = None
        elif k == "anim" and ty and len(t) > 1:
            first = int(float(t[2])) if len(t) > 2 else 0
            last = int(float(t[3])) if len(t) > 3 else 0
            mv.types.setdefault(ty, (t[1].replace("\\", "/").lower(),
                                     first, last))
        elif k == "requires":
            mv.requires.update(x.upper() for x in t[1:])
        elif k == "priority" and len(t) > 1:
            mv.priority = int(float(t[1]))
        elif k == "member":
            mv.member.update(x.lower() for x in t[1:])
        elif k == "interrupts":
            mv.interrupts.update(x.lower() for x in t[1:])
        elif k == "nextmove" and len(t) > 1:
            mv.next_move = t[1]
        elif k == "cyclemove" and len(t) > 1:
            mv.cycle_move = t[1]
        elif k == "flags":
            mv.flags.update(x.lower() for x in t[1:])
        elif k == "sets":
            mv.sets.update(x.upper() for x in t[1:])
        elif k == "playfx" and len(t) > 1:
            mv.fx.append(t[1:])
    return seq


# ---------------------------------------------------------------- powers
def _bits(v):
    out = set()
    for x in v:
        for y in x.split(","):
            y = y.strip().upper()
            if y.startswith("ANIM_"):
                y = y[5:]
            if y:
                out.add(y)
    return out


def _num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except ValueError:
        return v


class AnimFX:
    """The animation and FX fields of a power or one of its CustomFX."""

    def __init__(self):
        self.f = {}

    def add(self, key, vals):
        lk = key.lower()
        for name in BIT_FIELDS + ("ModeBits",):
            if lk == name.lower():
                self.f[name] = sorted(_bits(vals))
                return
        for name in TIMING:
            if lk == name.lower() and vals:
                self.f[name] = _num(vals[0])
                return
        for name in FX_FIELDS:
            if lk == name.lower() and vals:
                self.f[name] = vals[0].replace("\\", "/")
                return
        if lk in ("palette", "displayname", "alttheme", "primarytint",
                  "secondarytint") and vals:
            self.f[key[0].upper() + key[1:]] = " ".join(vals)


def load_powers(paths, data_dir):
    """{power full name: (AnimFX, [(theme, AnimFX)])} from defs/powers."""
    out = {}

    def lines_of(path, depth=0):
        res = []
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                t = _tokens(line.replace(",", " , "))
                t = [x for x in t if x != ","]
                if t and t[0].lower() == "include" and len(t) > 1:
                    p = paths.find(t[1]) or paths.find("defs/" + t[1])
                    if p and depth < 4:
                        res.extend(lines_of(p, depth + 1))
                elif t:
                    res.append(t)
        return res

    for path in sorted(glob.glob(os.path.join(data_dir, "defs", "powers",
                                              "*.powers"))):
        lines = lines_of(path)
        depth = 0
        cur = None
        custom = None
        for t in lines:
            k = t[0]
            if k == "{":
                depth += 1
                continue
            if k == "}":
                depth -= 1
                if depth == 0 and cur is not None:
                    out[cur[0]] = (cur[1], cur[2])
                    cur = None
                continue
            if depth == 0 and k.lower() == "power" and len(t) > 1:
                cur = (t[1], AnimFX(), [])
                custom = None
                continue
            if cur is None or depth != 1:
                continue
            if k.lower() == "customfx":
                custom = AnimFX()
                cur[2].append((" ".join(t[1:]), custom))
                continue
            if k.lower() == "end" and custom is not None:
                custom = None
                continue
            (custom or cur[1]).add(k, t[1:])
    return out


def resolve(seq, fields, body, readies):
    """{bit field: [[move, anim, first, last], ...]} for one body type.
    The move is picked from combat ready, else from the plain ready (some
    activations and reactions only interrupt that one)."""
    mode = set(fields.get("ModeBits", []))
    res = {}
    for bf in BIT_FIELDS:
        bits = fields.get(bf)
        if not bits:
            continue
        state = set(bits) | mode
        found = []
        for ready in readies:
            found = seq.pick(state, ready)
            if found:
                break
        if not found:
            res[bf] = None
            continue
        segs = []
        for m in seq.chain(found[0]):
            a = seq.anim_for(m, body)
            if a is None:
                continue
            segs.append([m.name, a[0], a[1], a[2]])
        entry = {"segments": segs}
        if len(found) > 1:
            entry["alternates"] = [m.name for m in found[1:]]
        res[bf] = entry
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", required=True, help="i24/data folder")
    ap.add_argument("--out", required=True)
    ap.add_argument("--powers-json",
                    help="limit the output to player powers: hero_all_sets.json "
                         "(tools/rules/coh_rules.py testhero) or powers.json "
                         "(tools/powers/export_powers.py)")
    ap.add_argument("--power", action="append", default=[],
                    help="only these powers (full names); prints them")
    args = ap.parse_args(argv)

    paths = PathIndex(args.data)
    seq = load_sequencer(paths, "player.txt")
    print("player sequencer: %d moves, %d types" % (len(seq.order),
                                                     len(seq.typedefs)))
    ready = [seq.moves["combatready"], seq.moves["ready"]]
    powers = load_powers(paths, args.data)
    print("powers with animation bits: %d of %d" % (
        sum(1 for p in powers.values() if any(k in p[0].f for k in BIT_FIELDS)),
        len(powers)))

    wanted = None
    if args.powers_json:
        with open(args.powers_json, encoding="utf-8") as f:
            pj = json.load(f)
        if isinstance(pj, dict):
            wanted = {p.lower() for s in pj["sets"] for p in s["powers"]}
        else:
            wanted = {p["id"].lower() for p in pj}
    if args.power:
        wanted = {p.lower() for p in args.power}

    os.makedirs(args.out, exist_ok=True)
    result = {}
    anims = {b: {} for b in BODIES}
    unresolved = 0
    for name, (base, customs) in sorted(powers.items()):
        if wanted is not None and name.lower() not in wanted:
            continue
        if not base.f:
            continue
        entry = dict(base.f)
        entry["moves"] = {b: resolve(seq, base.f, b, ready) for b in BODIES}
        themes = []
        for theme, c in customs:
            t = dict(c.f)
            t["theme"] = theme
            t["moves"] = {b: resolve(seq, c.f, b, ready) for b in BODIES}
            themes.append(t)
        if themes:
            entry["themes"] = themes
        for e in [entry] + themes:
            for b in BODIES:
                for bf, r in e["moves"][b].items():
                    if r is None:
                        unresolved += 1
                        continue
                    for _m, an, _f, _l in r["segments"]:
                        anims[b].setdefault(an, set()).add(name)
        result[name] = entry
        if args.power:
            print(json.dumps({name: entry}, indent=1))

    for b in BODIES:
        for mname in CORE_MOVES:
            m = seq.moves.get(mname.lower())
            if m is None:
                continue
            for c in seq.chain(m):
                a = seq.anim_for(c, b)
                if a:
                    anims[b].setdefault(a[0], set()).add("core:" + mname)

    with open(os.path.join(args.out, "power_anims.json"), "w") as f:
        json.dump(result, f, indent=1)
    with open(os.path.join(args.out, "anim_list.json"), "w") as f:
        json.dump({b: {a: sorted(u)[:5] + (["..."] if len(u) > 5 else [])
                       for a, u in sorted(anims[b].items())}
                   for b in BODIES}, f, indent=1)
    print("powers %d, unresolved bit sets %d, anims male %d fem %d huge %d"
          % (len(result), unresolved, len(anims["male"]), len(anims["fem"]),
             len(anims["huge"])))


if __name__ == "__main__":
    sys.exit(main())

"""Extract City of Heroes idle and pose graphs for Unreal.

The original client never played one looping idle. A standing NPC sat in a
sequencer move flagged `Cycle`; each time the move's animation reached its
last frame, seqStep (Common/seq/seqsequence.c) picked one of the move's
`CycleMove` entries at random (a name listed twice is twice as likely) or,
with none, looped the move. `Ready` -> `Ready2` -> `Ready_Look` /
`Ready_2Hips` -> ... is the default idle; encounter poses (arms crossed,
lean on a wall, talk, deal) are the same kind of chain.

Spawn defs choose a pose with `AI_InActive <<PL_ArmsCrossed>>`. `PL_` names
an AnimList (sequencers/animlists/*.al) that sets state bits such as
`ENCOUNTER COMMAND OBSERVE LOW`; the sequencer then plays the move whose
`Requires` bits are met with the highest priority (seqsequence.c).

This module resolves that chain into a small graph per pose:

    python -m coh2unreal.idles --data <i24/data> --group Hellions --out idles.json

`--group` ranks the poses that group's spawn defs use (scripts.loc/spawndefs);
`--animlist` adds poses by name. Each graph lists its states (one per move,
with anim, frame range, play rate and blend frames) and weighted next states.
character.py exports the states as clips (`--idles idles.json`) and
UCoHIdleComponent plays the graph in Unreal.
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

from .defs import _tokens

# State bits that mean a pose only reads right with something else present.
# Unreal leaves these out of the random pool unless a pose is set by hand.
NEEDS = {"prop": {"WEAPON", "CUSTOMWEAPON", "SPRAYCAN", "PROP", "BOX",
                  "CARRY", "BRIEFCASE", "CLIPBOARD", "SMARTPHONE"},
         "partner": {"DEALING", "RECEIVING", "PURSETUG", "RELICTUG",
                     "RUMBLEA", "RUMBLEB", "PUSH", "CHAT"},
         "seat": {"SIT"},
         "wall": {"LEANWALL", "WALL"}}
DEFAULT_INTERPOLATE = 5     # seqload.c DEFAULT_MOVE_INTERPOLATION_RATE
FPS = 30.0


class Move:
    def __init__(self, name):
        self.name = name
        self.requires = set()
        self.priority = 0
        self.flags = set()
        self.cycle = []          # CycleMove names, duplicates kept (weights)
        self.next = []
        self.scale = 1.0
        self.interpolate = DEFAULT_INTERPOLATE
        self.types = {}          # type lower -> {"anim", "first", "last", "scale"}


class Sequencer:
    def __init__(self):
        self.typedefs = {}
        self.moves = {}
        self.order = []

    def type_chain(self, seqtype):
        chain = []
        t = (seqtype or "").lower()
        while t and t != "none" and t not in chain:
            chain.append(t)
            t = self.typedefs.get(t, {}).get("parenttype", "none").lower()
        return chain

    def gfx(self, move, seqtype):
        """The Type block a seqtype plays for a move (seqGetTypeGfx)."""
        for t in self.type_chain(seqtype):
            if t in move.types:
                return move.types[t]
        return None


def load_sequencer(data_dir, name):
    """Like defs.load_sequencer, but keeps what idle graphs need: Requires,
    Priority, CycleMove, NextMove, Scale and Interpolate."""
    seq = Sequencer()
    seen = set()

    def read(rel):
        rel = rel.replace("\\", "/")
        if not rel.lower().startswith("sequencers/"):
            rel = "sequencers/" + rel
        path = _ci_path(data_dir, rel)
        if not path or path.lower() in seen:
            return []
        seen.add(path.lower())
        with open(path, encoding="latin-1") as f:
            lines = f.read().splitlines()
        out = []
        for line in lines:
            t = _tokens(line)
            if t and t[0].lower() == "include" and len(t) > 1:
                out.extend(read(t[1]))
            else:
                out.append(t)
        return out

    td = mv = ty = None
    for t in read(name):
        if not t:
            continue
        k = t[0].lower()
        if k == "typedef" and len(t) > 1:
            td = seq.typedefs.setdefault(t[1].lower(), {})
        elif k == "typedefend":
            td = None
        elif td is not None and len(t) > 1:
            td[k] = t[1]
        elif k == "move" and len(t) > 1:
            if t[1].lower() in seq.moves:
                mv = Move(t[1])     # duplicate: first definition wins
            else:
                mv = seq.moves[t[1].lower()] = Move(t[1])
                seq.order.append(t[1].lower())
            ty = None
        elif k == "mend":
            mv = ty = None
        elif mv is None:
            continue
        elif k == "type" and len(t) > 1:
            ty = mv.types.setdefault(t[1].lower(), {"scale": 1.0})
        elif k == "tend":
            ty = None
        elif ty is not None and k == "anim" and len(t) > 1 \
                and "anim" not in ty:
            ty["anim"] = t[1].replace("\\", "/")
            ty["first"] = int(float(t[2])) if len(t) > 2 else 0
            ty["last"] = int(float(t[3])) if len(t) > 3 else 0
        elif ty is not None and k == "scale" and len(t) > 1:
            ty["scale"] = float(t[1])
        elif k == "requires":
            mv.requires.update(x.upper() for x in t[1:])
        elif k == "priority" and len(t) > 1:
            mv.priority = int(float(t[1]))
        elif k == "flags":
            mv.flags.update(x.lower() for x in t[1:])
        elif k == "cyclemove" and len(t) > 1:
            mv.cycle.append(t[1].lower())
        elif k == "nextmove" and len(t) > 1:
            mv.next.append(t[1].lower())
        elif k == "scale" and len(t) > 1:
            mv.scale = float(t[1])
        elif k == "interpolate" and len(t) > 1:
            mv.interpolate = int(float(t[1]))
    for m in seq.moves.values():
        for k in [k for k, v in m.types.items() if "anim" not in v]:
            del m.types[k]
    return seq


def _ci_path(root, rel):
    """Case-insensitive path lookup (the data was authored on Windows)."""
    cur = root
    for part in rel.split("/"):
        if not part:
            continue
        p = os.path.join(cur, part)
        if not os.path.exists(p):
            try:
                hit = [n for n in os.listdir(cur) if n.lower() == part.lower()]
            except OSError:
                return None
            if not hit:
                return None
            p = os.path.join(cur, hit[0])
        cur = p
    return cur


def load_animlists(data_dir):
    """{name lower: (name, [state bits])} from sequencers/animlists/*.al."""
    out = {}
    for path in glob.glob(os.path.join(data_dir, "sequencers", "animlists",
                                       "*.al")):
        with open(path, encoding="latin-1") as f:
            for line in f:
                line = line.split("//", 1)[0]
                m = re.match(r"\s*AnimList:\s*([^\s,]+)\s*,?\s*(.*)", line)
                if m:
                    out.setdefault(m.group(1).lower(),
                                   (m.group(1), m.group(2).upper().split()))
    return out


def spawn_poses(data_dir, group, zones=None):
    """Counter of the AnimList names a villain group's spawn defs use for
    AI_InActive (what they do before a hero shows up)."""
    root = os.path.join(data_dir, "scripts.loc", "spawndefs")
    files = []
    for z in (zones or [d for d in os.listdir(root)
                        if os.path.isdir(os.path.join(root, d))]):
        files += glob.glob(os.path.join(root, z, "*.spawndef"))
    g = group.lower().replace(" ", "")
    counts = collections.Counter()
    for path in files:
        if g not in os.path.basename(path).lower().replace("_", ""):
            continue
        with open(path, encoding="latin-1") as f:
            for line in f:
                line = line.split("//", 1)[0]
                m = re.search(r"AI_InActive\s+\W*(?:PL_)?([A-Za-z0-9_]+)",
                              line)
                if m:
                    counts[m.group(1).lower()] += 1
    return counts


def _best_moves(seq, bits, seqtype):
    """Moves the sequencer would start for these state bits: requirements
    met, highest priority, then most requirements (seqsequence.c)."""
    best, score = [], None
    for k in seq.order:
        m = seq.moves[k]
        if not m.requires or not m.requires <= bits:
            continue
        if "notselectable" in m.flags or not seq.gfx(m, seqtype):
            continue
        s = (m.priority, len(m.requires))
        if score is None or s > score:
            best, score = [m], s
        elif s == score:
            best.append(m)
    return best


def build_graph(seq, seqtype, entry_moves, bits):
    """Walks CycleMove / NextMove links from the entry moves. Links to moves
    this seqtype has no animation for, or whose requirements the pose does
    not meet, go back to the entries (the sequencer would re-pick)."""
    entries = [m.name.lower() for m in entry_moves]
    states = collections.OrderedDict()
    todo = list(entries)
    while todo:
        k = todo.pop(0)
        if k in states:
            continue
        m = seq.moves[k]
        gfx = seq.gfx(m, seqtype)
        cyc = "cycle" in m.flags
        links = (m.cycle or [k]) if cyc else (m.next or entries)
        nxt = collections.Counter()
        for n in links:
            t = seq.moves.get(n)
            ok = t is not None and seq.gfx(t, seqtype) and \
                t.requires <= bits and (t.requires or not bits) and \
                "notselectable" not in t.flags
            for e in ([n] if ok else entries):
                nxt[e] += 1
                if e not in states and e not in todo:
                    todo.append(e)
        scale = gfx["scale"] if gfx["scale"] != 1 else m.scale
        states[k] = {"move": m.name, "anim": gfx["anim"],
                     "frames": [gfx["first"], gfx["last"]],
                     "playRate": scale,
                     "blendFrames": m.interpolate,
                     "next": [[seq.moves[n].name, w]
                              for n, w in sorted(nxt.items())]}
    return {"entries": [seq.moves[e].name for e in entries],
            "states": list(states.values())}


def pose_needs(bits):
    b = set(bits)
    return sorted(k for k, v in NEEDS.items() if b & v)


def pose_graph(seq, animlists, pose, seqtype):
    """Graph for an AnimList name, or `Ready` for the default idle."""
    if pose.lower() in ("ready", "idle", "none"):
        return dict(build_graph(seq, seqtype, [seq.moves["ready"]], set()),
                    pose="Ready", bits=[], needs=[])
    name, bits = animlists[pose.lower()]
    entry = _best_moves(seq, set(bits), seqtype)
    if not entry:
        return None
    return dict(build_graph(seq, seqtype, entry, set(bits)),
                pose=name, bits=bits, needs=pose_needs(bits))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", required=True, help="i24/data folder")
    ap.add_argument("--sequencer", default="player.txt")
    ap.add_argument("--seqtype", action="append",
                    help="sequencer types (default male, fem, huge)")
    ap.add_argument("--group", help="rank this villain group's spawn poses")
    ap.add_argument("--zone", action="append",
                    help="spawndef folders to scan (default all)")
    ap.add_argument("--top", type=int, default=12,
                    help="how many of the group's poses to keep")
    ap.add_argument("--animlist", action="append", default=[],
                    help="extra AnimList names to include")
    ap.add_argument("--out", help="JSON file (default: print a summary)")
    args = ap.parse_args(argv)

    seq = load_sequencer(args.data, args.sequencer)
    als = load_animlists(args.data)
    poses = collections.OrderedDict([("ready", 0)])
    if args.group:
        for name, n in spawn_poses(args.data, args.group,
                                   args.zone).most_common():
            if name in als and len([p for p in poses if p != "ready"]) \
                    < args.top:
                poses.setdefault(name, n)
    for name in args.animlist:
        if name.lower() in als or name.lower() == "ready":
            poses.setdefault(name.lower(), 0)
        else:
            print("unknown AnimList %s" % name, file=sys.stderr)

    out = {"sequencer": args.sequencer, "group": args.group, "types": {}}
    for st in args.seqtype or ["male", "fem", "huge"]:
        graphs = []
        for p, n in poses.items():
            g = pose_graph(seq, als, p, st)
            if g is None:
                print("%s: no move for %s" % (st, p), file=sys.stderr)
                continue
            g["spawnCount"] = n
            graphs.append(g)
        out["types"][st] = graphs

    if args.out:
        with open(args.out, "w") as f:
            json.dump(out, f, indent=1)
    for st, graphs in out["types"].items():
        print("== %s" % st)
        for g in graphs:
            print("  %-22s x%-4d %-14s %s" % (
                g["pose"], g["spawnCount"], ",".join(g["needs"]), "  ".join(
                "%s(%s %d-%d)" % (s["move"], s["anim"], *s["frames"])
                for s in g["states"])))
    return out


def clip_moves(idles_json):
    """(clip name, [move]) pairs for character.export_npc: one clip per idle
    state of every type, named after its move (export_npc skips moves a
    character's type has no animation for)."""
    with open(idles_json) as f:
        data = json.load(f)
    seen, out = set(), []
    for graphs in data["types"].values():
        for g in graphs:
            for s in g["states"]:
                if s["move"].lower() not in seen:
                    seen.add(s["move"].lower())
                    out.append((s["move"], [s["move"]]))
    return out


if __name__ == "__main__":
    main()

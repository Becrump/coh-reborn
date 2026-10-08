"""Edits to a zone before export: drop pieces, cut pieces down to ruins, and
limit the export to the tiles an edit touches.

Rules are written as text on the command line:

    --drop  "PATTERNS@x0,z0,x1,z1"
    --ruin  "PATTERNS@x0,z0,x1,z1@h0:h1"

PATTERNS is one or more shell-style patterns separated by "|". A pattern
matches a placed model's name or any group name on its path (so
"warwall_shield_door" drops the whole door shield group). Matching is not
case sensitive. The box is in game feet, tested against the model's
origin.

A ruin rule keeps the model but clamps its vertices to a height that runs
from h0 (feet) at x0 to h1 at x1, so a 1000 ft wall becomes a broken
stump that is low at one end and taller at the other.
"""
import fnmatch
import math


class Rule:
    def __init__(self, text, kind):
        parts = text.split("@")
        if len(parts) < 2 or (kind == "ruin" and len(parts) < 3):
            raise ValueError("bad --%s rule: %r" % (kind, text))
        self.text = text
        self.patterns = [p.strip().lower() for p in parts[0].split("|")
                         if p.strip()]
        self.box = tuple(float(v) for v in parts[1].split(","))
        if len(self.box) != 4:
            raise ValueError("bad box in %r" % text)
        self.heights = None
        if kind == "ruin":
            h0, h1 = (float(v) for v in parts[2].split(":"))
            self.heights = (h0, h1)
        self.hits = 0

    def matches(self, inst):
        x, z = inst.matrix[3][0], inst.matrix[3][2]
        x0, z0, x1, z1 = self.box
        if not (min(x0, x1) <= x <= max(x0, x1)
                and min(z0, z1) <= z <= max(z0, z1)):
            return False
        names = [inst.model.lower()] + inst.path.lower().split("/")
        return any(fnmatch.fnmatchcase(n, p)
                   for p in self.patterns for n in names)

    def height_at(self, x):
        """Ruin top (feet) at world x."""
        x0, _z0, x1, _z1 = self.box
        h0, h1 = self.heights
        if x1 == x0:
            return h0
        t = min(1.0, max(0.0, (x - x0) / (x1 - x0)))
        return h0 + (h1 - h0) * t


def tile_of(inst, tile_ft):
    m = inst.matrix
    return (math.floor(m[3][0] / tile_ft), math.floor(-m[3][2] / tile_ft))


def apply(instances, drops, ruins, tile_ft, log=print):
    """Returns (kept instances, {id(inst): ruin rule}, touched tiles)."""
    keep, ruined, touched = [], {}, set()
    for inst in instances:
        rule = next((r for r in drops if r.matches(inst)), None)
        if rule is not None:
            rule.hits += 1
            touched.add(tile_of(inst, tile_ft))
            continue
        rule = next((r for r in ruins if r.matches(inst)), None)
        if rule is not None:
            rule.hits += 1
            ruined[id(inst)] = rule
            touched.add(tile_of(inst, tile_ft))
        keep.append(inst)
    for r in drops:
        log("drop %-60s %d pieces" % (r.text, r.hits))
    for r in ruins:
        log("ruin %-60s %d pieces" % (r.text, r.hits))
    return keep, ruined, touched


def parse_tiles(text):
    """'1,-3;2,-3' -> {(1, -3), (2, -3)}"""
    out = set()
    for part in text.split(";"):
        if part.strip():
            x, z = (int(v) for v in part.split(","))
            out.add((x, z))
    return out

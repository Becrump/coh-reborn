"""Step 6b: sit the buildings on the ground.

The lot heights come from the median ground at the lot centre, so on a slope
a building's low side hangs in the air. This traces the landscape on a 5 m
grid under every PCG building and lowers any building whose base is above
the lowest ground under it, so it touches everywhere (the high side sinks
in instead). Buildings are only ever lowered, never raised, so ones already
fixed by hand stay as they are. The lot's TargetPoint drops by the same amount, so
regenerating PCG_Reborn_Buildings keeps the fix.

A building that would have to drop more than MAX_DROP (it overhangs a bank
or the water) is left alone and listed for a look.
REBORN_CHECK=1 only reports."""
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
CHECK = os.environ.get("REBORN_CHECK") == "1"
MAX_DROP = 300.0     # cm
SINK = 10.0          # cm below the lowest ground
STEP = 500.0
w = world()


def is_landscape(a):
    return a is not None and "Landscape" in a.get_class().get_name()


def ground_min(b):
    o, e = b.get_actor_bounds(False)
    ex, ey = max(e.x - 100, 50), max(e.y - 100, 50)
    nx, ny = max(2, int(2 * ex / STEP) + 1), max(2, int(2 * ey / STEP) + 1)
    zs = []
    for i in range(nx + 1):
        for j in range(ny + 1):
            x, y = o.x - ex + 2 * ex * i / nx, o.y - ey + 2 * ey * j / ny
            hits = unreal.SystemLibrary.line_trace_multi(
                w, unreal.Vector(x, y, 60000), unreal.Vector(x, y, -20000), unreal.TraceTypeQuery.ECC_VISIBILITY,
                True, [b], unreal.DrawDebugTrace.NONE, True)
            for h in hits:
                t = h.to_tuple()
                if is_landscape(t[9]):
                    zs.append(t[4].z)
                    break
    return min(zs) if zs else None


buildings = [a for a in actors.get_all_level_actors()
             if "PCG Generated Actor" in [str(t) for t in a.tags] and "CitySampleBuildings" in a.get_class().get_path_name()]
targets = [a for a in find(cls=unreal.TargetPoint) if any("RebornBucket" in str(t) for t in a.tags)]
lowered, review = [], []
for b in buildings:
    g = ground_min(b)
    if g is None:
        continue
    z = b.get_actor_location().z
    drop = z - g
    if drop <= 15:
        continue
    if drop > MAX_DROP:
        review.append((b.get_actor_label(), round(drop / 100, 1)))
        continue
    lowered.append((b.get_actor_label(), round(drop / 100, 2)))
    if CHECK:
        continue
    d = drop + SINK
    b.set_actor_location(b.get_actor_location() - unreal.Vector(0, 0, d), False, False)
    p = b.get_actor_location()
    t = min(targets, key=lambda t: (t.get_actor_location().x - p.x) ** 2 + (t.get_actor_location().y - p.y) ** 2)
    if (t.get_actor_location().x - p.x) ** 2 + (t.get_actor_location().y - p.y) ** 2 < 2500.0 ** 2 and \
            t.get_actor_location().z > p.z + 1:
        t.set_actor_location(unreal.Vector(t.get_actor_location().x, t.get_actor_location().y, p.z), False, False)

print("buildings", len(buildings), "floating", len(lowered), "(lowered)" if not CHECK else "(check only)")
for n, dz in lowered:
    print("  %-40s %.2f m" % (n, dz))
for n, dz in review:
    print("  REVIEW %-33s would drop %.1f m" % (n, dz))
if not CHECK and lowered:
    unreal.EditorLoadingAndSavingUtils.save_map(world(), MAP)

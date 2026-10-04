"""Takes props out of the baked tiles so Unreal can place modern versions.

Street lamps are the first case. CoH builds a lamp from a pole, a bulb and
three fake effects (a ground-glow square, a lens flare, a shadow decal);
those fakes look wrong under real lighting. Each lamp found here is
removed from the tiles and written to <name>_props.json with its base
position, the lamp head position and facing, for the Unreal setup script
to spawn a new lamp model and a real light.

Lamps mounted on traffic-light poles keep their pole (the signal hangs
from it); only their fake effects are removed and a light is added.
"""
import math

FEET_TO_METERS = 0.3048

# def name in the map path -> kind of replacement
ROOTS = {"lamp_plain": "street", "lamp_parkinglot_01": "parking"}
# parts that only fake lighting
FAKE_FX = {"_lamp_groundglow", "_lamp_lensflare", "_lamp_plain_shadow",
           "_parkinglot_light_beam"}
# the part whose transform is the lamp's base
POLE = {"street": "_lamp_plain_hi", "parking": "_parkinglot_light_base_hi"}
# the part that marks the lamp head
HEAD = {"street": "_lamp_lensflare", "parking": "_parkinglot_light_light"}
KEEP_POLE_UNDER = ("traffic_light",)


def _kind(path):
    segs = path.lower().split("/")
    for i, s in enumerate(segs):
        if s in ROOTS:
            mounted = any(k in p for p in segs[:i] for k in KEEP_POLE_UNDER)
            return ROOTS[s], mounted
    return None, False


def _gltf(p):
    """Game feet -> glTF metres (Y up, Z negated), as in export.py."""
    return [p[0] * FEET_TO_METERS, p[1] * FEET_TO_METERS,
            -p[2] * FEET_TO_METERS]


def split(instances):
    """Returns (instances to export, prop placements)."""
    keep, poles, heads = [], [], []
    for inst in instances:
        kind, mounted = _kind(inst.path)
        if kind is None:
            keep.append(inst)
            continue
        model = inst.model.lower()
        if model == POLE[kind]:
            poles.append((kind, mounted, inst))
        if model == HEAD[kind]:
            heads.append((kind, inst))
        if mounted and model not in FAKE_FX:
            keep.append(inst)
    # pair each pole with the nearest head of the same kind (same lamp)
    grid = {}
    for kind, h in heads:
        x, _, z = h.matrix[3]
        grid.setdefault((kind, int(x // 10), int(z // 10)), []).append(h)
    props = []
    for kind, mounted, p in poles:
        bx, by, bz = p.matrix[3]
        best, bd = None, 1e9
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for h in grid.get((kind, int(bx // 10) + dx,
                                   int(bz // 10) + dz), []):
                    hx, _, hz = h.matrix[3]
                    d = (hx - bx) ** 2 + (hz - bz) ** 2
                    if d < bd:
                        best, bd = h, d
        head = list(best.matrix[3]) if best else [bx, by + 21.4, bz]
        if bd > 100:            # over 10 ft away: not this lamp's head
            head = [bx, by + 21.4, bz]
        # facing: from the pole towards the head, else the pole's own x axis
        fx, fz = head[0] - bx, head[2] - bz
        if fx * fx + fz * fz < 0.25:
            fx, fz = p.matrix[0][0], p.matrix[0][2]
        b, h = _gltf((bx, by, bz)), _gltf(head)
        props.append({
            "kind": kind,
            "keep_pole": mounted,
            "base": [round(v, 3) for v in b],
            "head": [round(v, 3) for v in h],
            # glTF facing direction in the ground plane (x, z)
            "facing": [round(fx, 4), round(-fz, 4)],
            "path": p.path,
        })
    return keep, props

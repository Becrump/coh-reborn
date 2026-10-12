"""Blender: modern monorail kit for Atlas Park Reborn (all new geometry).

    blender -b --factory-startup -P monorail_kit.py -- <out dir> [station drop m]

Writes one FBX per asset (metres, Z up, X forward), with UCX_ collision
boxes so players can walk in the train and the station:
  SM_Mono_Beam      10 m guideway beam, top at z = 0 (spline-mesh friendly)
  SM_Mono_Pillar    support column, pivot at the beam's underside, 40 m deep
  SM_Mono_Car       one 15 m car: rounded shell, window band, floor,
                    seats, grab poles; door openings on both sides
  SM_Mono_CarNose   end-car shell variant with a sloped nose
  SM_Mono_Door      sliding door leaf (two per side per car)
  SM_Mono_Station   elevated station: twin side platforms at train-floor
                    height, glass canopy, ground hall with entrances and a
                    switchback stair tower up to each platform
Material slots: Body, Stripe, Glass, Dark, Floor, Metal, Concrete, Light.
"""
import math
import os
import sys

import bmesh
import bpy

ARGS = sys.argv[sys.argv.index("--") + 1:]
OUT = ARGS[0]
# height of the beam top above the street at the station (monorail.json)
DROP = float(ARGS[1]) if len(ARGS) > 1 else 22.8
os.makedirs(OUT, exist_ok=True)
FLOOR = 1.0          # train floor above the beam top (m)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for n in ["Body", "Stripe", "Glass", "Dark", "Floor", "Metal", "Concrete", "Light"]:
        if n not in bpy.data.materials:
            bpy.data.materials.new(n)


def box(name, cx, cy, cz, sx, sy, sz, mat=None, bevel=0.0, coll=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    o = bpy.context.active_object
    o.name = name
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        m = o.modifiers.new("b", "BEVEL")
        m.width = bevel
        m.segments = 4
        bpy.ops.object.modifier_apply(modifier="b")
    if mat:
        o.data.materials.append(bpy.data.materials[mat])
    return o


def ucx(base, i, cx, cy, cz, sx, sy, sz):
    o = box("UCX_%s_%02d" % (base, i), cx, cy, cz, sx, sy, sz)
    return o


def cyl(name, cx, cy, cz, r, h, mat, verts=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=(cx, cy, cz))
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(bpy.data.materials[mat])
    return o


def join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = name
    return o


def export(name):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, name + ".fbx"), use_selection=True,
                             apply_unit_scale=True, global_scale=1.0, axis_forward="X", axis_up="Z",
                             mesh_smooth_type="FACE", bake_space_transform=True)
    print("EXPORTED", name)


# ------------------------------------------------------------- beam
reset()
b = box("SM_Mono_Beam", 0, 0, -0.9, 10.0, 1.0, 1.8, "Concrete", 0.04)
rail = box("rail", 0, 0, -0.02, 10.0, 0.7, 0.04, "Metal")
join([b, rail], "SM_Mono_Beam")
ucx("SM_Mono_Beam", 0, 0, 0, -0.9, 10.0, 1.0, 1.8)
export("SM_Mono_Beam")

# ------------------------------------------------------------- pillar
reset()
col = cyl("SM_Mono_Pillar", 0, 0, -21.8, 0.75, 40.0, "Concrete", 32)
cap = box("cap", 0, 0, -2.25, 2.6, 1.6, 0.9, "Concrete", 0.08)
join([col, cap], "SM_Mono_Pillar")
ucx("SM_Mono_Pillar", 0, 0, 0, -21.8, 1.4, 1.4, 40.0)
export("SM_Mono_Pillar")


# ------------------------------------------------------------- car shell
def car(name, nose=False):
    reset()
    L, W, H = 15.0, 3.0, 3.1
    z0 = FLOOR - 0.35                     # underside of the floor slab
    parts = []
    # floor slab and the skirt that wraps the beam
    parts.append(box("floor", 0, 0, z0 + 0.15, L, W - 0.1, 0.3, "Floor"))
    parts.append(box("skirtL", 0, 0.75, -0.5, L - 0.6, 0.12, 1.2, "Dark"))
    parts.append(box("skirtR", 0, -0.75, -0.5, L - 0.6, 0.12, 1.2, "Dark"))
    # side walls with two door openings each (doors at x = -3.5 and +3.5, 1.6 m wide)
    zw = z0 + 0.3
    wall_h = 2.3
    for side in (1, -1):
        y = side * (W / 2 - 0.06)
        xs = [(-L / 2, -4.3), (-2.7, 2.7), (4.3, L / 2)]
        for a, c in xs:
            parts.append(box("lower", (a + c) / 2, y, zw + 0.45, c - a, 0.12, 0.9, "Body"))
            parts.append(box("glass", (a + c) / 2, y, zw + 1.45, c - a, 0.08, 1.1, "Glass"))
            parts.append(box("upper", (a + c) / 2, y, zw + 2.15, c - a, 0.12, 0.3, "Body"))
        parts.append(box("stripe", 0, y * 1.01, zw + 0.75, L, 0.02, 0.12, "Stripe"))
        for x in (-3.5, 3.5):
            parts.append(box("lintel", x, y, zw + 2.2, 1.6, 0.12, 0.2, "Body"))
    # roof (rounded), end walls with a through gangway
    roof = box("roof", 0, 0, zw + wall_h + 0.2, L, W, 0.4, "Body", 0.18)
    parts.append(roof)
    for sx in (1, -1):
        x = sx * (L / 2 - 0.06)
        if nose and sx == 1:
            # sloped nose: a big wedge of glass and body ahead of the cab
            bm = bmesh.new()
            pts = [(x, -W / 2, zw), (x, W / 2, zw), (x + 2.2, W / 2 - 0.5, zw), (x + 2.2, -W / 2 + 0.5, zw),
                   (x, -W / 2, zw + wall_h + 0.4), (x, W / 2, zw + wall_h + 0.4),
                   (x + 0.9, W / 2 - 0.3, zw + wall_h), (x + 0.9, -W / 2 + 0.3, zw + wall_h)]
            v = [bm.verts.new(p) for p in pts]
            for f in [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (2, 6, 7, 3), (1, 5, 6, 2), (0, 3, 7, 4)]:
                bm.faces.new([v[i] for i in f])
            me = bpy.data.meshes.new("nose")
            bm.to_mesh(me)
            o = bpy.data.objects.new("nose", me)
            bpy.context.collection.objects.link(o)
            o.data.materials.append(bpy.data.materials["Glass"])
            parts.append(o)
            parts.append(box("cabwall", x - 2.0, 0, zw + 1.2, 0.1, W - 0.3, 2.4, "Body"))
        else:
            parts.append(box("endL", x, 0.95, zw + 1.15, 0.12, 0.9, 2.3, "Body"))
            parts.append(box("endR", x, -0.95, zw + 1.15, 0.12, 0.9, 2.3, "Body"))
            parts.append(box("endTop", x, 0, zw + 2.15, 0.12, 1.0, 0.3, "Body"))
    # seats along the walls between the doors, grab poles, ceiling light strip
    for side in (1, -1):
        for a, c in [(-6.8, -4.6), (-2.4, 2.4), (4.6, 6.8)]:
            parts.append(box("seat", (a + c) / 2, side * 1.2, zw + 0.25, c - a, 0.5, 0.5, "Dark", 0.03))
    for x in (-5.5, -1.5, 1.5, 5.5):
        parts.append(cyl("pole", x, 0, zw + 1.15, 0.025, 2.3, "Metal", 12))
    parts.append(box("lightstrip", 0, 0, zw + 2.3, L - 1.0, 0.25, 0.04, "Light"))
    join(parts, name)
    # collision: floor, wall pieces either side of the doors, roof, ends
    k = 0
    ucx(name, k, 0, 0, z0 + 0.15, L, W, 0.3); k += 1
    for side in (1, -1):
        y = side * (W / 2 - 0.06)
        for a, c in [(-L / 2, -4.3), (-2.7, 2.7), (4.3, L / 2)]:
            ucx(name, k, (a + c) / 2, y, zw + 1.15, c - a, 0.15, 2.3); k += 1
    ucx(name, k, 0, 0, zw + wall_h + 0.2, L, W, 0.4); k += 1
    ucx(name, k, 0, 0, -0.5, L - 0.6, 1.62, 1.2); k += 1
    export(name)


car("SM_Mono_Car")
car("SM_Mono_CarNose", nose=True)

# ------------------------------------------------------------- door leaf
reset()
d = box("SM_Mono_Door", 0, 0, 1.15, 0.82, 0.06, 2.3, "Body")
g = box("dg", 0, 0, 1.35, 0.6, 0.07, 1.3, "Glass")
join([d, g], "SM_Mono_Door")
ucx("SM_Mono_Door", 0, 0, 0, 1.15, 0.82, 0.08, 2.3)
export("SM_Mono_Door")

# ------------------------------------------------------------- station
reset()
P_LEN, P_W = 70.0, 5.0          # each side platform
TOP = FLOOR                      # platform surface = train floor (beam top = 0)
GAP = 1.75                       # beam centre to platform edge
parts, cols = [], []
for side in (1, -1):
    yc = side * (GAP + P_W / 2)
    parts.append(box("deck", 0, yc, TOP - 0.3, P_LEN, P_W, 0.6, "Concrete", 0.02))
    parts.append(box("edge", 0, side * (GAP + 0.25), TOP + 0.005, P_LEN, 0.5, 0.01, "Stripe"))
    # platform screen: glass with door gaps matching a 3-car train stopped at x = 0
    xs = []
    for car_x in (-15.5, 0, 15.5):
        for dx in (-3.5, 3.5):
            xs.append(car_x + dx)
    xs.sort()
    edges = [-P_LEN / 2] + [v for x in xs for v in (x - 0.9, x + 0.9)] + [P_LEN / 2]
    for a, c in zip(edges[0::2], edges[1::2]):
        if c - a > 0.2:
            parts.append(box("screen", (a + c) / 2, side * (GAP + 0.1), TOP + 1.1, c - a, 0.06, 2.2, "Glass"))
            cols.append(("screen", (a + c) / 2, side * (GAP + 0.1), TOP + 1.1, c - a, 0.1, 2.2))
    # back wall (glass) and roof canopy
    parts.append(box("back", 0, side * (GAP + P_W), TOP + 1.6, P_LEN, 0.1, 3.2, "Glass"))
    cols.append(("back", 0, side * (GAP + P_W), TOP + 1.6, P_LEN, 0.2, 3.2))
    cols.append(("deck", 0, yc, TOP - 0.3, P_LEN, P_W, 0.6))
    for x in range(-30, 31, 10):
        parts.append(box("post", x, side * (GAP + P_W - 0.2), TOP + 2.6, 0.25, 0.25, 5.2, "Metal"))
        parts.append(box("lamp", x, side * (GAP + P_W / 2), TOP + 4.6, 1.6, 0.3, 0.08, "Light"))
canopy = box("canopy", 0, 0, TOP + 5.3, P_LEN + 4, 2 * (GAP + P_W) + 2, 0.35, "Body", 0.15)
parts.append(canopy)
# ground hall: a glass box under one end with two street entrances
HALL_X, HALL_L, HALL_W, HALL_H = 22.0, 22.0, 16.0, 6.0
GZ = -DROP                       # street level below the beam top
parts.append(box("hallfloor", HALL_X, 0, GZ + 0.1, HALL_L, HALL_W, 0.2, "Floor"))
parts.append(box("hallroof", HALL_X, 0, GZ + HALL_H, HALL_L, HALL_W, 0.4, "Body"))
for side in (1, -1):
    y = side * HALL_W / 2
    for a, c in [(HALL_X - HALL_L / 2, HALL_X - 2.5), (HALL_X + 2.5, HALL_X + HALL_L / 2)]:
        parts.append(box("hallwall", (a + c) / 2, y, GZ + HALL_H / 2, c - a, 0.12, HALL_H, "Glass"))
        cols.append(("hallwall", (a + c) / 2, y, GZ + HALL_H / 2, c - a, 0.2, HALL_H))
for x in (HALL_X - HALL_L / 2, HALL_X + HALL_L / 2):
    parts.append(box("hallend", x, 0, GZ + HALL_H / 2, 0.12, HALL_W, HALL_H, "Glass"))
    cols.append(("hallend", x, 0, GZ + HALL_H / 2, 0.2, HALL_W, HALL_H))
cols.append(("hallfloor", HALL_X, 0, GZ + 0.1, HALL_L, HALL_W, 0.2))
# stair towers: switchback flights from the hall up to each platform end
RISE = TOP - GZ                  # 23.8 m
FL_RISE, FL_RUN, FL_W = 2.0, 3.6, 1.8
n_fl = int(math.ceil(RISE / FL_RISE))
for side in (1, -1):
    tx = HALL_X + HALL_L / 2 - 6
    ty = side * (GAP + P_W - 1.0)
    z = GZ + 0.2
    for i in range(n_fl):
        dirx = 1 if i % 2 == 0 else -1
        lane = ty + side * (0 if i % 2 == 0 else -FL_W - 0.2)
        x0 = tx - dirx * FL_RUN / 2
        rise = min(FL_RISE, TOP - z)
        # steps
        steps = 12
        for s in range(steps):
            sx = x0 + dirx * (s + 0.5) * FL_RUN / steps
            parts.append(box("step", sx, lane, z + (s + 0.5) * rise / steps, FL_RUN / steps, FL_W, rise / steps, "Concrete"))
        # ramp collision under the steps (smooth to walk)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(tx, lane, z + rise / 2))
        r = bpy.context.active_object
        r.name = "UCX_SM_Mono_Station_ramp%02d_%d" % (i, side + 1)
        r.scale = (math.hypot(FL_RUN, rise), FL_W, 0.2)
        r.rotation_euler = (0, -dirx * math.atan2(rise, FL_RUN), 0)
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        z += rise
        # landing
        lx = tx + dirx * (FL_RUN / 2 + 0.9)
        parts.append(box("landing", lx, ty + side * (-(FL_W + 0.2) / 2), z - 0.1, 1.8, 2 * FL_W + 0.2, 0.2, "Concrete"))
        cols.append(("landing", lx, ty + side * (-(FL_W + 0.2) / 2), z - 0.1, 1.8, 2 * FL_W + 0.2, 0.2))
    parts.append(box("towerglass", tx, ty + side * (-(FL_W + 0.2) / 2), (GZ + TOP) / 2, FL_RUN + 4.0, 2 * FL_W + 1.2, RISE, "Glass"))
station = join(parts, "SM_Mono_Station")
for k, c in enumerate(cols):
    ucx("SM_Mono_Station", k, *c[1:])
export("SM_Mono_Station")
print("KIT_DONE")

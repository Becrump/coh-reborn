"""Places City Sample cars where the original CoH parked cars were (run in the editor,
after cs_hide_coh_cars.py has taken the old cars out of the tiles).

One actor per CoH car, same spot and heading (CoH cars point down local -Y,
City Sample cars down +X, so yaw - 90), centred on the old car's middle and
snapped to the ground. Model by size (compacts get the small City Sample
cars, vans get vans), paint colour varied, both picked from a fixed seed so
reruns place the same cars.

Collision on: PhysicsActor profile (blocks players, enemies, the camera and
powers' line of sight), physics simulated but asleep until something hits
it, ~1.3-2.4 t, movement replicated. The PPD squad car prop becomes the
City Sample police car.

Fit checks, fixed by moving the car (the parking spot) up to 1.5 m, then
by a shorter model:
* clear of buildings, poles and walls (box from 40 cm above the ground, so
  curbs and the road do not count),
* clear of the other new cars,
* clear of the traffic lanes the CoHLifeManager drives (its cars collide).
Every move is written to place_report.json.

Env: CSPLACE_SAVE=1 saves the new actors (default: place only, no save).
"""
import json
import math
import os
import random
import unreal

here = os.path.dirname(os.path.abspath(__file__))
SAVE = os.environ.get("CSPLACE_SAVE") == "1"
FOLDER = "CitySampleCars/Parked"
KIT = json.load(open(os.path.join(here, "kit.json")))
CARS = json.load(open(os.path.join(here, "coh_cars_in_map.json")))
CHOICES = {
    "_Prkd_Compact1__dmgcarLod1": ["vehicle06_Car", "vehicle07_Car", "vehicle05_Car"],
    "_Prkd_Sport1_1__dmgcarLod1": ["vehicle03_Car", "vehicle12_Car", "vehicle05_Car", "vehicle02_Car"],
    "_Prkd_Sport2_1__dmgcarLod1": ["vehicle03_Car", "vehicle12_Car", "vehicle05_Car", "vehicle02_Car"],
    "_Prkd_Lux1_2__dmgcarLod5": ["vehicle02_Car", "vehicle03_Car", "vehicle12_Car"],
    "_Prkd_Lux2_1__dmgcarLod1": ["vehicle02_Car", "vehicle03_Car", "vehicle12_Car"],
    "_Prkd_Truck_1__dmgtruckLod1a": ["vehicle09_Van", "vehicle01_Van", "vehicle04_Truck"],
}
MASS = {"vehicle01_Van": 2100, "vehicle09_Van": 2400, "vehicle04_Truck": 2200}
PAINT = ["White", "Black", "Silver", "Silver", "Red", "Navy", "Green", "Maroon", "Blue", "White", "Black", "Yellow"]
LANE_CLEAR = 120.0   # half width of a moving car + a little air (cm)

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
WS = [unreal.ObjectTypeQuery.ECC_WORLD_STATIC]


def log(*a):
    unreal.log("cs_place: " + " ".join(str(x) for x in a))
    print(*a)


def size(v):
    k = KIT[v]
    return [(k["max"][i] - k["min"][i]) for i in range(3)], [(k["max"][i] + k["min"][i]) / 2 for i in range(3)]


def ground(x, y, z):
    h = unreal.SystemLibrary.line_trace_single_for_objects(world, unreal.Vector(x, y, z + 250), unreal.Vector(x, y, z - 400),
                                                           WS, True, [], unreal.DrawDebugTrace.NONE, True)
    return h.to_tuple()[5].z if h else None


def corners(cx, cy, yaw, hl, hw):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return [(cx + a * hl * c - b * hw * s, cy + a * hl * s + b * hw * c) for a, b in ((1, 1), (1, -1), (-1, -1), (-1, 1))]


def obb_overlap(A, B):
    """2D separating-axis test of two rectangles given as 4 corners."""
    for poly in (A, B):
        for i in range(4):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % 4]
            nx, ny = y2 - y1, x1 - x2
            pa = [nx * x + ny * y for x, y in A]
            pb = [nx * x + ny * y for x, y in B]
            if max(pa) < min(pb) or max(pb) < min(pa):
                return False
    return True


def blocked_static(cx, cy, z, yaw, hl, hw, h):
    hits = unreal.SystemLibrary.box_overlap_actors(world, unreal.Vector(cx, cy, z + 40 + (h - 40) / 2),
                                                   unreal.Vector(hl - 5, hw - 5, (h - 40) / 2), WS, None, [])
    return [a.get_actor_label() for a in hits if not a.get_actor_label().startswith("CSCar_")]


def lane_points():
    lm = [a for a in actors.get_all_level_actors() if a.get_class().get_name() == "CoHLifeManager"]
    if not lm:
        return []
    path = lm[0].get_editor_property("life_json").get_editor_property("file_path")
    if not os.path.isabs(path):
        path = os.path.join(unreal.Paths.project_dir(), path)
    try:
        data = json.load(open(path))
    except Exception as e:
        log("no lane data", path, e)
        return []
    return [(p["p"][0], p["p"][1], p["p"][2]) for p in data.get("traffic", [])]


LANES = lane_points()
GRID = {}
for p in LANES:
    GRID.setdefault((int(p[0] // 1000), int(p[1] // 1000)), []).append(p)


def in_lane(rect, z):
    xs = [x for x, _ in rect]
    ys = [y for _, y in rect]
    for gx in range(int(min(xs) // 1000) - 1, int(max(xs) // 1000) + 2):
        for gy in range(int(min(ys) // 1000) - 1, int(max(ys) // 1000) + 2):
            for p in GRID.get((gx, gy), []):
                if abs(p[2] - z) > 250:
                    continue
                # distance from lane point to the rectangle (approx: grow the rect)
                cx, cy = sum(xs) / 4, sum(ys) / 4
                if obb_overlap(rect, [(p[0] - LANE_CLEAR, p[1] - LANE_CLEAR), (p[0] + LANE_CLEAR, p[1] - LANE_CLEAR),
                                      (p[0] + LANE_CLEAR, p[1] + LANE_CLEAR), (p[0] - LANE_CLEAR, p[1] + LANE_CLEAR)]):
                    return True
    return False


def spawn(v, colour, loc, yaw, label, mass):
    mesh = eas.load_asset(KIT[v]["mesh"])
    a = actors.spawn_actor_from_object(mesh, loc, unreal.Rotator(0, 0, yaw))
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    c = a.static_mesh_component
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_collision_profile_name("PhysicsActor")
    c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
    bi = c.get_editor_property("body_instance")
    bi.set_editor_property("simulate_physics", True)
    bi.set_editor_property("start_awake", False)
    bi.set_editor_property("override_mass", True)
    bi.set_editor_property("mass_in_kg_override", float(mass))
    bi.set_editor_property("linear_damping", 0.4)
    bi.set_editor_property("angular_damping", 0.8)
    c.set_editor_property("body_instance", bi)
    c.set_simulate_physics(True)
    if colour and KIT[v]["colours"].get(colour) and KIT[v]["paint_slot"] >= 0:
        c.set_material(KIT[v]["paint_slot"], eas.load_asset(KIT[v]["colours"][colour]))
    a.set_editor_property("replicates", True)
    try:
        a.set_editor_property("static_mesh_replicate_movement", True)
    except Exception:
        a.set_editor_property("replicate_movement", True)
    a.tags = [unreal.Name("CitySampleCar")]
    return a


# rerun-safe: drop cars this script placed before
for a in actors.get_all_level_actors():
    if a.get_actor_label().startswith("CSCar_"):
        actors.destroy_actor(a)

rng = random.Random(1959)
placed, report = [], dict(cars=[], moved=[], swapped_model=[], unresolved=[])
for i, car in enumerate(CARS):
    choices = list(CHOICES[car["kind"]])
    first = rng.choice(choices)
    order = [first] + sorted((v for v in choices if v != first), key=lambda v: size(v)[0][0])
    colour = rng.choice(PAINT)
    yaw = car["yaw"] - 90.0
    done = None
    for vi, v in enumerate(order):
        (L, W, H), (ox, oy, oz) = size(v)
        hl, hw = L / 2 + 10, W / 2 + 10
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        for shift_l, shift_w in ((0, 0), (60, 0), (-60, 0), (0, 40), (0, -40), (120, 0), (-120, 0), (0, 80), (0, -80), (150, 40), (-150, -40)):
            cx = car["c"][0] + shift_l * c - shift_w * s
            cy = car["c"][1] + shift_l * s + shift_w * c
            z = ground(cx, cy, car["l"][2])
            if z is None:
                continue
            rect = corners(cx, cy, yaw, hl, hw)
            why = []
            if blocked_static(cx, cy, z, yaw, L / 2, W / 2, H):
                why.append("static")
            if any(obb_overlap(rect, r) for r in placed):
                why.append("car")
            if LANES and in_lane(corners(cx, cy, yaw, L / 2, W / 2), z):
                why.append("lane")
            if not why:
                done = (v, cx, cy, z, shift_l, shift_w, rect)
                break
        if done:
            break
    if not done:
        v = order[-1]
        (L, W, H), _ = size(v)
        z = ground(car["c"][0], car["c"][1], car["l"][2]) or car["l"][2]
        done = (v, car["c"][0], car["c"][1], z, 0, 0, corners(car["c"][0], car["c"][1], yaw, L / 2 + 10, W / 2 + 10))
        report["unresolved"].append(dict(i=i, kind=car["kind"], at=[round(car["c"][0]), round(car["c"][1])]))
    v, cx, cy, z, sl, sw, rect = done
    (L, W, H), (ox, oy, oz) = size(v)
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    loc = unreal.Vector(cx - (ox * c - oy * s), cy - (ox * s + oy * c), z + 2.0)
    a = spawn(v, colour, loc, yaw, "CSCar_%03d_%s" % (i, v.split("_")[0]), MASS.get(v, 1350))
    placed.append(rect)
    entry = dict(i=i, kind=car["kind"], vehicle=v, colour=colour, at=[round(cx), round(cy), round(z)], yaw=round(yaw, 1))
    report["cars"].append(entry)
    if sl or sw:
        report["moved"].append(dict(entry, shift_along_cm=sl, shift_across_cm=sw))
    if v != order[0]:
        report["swapped_model"].append(dict(entry, wanted=order[0]))

# the PPD squad car prop -> City Sample police car
for a in actors.get_all_level_actors():
    c = getattr(a, "static_mesh_component", None)
    if c and c.static_mesh and c.static_mesh.get_name() == "PPD_SquadCar" and "vehicle13_Car" in KIT:
        t = a.get_actor_transform()
        b0 = c.static_mesh.get_bounding_box()
        (L, W, H), (ox, oy, oz) = size("vehicle13_Car")
        long_x = (b0.max.x - b0.min.x) >= (b0.max.y - b0.min.y)
        yaw = t.rotation.rotator().yaw + (0.0 if long_x else -90.0)
        p = t.translation
        z = ground(p.x, p.y, p.z) or p.z
        cc, ss = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        spawn("vehicle13_Car", None, unreal.Vector(p.x - (ox * cc - oy * ss), p.y - (ox * ss + oy * cc), z + 2.0), yaw, "CSCar_Police_vehicle13", 1600)
        a.set_is_temporarily_hidden_in_editor(False)
        c.set_visibility(False)
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        report["squad_car"] = dict(old=a.get_actor_label(), at=[round(p.x), round(p.y), round(z)], yaw=round(yaw, 1), actor=a.get_path_name())

json.dump(report, open(os.path.join(here, "place_report.json"), "w"), indent=1)
log("placed", len(report["cars"]), "moved", len(report["moved"]), "other model", len(report["swapped_model"]),
    "unresolved", len(report["unresolved"]), "lanes", len(LANES))
if SAVE:
    pkgs = [a.get_package() for a in actors.get_all_level_actors() if a.get_actor_label().startswith("CSCar_")]
    if report.get("squad_car"):
        pkgs.append(unreal.find_object(None, report["squad_car"]["actor"]).get_package())
    log("saved", len(pkgs), unreal.EditorLoadingAndSavingUtils.save_packages(pkgs, False))

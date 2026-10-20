"""Removes the original CoH parked cars from AtlasPark_DressingStudy_Nanite.

The CoH cars are baked into the merged tile meshes. Their materials
(Car_tire*, Compact_*, Lux1_*, Lux2_*, Sport1_*, Sport2_*, Cubevan_*,
underside_longrust01) belong to the six _Prkd_ car models only, so:

* visible tiles: the car material slots get an invisible (masked, opacity 0)
  override ON THE ACTOR. The shared tile meshes are untouched.
* collision tiles: a copy of the mesh with collision switched off on the
  car sections goes to /Game/AtlasPark4/CitySampleCars/Tiles/ and only this
  map's actor is repointed (the originals are shared with other study maps).

Checked with downward traces before and after: every car spot must reach
the road afterwards, and a floor point next to each car (outside every car
footprint) must land on the same height. A copy that breaks a floor point
is put back to the original mesh and reported.

Env: CSHIDE_SAVE=1 saves the touched actors and new assets (default: no
save). CSHIDE_SKIP=label,label leaves tiles alone. Needs
coh_cars_in_map.json (cs_coh_cars.py). Writes hide_report.json.
"""
import json
import math
import os
import re
import unreal

ROOT = "/Game/AtlasPark4/CitySampleCars"
HIDDEN = ROOT + "/M_CSCar_HiddenCoHCar"
CAR = re.compile(r"(?i)^(car_tire|compact_|lux1_|lux2_|sport1_|sport2_|cubevan_|underside_longrust01)")
here = os.path.dirname(os.path.abspath(__file__))
SAVE = os.environ.get("CSHIDE_SAVE") == "1"
SKIP = set(x for x in os.environ.get("CSHIDE_SKIP", "").split(",") if x)
# render actors whose label contains one of these keep their materials (another job's overrides)
SKIP_RENDER = [x for x in os.environ.get("CSHIDE_SKIP_RENDER", "").split(",") if x]

eas = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def log(*a):
    unreal.log("cs_hide: " + " ".join(str(x) for x in a))
    print(*a)


def hidden_material():
    if eas.does_asset_exist(HIDDEN):
        return eas.load_asset(HIDDEN)
    m = tools.create_asset(HIDDEN.rsplit("/", 1)[1], ROOT, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    zero = mel.create_material_expression(m, unreal.MaterialExpressionConstant, -300, 0)
    zero.set_editor_property("r", 0.0)
    mel.connect_material_property(zero, "", unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.recompile_material(m)
    if SAVE:
        eas.save_loaded_asset(m, False)
    return m


def trace(x, y, z):
    hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, z + 500), unreal.Vector(x, y, z - 300),
                                                 unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
                                                 unreal.DrawDebugTrace.NONE, True)
    if not hit:
        return None, ""
    t = hit.to_tuple()   # (blocking, initial_overlap, time, distance, location, impact_point, ..., hit_actor=9)
    who = t[9].get_actor_label() if t[9] else ""
    return t[5].z, who


def in_car(x, y, pad=60.0):
    for s in spots:
        dx, dy = x - s["c"][0], y - s["c"][1]
        yaw = math.radians(s["yaw"])
        # car local: X across the width, Y along the length (CoH meshes)
        lx = dx * math.cos(yaw) + dy * math.sin(yaw)
        ly = -dx * math.sin(yaw) + dy * math.cos(yaw)
        if abs(lx) <= s["half"][0] + pad and abs(ly) <= s["half"][1] + pad:
            return True
    return False


def floor_point(s):
    yaw = math.radians(s["yaw"])
    wx, wy = math.cos(yaw), math.sin(yaw)       # width axis
    lx, ly = -math.sin(yaw), math.cos(yaw)      # length axis
    for d in (1, -1):
        for k in (180.0, 260.0, 340.0):
            px, py = s["c"][0] + d * wx * (s["half"][0] + k - 100), s["c"][1] + d * wy * (s["half"][0] + k - 100)
            if not in_car(px, py):
                return px, py
        for k in (120.0, 220.0):
            px, py = s["c"][0] + d * lx * (s["half"][1] + k), s["c"][1] + d * ly * (s["half"][1] + k)
            if not in_car(px, py):
                return px, py
    return None


spots = json.load(open(os.path.join(here, "coh_cars_in_map.json")))
DIRTY_BEFORE = set(p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
report = dict(render=[], collision=[], skipped=[], reverted=[], spots_blocked=[], floor_changed=[])
hide = hidden_material()

# 1) traces before any change
floors = [floor_point(s) for s in spots]
before = [trace(s["c"][0], s["c"][1], s["l"][2]) for s in spots]
before_floor = [trace(f[0], f[1], s["l"][2]) if f else (None, "") for s, f in zip(spots, floors)]

# 2) hide render sections, swap collision tiles
swapped = {}   # actor label -> (actor, original mesh, copy path)
for a in actors.get_all_level_actors():
    if a.get_class().get_name() != "StaticMeshActor":
        continue
    c = a.static_mesh_component
    mesh = c.static_mesh
    if not mesh:
        continue
    label = a.get_actor_label()
    if label.startswith("CoHOriginal_"):
        continue   # the PPD squad car prop is swapped by cs_place_cars
    mats = c.get_materials()
    slots = [i for i, m in enumerate(mats) if m and CAR.match(m.get_name())]
    if not slots:
        continue
    # leave tiles another job has unsaved edits on (saving them would save its work too)
    if label in SKIP or a.get_package().get_name() in DIRTY_BEFORE:
        report["skipped"].append(dict(label=label, mesh=mesh.get_path_name(), why="skip list or unsaved edits"))
        continue
    if c.is_visible() and any(k in label for k in SKIP_RENDER):
        report["skipped"].append(dict(label=label, mesh=mesh.get_path_name(), why="render overrides of another job"))
    elif c.is_visible():
        for i in slots:
            c.set_material(i, hide)
        report["render"].append(dict(label=label, actor=a.get_path_name(), slots=slots,
                                     was=[mats[i].get_path_name() for i in slots]))
    if c.get_collision_enabled() == unreal.CollisionEnabled.NO_COLLISION:
        continue
    src = mesh.get_path_name().split(".")[0]
    dst = ROOT + "/Tiles/" + src.rsplit("/", 1)[1] + "_NoCars"
    copy = eas.load_asset(dst) if eas.does_asset_exist(dst) else eas.duplicate_asset(src, dst)
    if not copy:
        report["reverted"].append(dict(label=label, why="duplicate failed", src=src))
        continue
    off = []
    for sec in range(copy.get_num_sections(0)):
        slot = sme.get_lod_material_slot(copy, 0, sec)
        mi = copy.static_materials[slot].material_interface if 0 <= slot < len(copy.static_materials) else None
        if slot in slots or (mi and CAR.match(mi.get_name())):
            sme.enable_section_collision(copy, False, 0, sec)
            off.append(sec)
    c.set_static_mesh(copy)
    swapped[label] = (a, mesh, dst)
    report["collision"].append(dict(label=label, actor=a.get_path_name(), src=src, copy=dst, sections_off=off))
    log(label, "sections off", len(off), "of", copy.get_num_sections(0))

# 3) traces after
after = [trace(s["c"][0], s["c"][1], s["l"][2]) for s in spots]
after_floor = [trace(f[0], f[1], s["l"][2]) if f else (None, "") for s, f in zip(spots, floors)]
broken = set()
cleared = 0
for s, f, b, a_, bf, af in zip(spots, floors, before, after, before_floor, after_floor):
    if a_[0] is None or a_[0] > s["l"][2] + 60:
        report["spots_blocked"].append(dict(kind=s["kind"], c=[round(v) for v in s["c"]], before=b, after=a_))
    elif b[0] is not None and b[0] > s["l"][2] + 60:
        cleared += 1
    if f and bf[0] is not None and (af[0] is None or abs(af[0] - bf[0]) > 5):
        report["floor_changed"].append(dict(p=[round(f[0]), round(f[1])], before=bf, after=af))
        if bf[1] in swapped:
            broken.add(bf[1])
for label in broken:
    a, mesh, dst = swapped[label]
    a.static_mesh_component.set_static_mesh(mesh)
    report["reverted"].append(dict(label=label, copy=dst, why="floor point changed"))
    report["collision"] = [e for e in report["collision"] if e["label"] != label]
report["cars"] = len(spots)
report["car_spots_cleared"] = cleared
json.dump(report, open(os.path.join(here, "hide_report.json"), "w"), indent=1)
log("spots", len(spots), "cleared", cleared, "still blocked", len(report["spots_blocked"]),
    "floor changed", len(report["floor_changed"]), "render tiles", len(report["render"]),
    "collision tiles", len(report["collision"]), "reverted", len(report["reverted"]), "skipped", len(report["skipped"]))
if SAVE:
    eas.save_asset(HIDDEN, False)
    for e in report["collision"]:
        eas.save_asset(e["copy"], False)
    pkgs = [unreal.find_object(None, e["actor"]).get_package() for e in report["render"] + report["collision"]]
    ok = unreal.EditorLoadingAndSavingUtils.save_packages(pkgs, False)
    log("saved", len(pkgs), "actor packages", ok)

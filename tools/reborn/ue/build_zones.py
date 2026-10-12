"""Step 4: place the PCG inputs from lots_plan.json (plan_lots.py).

* one TargetPoint per building lot, rotated to the lot, tagged RebornLot and
  RebornBucket_<bucket>; the PCG building graph picks the building
* one closed-spline zone actor (BP_RebornZone) per wood or park, tagged
  RebornZone_<kind>; the PCG planting graphs fill them
Landmark lots (City Hall, the Atlas statue) get a marker tagged
RebornLandmark and stay empty for a hand-picked replacement."""
import json
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
plan = json.load(open(os.path.join(OUT, "lots_plan.json")))
LAY = ROOT + "/Layout"
BP = LAY + "/BP_RebornZone"
if not el.does_asset_exist(BP):
    f = unreal.BlueprintFactory()
    f.set_editor_property("parent_class", unreal.Actor)
    bp = tools.create_asset("BP_RebornZone", LAY, unreal.Blueprint, f)
    ss = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    root = ss.k2_gather_subobject_data_for_blueprint(bp)[0]
    params = unreal.AddNewSubobjectParams(parent_handle=root, new_class=unreal.SplineComponent, blueprint_context=bp)
    ss.add_new_subobject(params)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    el.save_loaded_asset(bp)
zone_cls = el.load_blueprint_class(BP)

for a in actors.get_all_level_actors():
    if str(a.get_folder_path()).startswith("AtlasReborn/Layout"):
        actors.destroy_actor(a)

n_lots = 0
for lot in plan["lots"]:
    x, y = lot["center"]
    a = actors.spawn_actor_from_class(unreal.TargetPoint, unreal.Vector(x * 100, y * 100, lot["ground"] * 100),
                                      unreal.Rotator(0, 0, lot["yaw"]))
    a.set_actor_rotation(unreal.Rotator(pitch=0, yaw=lot["yaw"], roll=0), False)
    a.set_actor_label("Lot_" + lot["id"])
    if lot["kind"].startswith("landmark"):
        a.set_folder_path("AtlasReborn/Layout/Landmarks")
        a.set_editor_property("tags", ["RebornLandmark", lot["kind"]])
        continue
    a.set_folder_path("AtlasReborn/Layout/Lots")
    a.set_editor_property("tags", ["RebornLot", "RebornBucket_" + lot["bucket"], lot["kind"]])
    n_lots += 1

n_zones = 0
for z in plan["zones"]:
    pts = z["poly"][:-1]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    a = actors.spawn_actor_from_class(zone_cls, unreal.Vector(cx * 100, cy * 100, 0))
    a.set_actor_label("Zone_" + z["name"])
    a.set_folder_path("AtlasReborn/Layout/Zones")
    a.set_editor_property("tags", ["RebornZone", "RebornZone_" + z["kind"]])
    s = a.get_component_by_class(unreal.SplineComponent)
    s.clear_spline_points(False)
    for x, y in pts:
        s.add_spline_point(unreal.Vector(x * 100, y * 100, 0), unreal.SplineCoordinateSpace.WORLD, False)
    for i in range(len(pts)):
        s.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
    s.set_closed_loop(True, True)
    mark_spline_edited(s)
    n_zones += 1
print("lots", n_lots, "zones", n_zones)

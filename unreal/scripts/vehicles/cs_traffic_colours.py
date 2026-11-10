"""Gives the CoHLifeManager traffic paint colours again (run in the editor).

The instanced traffic cars use one static mesh per ISM, so a colour needs its own mesh asset:
for every traffic model this duplicates the merged City Sample mesh once per colour into
/Game/AtlasPark4/CitySampleCars/TrafficMeshes and swaps the paint slot to that colour's
instance (made by cs_build_kit.py, listed in kit.json), then points the manager's car_meshes at
them with the old weights. Env CSTC_SAVE=1 saves the new assets and the LifeManager actor.
Revert: run cs_traffic_cars.py (plain meshes) - the previous list is in traffic_colours_report.json.
"""
import json
import os
import unreal

here = os.path.dirname(os.path.abspath(__file__))
KIT = json.load(open(os.path.join(here, "kit.json")))
WEIGHTS = {"vehicle02_Car": 4, "vehicle03_Car": 4, "vehicle05_Car": 4, "vehicle06_Car": 4, "vehicle07_Car": 4,
           "vehicle12_Car": 4, "vehicle01_Van": 2, "vehicle09_Van": 2, "vehicle04_Truck": 1}
COLOURS = ["White", "Black", "Silver", "Red"]
DEST = "/Game/AtlasPark4/CitySampleCars/TrafficMeshes"
eas = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
lm = [a for a in actors.get_all_level_actors() if a.get_class().get_name() == "CoHLifeManager"][0]
old = [m.get_path_name() for m in lm.get_editor_property("car_meshes")]
new, made = [], []
for v, w in WEIGHTS.items():
    k = KIT[v]
    per = max(1, round(w / len(COLOURS))) if w >= len(COLOURS) else 1
    for ci, c in enumerate(COLOURS):
        if c not in k["colours"]:
            continue
        dst = "%s/SM_CSTraffic_%s_%s" % (DEST, v, c)
        if not eas.does_asset_exist(dst):
            eas.duplicate_asset(k["mesh"].split(".")[0], dst)
        m = eas.load_asset(dst)
        m.set_material(k["paint_slot"], eas.load_asset(k["colours"][c].split(".")[0]))
        made.append(dst)
        # weights: a model's weight is spread over its colours (vans and the truck: one entry per colour)
        new += [m] * per
lm.set_editor_property("car_meshes", new)
json.dump(dict(actor=lm.get_path_name(), before=old, after=[m.get_path_name() for m in new], assets=made),
          open(os.path.join(here, "traffic_colours_report.json"), "w"), indent=1)
print("assets", len(made), "car_meshes", len(old), "->", len(new))
if os.environ.get("CSTC_SAVE") == "1":
    for p in made:
        eas.save_asset(p)
    print("saved", unreal.EditorLoadingAndSavingUtils.save_packages([lm.get_package()], False))

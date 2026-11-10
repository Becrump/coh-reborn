"""Points the CoHLifeManager traffic (moving cars and its own curb-side parked
cars) at the merged City Sample car meshes (run in the editor).

The entries are weighted the way the old list was: mostly cars, some vans,
one truck; the police car is left out (it is the encounter prop). The C++
already gives these instanced cars collision (BlockAllDynamic,
QueryAndPhysics), and the merged meshes carry the box collision it uses.
Env CSLM_SAVE=1 saves the LifeManager actor only.
"""
import json
import os
import unreal

here = os.path.dirname(os.path.abspath(__file__))
KIT = json.load(open(os.path.join(here, "kit.json")))
WEIGHTS = {"vehicle02_Car": 4, "vehicle03_Car": 4, "vehicle05_Car": 4, "vehicle06_Car": 4, "vehicle07_Car": 4,
           "vehicle12_Car": 4, "vehicle01_Van": 2, "vehicle09_Van": 2, "vehicle04_Truck": 1}
eas = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
lm = [a for a in actors.get_all_level_actors() if a.get_class().get_name() == "CoHLifeManager"][0]
old = [m.get_path_name() for m in lm.get_editor_property("car_meshes")]
new = []
for v, w in WEIGHTS.items():
    new += [eas.load_asset(KIT[v]["mesh"])] * w
lm.set_editor_property("car_meshes", new)
json.dump(dict(actor=lm.get_path_name(), before=old, after=[m.get_path_name() for m in new]),
          open(os.path.join(here, "traffic_report.json"), "w"), indent=1)
print("car meshes", len(old), "->", len(new))
if os.environ.get("CSLM_SAVE") == "1":
    print("saved", unreal.EditorLoadingAndSavingUtils.save_packages([lm.get_package()], False))

"""Step 12: place the rideable monorail train (C++ ARebornMonorail).

Puts the train on Monorail_Track with one stop at the Atlas Park station
(from monorail.json); it shuttles end to end, stopping there both ways, and
turns round at the tunnel portals (east toward Steel Canyon, south)."""
import json
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
mono = json.load(open(os.path.join(OUT, "monorail.json")))
track = find(label="Monorail_Track")
assert track, "run build_monorail.py first"
for a in find(label="Monorail_Train"):
    actors.destroy_actor(a)
D = ROOT + "/Monorail/"
t = actors.spawn_actor_from_class(unreal.RebornMonorail, unreal.Vector(0, 0, 0))
t.set_actor_label("Monorail_Train")
t.set_folder_path("AtlasReborn/Monorail")
t.set_editor_property("track", track[0])
t.set_editor_property("car_mesh", el.load_asset(D + "SM_Mono_Car"))
t.set_editor_property("nose_mesh", el.load_asset(D + "SM_Mono_CarNose"))
t.set_editor_property("door_mesh", el.load_asset(D + "SM_Mono_Door"))
stop = unreal.RebornMonorailStop()
stop.set_editor_property("name", "Atlas Park")
c = mono["station"]["center"]
stop.set_editor_property("location", unreal.Vector(c[0] * 100, c[1] * 100, c[2] * 100))
t.set_editor_property("stops", [stop])
actors.set_actor_transform(t, t.get_actor_transform())   # reruns construction: cars appear
print("train placed; line", mono["length_m"], "m")

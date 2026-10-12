"""Step 10: bring the streets to life with ACoHLifeManager (project C++).

Reads reborn_life.json (make_life.py, built from the ZoneGraph lanes): cars
drive the car lanes (Vehicle Variety Pack meshes, headlights at night,
parked cars by the curbs), civilians walk the sidewalk lanes (UE mannequins
for now; MetaHuman crowd later). Fewer of both at night via MPC_Reborn.Night.
No monorail, blimp or drones yet: the new monorail is its own step."""
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
for a in find(label="Reborn_Life"):
    actors.destroy_actor(a)
m = actors.spawn_actor_from_class(unreal.CoHLifeManager, unreal.Vector(0, 0, 0))
m.set_actor_label("Reborn_Life")
m.set_folder_path("AtlasReborn/Life")
fp = unreal.FilePath()
fp.set_editor_property("file_path", os.path.join(OUT, "reborn_life.json").replace("\\", "/"))
m.set_editor_property("life_json", fp)
V = "/Game/CoH/Vehicles/VVP/SM_"
cars = [el.load_asset(V + n) for n in ["Hatchback_Navy", "Hatchback_Red", "Hatchback_Silver", "Hatchback_Taxi",
                                      "Hatchback_White", "Pickup_Black", "Pickup_Green", "Pickup_Silver", "Pickup_White",
                                      "SUV_Black", "SUV_Navy", "SUV_Silver", "SUV_White", "SportsCar_Black",
                                      "SportsCar_Red", "SportsCar_Silver", "Truck_Box_Silver", "Truck_Box_White"]]
m.set_editor_property("car_meshes", [c for c in cars if c])
C = "/Game/Characters/Mannequins/"
m.set_editor_property("civilian_meshes", [el.load_asset(C + "Meshes/SKM_Manny_Simple"), el.load_asset(C + "Meshes/SKM_Quinn_Simple")])
m.set_editor_property("walk_anim", el.load_asset(C + "Anims/Unarmed/Walk/MF_Unarmed_Walk_Fwd"))
m.set_editor_property("idle_anim", el.load_asset(C + "Anims/Unarmed/MM_Idle"))
m.set_editor_property("run_anim", el.load_asset(C + "Anims/Unarmed/Jog/MF_Unarmed_Jog_Fwd"))
m.set_editor_property("night_collection", el.load_asset(ROOT + "/Materials/MPC_Reborn"))
for k, v in [("max_cars", 70), ("max_civilians", 160), ("active_radius", 15000.0), ("parked_cars_day", 20),
             ("parked_cars_night", 40), ("headlight_cars", 10)]:
    m.set_editor_property(k, v)
print("life manager placed", len(cars), "car meshes")

"""Step 14: zone travel by monorail.

1. Creates the ride level /Game/AtlasReborn/Transit/L_MonorailRide: a train
   car (the monorail kit), PlayerStarts on its floor, dim tunnel lighting and
   an ARebornRideDirector that scrolls the tunnel past the windows and moves
   the group on to the destination after the ride. It is also the project's
   seamless-travel transition map (Config/DefaultEngine.ini), so the zone
   loads while the ride plays.
2. In AtlasPark_Reborn: the train gets its destinations and the ride map, and
   PlayerStarts tagged MonorailArrival are placed inside the train where it
   stands at the station (bStartAtFirstStop), so arrivals step off there.
Run with AtlasPark_Reborn open; it reopens it at the end."""
import json
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
mono = json.load(open(os.path.join(OUT, "monorail.json")))
RIDE = ROOT + "/Transit/L_MonorailRide"
MAT = ROOT + "/Materials"

# ------------------------------------------------------------ Atlas Park side
train = find(label="Monorail_Train")[0]
dest = []
for name, path in [("Atlas Park (round trip)", MAP), ("Steel Canyon", None), ("King's Row", None),
                   ("Skyway City", None), ("Galaxy City", None)]:
    d = unreal.RebornDestination()
    d.set_editor_property("name", name)
    if path:
        d.set_editor_property("map", el.load_asset(path))
    dest.append(d)
train.set_editor_property("destinations", dest)
for a in find(cls=unreal.PlayerStart):
    if str(a.get_editor_property("player_start_tag")) == "MonorailArrival":
        actors.destroy_actor(a)
# the train waits at the station centre; spread arrivals over the 3 car floors
st = mono["station"]
cx, cy, cz = st["center"]
yaw = math.radians(st["yaw"])
fx, fy = math.cos(yaw), math.sin(yaw)
for car in (-15.5, 0.0, 15.5):
    for k, along in enumerate((-4.5, 0.0, 4.5)):
        x, y = cx + fx * (car + along), cy + fy * (car + along)
        ps = actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(x * 100, y * 100, cz * 100 + 200))
        ps.set_actor_rotation(unreal.Rotator(pitch=0, yaw=st["yaw"] + 90, roll=0), False)
        ps.set_editor_property("player_start_tag", "MonorailArrival")
        ps.set_folder_path("AtlasReborn/Monorail/Arrivals")
unreal.EditorLoadingAndSavingUtils.save_map(world(), MAP)

# tunnel lamp: always lit (the station lamps follow Night instead)
tl = MAT + "/M_Reborn_TunnelLight"
if not el.does_asset_exist(tl):
    m = new_material(tl)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    c = expr(m, unreal.MaterialExpressionConstant3Vector, -300, 0, constant=unreal.LinearColor(30, 26, 18, 1))
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    el.save_loaded_asset(m)

# ------------------------------------------------------------ ride level
if not el.does_asset_exist(RIDE):
    unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    unreal.EditorLoadingAndSavingUtils.save_map(world(), RIDE)
unreal.EditorLoadingAndSavingUtils.load_map(RIDE)
for a in actors.get_all_level_actors():
    actors.destroy_actor(a)
car = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
car.static_mesh_component.set_static_mesh(el.load_asset(ROOT + "/Monorail/SM_Mono_Car"))
car.set_actor_label("Ride_Car")
for x in (-450.0, 0.0, 450.0):
    ps = actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(x, 0, 200))
    ps.set_actor_rotation(unreal.Rotator(pitch=0, yaw=90, roll=0), False)
d = actors.spawn_actor_from_class(unreal.RebornRideDirector, unreal.Vector(0, 0, 0))
d.set_actor_label("Ride_Director")
d.set_editor_property("wall_mesh", el.load_asset("/Engine/BasicShapes/Cube"))
d.set_editor_property("wall_material", el.load_asset(MAT + "/MI_Mono_Concrete"))
d.set_editor_property("light_material", el.load_asset(MAT + "/M_Reborn_TunnelLight"))
sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 500))
sky.get_component_by_class(unreal.SkyLightComponent).set_editor_property("intensity", 0.4)
lamp = actors.spawn_actor_from_class(unreal.PointLight, unreal.Vector(0, 0, 260))
lc = lamp.get_component_by_class(unreal.PointLightComponent)
lc.set_editor_property("intensity", 4000.0)
lc.set_editor_property("attenuation_radius", 1200.0)
ppv = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
ppv.set_editor_property("unbound", True)
s = ppv.get_editor_property("settings")
s.set_editor_property("override_auto_exposure_min_brightness", True)
s.set_editor_property("auto_exposure_min_brightness", 0.0)
s.set_editor_property("override_auto_exposure_max_brightness", True)
s.set_editor_property("auto_exposure_max_brightness", 3.0)
ppv.set_editor_property("settings", s)
unreal.EditorLoadingAndSavingUtils.save_map(world(), RIDE)
print("ride level built")
# drop every Python reference into the ride level before leaving it, or the
# editor finds the old world still referenced and stops with a fatal error
del car, d, sky, lamp, lc, ppv, s, ps
import gc
gc.collect()
unreal.SystemLibrary.collect_garbage()
unreal.EditorLoadingAndSavingUtils.load_map(MAP)
train = find(label="Monorail_Train")[0]
train.set_editor_property("ride_map", el.load_asset(RIDE))
unreal.EditorLoadingAndSavingUtils.save_map(world(), MAP)
print("destinations", len(dest), "arrival starts placed")

"""Step 11b: monorail support pillars, kept out of the streets.

Places the pillars planned by plan_pillars.py (monorail.json "pillars") as
ordinary actors in AtlasReborn/Monorail/Pillars, so any of them can be nudged
by hand. A pillar right under the beam is SM_Mono_Pillar; where the track runs
down a street the pillar stands on the sidewalk and a concrete arm reaches out
under the beam. Also takes the old every-30 m pillar branch out of
PCG_Reborn_Monorail (beam only now) and regenerates it."""
import json
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
mono = json.load(open(os.path.join(OUT, "monorail.json")))
assert "pillars" in mono, "run plan_pillars.py first"
H = mono["height"]
FOLDER = "AtlasReborn/Monorail/Pillars"
pillar = el.load_asset(ROOT + "/Monorail/SM_Mono_Pillar")
cube = el.load_asset("/Engine/BasicShapes/Cube")
concrete = el.load_asset(ROOT + "/Materials/MI_Mono_Concrete")

# PCG: beam only
g = el.load_asset(ROOT + "/PCG/PCG_Reborn_Monorail")
for n in list(g.nodes):
    s = n.get_settings()
    if isinstance(s, (unreal.PCGSplineSamplerSettings, unreal.PCGStaticMeshSpawnerSettings)):
        g.remove_node(n)
el.save_loaded_asset(g)
vol = find(label="PCG_Reborn_Monorail")[0]
vol.get_component_by_class(unreal.PCGComponent).generate(True)

for a in actors.get_all_level_actors():
    if str(a.get_folder_path()) == FOLDER:
        actors.destroy_actor(a)

track = mono["track"]


def tangent_yaw(x, y):
    i = min(range(len(track) - 1), key=lambda k: (track[k][0] - x) ** 2 + (track[k][1] - y) ** 2)
    return math.degrees(math.atan2(track[i + 1][1] - track[i][1], track[i + 1][0] - track[i][0]))


arms = 0
for k, p in enumerate(mono["pillars"]):
    fx, fy = p["foot"][:2]
    bx, by = p["beam"]
    yaw = math.degrees(math.atan2(by - fy, bx - fx)) if p["arm_m"] > 0 else tangent_yaw(bx, by)
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(fx * 100, fy * 100, H * 100),
                                      unreal.Rotator(pitch=0, yaw=yaw, roll=0))
    a.static_mesh_component.set_static_mesh(pillar)
    a.set_actor_label("Monorail_Pillar_%02d" % k)
    a.set_folder_path(FOLDER)
    if p["arm_m"] > 0:
        # arm: 1.6 m wide, 1.4 m deep, top at the beam underside (1.8 m below its top)
        L = p["arm_m"] + 1.3
        mid = unreal.Vector((fx + bx) * 50, (fy + by) * 50, (H - 1.8 - 0.7) * 100)
        arm = actors.spawn_actor_from_class(unreal.StaticMeshActor, mid, unreal.Rotator(pitch=0, yaw=yaw, roll=0))
        arm.static_mesh_component.set_static_mesh(cube)
        arm.static_mesh_component.set_material(0, concrete)
        arm.set_actor_scale3d(unreal.Vector(L, 1.6, 1.4))
        arm.set_actor_label("Monorail_PillarArm_%02d" % k)
        arm.set_folder_path(FOLDER)
        arms += 1
unreal.EditorLoadingAndSavingUtils.save_map(world(), MAP)
print("pillars", len(mono["pillars"]), "with arms", arms)

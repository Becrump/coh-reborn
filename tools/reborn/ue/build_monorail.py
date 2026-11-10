"""Step 11: monorail track, station and line-end portals (the train is the
C++ ARebornMonorail, placed by place_train.py once the module is built).

Imports the Blender kit (blender/monorail_kit.py FBX, with UCX collision),
gives it materials, makes the track spline from monorail.json
(plan_monorail.py), and runs PCG_Reborn_Monorail: the guideway beam as
spline meshes along the track. The pillars are placed by place_pillars.py
(they reach 40 m down, so the ground's height under them does not matter)."""
import json
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa
import build_pcg as P  # noqa

require_map()
mono = json.load(open(os.path.join(OUT, "monorail.json")))
KIT = os.path.join(OUT, "monorail")
DST = ROOT + "/Monorail"
MAT = ROOT + "/Materials"


def import_fbx(name):
    task = unreal.AssetImportTask()
    task.filename = os.path.join(KIT, name + ".fbx")
    task.destination_path = DST
    task.destination_name = name
    task.replace_existing = True
    task.automated = True
    task.save = True
    tools.import_asset_tasks([task])
    return el.load_asset(DST + "/" + name)


def glass_material():
    path = MAT + "/M_Reborn_Glass"
    if el.does_asset_exist(path):
        return el.load_asset(path)
    m = new_material(path)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE)
    c = expr(m, unreal.MaterialExpressionConstant3Vector, -400, 0, constant=unreal.LinearColor(0.05, 0.08, 0.1, 1))
    o = expr(m, unreal.MaterialExpressionConstant, -400, 150, r=0.35)
    r = expr(m, unreal.MaterialExpressionConstant, -400, 250, r=0.05)
    me = expr(m, unreal.MaterialExpressionConstant, -400, 350, r=0.8)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(o, "", unreal.MaterialProperty.MP_OPACITY)
    mel.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(me, "", unreal.MaterialProperty.MP_SPECULAR)
    mel.recompile_material(m)
    el.save_loaded_asset(m)
    return m


def paint(name, color):
    parent = el.load_asset(MAT + "/M_Reborn_Paint")
    path = MAT + "/" + name
    m = el.load_asset(path) or tools.create_asset(name, MAT, unreal.MaterialInstanceConstant,
                                                   unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(m, parent)
    mel.set_material_instance_vector_parameter_value(m, "Color", unreal.LinearColor(*color, 1))
    el.save_loaded_asset(m)
    return m


MATS = {
    "Body": paint("MI_Mono_Body", (0.82, 0.84, 0.86)),
    "Stripe": paint("MI_Mono_Stripe", (0.02, 0.18, 0.55)),
    "Glass": glass_material(),
    "Dark": paint("MI_Mono_Dark", (0.03, 0.035, 0.04)),
    "Floor": paint("MI_Mono_Floor", (0.18, 0.18, 0.2)),
    "Metal": paint("MI_Mono_Metal", (0.55, 0.56, 0.58)),
    "Concrete": paint("MI_Mono_Concrete", (0.45, 0.44, 0.42)),
    "Light": el.load_asset(MAT + "/M_Reborn_LampGlow"),
}
meshes = {}
for n in ["SM_Mono_Beam", "SM_Mono_Pillar", "SM_Mono_Car", "SM_Mono_CarNose", "SM_Mono_Door", "SM_Mono_Station"]:
    m = import_fbx(n)
    assert m, n
    for i, sm in enumerate(m.static_materials):
        slot = str(sm.material_slot_name)
        key = next((k for k in MATS if slot.startswith(k)), None)
        if key:
            m.set_material(i, MATS[key])
    el.save_loaded_asset(m)
    meshes[n] = m
    print("imported", n, "materials", [str(s.material_slot_name) for s in m.static_materials])

# ------------------------------------------------------------ track spline
zone_cls = el.load_blueprint_class(ROOT + "/Layout/BP_RebornZone")
for a in actors.get_all_level_actors():
    if str(a.get_folder_path()).startswith("AtlasReborn/Monorail"):
        actors.destroy_actor(a)
tr = mono["track"]
track = actors.spawn_actor_from_class(zone_cls, unreal.Vector(tr[0][0] * 100, tr[0][1] * 100, tr[0][2] * 100))
track.set_actor_label("Monorail_Track")
track.set_folder_path("AtlasReborn/Monorail")
track.set_editor_property("tags", ["RebornMonorail"])
s = track.get_component_by_class(unreal.SplineComponent)
s.clear_spline_points(False)
for x, y, z in tr:
    s.add_spline_point(unreal.Vector(x * 100, y * 100, z * 100), unreal.SplineCoordinateSpace.WORLD, False)
s.set_closed_loop(False, True)
mark_spline_edited(s)

# ------------------------------------------------------------ station, portals
st = mono["station"]
cx, cy, cz = st["center"]
sa = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(cx * 100, cy * 100, cz * 100),
                                   unreal.Rotator(yaw=st["yaw"]))
sa.set_actor_rotation(unreal.Rotator(pitch=0, yaw=st["yaw"], roll=0), False)
sa.set_actor_label("Monorail_Station_AtlasPark")
sa.set_folder_path("AtlasReborn/Monorail")
sa.static_mesh_component.set_static_mesh(meshes["SM_Mono_Station"])
cube = el.load_asset("/Engine/BasicShapes/Cube")
for p in mono["portals"]:
    x, y, z = p["at"]
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(x * 100, y * 100, z * 100 + 200))
    a.set_actor_rotation(unreal.Rotator(pitch=0, yaw=p["yaw"], roll=0), False)
    a.set_actor_label("Monorail_Portal_" + p["name"].replace(" ", ""))
    a.set_folder_path("AtlasReborn/Monorail")
    a.static_mesh_component.set_static_mesh(cube)
    a.static_mesh_component.set_material(0, MATS["Dark"])
    a.set_actor_scale3d(unreal.Vector(0.6, 6.0, 7.0))   # a dark tunnel mouth the train runs into
    a.static_mesh_component.set_collision_profile_name("NoCollision")

# ------------------------------------------------------------ PCG: beam
g = P.new_graph("PCG_Reborn_Monorail")
gs_n, gs = P.node(g, unreal.PCGGetSplineSettings, 0, 0)
P.by_tag(gs, "RebornMonorail")
n, sset = P.node(g, unreal.PCGSpawnSplineMeshSettings, 300, 0)
d = sset.get_editor_property("spline_mesh_descriptor")
d.set_editor_property("static_mesh", meshes["SM_Mono_Beam"])
sset.set_editor_property("spline_mesh_descriptor", d)
pp = sset.get_editor_property("spline_mesh_params")
pp.set_editor_property("scale_mesh_to_bounds", False)
sset.set_editor_property("spline_mesh_params", pp)
P.edge(g, gs_n, "Out", n, "In")
P.edge(g, n, "Out", g.get_output_node(), "Out")
# pillars: place_pillars.py (planned off the streets by plan_pillars.py)
comp = P.volume("PCG_Reborn_Monorail", g)
comp.generate(True)
print("monorail track", len(tr), "points,", mono["length_m"], "m; station at", [round(v) for v in st["center"]])

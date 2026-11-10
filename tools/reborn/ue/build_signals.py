"""Step 13: traffic signals at the junctions (signals.json from make_life.py).

All signal poles are one instanced mesh (ACoHInstances); each instance
carries its junction's phase offset and its direction group as custom data.
M_Reborn_Signal lights the red/amber/green lamp from MPC_Reborn.SignalClock,
which the life manager writes every frame from the server clock - the same
clock it uses to stop cars at red - so lamps and traffic always agree."""
import json
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
heads = json.load(open(os.path.join(OUT, "signals.json")))
MAT = ROOT + "/Materials"
mpc = el.load_asset(MAT + "/MPC_Reborn")
ps = list(mpc.get_editor_property("scalar_parameters"))
if not any(str(p.get_editor_property("parameter_name")) == "SignalClock" for p in ps):
    p = unreal.CollectionScalarParameter()
    p.set_editor_property("parameter_name", "SignalClock")
    ps.append(p)
    mpc.set_editor_property("scalar_parameters", ps)
    el.save_loaded_asset(mpc)

# ------------------------------------------------------------ lamp material
path = MAT + "/M_Reborn_Signal"
if el.does_asset_exist(path):
    el.delete_asset(path)
m = new_material(path)
m.set_editor_property("used_with_instanced_static_meshes", True)
clk = expr(m, unreal.MaterialExpressionCollectionParameter, -1800, 0, collection=mpc, parameter_name="SignalClock")
off = expr(m, unreal.MaterialExpressionPerInstanceCustomData, -1800, 120, data_index=0)
grp = expr(m, unreal.MaterialExpressionPerInstanceCustomData, -1800, 240, data_index=1)
gm = expr(m, unreal.MaterialExpressionMultiply, -1600, 240, const_b=20.0)
link(grp, "", gm, "A")
a1 = expr(m, unreal.MaterialExpressionAdd, -1450, 60)
link(clk, "", a1, "A")
link(off, "", a1, "B")
a2 = expr(m, unreal.MaterialExpressionAdd, -1300, 120)
link(a1, "", a2, "A")
link(gm, "", a2, "B")
t = expr(m, unreal.MaterialExpressionFmod, -1150, 120)
link(a2, "", t, "A")
c40 = expr(m, unreal.MaterialExpressionConstant, -1300, 260, r=40.0)
link(c40, "", t, "B")
# green while T < 17, amber while T < 20, red after
s17 = expr(m, unreal.MaterialExpressionSubtract, -1000, 0, const_a=17.0)
link(t, "", s17, "B")
g = expr(m, unreal.MaterialExpressionSaturate, -700, 0)
sg = expr(m, unreal.MaterialExpressionSign, -850, 0)
link(s17, "", sg, "")
link(sg, "", g, "")
s20 = expr(m, unreal.MaterialExpressionSubtract, -1000, 200, const_a=20.0)
link(t, "", s20, "B")
sa = expr(m, unreal.MaterialExpressionSign, -850, 200)
link(s20, "", sa, "")
ga = expr(m, unreal.MaterialExpressionSaturate, -700, 200)
link(sa, "", ga, "")
amber = expr(m, unreal.MaterialExpressionSubtract, -550, 200)
link(ga, "", amber, "A")
link(g, "", amber, "B")
red = expr(m, unreal.MaterialExpressionOneMinus, -550, 400)
link(ga, "", red, "")
ra = expr(m, unreal.MaterialExpressionAppendVector, -400, 300)
link(red, "", ra, "A")
link(amber, "", ra, "B")
rag = expr(m, unreal.MaterialExpressionAppendVector, -250, 200)
link(ra, "", rag, "A")
link(g, "", rag, "B")
mask = expr(m, unreal.MaterialExpressionVectorParameter, -400, 500, parameter_name="LampMask",
            default_value=unreal.LinearColor(1, 0, 0, 0))
mm = expr(m, unreal.MaterialExpressionComponentMask, -250, 500, r=True, g=True, b=True, a=False)
link(mask, "", mm, "")
on = expr(m, unreal.MaterialExpressionDotProduct, -100, 300)
link(rag, "", on, "A")
link(mm, "", on, "B")
col = expr(m, unreal.MaterialExpressionVectorParameter, -100, 500, parameter_name="LampColor",
           default_value=unreal.LinearColor(1, 0.05, 0.02, 1))
glow = expr(m, unreal.MaterialExpressionMultiply, 100, 300, const_b=60.0)
lit = expr(m, unreal.MaterialExpressionMultiply, 100, 420)
link(on, "", lit, "A")
link(col, "", lit, "B")
link(lit, "", glow, "A")
dim = expr(m, unreal.MaterialExpressionMultiply, 100, 560, const_b=0.15)
link(col, "", dim, "A")
mel.connect_material_property(glow, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.connect_material_property(dim, "", unreal.MaterialProperty.MP_BASE_COLOR)
mel.recompile_material(m)
el.save_loaded_asset(m)


def lamp_mi(name, mask_rgb, color):
    p = MAT + "/" + name
    mi = el.load_asset(p) or tools.create_asset(name, MAT, unreal.MaterialInstanceConstant,
                                                 unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, m)
    mel.set_material_instance_vector_parameter_value(mi, "LampMask", unreal.LinearColor(*mask_rgb, 0))
    mel.set_material_instance_vector_parameter_value(mi, "LampColor", unreal.LinearColor(*color, 1))
    el.save_loaded_asset(mi)
    return mi


lamps = {"LampRed": lamp_mi("MI_Signal_Red", (1, 0, 0), (1.0, 0.04, 0.02)),
         "LampAmber": lamp_mi("MI_Signal_Amber", (0, 1, 0), (1.0, 0.45, 0.02)),
         "LampGreen": lamp_mi("MI_Signal_Green", (0, 0, 1), (0.05, 1.0, 0.45))}
dark = el.load_asset(MAT + "/MI_Mono_Dark")

# ------------------------------------------------------------ mesh
task = unreal.AssetImportTask()
task.filename = os.path.join(OUT, "street", "SM_Reborn_TrafficSignal.fbx")
task.destination_path = ROOT + "/Roads"
task.destination_name = "SM_Reborn_TrafficSignal"
task.replace_existing = True
task.automated = True
task.save = True
tools.import_asset_tasks([task])
mesh = el.load_asset(ROOT + "/Roads/SM_Reborn_TrafficSignal")
for i, sm in enumerate(mesh.static_materials):
    slot = str(sm.material_slot_name)
    mesh.set_material(i, lamps.get(slot, dark))
el.save_loaded_asset(mesh)

# ------------------------------------------------------------ placement
for a in find(label="Reborn_TrafficSignals"):
    actors.destroy_actor(a)
inst = actors.spawn_actor_from_class(unreal.CoHInstances, unreal.Vector(0, 0, 0))
inst.set_actor_label("Reborn_TrafficSignals")
inst.set_folder_path("AtlasReborn/Roads")
hism = inst.get_editor_property("instances")
hism.set_editor_property("num_custom_data_floats", 2)
xf = [unreal.Transform(location=unreal.Vector(h["p"][0] * 100, h["p"][1] * 100, h["p"][2] * 100),
                       rotation=unreal.Rotator(yaw=h["yaw"])) for h in heads]
inst.set_instances(mesh, xf)
hism.set_editor_property("num_custom_data_floats", 2)
for i, h in enumerate(heads):
    hism.set_custom_data_value(i, 0, h["offset"], False)
    hism.set_custom_data_value(i, 1, float(h["group"]), i == len(heads) - 1)
life = find(label="Reborn_Life")
if life:
    try:
        life[0].set_editor_property("signal_collection", mpc)
    except Exception as e:
        print("life manager not rebuilt yet:", e)
print("traffic signals", len(heads))

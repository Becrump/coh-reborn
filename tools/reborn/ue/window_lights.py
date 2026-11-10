"""Tie City Sample window lights to day and night.

City Sample's M_Window has a 'LightsOff' parameter that defaults to 0, so
every window glows in daylight. This adds MPC_Reborn.Night: LightsOff becomes
max(LightsOff, 1 - Night), so windows are dark by day and light up (as lit
rooms, via the interior cubemaps) when Night goes to 1. The day/night
sequence only has to animate MPC_Reborn.Night. Safe to run twice."""
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

MPC = ROOT + "/Materials/MPC_Reborn"
mpc = el.load_asset(MPC)
if not mpc:
    mpc = tools.create_asset("MPC_Reborn", ROOT + "/Materials", unreal.MaterialParameterCollection,
                             unreal.MaterialParameterCollectionFactoryNew())
    p = unreal.CollectionScalarParameter()
    p.set_editor_property("parameter_name", "Night")
    p.set_editor_property("default_value", 0.0)
    mpc.set_editor_property("scalar_parameters", [p])
    el.save_loaded_asset(mpc)
m = el.load_asset("/Game/CitySampleBuildings/Material/Window/M_Window")
exprs = mel.get_material_expressions(m)
if any(isinstance(e, unreal.MaterialExpressionCollectionParameter) and e.get_editor_property("collection") == mpc
       for e in exprs):
    print("already wired")
else:
    lo = [e for e in exprs if isinstance(e, unreal.MaterialExpressionScalarParameter)
          and str(e.get_editor_property("parameter_name")) == "LightsOff"]
    assert len(lo) == 1, lo
    lo = lo[0]
    uses = []
    for e in exprs:
        if e == lo:
            continue
        names = mel.get_material_expression_input_names(e)
        ins = mel.get_inputs_for_material_expression(m, e)
        for name, src in zip(names, ins):
            if src == lo:
                uses.append((e, name))
    x, y = mel.get_material_expression_node_position(lo)
    cp = mel.create_material_expression(m, unreal.MaterialExpressionCollectionParameter, x, y + 120)
    cp.set_editor_property("collection", mpc)
    cp.set_editor_property("parameter_name", "Night")
    om = mel.create_material_expression(m, unreal.MaterialExpressionOneMinus, x + 200, y + 120)
    mx = mel.create_material_expression(m, unreal.MaterialExpressionMax, x + 400, y)
    assert mel.connect_material_expressions(cp, "", om, "")
    assert mel.connect_material_expressions(lo, "", mx, "A")
    assert mel.connect_material_expressions(om, "", mx, "B")
    for e, name in uses:
        assert mel.connect_material_expressions(mx, "", e, name), (e, name)
    mel.recompile_material(m)
    el.save_loaded_asset(m)
    print("wired LightsOff to MPC_Reborn.Night for", len(uses), "inputs")

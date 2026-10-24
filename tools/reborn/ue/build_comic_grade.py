"""Step: comic-book colour grading in M_CoH_Comic, and the vibrant preset.

Rebuilds M_CoH_Comic from coh2unreal/unreal/setup_comic.py with two more
parameters, applied after its saturation step:
  Contrast   contrast about mid grey (1 = none)
  WarmCool   comic colouring: lit areas warmer, shadows cooler (0 = none)
Both default to neutral, so MI_CoH_Comic (light) and MI_CoH_Comic_Strong
look as before. Then makes MI_CoH_Comic_Vibrant (the F10 "vibrant comic").
Safe to run again.
"""
import os

import unreal

SRC = r"C:\Users\rtcru\ClaudeProjects\coh-reborn\coh2unreal\unreal\setup_comic.py"
VIBRANT = "/Game/CoH/Materials/MI_CoH_Comic_Vibrant"
VIBRANT_VALUES = {
    "Saturation": 1.35, "Contrast": 1.22, "WarmCool": 1.2, "Brightness": 0.98,
    "PaintRadius": 2.0, "Bands": 5.0, "BandStrength": 0.10,
    "LineThickness": 0.7, "LineStrength": 0.65, "DepthSensitivity": 4.0,
    "NormalSensitivity": 0.6, "InkDarkness": 0.32, "LineFadeDistance": 30000.0,
}
GRADE = r"""
// 3b. comic colouring: contrast about mid grey, warm lights, cool shadows
paint = max(0, (paint - 0.45) * Contrast + 0.45);
float tl = saturate((dot(paint, lw) - 0.15) / 0.6);
float3 warm = float3(1 + 0.07 * WarmCool, 1 + 0.02 * WarmCool, 1 - 0.06 * WarmCool);
float3 cool = float3(1 - 0.05 * WarmCool, 1.0, 1 + 0.08 * WarmCool);
paint *= lerp(cool, warm, tl);

// 4. ink lines"""

src = open(SRC, encoding="utf-8").read()
src = src[:src.index("\nmi = build()")]          # definitions only, no run
ns = {"__name__": "setup_comic", "__file__": SRC}
exec(compile(src, SRC, "exec"), ns)
assert "// 4. ink lines" in ns["HLSL"]
ns["HLSL"] = ns["HLSL"].replace("\n// 4. ink lines", GRADE, 1)
ns["PARAMS"]["Contrast"] = 1.0
ns["PARAMS"]["WarmCool"] = 0.0
mi_light = ns["build"]()              # rebuilds M_CoH_Comic in place, keeps MI_CoH_Comic's values

mel = unreal.MaterialEditingLibrary
el = unreal.EditorAssetLibrary
if el.does_asset_exist(VIBRANT):
    v = unreal.load_asset(VIBRANT)
else:
    f, n = VIBRANT.rsplit("/", 1)
    v = unreal.AssetToolsHelpers.get_asset_tools().create_asset(n, f, unreal.MaterialInstanceConstant,
                                                                 unreal.MaterialInstanceConstantFactoryNew())
mel.set_material_instance_parent(v, unreal.load_asset(ns["MAT"]))
for k, val in VIBRANT_VALUES.items():
    mel.set_material_instance_scalar_parameter_value(v, k, val)
mel.update_material_instance(v)
el.save_loaded_asset(v, False)
print("comic grading built; vibrant", VIBRANT_VALUES["Saturation"], VIBRANT_VALUES["Contrast"], VIBRANT_VALUES["WarmCool"])

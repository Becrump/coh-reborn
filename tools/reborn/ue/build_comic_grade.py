"""Step: comic-book colour grading in M_CoH_Comic, and the vibrant preset.

Rebuilds M_CoH_Comic from coh2unreal/unreal/setup_comic.py with two more
parameters, applied after its saturation step:
  Contrast   contrast about mid grey (1 = none)
  WarmCool   comic colouring: lit areas warmer, shadows cooler (0 = none)
  ShadowSat  colour kept in shade (1 = all): the blue sky fill in building
             shadows, pushed by the saturation step, read as blue patches
Both default to neutral, so MI_CoH_Comic (light) and MI_CoH_Comic_Strong
look as before. Then makes MI_CoH_Comic_Vibrant (the F10 "vibrant comic").
Safe to run again.
"""
import os

import unreal

SRC = r"C:\Users\rtcru\ClaudeProjects\coh-reborn\coh2unreal\unreal\setup_comic.py"
VIBRANT = "/Game/CoH/Materials/MI_CoH_Comic_Vibrant"
VIBRANT_VALUES = {
    "Saturation": 1.35, "Contrast": 1.22, "WarmCool": 1.2, "ShadowSat": 0.35, "Brightness": 0.98,
    "PaintRadius": 2.0, "Bands": 5.0, "BandStrength": 0.10,
    "LineThickness": 0.7, "LineStrength": 0.65, "DepthSensitivity": 4.0,
    "NormalSensitivity": 0.6, "InkDarkness": 0.32, "LineFadeDistance": 30000.0,
}
GRADE = r"""
// 3b. comic colouring: contrast about mid grey, warm lights, cool shadows
paint = max(0, (paint - 0.45) * Contrast + 0.45);
float tl = saturate((dot(paint, lw) - 0.15) / 0.6);
// shade goes to a neutral dark tone: dark, blue-tinted pixels (sky fill in
// a shadow) lose most of their colour; lit grass, brick and sky keep theirs
float sl = dot(paint, lw);
float bm = max(paint.b, 1e-3);
float blue = saturate((paint.b - max(paint.r, paint.g)) / bm * 4.0);
float dark = 1.0 - saturate((sl - 0.08) / 0.30);
paint = max(0, lerp(paint, float3(sl, sl, sl), (1.0 - ShadowSat) * blue * dark));
float3 warm = float3(1 + 0.07 * WarmCool, 1 + 0.02 * WarmCool, 1 - 0.06 * WarmCool);
// only a slight cool shift in shade
float3 cool = float3(1 - 0.015 * WarmCool, 1.0, 1 + 0.025 * WarmCool);
// grey, unsaturated surfaces in shade (asphalt, concrete) stay neutral:
// only coloured shadows are cooled
float mx = max(paint.r, max(paint.g, paint.b));
float sat = (mx - min(paint.r, min(paint.g, paint.b))) / max(mx, 1e-3);
cool = lerp(float3(1, 1, 1), cool, saturate(sat * 4.0));
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
ns["PARAMS"]["ShadowSat"] = 1.0
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

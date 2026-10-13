"""Step 2: landscape material driven by surface.png (atlas_layout.py).

surface.png covers the landscape exactly: R asphalt, G mown lawn, B paving,
A sand/dirt; where all are zero the ground is wild grass (hills, woods).
Tiling textures come from packs already in the project (City Sample,
Procedural Building Generator); none come from the original game."""
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
L = layout()["landscape"]
gd = ROOT + "/Guide"
surf = import_texture(os.path.join(OUT, L["surface_png"]), gd, "T_Reborn_Surface", srgb=False,
                      compression=unreal.TextureCompressionSettings.TC_MASKS)
span = (L["verts"] - 1) * L["scale"][0]
TEX = {
    "wild": ("/Game/ProceduralBuildingGenerator/Landscape/Texture/T_LV_Soul_grass_D", 450.0, (0.95, 1.0, 0.9)),
    "lawn": ("/Game/ProceduralBuildingGenerator/Landscape/Texture/T_GroundGrass_D", 300.0, (1.0, 1.08, 0.95)),
    "sand": ("/Game/ProceduralBuildingGenerator/Landscape/Texture/T_LV_Soul_BaseDirt_D", 400.0, (1.0, 0.9, 0.68)),
    "pave": ("/Game/CitySampleBuildings/Textures/ConcreteDirty/T_ConcreteDirty_C", 350.0, (0.5, 0.5, 0.5)),
    "asph": ("/Game/CitySampleVehicles/Material/MaterialLayer/Textures/T_Concrete_03_C", 300.0, (0.3, 0.3, 0.32)),
}
ROUGH = {"wild": 0.95, "lawn": 0.9, "sand": 0.9, "pave": 0.8, "asph": 0.75}
mat = new_material(ROOT + "/Materials/M_Reborn_Ground")
wp = expr(mat, unreal.MaterialExpressionWorldPosition, -2200, 0)
xy = expr(mat, unreal.MaterialExpressionComponentMask, -2000, 0, r=True, g=True, b=False, a=False)
link(wp, "", xy, "")
org = expr(mat, unreal.MaterialExpressionConstant2Vector, -2000, 150, r=L["origin_cm"][0], g=L["origin_cm"][1])
sub = expr(mat, unreal.MaterialExpressionSubtract, -1800, 50)
link(xy, "", sub, "A")
link(org, "", sub, "B")
div = expr(mat, unreal.MaterialExpressionDivide, -1650, 50, const_b=span)
link(sub, "", div, "A")
smp = expr(mat, unreal.MaterialExpressionTextureSample, -1450, 50, texture=surf,
           sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
link(div, "", smp, "UVs")
layers, rough = {}, {}
y = -900
for k, (path, tile, tint) in TEX.items():
    t = el.load_asset(path)
    assert t, path
    d = expr(mat, unreal.MaterialExpressionDivide, -1650, y, const_b=tile)
    link(xy, "", d, "A")
    s = expr(mat, unreal.MaterialExpressionTextureSample, -1450, y, texture=t)
    link(d, "", s, "UVs")
    c = expr(mat, unreal.MaterialExpressionConstant3Vector, -1450, y + 180, constant=unreal.LinearColor(*tint, 1))
    m = expr(mat, unreal.MaterialExpressionMultiply, -1200, y)
    link(s, "RGB", m, "A")
    link(c, "", m, "B")
    layers[k] = m
    rough[k] = expr(mat, unreal.MaterialExpressionConstant, -1200, y + 120, r=ROUGH[k])
    y += 320
# large-scale variation so wide lawns and hills do not tile visibly
mdv = expr(mat, unreal.MaterialExpressionDivide, -1650, 900, const_b=5200.0)
link(xy, "", mdv, "A")
macro = expr(mat, unreal.MaterialExpressionTextureSample, -1450, 900, texture=el.load_asset(TEX["wild"][0]))
link(mdv, "", macro, "UVs")
mlerp = expr(mat, unreal.MaterialExpressionLinearInterpolate, -1200, 900, const_a=0.8, const_b=1.25)
link(macro, "G", mlerp, "Alpha")
chain = [("lawn", "G"), ("sand", "A"), ("pave", "B"), ("asph", "R")]
col, rgh = layers["wild"], rough["wild"]
x = -900
for k, ch in chain:
    lc = expr(mat, unreal.MaterialExpressionLinearInterpolate, x, 0)
    link(col, "", lc, "A")
    link(layers[k], "", lc, "B")
    link(smp, ch, lc, "Alpha")
    lr = expr(mat, unreal.MaterialExpressionLinearInterpolate, x, 300)
    link(rgh, "", lr, "A")
    link(rough[k], "", lr, "B")
    link(smp, ch, lr, "Alpha")
    col, rgh = lc, lr
    x += 180
fin = expr(mat, unreal.MaterialExpressionMultiply, x, 0)
link(col, "", fin, "A")
link(mlerp, "", fin, "B")
mel.connect_material_property(fin, "", unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(rgh, "", unreal.MaterialProperty.MP_ROUGHNESS)
mel.recompile_material(mat)
el.save_loaded_asset(mat)
land = find(cls=unreal.Landscape)[0]
land.set_editor_property("landscape_material", mat)
print("ground material set", mat.get_path_name())

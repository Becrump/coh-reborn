"""Step 1: shape the Reborn landscape from heightmap.png (atlas_layout.py).

Run in the editor with AtlasPark_Reborn open. Moves the landscape to the
layout origin (1 m per vertex) and writes the heights through a float render
target (R = raw 16-bit landscape height)."""
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
L = layout()["landscape"]
land = find(cls=unreal.Landscape)
assert len(land) == 1, land
land = land[0]
land.set_actor_location(unreal.Vector(*L["origin_cm"]), False, False)
land.set_actor_scale3d(unreal.Vector(*L["scale"]))
land.set_actor_label("Reborn_Landscape")
gd = ROOT + "/Guide"
tex = import_texture(os.path.join(OUT, L["height_png"]), gd, "T_Reborn_Height", srgb=False,
                     nearest=True, mips=False, compression=unreal.TextureCompressionSettings.TC_GRAYSCALE)
print("height texture", tex.blueprint_get_size_x(), tex.blueprint_get_size_y(), tex.get_editor_property("compression_settings"))
mat = new_material(gd + "/M_Reborn_HeightToRT")
mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
t = expr(mat, unreal.MaterialExpressionTextureSample, -600, 0)
t.set_editor_property("texture", tex)
t.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
m = expr(mat, unreal.MaterialExpressionMultiply, -300, 0)
m.set_editor_property("const_b", 65535.0)
link(t, "R", m, "A")
mel.connect_material_property(m, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.recompile_material(mat)
el.save_loaded_asset(mat)
n = L["verts"]
rt = unreal.RenderingLibrary.create_render_target2d(world(), n, n, unreal.TextureRenderTargetFormat.RTF_RGBA32F,
                                                    unreal.LinearColor(0, 0, 0, 0), False)
unreal.RenderingLibrary.clear_render_target2d(world(), rt, unreal.LinearColor(0, 0, 0, 0))
unreal.RenderingLibrary.draw_material_to_render_target(world(), rt, mat)
px = unreal.RenderingLibrary.read_render_target_raw_uv(world(), rt, 0.5, 0.5)
print("rt centre sample", px)
ok = land.landscape_import_heightmap_from_render_target(rt, False)
print("import", ok)
o, e = land.get_actor_bounds(False)
print("landscape bounds", o, e)

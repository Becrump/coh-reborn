"""Mild comic-book look as a post-process layer (toggle with Strength).

Run in the Unreal editor:
    py "<repo>/coh2unreal/unreal/setup_comic.py" [--off]

M_CoH_Comic (after tonemapping) does, in one pass:
  1. paint smoothing: a 4-quadrant Kuwahara filter flattens fine texture
     noise into painted areas while keeping edges sharp, so 2004 CoH
     textures and modern assets read as one style
  2. soft light banding: brightness snaps gently towards a few steps
  3. a little more saturation
  4. ink outlines from depth and surface-direction changes, thinning out
     with distance so the skyline doesn't turn black
MI_CoH_Comic holds the tunable values and is added to the level's
unbound post-process volume. Strength 0 = off, 1 = full.
"""
import sys

import unreal

MAT = "/Game/CoH/Materials/M_CoH_Comic"
MI = "/Game/CoH/Materials/MI_CoH_Comic"
PARAMS = {                      # name: default
    "Strength": 1.0,            # 0 off .. 1 full effect
    "PaintRadius": 0.0,         # Kuwahara radius in pixels (0 = no smoothing)
    "Bands": 5.0,               # light steps
    "BandStrength": 0.08,       # 0 smooth shading .. 1 hard cel bands
    "Saturation": 1.08,
    "LineThickness": 0.6,       # pixels
    "LineStrength": 0.55,
    "DepthSensitivity": 4.0,     # higher = more depth lines; above ~6 flat ground at a distance streaks
    "NormalSensitivity": 0.8,
    "LineFadeDistance": 30000.0,  # cm: lines fade out by this distance
    "Brightness": 1.05,         # lift: banding and ink darken the image a bit
    "InkDarkness": 0.35,        # line colour as a fraction of the colour under it
}

HLSL = r"""
float2 uv = GetDefaultSceneTextureUV(Parameters, 14);
float2 px = View.ViewSizeAndInvSize.zw;
float3 src = SceneTextureLookup(uv, 14, false).rgb + Dummy * 0;

// 1. Kuwahara: mean colour of the quadrant with the lowest variance
int r = (int)clamp(PaintRadius, 0, 4);
float3 paint = src;
if (r > 0)
{
    float best = 1e9;
    for (int q = 0; q < 4; q++)
    {
        float2 dir = float2((q & 1) ? 1 : -1, (q & 2) ? 1 : -1);
        float3 m = 0; float3 m2 = 0; float n = 0;
        for (int i = 0; i <= r; i++)
            for (int j = 0; j <= r; j++)
            {
                float3 c = SceneTextureLookup(uv + dir * float2(i, j) * px, 14, false).rgb;
                m += c; m2 += c * c; n += 1;
            }
        m /= n;
        float3 v = m2 / n - m * m;
        float var = v.r + v.g + v.b;
        if (var < best) { best = var; paint = m; }
    }
}

// 2. soft banding of brightness
float3 lw = float3(0.299, 0.587, 0.114);
float lum = max(dot(paint, lw), 1e-4);
float stepped = floor(lum * Bands + 0.5) / Bands;
paint *= lerp(1.0, stepped / lum, BandStrength);

// 3. saturation
float g = dot(paint, lw);
paint = lerp(g.xxx, paint, Saturation);

// 4. ink lines: depth discontinuities and normal creases
// After tonemapping, PostProcessInput0 is at output resolution while depth
// and normals stay at render resolution (lower whenever TSR/screen
// percentage upscales), so they need their own UV and texel size or the
// lines drift off the edges.
float2 uvG = GetDefaultSceneTextureUV(Parameters, 1);
float2 o = View.BufferSizeAndInvSize.zw * max(LineThickness, 0.5);
float d  = SceneTextureLookup(uvG, 1, false).r;
float dl = SceneTextureLookup(uvG + float2(-o.x, 0), 1, false).r;
float dr = SceneTextureLookup(uvG + float2( o.x, 0), 1, false).r;
float du = SceneTextureLookup(uvG + float2(0, -o.y), 1, false).r;
float dd = SceneTextureLookup(uvG + float2(0,  o.y), 1, false).r;
// Laplacian of 1/depth: zero on any flat surface (1/z is linear across a
// plane in screen space), so grazing floors don't streak; a real depth step
// still gives roughly its relative size
float depthEdge = abs(1 / max(dl, 1.0) + 1 / max(dr, 1.0) + 1 / max(du, 1.0)
                      + 1 / max(dd, 1.0) - 4 / max(d, 1.0)) * max(d, 1.0);
float3 n0 = SceneTextureLookup(uvG, 8, false).rgb;
float3 nl = SceneTextureLookup(uvG + float2(-o.x, 0), 8, false).rgb;
float3 nr = SceneTextureLookup(uvG + float2( o.x, 0), 8, false).rgb;
float3 nu = SceneTextureLookup(uvG + float2(0, -o.y), 8, false).rgb;
float3 nd = SceneTextureLookup(uvG + float2(0,  o.y), 8, false).rgb;
float normalEdge = (1 - dot(n0, nl)) + (1 - dot(n0, nr)) + (1 - dot(n0, nu)) + (1 - dot(n0, nd));
float edge = max(saturate((depthEdge * DepthSensitivity - 0.15) * 4),
                 saturate((normalEdge * NormalSensitivity - 0.35) * 3));
edge *= saturate(1 - d / LineFadeDistance) * LineStrength;
paint *= Brightness;
paint = lerp(paint, paint * InkDarkness, edge);

return lerp(src, paint, Strength);
"""

el = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def build():
    folder, name = MAT.rsplit("/", 1)
    if el.does_asset_exist(MAT):
        m = unreal.load_asset(MAT)
        mel.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, folder, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("material_domain",
                          unreal.MaterialDomain.MD_POST_PROCESS)
    m.set_editor_property(
        "blendable_location",
        unreal.BlendableLocation.BL_SCENE_COLOR_AFTER_TONEMAPPING)
    custom = mel.create_material_expression(
        m, unreal.MaterialExpressionCustom, -200, 0)
    custom.set_editor_property("code", HLSL)
    custom.set_editor_property("output_type",
                               unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    names = list(PARAMS) + ["Dummy"]
    inputs = []
    for n in names:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        inputs.append(ci)
    custom.set_editor_property("inputs", inputs)
    for i, (n, v) in enumerate(PARAMS.items()):
        p = mel.create_material_expression(
            m, unreal.MaterialExpressionScalarParameter, -600, i * 70)
        p.set_editor_property("parameter_name", n)
        p.set_editor_property("default_value", v)
        if not mel.connect_material_expressions(p, "", custom, n):
            raise RuntimeError("connect " + n)
    # scene texture nodes so the lookups above are allowed in this material
    st_sum = None
    for k, sid in enumerate((unreal.SceneTextureId.PPI_POST_PROCESS_INPUT0,
                             unreal.SceneTextureId.PPI_SCENE_DEPTH,
                             unreal.SceneTextureId.PPI_WORLD_NORMAL)):
        st = mel.create_material_expression(
            m, unreal.MaterialExpressionSceneTexture, -900, 800 + k * 120)
        st.set_editor_property("scene_texture_id", sid)
        mask = mel.create_material_expression(
            m, unreal.MaterialExpressionComponentMask, -750, 800 + k * 120)
        for c in ("r", "g", "b", "a"):
            mask.set_editor_property(c, c == "r")
        mel.connect_material_expressions(st, "Color", mask, "")
        if st_sum is None:
            st_sum = mask
        else:
            add = mel.create_material_expression(
                m, unreal.MaterialExpressionAdd, -600, 800 + k * 120)
            mel.connect_material_expressions(st_sum, "", add, "A")
            mel.connect_material_expressions(mask, "", add, "B")
            st_sum = add
    mel.connect_material_expressions(st_sum, "", custom, "Dummy")
    mel.connect_material_property(custom, "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    el.save_loaded_asset(m, False)
    if el.does_asset_exist(MI):
        mi = unreal.load_asset(MI)
    else:
        f, n = MI.rsplit("/", 1)
        mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            n, f, unreal.MaterialInstanceConstant,
            unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, m)
    mel.update_material_instance(mi)
    el.save_loaded_asset(mi, False)
    return mi


def attach(mi, on=True):
    asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vols = [a for a in asub.get_all_level_actors()
            if isinstance(a, unreal.PostProcessVolume)]
    if not vols:
        raise RuntimeError("no post-process volume in the level")
    v = vols[0]
    v.modify()
    s = v.get_editor_property("settings")
    wb = s.get_editor_property("weighted_blendables")
    arr = [b for b in wb.get_editor_property("array")
           if b.get_editor_property("object") != mi]
    b = unreal.WeightedBlendable()
    b.set_editor_property("weight", 1.0 if on else 0.0)
    b.set_editor_property("object", mi)
    arr.append(b)
    wb.set_editor_property("array", arr)
    s.set_editor_property("weighted_blendables", wb)
    v.set_editor_property("settings", s)
    unreal.log("[CoH comic] %s on %s" % ("enabled" if on else "disabled",
                                         v.get_actor_label()))


mi = build()
attach(mi, "--off" not in sys.argv)
unreal.EditorLevelLibrary.save_current_level()

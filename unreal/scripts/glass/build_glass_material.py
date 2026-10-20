"""Build /Game/GlassUpgrade/M_CoH_WindowGlass and its three option instances.

Run inside the open editor:  python unreal/scripts/ue_exec.py - < unreal/scripts/glass/build_glass_material.py
Re-running rebuilds the master graph in place (instances keep their paths).

Opaque, default-lit master (Nanite and Lumen friendly, no translucency):
  - WindowTexture: the original CoH window texture; frames/mullions stay as they were,
    panes are found by a luminance mask (MaskThreshold / MaskSoftness / MaskInvert).
  - Panes get a tinted, low-roughness, Fresnel-boosted glass response (A).
  - UseGrime switch: tiling noise breaks up roughness + darkened pane edges (B).
  - UseInterior switch: furnished parallax rooms from City Sample's room capture arrays
    (interior_room.hlsl): rooms span several panes, widths re-rolled per floor, theme per
    actor from Custom Primitive Data[0], random lit rooms at night via MPC_CoH.Night (C).
"""
import os
import unreal

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    r"C:\Users\rtcru\ClaudeProjects\coh-reborn-dm8n7k\unreal\scripts\glass"
FOLDER = "/Game/GlassUpgrade"
MASTER = "M_CoH_WindowGlass"
MEL = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
EAL = unreal.EditorAssetLibrary

DEF_WINDOW = "/Game/atlas_park/Textures/deco_skyscraper_02_window_01_b"
DEF_NORMAL = "/Engine/EngineMaterials/DefaultNormal"
DEF_GRIME = "/Engine/Functions/Engine_MaterialFunctions02/ExampleContent/Textures/LowResBlurredNoise"  # 64x64
DEF_GLOW = "/Engine/EngineResources/Black"
MPC = "/Game/CoH/Materials/MPC_CoH"


def get_or_create_material():
    path = "%s/%s" % (FOLDER, MASTER)
    if EAL.does_asset_exist(path):
        m = unreal.load_asset(path)
        for e in MEL.get_material_expressions(m):  # delete_all leaves stale nodes behind
            MEL.delete_material_expression(m, e)
        MEL.delete_all_material_expressions(m)
        return m
    return tools.create_asset(MASTER, FOLDER, unreal.Material, unreal.MaterialFactoryNew())


m = get_or_create_material()
m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
m.set_editor_property("two_sided", False)
m.set_editor_property("used_with_nanite", True)
m.set_editor_property("used_with_static_lighting", True)

_x = [0]


def node(cls, x, y, **props):
    e = MEL.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, a_out, b, b_in):
    if not MEL.connect_material_expressions(a, a_out, b, b_in):
        raise RuntimeError("connect failed %s.%s -> %s.%s" % (a.get_name(), a_out, b.get_name(), b_in))


def scalar(name, val, x, y, group="Glass"):
    return node(unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=val, group=group)


def vector(name, rgba, x, y, group="Glass"):
    return node(unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name,
                default_value=unreal.LinearColor(*rgba), group=group)


def tex(name, path, x, y, sampler=None, group="Textures"):
    e = node(unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=name,
             texture=unreal.load_asset(path), group=group)
    if sampler is not None:
        e.set_editor_property("sampler_type", sampler)
    return e


def custom(code, out_type, inputs, x, y, desc):
    e = node(unreal.MaterialExpressionCustom, x, y, code=code, output_type=out_type, description=desc)
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    e.set_editor_property("inputs", ins)
    return e


def mul(a, a_out, b, b_out, x, y):
    e = node(unreal.MaterialExpressionMultiply, x, y)
    link(a, a_out, e, "A")
    link(b, b_out, e, "B")
    return e


def lerp(a, a_out, b, b_out, alpha, alpha_out, x, y):
    e = node(unreal.MaterialExpressionLinearInterpolate, x, y)
    link(a, a_out, e, "A")
    link(b, b_out, e, "B")
    link(alpha, alpha_out, e, "Alpha")
    return e


def switch(name, default, true_e, true_out, false_e, false_out, x, y):
    e = node(unreal.MaterialExpressionStaticSwitchParameter, x, y, parameter_name=name, default_value=default,
             group="Options")
    link(true_e, true_out, e, "True")
    link(false_e, false_out, e, "False")
    return e


F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
F3 = unreal.CustomMaterialOutputType.CMOT_FLOAT3
F4 = unreal.CustomMaterialOutputType.CMOT_FLOAT4

# ---- UVs and source textures -------------------------------------------------
tc = node(unreal.MaterialExpressionTextureCoordinate, -2200, 0)
uv_scale = scalar("UVScale", 1.0, -2200, 100, "UV")
uvs = mul(tc, "", uv_scale, "", -2000, 50)
win = tex("WindowTexture", DEF_WINDOW, -1800, -200)
link(uvs, "", win, "UVs")
nrm = tex("NormalTexture", DEF_NORMAL, -1800, 600, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
link(uvs, "", nrm, "UVs")

# ---- pane mask from a per-texture colour key ------------------------------------
mask = custom("float l = dot(C, W.rgb);  // luma (0.3,0.59,0.11) or blue key (-1,0,1)\n"
              "float k = saturate((l - Thr) / max(Soft, 1e-4));\n"
              "return lerp(k, 1 - k, Inv);", F1, ["C", "W", "Thr", "Soft", "Inv"], -1500, -300, "PaneMask")
link(win, "RGB", mask, "C")
link(vector("MaskWeights", (0.3, 0.59, 0.11, 0), -1800, -480, "Mask"), "", mask, "W")
link(scalar("MaskThreshold", 0.15, -1800, -420, "Mask"), "", mask, "Thr")
link(scalar("MaskSoftness", 0.08, -1800, -360, "Mask"), "", mask, "Soft")
link(scalar("MaskInvert", 0.0, -1800, -300, "Mask"), "", mask, "Inv")

# ---- grime (option B) ----------------------------------------------------------
rooms = scalar("PanesPerTile", 2.0, -2200, 300, "UV")
edge = custom("float2 f = frac(UV * Rooms);\n"
              "float e = min(min(f.x, 1 - f.x), min(f.y, 1 - f.y));\n"
              "return 1 - saturate(e / max(W, 1e-3));", F1, ["UV", "Rooms", "W"], -1500, 250, "PaneEdge")
link(uvs, "", edge, "UV")
link(rooms, "", edge, "Rooms")
link(scalar("EdgeWidth", 0.12, -1800, 330, "Grime"), "", edge, "W")
grime_uv = mul(uvs, "", scalar("GrimeUVScale", 0.37, -2200, 420, "Grime"), "", -2000, 420)
gtex = tex("GrimeTexture", DEF_GRIME, -1800, 420, group="Grime")
link(grime_uv, "", gtex, "UVs")
grime_calc = custom("return saturate(smoothstep(0.35, 0.75, N) * Amt + Edge * EdgeAmt);", F1,
                    ["N", "Amt", "Edge", "EdgeAmt"], -1300, 350, "Grime")
link(gtex, "R", grime_calc, "N")
link(scalar("GrimeAmount", 0.5, -1500, 450, "Grime"), "", grime_calc, "Amt")
link(edge, "", grime_calc, "Edge")
link(scalar("EdgeDirt", 0.6, -1500, 510, "Grime"), "", grime_calc, "EdgeAmt")
zero = node(unreal.MaterialExpressionConstant, -1300, 500, r=0.0)
grime = switch("UseGrime", False, grime_calc, "", zero, "", -1100, 380)

# ---- glass colour + reflectivity -----------------------------------------------
tint = vector("TintColor", (0.55, 0.66, 0.8, 1), -1500, -560)
fres = node(unreal.MaterialExpressionFresnel, -1500, -700, exponent=5.0, base_reflect_fraction=0.04)
refl = scalar("ReflectStrength", 1.0, -1500, -640)
glass_col = custom("float3 g = C * Tint * (1 - Grime * 0.55);\n"
                   "return g * (1 - saturate(F * R) * 0.5);", F3, ["C", "Tint", "Grime", "F", "R"], -1100, -560,
                   "GlassColour")
link(win, "RGB", glass_col, "C")
link(tint, "", glass_col, "Tint")
link(grime, "", glass_col, "Grime")
link(fres, "", glass_col, "F")
link(refl, "", glass_col, "R")

# ---- interior (option C) -------------------------------------------------------
camv = node(unreal.MaterialExpressionCameraVectorWS, -2200, 800)
to_ts = node(unreal.MaterialExpressionTransform, -2000, 800,
             transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
             transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
link(camv, "", to_ts, "")
ARR = "/Game/CitySampleBuildings/Material/Window/Texture/RoomInteriors/Arrays/"  # same arrays M_Window uses
HLSL = open(os.path.join(HERE, "interior_room.hlsl")).read()
room = custom(HLSL, F4, ["UV", "V", "Panes", "WMin", "WMax", "RoomH", "Depth", "Theme", "Seed", "LitFrac",
                         "EmptyFrac", "BlindsFrac", "BlindsColor", "Bright", "Yaw", "MipDist", "PixelDepth", "Steps",
                         "Rooms1", "Rooms2", "FG1C", "FG1D", "FG2C", "FG2D"], -1500, 800, "InteriorRoom")
link(uvs, "", room, "UV")
link(to_ts, "", room, "V")
link(rooms, "", room, "Panes")
link(scalar("RoomWidthMin", 2.0, -2000, 900, "Interior"), "", room, "WMin")
link(scalar("RoomWidthMax", 4.0, -2000, 960, "Interior"), "", room, "WMax")
link(scalar("RoomHeight", 1.0, -2000, 1020, "Interior"), "", room, "RoomH")
link(scalar("InteriorDepth", 1.0, -2000, 1080, "Interior"), "", room, "Depth")
# Theme: per-actor Custom Primitive Data [0] (0 office, 1 residential, 2 retail) unless ThemeOverride >= 0
cpd_theme = node(unreal.MaterialExpressionCustomPrimitiveData, -2300, 1140, primitive_data_index=0)
cpd_seed = node(unreal.MaterialExpressionCustomPrimitiveData, -2300, 1200, primitive_data_index=1)
theme = custom("return Override >= 0 ? Override : CPD;", F1, ["Override", "CPD"], -2000, 1140, "Theme")
link(scalar("ThemeOverride", -1.0, -2300, 1080, "Interior"), "", theme, "Override")
link(cpd_theme, "", theme, "CPD")
link(theme, "", room, "Theme")
link(cpd_seed, "", room, "Seed")
link(scalar("LitFraction", 0.6, -2000, 1260, "Interior"), "", room, "LitFrac")
link(scalar("EmptyFloorFraction", 0.15, -2000, 1320, "Interior"), "", room, "EmptyFrac")
link(scalar("BlindsFraction", 0.3, -2000, 1380, "Interior"), "", room, "BlindsFrac")
link(vector("BlindsColor", (0.55, 0.52, 0.47, 1), -2000, 1440, "Interior"), "", room, "BlindsColor")
link(scalar("InteriorBrightness", 0.6, -2000, 1500, "Interior"), "", room, "Bright")
link(scalar("CubeYaw", 0.0, -2000, 1560, "Interior"), "", room, "Yaw")
link(scalar("InteriorMipDistance", 1500.0, -2000, 1620, "Interior"), "", room, "MipDist")
link(node(unreal.MaterialExpressionPixelDepth, -2000, 1680), "", room, "PixelDepth")
link(scalar("ForegroundSteps", 8.0, -2000, 1740, "Interior"), "", room, "Steps")
for i, (inp, asset) in enumerate([("Rooms1", "TCA_1x1x1_Rooms"), ("Rooms2", "TCA_2x2x1_Rooms"),
                                  ("FG1C", "T2A_1x1x1_CaptureFG"), ("FG1D", "T2A_1x1x1_DepthFG"),
                                  ("FG2C", "T2A_2x2x1_CaptureFG"), ("FG2D", "T2A_2x2x1_DepthFG")]):
    link(node(unreal.MaterialExpressionTextureObject, -1800, 1800 + 70 * i, texture=unreal.load_asset(ARR + asset)),
         "", room, inp)
room_rgb = node(unreal.MaterialExpressionComponentMask, -1200, 800, r=True, g=True, b=True, a=False)
link(room, "", room_rgb, "")
room_lit = node(unreal.MaterialExpressionComponentMask, -1200, 900, r=False, g=False, b=False, a=True)
link(room, "", room_lit, "")
night = node(unreal.MaterialExpressionCollectionParameter, -1400, 1050, collection=unreal.load_asset(MPC),
             parameter_name="Night")
int_mix = custom("float top = saturate(Base + F * R);\n"
                 "return lerp(Room, Glass, top);", F3, ["Room", "Glass", "F", "R", "Base"], -1000, 800,
                 "InteriorUnderGlass")
link(room_rgb, "", int_mix, "Room")
link(glass_col, "", int_mix, "Glass")
link(fres, "", int_mix, "F")
link(refl, "", int_mix, "R")
link(scalar("ReflectBase", 0.25, -1400, 1110, "Interior"), "", int_mix, "Base")
pane_col = switch("UseInterior", False, int_mix, "", glass_col, "", -800, -300)

# ---- emissive: interior lights and original glow map at night ------------------
glow_scale = node(unreal.MaterialExpressionComponentMask, -2100, 1250, r=True, g=True, b=False, a=False)
link(vector("GlowUVScale", (1, 1, 0, 0), -2300, 1250, "Night"), "", glow_scale, "")
glow_uv = mul(tc, "", glow_scale, "", -2000, 1250)
glow_tex = tex("GlowTexture", DEF_GLOW, -1800, 1250, group="Night")
link(glow_uv, "", glow_tex, "UVs")
emis_int = custom("return Room * Lit * Strength;", F3, ["Room", "Lit", "Strength"], -1000, 1050,
                  "InteriorLights")
link(room_rgb, "", emis_int, "Room")
link(room_lit, "", emis_int, "Lit")
link(scalar("InteriorEmissive", 3.0, -1400, 1170, "Night"), "", emis_int, "Strength")
emis_none = node(unreal.MaterialExpressionConstant3Vector, -1000, 1180, constant=unreal.LinearColor(0, 0, 0, 1))
emis_room = switch("UseInterior", False, emis_int, "", emis_none, "", -800, 1100)
emissive = custom("return Mask * Night * (Room + Glow * GlowStrength);", F3,
                  ["Mask", "Night", "Room", "Glow", "GlowStrength"], -500, 1100, "NightEmissive")
link(mask, "", emissive, "Mask")
link(night, "", emissive, "Night")
link(emis_room, "", emissive, "Room")
link(glow_tex, "RGB", emissive, "Glow")
link(scalar("GlowStrength", 0.0, -800, 1250, "Night"), "", emissive, "GlowStrength")

# ---- final PBR outputs ---------------------------------------------------------
base = lerp(win, "RGB", pane_col, "", mask, "", -400, -300)
rough = custom("float g = saturate(Rough + Grime * 0.45);\n"
               "return lerp(FrameRough, g, Mask);", F1, ["Rough", "Grime", "FrameRough", "Mask"], -400, 0,
               "Roughness")
link(scalar("Roughness", 0.07, -800, 0), "", rough, "Rough")
link(grime, "", rough, "Grime")
link(scalar("FrameRoughness", 0.55, -800, 60), "", rough, "FrameRough")
link(mask, "", rough, "Mask")
metal = custom("return Mask * Metal * saturate(R) * (1 - Grime * 0.5);", F1, ["Mask", "Metal", "R", "Grime"],
               -400, 150, "Metallic")
link(mask, "", metal, "Mask")
link(scalar("Metallic", 0.3, -800, 150), "", metal, "Metal")
link(refl, "", metal, "R")
link(grime, "", metal, "Grime")
spec = custom("return lerp(0.5, lerp(Spec, 1, saturate(F * R)), Mask);", F1, ["Spec", "F", "R", "Mask"],
              -400, 250, "Specular")
link(scalar("Specular", 0.9, -800, 250), "", spec, "Spec")
link(fres, "", spec, "F")
link(refl, "", spec, "R")
link(mask, "", spec, "Mask")
flat = node(unreal.MaterialExpressionConstant3Vector, -800, 600, constant=unreal.LinearColor(0, 0, 1, 1))
normal = lerp(nrm, "RGB", flat, "", mask, "", -400, 600)

P = unreal.MaterialProperty
MEL.connect_material_property(base, "", P.MP_BASE_COLOR)
MEL.connect_material_property(rough, "", P.MP_ROUGHNESS)
MEL.connect_material_property(metal, "", P.MP_METALLIC)
MEL.connect_material_property(spec, "", P.MP_SPECULAR)
MEL.connect_material_property(normal, "", P.MP_NORMAL)
MEL.connect_material_property(emissive, "", P.MP_EMISSIVE_COLOR)
MEL.layout_material_expressions(m)
MEL.recompile_material(m)
EAL.save_loaded_asset(m)
print("master built:", m.get_path_name(), "expressions", len(MEL.get_material_expressions(m)))

# ---- option instances ----------------------------------------------------------
OPTIONS = {
    "MI_Glass_Reflective": dict(
        scalars={"Roughness": 0.06, "ReflectStrength": 1.0, "Metallic": 0.35, "Specular": 1.0},
        vectors={"TintColor": (0.5, 0.62, 0.8, 1)},
        switches={"UseGrime": False, "UseInterior": False}),
    "MI_Glass_Smudgy": dict(
        scalars={"Roughness": 0.08, "ReflectStrength": 0.9, "Metallic": 0.3, "GrimeAmount": 0.55,
                 "EdgeDirt": 0.7, "EdgeWidth": 0.12, "GrimeUVScale": 0.37},
        vectors={"TintColor": (0.48, 0.58, 0.72, 1)},
        switches={"UseGrime": True, "UseInterior": False}),
    "MI_Glass_Interior": dict(
        scalars={"Roughness": 0.05, "ReflectStrength": 0.8, "Metallic": 0.05, "Specular": 1.0, "GrimeAmount": 0.2,
                 "EdgeDirt": 0.4, "InteriorDepth": 1.0, "InteriorBrightness": 0.25, "ReflectBase": 0.15,
                 "InteriorEmissive": 4.0},
        vectors={"TintColor": (0.6, 0.7, 0.8, 1)},
        switches={"UseGrime": True, "UseInterior": True}),
}
for name, o in OPTIONS.items():
    path = "%s/%s" % (FOLDER, name)
    if EAL.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = tools.create_asset(name, FOLDER, unreal.MaterialInstanceConstant,
                                unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, m)
    for k, v in o["scalars"].items():
        MEL.set_material_instance_scalar_parameter_value(mi, k, v)
    for k, v in o["vectors"].items():
        MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v))
    for k, v in o["switches"].items():
        MEL.set_material_instance_static_switch_parameter_value(mi, k, v)
    MEL.update_material_instance(mi)
    EAL.save_loaded_asset(mi)
    print("instance", path)

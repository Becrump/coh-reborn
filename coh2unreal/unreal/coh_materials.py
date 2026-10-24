"""Master materials for converted CoH zones, built in the Unreal editor.

Unreal's glTF master (M_GLTF) does not cut out alpha when its instances are
switched to Masked afterwards, so cutouts (lane lines, leaves, decals) and
the other CoH-specific looks get small masters of our own. Material
instances are re-parented onto them and keep their textures, because the
parameter names match M_GLTF's (BaseColorTexture, ..._OffsetScale,
NormalTexture, AlphaCutoff, ...).

    import coh_materials; coh_materials.build_all()
"""
import unreal

DIR = "/Game/CoH/Materials"
mel = unreal.MaterialEditingLibrary
E = unreal.MaterialExpression
_connect = unreal.MaterialEditingLibrary.connect_material_expressions


class _Mel:
    """MaterialEditingLibrary, but a failed connection raises instead of
    silently leaving a pin empty."""
    def __getattr__(self, name):
        return getattr(unreal.MaterialEditingLibrary, name)

    @staticmethod
    def connect_material_expressions(a, out, b, inp):
        if not _connect(a, out, b, inp):
            raise RuntimeError("could not connect %s.%r -> %s.%r" % (
                a.get_class().get_name(), out, b.get_class().get_name(), inp))
        return True


mel = _Mel()


def _new(name, blend, shading=None, two_sided=False):
    path = "%s/%s" % (DIR, name)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        # rebuild in place so instances already parented to it stay attached
        m = unreal.load_asset(path)
        mel.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, DIR, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", blend)
    m.set_editor_property("two_sided", two_sided)
    if shading is not None:
        m.set_editor_property("shading_model", shading)
    return m


def _node(m, cls, x, y, **props):
    n = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n


def _uv(m, prefix, x, y):
    """TexCoord * OffsetScale.ba + OffsetScale.rg (glTF texture transform)."""
    tc = _node(m, unreal.MaterialExpressionTextureCoordinate, x - 600, y)
    os_ = _node(m, unreal.MaterialExpressionVectorParameter, x - 600, y + 80,
                parameter_name=prefix + "_OffsetScale",
                default_value=unreal.LinearColor(0, 0, 1, 1))
    off = _node(m, unreal.MaterialExpressionComponentMask, x - 400, y + 60,
                r=True, g=True, b=False, a=False)
    scl = _node(m, unreal.MaterialExpressionComponentMask, x - 400, y + 140,
                r=False, g=False, b=True, a=True)
    # the parameter's default output is RGB only; scale needs B and A
    mel.connect_material_expressions(os_, "RGBA", off, "")
    mel.connect_material_expressions(os_, "RGBA", scl, "")
    mul = _node(m, unreal.MaterialExpressionMultiply, x - 250, y)
    mel.connect_material_expressions(tc, "", mul, "A")
    mel.connect_material_expressions(scl, "", mul, "B")
    add = _node(m, unreal.MaterialExpressionAdd, x - 120, y)
    mel.connect_material_expressions(mul, "", add, "A")
    mel.connect_material_expressions(off, "", add, "B")
    return add


def _tex(m, name, x, y, normal=False, srgb=True):
    uv = _uv(m, name, x, y)
    t = _node(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y,
              parameter_name=name)
    if normal:
        t.set_editor_property("sampler_type",
                              unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        t.set_editor_property("texture", unreal.load_asset(
            "/Engine/EngineMaterials/DefaultNormal"))
    else:
        # a texture parameter needs a default or the material won't compile
        t.set_editor_property("texture", unreal.load_asset(
            "/Engine/EngineResources/WhiteSquareTexture"))
    mel.connect_material_expressions(uv, "", t, "UVs")
    return t


def _base_color(m, x, y):
    tex = _tex(m, "BaseColorTexture", x, y)
    fac = _node(m, unreal.MaterialExpressionVectorParameter, x, y + 220,
                parameter_name="BaseColorFactor",
                default_value=unreal.LinearColor(1, 1, 1, 1))
    mul = _node(m, unreal.MaterialExpressionMultiply, x + 250, y)
    mel.connect_material_expressions(tex, "RGB", mul, "A")
    mel.connect_material_expressions(fac, "", mul, "B")
    return tex, mul


def _normal(m, x, y):
    """NormalTexture behind the bHasNormalTexture switch (flat if off)."""
    n = _tex(m, "NormalTexture", x, y, normal=True)
    flat = _node(m, unreal.MaterialExpressionConstant3Vector, x, y + 220,
                 constant=unreal.LinearColor(0, 0, 1, 0))
    sw = _node(m, unreal.MaterialExpressionStaticSwitchParameter, x + 250, y,
               parameter_name="bHasNormalTexture", default_value=False)
    mel.connect_material_expressions(n, "RGB", sw, "True")
    mel.connect_material_expressions(flat, "", sw, "False")
    return sw


MPC_PATH = DIR + "/MPC_CoH"


def night_collection():
    """MPC_CoH: global values the day/night cycle drives (Night 0..1)."""
    if unreal.EditorAssetLibrary.does_asset_exist(MPC_PATH):
        return unreal.load_asset(MPC_PATH)
    mpc = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "MPC_CoH", DIR, unreal.MaterialParameterCollection,
        unreal.MaterialParameterCollectionFactoryNew())
    p = unreal.CollectionScalarParameter()
    p.set_editor_property("parameter_name", "Night")
    p.set_editor_property("default_value", 0.0)
    mpc.set_editor_property("scalar_parameters", [p])
    unreal.EditorAssetLibrary.save_loaded_asset(mpc, False)
    return mpc


def _detail(m, color, x, y):
    """color * DetailTexture * 2 (CoH 'Multiply' blend: mid-grey keeps the
    colour), tiled by DetailScale; off unless bHasDetailTexture."""
    tc = _node(m, unreal.MaterialExpressionTextureCoordinate, x - 500, y)
    sc = _node(m, unreal.MaterialExpressionVectorParameter, x - 500, y + 80,
               parameter_name="DetailScale",
               default_value=unreal.LinearColor(1, 1, 0, 0))
    rg = _node(m, unreal.MaterialExpressionComponentMask, x - 350, y + 80,
               r=True, g=True, b=False, a=False)
    mel.connect_material_expressions(sc, "", rg, "")
    uv = _node(m, unreal.MaterialExpressionMultiply, x - 250, y)
    mel.connect_material_expressions(tc, "", uv, "A")
    mel.connect_material_expressions(rg, "", uv, "B")
    t = _node(m, unreal.MaterialExpressionTextureSampleParameter2D, x - 100, y,
              parameter_name="DetailTexture",
              texture=unreal.load_asset("/Engine/EngineResources/WhiteSquareTexture"))
    mel.connect_material_expressions(uv, "", t, "UVs")
    two = _node(m, unreal.MaterialExpressionConstant, x - 100, y + 200, r=2.0)
    d2 = _node(m, unreal.MaterialExpressionMultiply, x + 150, y)
    mel.connect_material_expressions(t, "RGB", d2, "A")
    mel.connect_material_expressions(two, "", d2, "B")
    mul = _node(m, unreal.MaterialExpressionMultiply, x + 300, y)
    mel.connect_material_expressions(color, "", mul, "A")
    mel.connect_material_expressions(d2, "", mul, "B")
    sw = _node(m, unreal.MaterialExpressionStaticSwitchParameter, x + 450, y,
               parameter_name="bHasDetailTexture", default_value=False)
    mel.connect_material_expressions(mul, "", sw, "True")
    mel.connect_material_expressions(color, "", sw, "False")
    return sw


def _glow(m, x, y):
    """GlowTexture * GlowStrength * MPC_CoH.Night: CoH's lit-window maps,
    on at night only; off unless bHasGlowTexture. GlowScale tiles the glow
    (CoH AddGlow1Scale) and GlowMask limits it to where its material layer
    shows (CoH AddGlowMat2 + Mask), e.g. only the windows of a brick wall."""
    uv = _uv(m, "BaseColorTexture", x - 500, y)   # glow maps share base UVs
    gs = _node(m, unreal.MaterialExpressionVectorParameter, x - 500, y + 100,
               parameter_name="GlowScale",
               default_value=unreal.LinearColor(1, 1, 0, 0))
    gs2 = _node(m, unreal.MaterialExpressionComponentMask, x - 350, y + 100,
                r=True, g=True, b=False, a=False)
    mel.connect_material_expressions(gs, "RGBA", gs2, "")
    guv = _node(m, unreal.MaterialExpressionMultiply, x - 200, y)
    mel.connect_material_expressions(uv, "", guv, "A")
    mel.connect_material_expressions(gs2, "", guv, "B")
    t = _node(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y,
              parameter_name="GlowTexture",
              texture=unreal.load_asset("/Engine/EngineResources/Black"))
    mel.connect_material_expressions(guv, "", t, "UVs")
    mk = _node(m, unreal.MaterialExpressionTextureSampleParameter2D, x,
               y + 450, parameter_name="GlowMask",
               texture=unreal.load_asset(
                   "/Engine/EngineResources/WhiteSquareTexture"))
    mel.connect_material_expressions(uv, "", mk, "UVs")
    pick = _node(m, unreal.MaterialExpressionLinearInterpolate, x + 200,
                 y + 450)
    mel.connect_material_expressions(mk, "R", pick, "A")
    mel.connect_material_expressions(mk, "A", pick, "B")
    mel.connect_material_expressions(
        _scalar(m, "GlowMaskAlpha", 0.0, x, y + 650), "", pick, "Alpha")
    inv = _node(m, unreal.MaterialExpressionOneMinus, x + 300, y + 550)
    mel.connect_material_expressions(pick, "", inv, "")
    mval = _node(m, unreal.MaterialExpressionLinearInterpolate, x + 400,
                 y + 450)
    mel.connect_material_expressions(pick, "", mval, "A")
    mel.connect_material_expressions(inv, "", mval, "B")
    mel.connect_material_expressions(
        _scalar(m, "GlowMaskInvert", 0.0, x + 200, y + 700), "", mval,
        "Alpha")
    night = _node(m, unreal.MaterialExpressionCollectionParameter, x, y + 220)
    night.set_editor_property("collection", night_collection())
    night.set_editor_property("parameter_name", "Night")
    strength = _scalar(m, "GlowStrength", 6.0, x, y + 320)
    a = _node(m, unreal.MaterialExpressionMultiply, x + 250, y)
    mel.connect_material_expressions(t, "RGB", a, "A")
    mel.connect_material_expressions(night, "", a, "B")
    am = _node(m, unreal.MaterialExpressionMultiply, x + 350, y + 100)
    mel.connect_material_expressions(a, "", am, "A")
    mel.connect_material_expressions(mval, "", am, "B")
    b = _node(m, unreal.MaterialExpressionMultiply, x + 450, y)
    mel.connect_material_expressions(am, "", b, "A")
    mel.connect_material_expressions(strength, "", b, "B")
    zero = _node(m, unreal.MaterialExpressionConstant3Vector, x + 400, y + 200,
                 constant=unreal.LinearColor(0, 0, 0, 0))
    sw = _node(m, unreal.MaterialExpressionStaticSwitchParameter, x + 600, y,
               parameter_name="bHasGlowTexture", default_value=False)
    mel.connect_material_expressions(b, "", sw, "True")
    mel.connect_material_expressions(zero, "", sw, "False")
    return sw


def _scalar(m, name, default, x, y):
    return _node(m, unreal.MaterialExpressionScalarParameter, x, y,
                 parameter_name=name, default_value=default)


def build_masked():
    """Cutouts: lane lines, leaves, grass cards, decals."""
    m = _new("M_CoH_Masked", unreal.BlendMode.BLEND_MASKED, two_sided=True)
    tex, col = _base_color(m, -900, -300)
    col = _detail(m, col, -300, -700)
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(_glow(m, -400, 1000), "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(tex, "A",
                                  unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.connect_material_property(_normal(m, -400, 200), "",
                                  unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(_scalar(m, "RoughnessFactor", 0.85, 0, 500),
                                  "", unreal.MaterialProperty.MP_ROUGHNESS)
    m.set_editor_property("opacity_mask_clip_value", 0.3)
    mel.recompile_material(m)
    unreal.EditorAssetLibrary.save_loaded_asset(m, False)
    return m


def build_surface():
    """Opaque surface with working UV tiling (M_GLTF skips its texture
    transform on Nanite meshes): turf and other tiled ground."""
    m = _new("M_CoH_Surface", unreal.BlendMode.BLEND_OPAQUE)
    tex, col = _base_color(m, -900, -400)
    col = _detail(m, col, -300, -700)
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(_glow(m, -400, 1000), "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(_normal(m, -400, 100), "",
                                  unreal.MaterialProperty.MP_NORMAL)
    mr = _tex(m, "MetallicRoughnessTexture", -400, 500)
    rf = _scalar(m, "RoughnessFactor", 1.0, -400, 720)
    rmul = _node(m, unreal.MaterialExpressionMultiply, -100, 500)
    mel.connect_material_expressions(mr, "G", rmul, "A")
    mel.connect_material_expressions(rf, "", rmul, "B")
    mel.connect_material_property(rmul, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(m)
    unreal.EditorAssetLibrary.save_loaded_asset(m, False)
    return m


def build_decal():
    """CoH blend decals: colour from a tiled texture (BaseColorTexture),
    shape from a separate mask (OpacityTexture, its own UVs). Dithered so
    the soft mask edge fades into the ground instead of a hard cut."""
    m = _new("M_CoH_Decal", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("dither_opacity_mask", True)
    tex, col = _base_color(m, -400, -400)
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mask = _tex(m, "OpacityTexture", -400, 100)
    mel.connect_material_property(mask, "R",
                                  unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.connect_material_property(_normal(m, -400, 450), "",
                                  unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(_scalar(m, "RoughnessFactor", 0.9, 0, 700),
                                  "", unreal.MaterialProperty.MP_ROUGHNESS)
    m.set_editor_property("opacity_mask_clip_value", 0.35)
    mel.recompile_material(m)
    unreal.EditorAssetLibrary.save_loaded_asset(m, False)
    return m


def build_water(normal_tex):
    """Water with Unreal's Single Layer Water shading: real depth (light is
    absorbed and scattered with distance, so shallow edges are clear and
    deep water goes dark green-blue), refraction of the canal bed, Lumen
    reflections of sky and towers, and three world-scaled ripple normals
    drifting in different directions (no texture tiling to see)."""
    m = _new("M_CoH_Water", unreal.BlendMode.BLEND_OPAQUE,
             unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
    wp = _node(m, unreal.MaterialExpressionWorldPosition, -1400, 200)
    xy = _node(m, unreal.MaterialExpressionComponentMask, -1250, 200,
               r=True, g=True, b=False, a=False)
    mel.connect_material_expressions(wp, "", xy, "")
    layers = []
    for i, (scale, sx, sy) in enumerate(((450.0, 0.014, 0.008),
                                         (1300.0, -0.007, 0.011),
                                         (320.0, 0.02, -0.016))):
        div = _node(m, unreal.MaterialExpressionDivide, -1100, 120 + i * 260)
        sc = _node(m, unreal.MaterialExpressionConstant, -1250, 300 + i * 260,
                   r=scale)
        mel.connect_material_expressions(xy, "", div, "A")
        mel.connect_material_expressions(sc, "", div, "B")
        pan = _node(m, unreal.MaterialExpressionPanner, -950, 120 + i * 260,
                    speed_x=sx, speed_y=sy)
        mel.connect_material_expressions(div, "", pan, "Coordinate")
        t = _node(m, unreal.MaterialExpressionTextureSampleParameter2D,
                  -750, 120 + i * 260, parameter_name="RippleNormal%d" % i,
                  texture=normal_tex,
                  sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        mel.connect_material_expressions(pan, "", t, "UVs")
        layers.append(t)
    add1 = _node(m, unreal.MaterialExpressionAdd, -550, 200)
    mel.connect_material_expressions(layers[0], "RGB", add1, "A")
    mel.connect_material_expressions(layers[1], "RGB", add1, "B")
    add2 = _node(m, unreal.MaterialExpressionAdd, -500, 300)
    mel.connect_material_expressions(add1, "", add2, "A")
    mel.connect_material_expressions(layers[2], "RGB", add2, "B")
    blend = _node(m, unreal.MaterialExpressionNormalize, -420, 300)
    mel.connect_material_expressions(add2, "", blend, "")
    flat = _node(m, unreal.MaterialExpressionConstant3Vector, -450, 420,
                 constant=unreal.LinearColor(0, 0, 1, 0))
    strength = _scalar(m, "RippleStrength", 0.4, -450, 500)
    nl = _node(m, unreal.MaterialExpressionLinearInterpolate, -250, 300)
    mel.connect_material_expressions(flat, "", nl, "A")
    mel.connect_material_expressions(blend, "", nl, "B")
    mel.connect_material_expressions(strength, "", nl, "Alpha")
    # Substrate (on in this project) needs its own water BSDF on the
    # front material; the legacy water output node is not picked up.
    bsdf = _node(m, unreal.MaterialExpressionSubstrateSingleLayerWaterBSDF,
                 200, 0)
    mel.connect_material_expressions(nl, "", bsdf, "Normal")
    for pin, name, val in (
            ("BaseColor", "SurfaceColor", unreal.LinearColor(0, 0, 0, 1)),
            # how strongly each colour is absorbed per centimetre (Unreal
            # units): red goes first, so depth turns green-blue; ~1 m of
            # canal stays see-through to the bed
            ("WaterExtinction", "Extinction",
             unreal.LinearColor(0.018, 0.007, 0.006, 1)),
            # share of the extinction scattered back: the teal body colour
            # that reads even in full sun
            ("WaterAlbedo", "Albedo", unreal.LinearColor(0.05, 0.42, 0.45, 1))):
        v = _node(m, unreal.MaterialExpressionVectorParameter, -50, -150,
                  parameter_name=name, default_value=val)
        mel.connect_material_expressions(v, "", bsdf, pin)
    for pin, name, val, y in (("Roughness", "Roughness", 0.04, 300),
                              ("Specular", "Specular", 0.8, 380),
                              ("WaterPhaseG", "PhaseG", 0.1, 460),
                              ("ColorScaleBehindWater",
                               "ColorScaleBehindWater", 1.0, 540)):
        mel.connect_material_expressions(_scalar(m, name, val, -50, y), "",
                                         bsdf, pin)
    mel.connect_material_property(bsdf, "",
                                  unreal.MaterialProperty.MP_FRONT_MATERIAL)
    # the water shading model also insists on its output node being present
    out = _node(m, unreal.MaterialExpressionSingleLayerWaterMaterialOutput,
                200, 400)
    for pin, val in (("AbsorptionCoefficients",
                      unreal.LinearColor(0.0035, 0.0012, 0.0009, 1)),
                     ("ScatteringCoefficients",
                      unreal.LinearColor(0.0001, 0.0002, 0.0002, 1))):
        mel.connect_material_expressions(
            _node(m, unreal.MaterialExpressionConstant3Vector, 0, 450,
                  constant=val), "", out, pin)
    mel.recompile_material(m)
    unreal.EditorAssetLibrary.save_loaded_asset(m, False)
    return m


def build_additive():
    """Glows added on top: lamp pools, beams, War Walls, flares."""
    m = _new("M_CoH_Additive", unreal.BlendMode.BLEND_ADDITIVE,
             unreal.MaterialShadingModel.MSM_UNLIT, two_sided=True)
    tex = _tex(m, "EmissiveTexture", -400, -100)
    strength = _scalar(m, "EmissiveStrength", 1.0, -400, 200)
    mul = _node(m, unreal.MaterialExpressionMultiply, -100, -100)
    mel.connect_material_expressions(tex, "RGB", mul, "A")
    mel.connect_material_expressions(strength, "", mul, "B")
    # NightScale: brightness at full night (1 = unchanged); lets big glows
    # like the War Walls calm down so they don't blind the night exposure
    night = _node(m, unreal.MaterialExpressionCollectionParameter, -400, 320)
    night.set_editor_property("collection", night_collection())
    night.set_editor_property("parameter_name", "Night")
    one = _node(m, unreal.MaterialExpressionConstant, -250, 420, r=1.0)
    ns = _scalar(m, "NightScale", 1.0, -400, 480)
    lerp = _node(m, unreal.MaterialExpressionLinearInterpolate, -100, 300)
    mel.connect_material_expressions(one, "", lerp, "A")
    mel.connect_material_expressions(ns, "", lerp, "B")
    mel.connect_material_expressions(night, "", lerp, "Alpha")
    out = _node(m, unreal.MaterialExpressionMultiply, 100, -100)
    mel.connect_material_expressions(mul, "", out, "A")
    mel.connect_material_expressions(lerp, "", out, "B")
    mel.connect_material_property(out, "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    unreal.EditorAssetLibrary.save_loaded_asset(m, False)
    return m


def _snapshot(mi, parent):
    """Values the instance has for every parameter the new parent uses."""
    vals = []
    for n in mel.get_texture_parameter_names(parent):
        v = mel.get_material_instance_texture_parameter_value(mi, n)
        if v:
            vals.append(("tex", n, v))
    for n in mel.get_vector_parameter_names(parent):
        vals.append(("vec", n,
                     mel.get_material_instance_vector_parameter_value(mi, n)))
    for n in mel.get_scalar_parameter_names(parent):
        vals.append(("scalar", n,
                     mel.get_material_instance_scalar_parameter_value(mi, n)))
    for n in mel.get_static_switch_parameter_names(parent):
        vals.append(("switch", n,
                     mel.get_material_instance_static_switch_parameter_value(
                         mi, n)))
    return vals


def reparent(mi, parent, extra=None):
    """Moves an instance onto `parent`, keeping its textures and values.
    `extra` maps parameter -> value to set afterwards (e.g. copy the base
    colour texture into EmissiveTexture)."""
    vals = _snapshot(mi, parent)
    mel.set_material_instance_parent(mi, parent)
    for kind, n, v in vals:
        if kind == "tex":
            mel.set_material_instance_texture_parameter_value(mi, n, v)
        elif kind == "vec":
            mel.set_material_instance_vector_parameter_value(mi, n, v)
        elif kind == "scalar":
            mel.set_material_instance_scalar_parameter_value(mi, n, v)
        elif kind == "switch":
            mel.set_material_instance_static_switch_parameter_value(mi, n, v)
    for n, v in (extra or {}).items():
        if isinstance(v, unreal.Texture):
            mel.set_material_instance_texture_parameter_value(mi, n, v)
        elif isinstance(v, unreal.LinearColor):
            mel.set_material_instance_vector_parameter_value(mi, n, v)
        else:
            mel.set_material_instance_scalar_parameter_value(mi, n, v)
    o = mi.get_editor_property("base_property_overrides")
    for p in ("override_blend_mode", "override_opacity_mask_clip_value",
              "override_two_sided", "override_shading_model"):
        try:
            o.set_editor_property(p, False)
        except Exception:
            pass
    mi.set_editor_property("base_property_overrides", o)
    mel.update_material_instance(mi)
    unreal.EditorAssetLibrary.save_loaded_asset(mi, False)

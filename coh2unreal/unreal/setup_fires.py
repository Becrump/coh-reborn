"""Lights the zone's fire spots (braziers etc.) at night.

Run in the Unreal editor after make_fire.py:
    py "<repo>/coh2unreal/unreal/setup_fires.py" "<out folder>"

For every CoH fire effect (N_Fire in <name>_life.json "fx") it places
crossed flame cards with M_CoH_Fire (additive, noise scrolling upwards and
eating the flame edges), a warm point light with a flickering light
function, and a thin smoke wisp (Soul: City's smoke column, if present).
All are labelled ..._night, so the day/night cycle shows them only at
night; re-run `setup_level.py --only daynight` afterwards to add them to it.
Safe to run again (replaces the Fire_* actors).
"""
import json
import os
import sys

import unreal

CONTENT = "/Game/CoH/FX/Fire"
MAT = "/Game/CoH/Materials/M_CoH_Fire"
FLICKER = "/Game/CoH/Materials/M_CoH_FireFlicker"
SMOKE = "/Game/SoulCity/EffectsMobileOpt/Smoke/ParticleSystems/P_smokeColumn"
# a Fab fire effect, used instead of the flame cards when present
FIRE_SYSTEM = "/Game/FireEffectVFX/VFX/NS_FireEffect"
FIRE_SYSTEM_SCALE = 4.0         # the pack effect is built small (torch size)
FLAME_SIZE = (1.5, 1.5, 1.3)       # scale of the 0.6 x 1 m cards
LIGHT_CANDELA = 550.0

el = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def log(msg):
    unreal.log("[CoH fires] " + msg)


def node(m, cls, x, y, **props):
    n = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n


def connect(a, out, b, inp):
    if not mel.connect_material_expressions(a, out, b, inp):
        raise RuntimeError("connect %s -> %s.%s" % (
            a.get_class().get_name(), b.get_class().get_name(), inp))


def new_material(path):
    folder, name = path.rsplit("/", 1)
    if el.does_asset_exist(path):
        m = unreal.load_asset(path)
        mel.delete_all_material_expressions(m)
        return m
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.Material, unreal.MaterialFactoryNew())


def mask(m, ch, x, y):
    flags = dict(r=False, g=False, b=False, a=False)
    flags[ch] = True
    return node(m, unreal.MaterialExpressionComponentMask, x, y, **flags)


def build_fire():
    m = new_material(MAT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("shading_model",
                          unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("two_sided", True)
    noise_tex = unreal.load_asset("/Game/CoH/Water/T_Water_N")
    uv = node(m, unreal.MaterialExpressionTextureCoordinate, -1500, 0)
    noises = []
    for i, (spd, tile) in enumerate(((-1.4, 1.0), (-2.3, 2.1))):
        mul = node(m, unreal.MaterialExpressionMultiply, -1350, i * 220)
        connect(uv, "", mul, "A")
        connect(node(m, unreal.MaterialExpressionConstant, -1500, 100 + i * 220,
                     r=tile), "", mul, "B")
        pan = node(m, unreal.MaterialExpressionPanner, -1200, i * 220,
                   speed_x=0.05 * (1 if i else -1), speed_y=spd)
        connect(mul, "", pan, "Coordinate")
        t = node(m, unreal.MaterialExpressionTextureSample, -1000, i * 220,
                 texture=noise_tex,
                 sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        connect(pan, "", t, "UVs")
        r = mask(m, "r", -800, i * 220)
        connect(t, "RGB", r, "")
        a = node(m, unreal.MaterialExpressionAbs, -700, i * 220)
        connect(r, "", a, "")
        noises.append(a)
    nsum = node(m, unreal.MaterialExpressionAdd, -600, 100)
    connect(noises[0], "", nsum, "A")
    connect(noises[1], "", nsum, "B")
    # flame shape: wide at the base, thinning to a point, soft sides
    u = mask(m, "r", -1300, 500)
    v = mask(m, "g", -1300, 600)
    connect(uv, "", u, "")
    connect(uv, "", v, "")
    centred = node(m, unreal.MaterialExpressionSubtract, -1150, 500)
    connect(u, "", centred, "A")
    connect(node(m, unreal.MaterialExpressionConstant, -1300, 420, r=0.5), "",
            centred, "B")
    side = node(m, unreal.MaterialExpressionAbs, -1050, 500)
    connect(centred, "", side, "")
    width = node(m, unreal.MaterialExpressionOneMinus, -1050, 600)
    connect(v, "", width, "")
    half = node(m, unreal.MaterialExpressionMultiply, -950, 600)
    connect(width, "", half, "A")
    connect(node(m, unreal.MaterialExpressionConstant, -1050, 680, r=0.5), "",
            half, "B")
    inside = node(m, unreal.MaterialExpressionSubtract, -850, 550)
    connect(half, "", inside, "A")
    connect(side, "", inside, "B")
    shape = node(m, unreal.MaterialExpressionMultiply, -750, 550)
    connect(inside, "", shape, "A")
    connect(node(m, unreal.MaterialExpressionConstant, -850, 650, r=4.0), "",
            shape, "B")
    # noise eats the flame: bright core, ragged licking edges
    eaten = node(m, unreal.MaterialExpressionSubtract, -500, 300)
    connect(shape, "", eaten, "A")
    connect(nsum, "", eaten, "B")
    body = node(m, unreal.MaterialExpressionSaturate, -400, 300)
    connect(eaten, "", body, "")
    # colour: deep orange at the edges/top, yellow-white in the core
    lerp = node(m, unreal.MaterialExpressionLinearInterpolate, -250, 150)
    connect(node(m, unreal.MaterialExpressionVectorParameter, -450, 50,
                 parameter_name="EdgeColor",
                 default_value=unreal.LinearColor(1.0, 0.18, 0.02, 1)), "",
            lerp, "A")
    connect(node(m, unreal.MaterialExpressionVectorParameter, -450, 150,
                 parameter_name="CoreColor",
                 default_value=unreal.LinearColor(1.0, 0.75, 0.3, 1)), "",
            lerp, "B")
    connect(body, "", lerp, "Alpha")
    em = node(m, unreal.MaterialExpressionMultiply, -100, 250)
    connect(lerp, "", em, "A")
    connect(body, "", em, "B")
    em2 = node(m, unreal.MaterialExpressionMultiply, 0, 250)
    connect(em, "", em2, "A")
    connect(node(m, unreal.MaterialExpressionScalarParameter, -100, 350,
                 parameter_name="Brightness", default_value=12.0), "",
            em2, "B")
    mel.connect_material_property(em2, "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    el.save_loaded_asset(m, False)
    return m


def build_flicker():
    """Light function: brightness wobbling 0.65-1.0 like a fire."""
    m = new_material(FLICKER)
    m.set_editor_property("material_domain",
                          unreal.MaterialDomain.MD_LIGHT_FUNCTION)
    t = node(m, unreal.MaterialExpressionTime, -900, 0)
    total = None
    for i, (freq, amp) in enumerate(((7.3, 0.12), (13.1, 0.08), (2.9, 0.1))):
        mul = node(m, unreal.MaterialExpressionMultiply, -700, i * 150)
        connect(t, "", mul, "A")
        connect(node(m, unreal.MaterialExpressionConstant, -850, 60 + i * 150,
                     r=freq), "", mul, "B")
        s = node(m, unreal.MaterialExpressionSine, -550, i * 150)
        connect(mul, "", s, "")
        k = node(m, unreal.MaterialExpressionMultiply, -400, i * 150)
        connect(s, "", k, "A")
        connect(node(m, unreal.MaterialExpressionConstant, -550, 60 + i * 150,
                     r=amp), "", k, "B")
        if total is None:
            total = k
        else:
            add = node(m, unreal.MaterialExpressionAdd, -250, i * 150)
            connect(total, "", add, "A")
            connect(k, "", add, "B")
            total = add
    base = node(m, unreal.MaterialExpressionAdd, -100, 150)
    connect(total, "", base, "A")
    connect(node(m, unreal.MaterialExpressionConstant, -250, 300, r=0.82), "",
            base, "B")
    mel.connect_material_property(base, "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    el.save_loaded_asset(m, False)
    return m


def import_cards(folder, mat):
    dest = CONTENT + "/fire_cards"
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    found = [d for d in reg.get_assets_by_path(dest, True)
             if str(d.asset_class_path.asset_name) == "StaticMesh"]
    if not found:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename",
                              os.path.join(folder, "fire", "fire_cards.glb"))
        t.set_editor_property("destination_path", dest)
        for k in ("automated", "replace_existing", "save"):
            t.set_editor_property(k, True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
        found = [d for d in reg.get_assets_by_path(dest, True)
                 if str(d.asset_class_path.asset_name) == "StaticMesh"]
    mesh = found[0].get_asset()
    mesh.set_material(0, mat)
    ns = mesh.get_editor_property("nanite_settings")
    ns.set_editor_property("enabled", False)
    mesh.set_editor_property("nanite_settings", ns)
    el.save_loaded_asset(mesh, False)
    return mesh


def main():
    folder = [a for a in sys.argv[1:] if not a.startswith("-")][0]
    life = None
    for f in os.listdir(folder):
        if f.endswith("_life.json"):
            life = json.load(open(os.path.join(folder, f)))
    fires = [e for e in life["fx"] if "/fire/" in e["fx"].lower()]
    flicker = build_flicker()
    system = unreal.load_asset(FIRE_SYSTEM)
    cards = None if system else import_cards(folder, build_fire())
    smoke = unreal.load_asset(SMOKE)
    for a in asub.get_all_level_actors():
        if a.get_actor_label().startswith("Fire_"):
            asub.destroy_actor(a)
    for i, e in enumerate(fires):
        p = unreal.Vector(*e["p"])
        if system:
            a = asub.spawn_actor_from_class(unreal.NiagaraActor, p)
            a.niagara_component.set_asset(system)
            a.set_actor_scale3d(unreal.Vector(FIRE_SYSTEM_SCALE,
                                              FIRE_SYSTEM_SCALE,
                                              FIRE_SYSTEM_SCALE))
        else:
            a = asub.spawn_actor_from_object(cards, p)
            a.set_actor_scale3d(unreal.Vector(*FLAME_SIZE))
            c = a.static_mesh_component
            c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            c.set_editor_property("cast_shadow", False)
        a.set_actor_label("Fire_%d_flame_night" % i)
        a.set_folder_path("CoH/Fires")
        lt = asub.spawn_actor_from_class(unreal.PointLight,
                                         p + unreal.Vector(0, 0, 80))
        lt.set_actor_label("Fire_%d_light_night" % i)
        lt.set_folder_path("CoH/Fires")
        lc = lt.get_component_by_class(unreal.PointLightComponent)
        lc.set_mobility(unreal.ComponentMobility.MOVABLE)
        lc.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
        lc.set_intensity(LIGHT_CANDELA)
        lc.set_editor_property("use_temperature", True)
        lc.set_editor_property("temperature", 2000.0)
        lc.set_attenuation_radius(1500.0)
        lc.set_editor_property("light_function_material", flicker)
        if smoke:
            s = asub.spawn_actor_from_object(smoke,
                                             p + unreal.Vector(0, 0, 150))
            s.set_actor_scale3d(unreal.Vector(0.12, 0.12, 0.12))
            s.set_actor_label("Fire_%d_smoke_night" % i)
            s.set_folder_path("CoH/Fires")
    log("fires: %d (%s, flickering lights%s)" % (
        len(fires), "Niagara fire" if system else "flame cards",
        ", smoke" if smoke else ""))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


main()

"""Adds water jets to the zone's fountains.

Run in the Unreal editor after make_jets.py:
    py "<repo>/coh2unreal/unreal/setup_fountains.py" "<out folder>"

Each CoH fountain (fountains.json) gets a rising column, a bell of water
falling back from its top and a foam crown where it lands, sized by the
fountain type, standing on the basin's water surface. M_CoH_WaterJet is a
translucent material whose ripple pattern runs along the flow, so the water
visibly pours. The spray particles already placed stay on top.
Safe to run again (replaces the Jet_* actors).
"""
import json
import os
import sys

import unreal

CONTENT = "/Game/CoH/FX/Jets"
MAT = "/Game/CoH/Materials/M_CoH_WaterJet"
# fountain type -> (jet height, bell radius) in cm
SIZES = {
    "large": (520.0, 220.0),
    "stream": (130.0, 55.0),
    "geo": (220.0, 95.0),
    "normal": (320.0, 130.0),
}

el = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def log(msg):
    unreal.log("[CoH fountains] " + msg)


def node(m, cls, x, y, **props):
    n = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n


def connect(a, out, b, inp):
    if not mel.connect_material_expressions(a, out, b, inp):
        raise RuntimeError("connect %s -> %s.%s" % (
            a.get_class().get_name(), b.get_class().get_name(), inp))


def build_material():
    folder, name = MAT.rsplit("/", 1)
    if el.does_asset_exist(MAT):
        m = unreal.load_asset(MAT)
        mel.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, folder, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("two_sided", True)
    m.set_editor_property(
        "translucency_lighting_mode",
        unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    ripple = unreal.load_asset("/Game/CoH/Water/T_Water_N")
    uv = node(m, unreal.MaterialExpressionTextureCoordinate, -1300, 0,
              u_tiling=5.0, v_tiling=2.0)
    layers = []
    for i, (spd, tile) in enumerate(((-1.6, 1.0), (-0.9, 0.55))):
        mul = node(m, unreal.MaterialExpressionMultiply, -1150, i * 250)
        c = node(m, unreal.MaterialExpressionConstant, -1300, 100 + i * 250,
                 r=tile)
        connect(uv, "", mul, "A")
        connect(c, "", mul, "B")
        pan = node(m, unreal.MaterialExpressionPanner, -1000, i * 250,
                   speed_x=0.03 * (1 if i else -1), speed_y=spd)
        connect(mul, "", pan, "Coordinate")
        t = node(m, unreal.MaterialExpressionTextureSample, -800, i * 250,
                 texture=ripple,
                 sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        connect(pan, "", t, "UVs")
        layers.append(t)
    nsum = node(m, unreal.MaterialExpressionAdd, -600, 100)
    connect(layers[0], "RGB", nsum, "A")
    connect(layers[1], "RGB", nsum, "B")
    nrm = node(m, unreal.MaterialExpressionNormalize, -500, 100)
    connect(nsum, "", nrm, "")
    mel.connect_material_property(nrm, "", unreal.MaterialProperty.MP_NORMAL)
    # streaks: how far the ripple bends the normal sideways
    streak = node(m, unreal.MaterialExpressionComponentMask, -500, 250,
                  r=True, g=False, b=False, a=False)
    connect(nsum, "", streak, "")
    absn0 = node(m, unreal.MaterialExpressionAbs, -450, 250)
    connect(streak, "", absn0, "")
    # strong streaks: broken sheets of water, not a smooth glass shell
    absn = node(m, unreal.MaterialExpressionMultiply, -400, 250)
    connect(absn0, "", absn, "A")
    connect(node(m, unreal.MaterialExpressionScalarParameter, -550, 320,
                 parameter_name="Streaks", default_value=3.0), "", absn, "B")
    # fade out at the end of the flow (V -> 1) and where it leaves the nozzle
    v = node(m, unreal.MaterialExpressionComponentMask, -1150, 500,
             r=False, g=True, b=False, a=False)
    uv1 = node(m, unreal.MaterialExpressionTextureCoordinate, -1300, 500)
    connect(uv1, "", v, "")
    vp = node(m, unreal.MaterialExpressionPower, -1000, 500)
    connect(v, "", vp, "Base")
    four = node(m, unreal.MaterialExpressionConstant, -1150, 600, r=4.0)
    connect(four, "", vp, "Exp")
    fade = node(m, unreal.MaterialExpressionOneMinus, -850, 500)
    connect(vp, "", fade, "")
    fres = node(m, unreal.MaterialExpressionFresnel, -600, 400)
    base_op = node(m, unreal.MaterialExpressionScalarParameter, -600, 550,
                   parameter_name="Opacity", default_value=0.13)
    fres_k = node(m, unreal.MaterialExpressionMultiply, -500, 400)
    connect(fres, "", fres_k, "A")
    connect(node(m, unreal.MaterialExpressionConstant, -600, 470, r=0.3), "",
            fres_k, "B")
    a1 = node(m, unreal.MaterialExpressionAdd, -400, 450)
    connect(base_op, "", a1, "A")
    connect(fres_k, "", a1, "B")
    a2 = node(m, unreal.MaterialExpressionAdd, -300, 350)
    connect(a1, "", a2, "A")
    connect(absn, "", a2, "B")
    op = node(m, unreal.MaterialExpressionMultiply, -200, 450)
    connect(a2, "", op, "A")
    connect(fade, "", op, "B")
    sat = node(m, unreal.MaterialExpressionSaturate, -100, 450)
    connect(op, "", sat, "")
    mel.connect_material_property(sat, "", unreal.MaterialProperty.MP_OPACITY)
    col = node(m, unreal.MaterialExpressionVectorParameter, -300, -250,
               parameter_name="WaterColor",
               default_value=unreal.LinearColor(0.85, 0.92, 0.95, 1))
    mel.connect_material_property(col, "",
                                  unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(
        node(m, unreal.MaterialExpressionConstant, -300, -100, r=0.05), "",
        unreal.MaterialProperty.MP_ROUGHNESS)
    # faint self-glow so the water still reads at night
    glow = node(m, unreal.MaterialExpressionMultiply, -150, -150)
    connect(col, "", glow, "A")
    connect(node(m, unreal.MaterialExpressionScalarParameter, -300, -50,
                 parameter_name="Glow", default_value=0.12), "", glow, "B")
    mel.connect_material_property(glow, "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    el.save_loaded_asset(m, False)
    return m


def import_meshes(folder, mat):
    meshes = {}
    for name in ("jet_column", "jet_bell", "jet_crown"):
        dest = "%s/%s" % (CONTENT, name)
        found = [d for d in unreal.AssetRegistryHelpers.get_asset_registry()
                 .get_assets_by_path(dest, True)
                 if str(d.asset_class_path.asset_name) == "StaticMesh"]
        if not found:
            t = unreal.AssetImportTask()
            t.set_editor_property("filename",
                                  os.path.join(folder, "jets", name + ".glb"))
            t.set_editor_property("destination_path", dest)
            for k in ("automated", "replace_existing", "save"):
                t.set_editor_property(k, True)
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
            found = [d for d in unreal.AssetRegistryHelpers
                     .get_asset_registry().get_assets_by_path(dest, True)
                     if str(d.asset_class_path.asset_name) == "StaticMesh"]
        mesh = found[0].get_asset()
        mesh.set_material(0, mat)
        ns = mesh.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)      # translucent
        mesh.set_editor_property("nanite_settings", ns)
        el.save_loaded_asset(mesh, False)
        meshes[name] = mesh
    return meshes


def water_level(world, p):
    """Water surface (or basin floor) under a fountain's effect point."""
    h = unreal.SystemLibrary.line_trace_single(
        world, unreal.Vector(p[0], p[1], p[2] + 150),
        unreal.Vector(p[0], p[1], p[2] - 600),
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
        unreal.DrawDebugTrace.NONE, True)
    return h.to_tuple()[4].z if h else p[2]


def kind(fx):
    low = fx.lower()
    if "stream" in low:
        return "stream"
    if "large" in low:
        return "large"
    if "geo" in low:
        return "geo"
    return "normal"


def place(meshes, fountains):
    world = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem).get_editor_world()
    for a in asub.get_all_level_actors():
        if a.get_actor_label().startswith("Jet_"):
            asub.destroy_actor(a)
    n = 0
    for i, f in enumerate(fountains):
        h, r = SIZES[kind(f["fx"])]
        z = water_level(world, f["p"])
        x, y = f["p"][0], f["p"][1]
        parts = (
            ("jet_column", (x, y, z), (h / 100 * 0.6, h / 100 * 0.6, h / 100)),
            ("jet_bell", (x, y, z + h), (r / 100 * 0.85, r / 100 * 0.85,
                                         h / 100 * 0.95)),
            ("jet_crown", (x, y, z), (r / 60, r / 60, r / 100)),
        )
        for name, loc, scale in parts:
            a = asub.spawn_actor_from_object(meshes[name], unreal.Vector(*loc))
            a.set_actor_scale3d(unreal.Vector(*scale))
            a.set_actor_label("Jet_%d_%s" % (i, name[4:]))
            a.set_folder_path("CoH/Fountains")
            c = a.static_mesh_component
            c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            c.set_editor_property("cast_shadow", False)
            n += 1
    log("water jets: %d pieces on %d fountains" % (n, len(fountains)))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    folder = args[0]
    fountains = json.load(open(os.path.join(folder, "fountains.json")))
    mat = build_material()
    meshes = import_meshes(folder, mat)
    place(meshes, fountains)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


main()

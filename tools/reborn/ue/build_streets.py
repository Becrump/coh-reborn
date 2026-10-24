"""Step 7: street splines and street lights (PCG).

Reads roads.json (since stage 2: build_road_surface.py, the approved dense
plan). Every avenue / street piece becomes a spline actor (BP_RebornZone,
tagged RebornRoad and RebornRoad_W<width>) at the shared road height every
20 m. PCG_Reborn_Streets puts street lights on both sidewalks every 40 m
(BP_RebornStreetLamp: the modern street light mesh plus a spot light; lamp
glow and light follow MPC_Reborn.Night).
Curbs, markings, asphalt and sidewalks are the road surface meshes of
stage 2 (ue/build_road_surface.py), no longer made here."""
import json
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa
import build_pcg as P  # noqa  (graph helpers; importing does not run it)

require_map()
roads = json.load(open(os.path.join(OUT, "roads.json")))
RD = ROOT + "/Roads"
MAT = ROOT + "/Materials"
MPC = el.load_asset(MAT + "/MPC_Reborn")


def box_mesh(name, sx, sy, sz):
    path = RD + "/" + name
    if el.does_asset_exist(path):
        return el.load_asset(path)
    m = el.duplicate_asset("/Engine/BasicShapes/Cube", path)
    sm = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    bs = sm.get_lod_build_settings(m, 0)
    bs.set_editor_property("build_scale3d", unreal.Vector(sx, sy, sz))
    sm.set_lod_build_settings(m, 0, bs)
    el.save_loaded_asset(m)
    return m


def paint_material():
    path = MAT + "/M_Reborn_Paint"
    if el.does_asset_exist(path):
        return el.load_asset(path)
    m = new_material(path)
    c = expr(m, unreal.MaterialExpressionVectorParameter, -400, 0, parameter_name="Color",
             default_value=unreal.LinearColor(0.8, 0.8, 0.78, 1))
    r = expr(m, unreal.MaterialExpressionConstant, -400, 200, r=0.55)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(m)
    el.save_loaded_asset(m)
    return m


def mi(name, parent, color):
    path = MAT + "/" + name
    m = el.load_asset(path) or tools.create_asset(name, MAT, unreal.MaterialInstanceConstant,
                                                   unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(m, parent)
    mel.set_material_instance_vector_parameter_value(m, "Color", unreal.LinearColor(*color, 1))
    el.save_loaded_asset(m)
    return m


def night_materials():
    """lamp glow and the spot light's light function, both scaled by Night"""
    led = MAT + "/M_Reborn_LampGlow"
    if not el.does_asset_exist(led):
        m = new_material(led)
        n = expr(m, unreal.MaterialExpressionCollectionParameter, -600, 0, collection=MPC, parameter_name="Night")
        c = expr(m, unreal.MaterialExpressionConstant3Vector, -600, 150, constant=unreal.LinearColor(40, 34, 26, 1))
        mul = expr(m, unreal.MaterialExpressionMultiply, -300, 0)
        link(n, "", mul, "A")
        link(c, "", mul, "B")
        base = expr(m, unreal.MaterialExpressionConstant3Vector, -300, 250, constant=unreal.LinearColor(0.6, 0.6, 0.55, 1))
        mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
        mel.recompile_material(m)
        el.save_loaded_asset(m)
    lf = MAT + "/M_Reborn_NightLight"
    if not el.does_asset_exist(lf):
        m = new_material(lf)
        m.set_editor_property("material_domain", unreal.MaterialDomain.MD_LIGHT_FUNCTION)
        n = expr(m, unreal.MaterialExpressionCollectionParameter, -300, 0, collection=MPC, parameter_name="Night")
        mel.connect_material_property(n, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        mel.recompile_material(m)
        el.save_loaded_asset(m)
    return el.load_asset(led), el.load_asset(lf)


def lamp_blueprint(glow, lf):
    path = RD + "/BP_RebornStreetLamp"
    if el.does_asset_exist(path):
        return el.load_blueprint_class(path)
    f = unreal.BlueprintFactory()
    f.set_editor_property("parent_class", unreal.Actor)
    bp = tools.create_asset("BP_RebornStreetLamp", RD, unreal.Blueprint, f)
    ss = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    root = ss.k2_gather_subobject_data_for_blueprint(bp)[0]
    h_mesh, _ = ss.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=root, new_class=unreal.StaticMeshComponent,
                                                                  blueprint_context=bp))
    h_light, _ = ss.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=root, new_class=unreal.SpotLightComponent,
                                                                   blueprint_context=bp))
    mesh = lib.get_object(lib.get_data(h_mesh))
    mesh.set_editor_property("static_mesh", el.load_asset(
        "/Game/CoH/Props/modern_streetlight/modern_streetlight/StaticMeshes/modern_streetlight"))
    mesh.set_editor_property("override_materials", [None, None, glow])
    light = lib.get_object(lib.get_data(h_light))
    light.set_editor_property("relative_location", unreal.Vector(150, 0, 640))
    light.set_editor_property("relative_rotation", unreal.Rotator(pitch=-90, yaw=0, roll=0))
    light.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    light.set_editor_property("intensity", 12000.0)
    light.set_editor_property("attenuation_radius", 2600.0)
    light.set_editor_property("outer_cone_angle", 62.0)
    light.set_editor_property("inner_cone_angle", 25.0)
    light.set_editor_property("light_color", unreal.Color(255, 214, 170, 255))
    light.set_editor_property("cast_shadows", False)
    # no light function: at 9,000 lm the lamps are lost in 75,000 lux daylight,
    # and the light function left them dark at night
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    el.save_loaded_asset(bp)
    return el.load_blueprint_class(path)


# ------------------------------------------------------------ assets
curb = box_mesh("SM_Reborn_Curb", 1.0, 0.3, 0.2)
line = box_mesh("SM_Reborn_Line", 1.0, 0.12, 0.02)
dash = box_mesh("SM_Reborn_Dash", 3.0, 0.15, 0.02)
paint = paint_material()
white = mi("MI_Reborn_PaintWhite", paint, (0.85, 0.85, 0.82))
yellow = mi("MI_Reborn_PaintYellow", paint, (0.9, 0.65, 0.08))
concrete = mi("MI_Reborn_Curb", paint, (0.2, 0.2, 0.19))
glow, lf = night_materials()
lamp_cls = lamp_blueprint(glow, lf)

# ------------------------------------------------------------ road splines
zone_cls = el.load_blueprint_class(ROOT + "/Layout/BP_RebornZone")
for a in actors.get_all_level_actors():
    if str(a.get_folder_path()).startswith("AtlasReborn/Roads"):
        actors.destroy_actor(a)
widths = set()
for r in roads["roads"]:
    w = int(round(r["width"]))
    widths.add(w)
    dense = r["dense"]
    a = actors.spawn_actor_from_class(zone_cls, unreal.Vector(dense[0][0] * 100, dense[0][1] * 100, 0))
    a.set_actor_label("Road_%03d" % r["id"])
    a.set_folder_path("AtlasReborn/Roads")
    a.set_editor_property("tags", ["RebornRoad", "RebornRoad_W%d" % w])
    s = a.get_component_by_class(unreal.SplineComponent)
    s.clear_spline_points(False)
    for x, y, z in dense:
        s.add_spline_point(unreal.Vector(x * 100, y * 100, z * 100 + 2), unreal.SplineCoordinateSpace.WORLD, False)
    for i in range(len(dense)):
        s.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
    s.set_closed_loop(False, True)
    mark_spline_edited(s)
print("road splines", len(roads["roads"]))

# ------------------------------------------------------------ PCG graph
g = P.new_graph("PCG_Reborn_Streets")


def spline_mesh(x, y, src, mesh, mat, off_y, off_z):
    n, s = P.node(g, unreal.PCGSpawnSplineMeshSettings, x, y)
    d = s.get_editor_property("spline_mesh_descriptor")
    d.set_editor_property("static_mesh", mesh)
    d.set_editor_property("override_materials", [mat])
    d.set_editor_property("cast_shadow", mesh == curb)
    s.set_editor_property("spline_mesh_descriptor", d)
    p = s.get_editor_property("spline_mesh_params")
    p.set_editor_property("scale_mesh_to_bounds", False)
    p.set_editor_property("start_offset", unreal.Vector2D(off_y, off_z))
    p.set_editor_property("end_offset", unreal.Vector2D(off_y, off_z))
    s.set_editor_property("spline_mesh_params", p)
    P.edge(g, src, "Out", n, "In")
    P.edge(g, n, "Out", g.get_output_node(), "Out")


def sampler(x, y, src, spacing, start=0.0):
    n, s = P.node(g, unreal.PCGSplineSamplerSettings, x, y)
    sp = s.get_editor_property("sampler_params")
    sp.set_editor_property("mode", unreal.PCGSplineSamplingMode.DISTANCE)
    sp.set_editor_property("distance_increment", spacing)
    sp.set_editor_property("start_offset", start)
    s.set_editor_property("sampler_params", sp)
    P.edge(g, src, "Out", n, "Spline")
    return n


def shift(x, y, src, dy, yaw=0.0, dz=0.0):
    n, _ = P.node(g, unreal.PCGTransformPointsSettings, x, y, offset_min=unreal.Vector(0, dy, dz),
                  offset_max=unreal.Vector(0, dy, dz), rotation_min=unreal.Rotator(yaw=yaw),
                  rotation_max=unreal.Rotator(yaw=yaw))
    P.edge(g, src, "Out", n, "In")
    return n


def mesh_spawn(x, y, srcs, mesh, mat):
    n, s = P.node(g, unreal.PCGStaticMeshSpawnerSettings, x, y)
    e = unreal.PCGMeshSelectorWeightedEntry()
    d = e.get_editor_property("descriptor")
    d.set_editor_property("static_mesh", mesh)
    d.set_editor_property("override_materials", [mat])
    d.set_editor_property("cast_shadow", False)
    d.set_editor_property("instance_end_cull_distance", 30000)
    e.set_editor_property("descriptor", d)
    e.set_editor_property("weight", 1)
    s.set_editor_property("mesh_selector_type", unreal.PCGMeshSelectorWeighted)
    s.get_editor_property("mesh_selector_parameters").set_editor_property("mesh_entries", [e])
    for src in srcs:
        P.edge(g, src, "Out", n, "In")
    P.edge(g, n, "Out", g.get_output_node(), "Out")


y = 0
for w in sorted(widths):
    gs_n, gs = P.node(g, unreal.PCGGetSplineSettings, 0, y)
    P.by_tag(gs, "RebornRoad_W%d" % w)
    half = w * 50.0
    # on the sidewalk, 1.1 m out from the curb face, 15 cm up
    s40 = sampler(400, y + 1100, gs_n, 4000.0, 800.0)
    l1 = shift(700, y + 1100, s40, half + 110, yaw=-90.0, dz=15.0)
    l2 = shift(700, y + 1260, s40, -(half + 110), yaw=90.0, dz=15.0)
    sp, ss = P.node(g, unreal.PCGSpawnActorSettings, 1000, y + 1160, template_actor_class=lamp_cls,
                    option=unreal.PCGSpawnActorOption.NO_MERGING)
    P.edge(g, l1, "Out", sp, "In")
    P.edge(g, l2, "Out", sp, "In")
    P.edge(g, sp, "Out", g.get_output_node(), "Out")
    y += 1600
comp = P.volume("PCG_Reborn_Streets", g)
comp.generate(True)
print("streets graph generated for widths", sorted(widths))

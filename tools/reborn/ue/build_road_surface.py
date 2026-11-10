"""Stage 2: put the road surface tiles in the level (after build_road_surface.py
and blender/road_tiles.py).

    python ue/run.py ue/build_road_surface.py

  * materials: M_Reborn_Asphalt (dark, even, a faint large-scale variation
    only), M_Reborn_Sidewalk (light concrete with paving joints every 1.5 m),
    M_Reborn_Curb (concrete); paint uses MI_Reborn_PaintWhite / Yellow
  * imports road_tiles/fbx/*.fbx into /Game/AtlasReborn/RoadSurface (collision
    from the mesh itself, so the hero walks on the road and sidewalks) and
    places one actor per tile in AtlasReborn/RoadSurface
  * removes the old road pieces: the street splines and the PCG curb / line /
    dash / lamp output (build_streets.py rebuilds the lamps on the new
    streets)
REBORN_ONLY=materials|tiles|clear limits it to one part.
"""
import glob
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
ONLY = os.environ.get("REBORN_ONLY")
DST = ROOT + "/RoadSurface"
MAT = ROOT + "/Materials"
FOLDER = "AtlasReborn/RoadSurface"
SRC = os.path.join(OUT, "road_tiles", "fbx")


def scalar(m, x, y, v):
    return expr(m, unreal.MaterialExpressionConstant, x, y, r=v)


def world_xy(m, x, y, div):
    wp = expr(m, unreal.MaterialExpressionWorldPosition, x - 400, y)
    xy = expr(m, unreal.MaterialExpressionComponentMask, x - 250, y, r=True, g=True, b=False, a=False)
    link(wp, "", xy, "")
    d = expr(m, unreal.MaterialExpressionDivide, x - 100, y, const_b=div)
    link(xy, "", d, "A")
    return d


def asphalt_material():
    path = MAT + "/M_Reborn_Asphalt"
    m = el.load_asset(path) or new_material(path)
    mel.delete_all_material_expressions(m)
    # base: dark grey; a very faint 40 m variation and a fine grain so it
    # doesn't look like plastic - no blotches
    base = expr(m, unreal.MaterialExpressionConstant3Vector, -400, 0, constant=unreal.LinearColor(0.032, 0.030, 0.028, 1))   # slightly warm: the comic grade cools darks
    big = expr(m, unreal.MaterialExpressionTextureSample, -700, 200,
               texture=el.load_asset("/Game/CitySampleVehicles/Material/MaterialLayer/Textures/T_Concrete_03_C"))
    link(world_xy(m, -900, 200, 4000.0), "", big, "UVs")
    fine = expr(m, unreal.MaterialExpressionTextureSample, -700, 450,
                texture=el.load_asset("/Game/CitySampleVehicles/Material/MaterialLayer/Textures/T_Concrete_03_C"))
    link(world_xy(m, -900, 450, 120.0), "", fine, "UVs")
    v1 = expr(m, unreal.MaterialExpressionLinearInterpolate, -450, 250, const_a=0.92, const_b=1.08)
    link(big, "G", v1, "Alpha")
    v2 = expr(m, unreal.MaterialExpressionLinearInterpolate, -450, 450, const_a=0.94, const_b=1.06)
    link(fine, "G", v2, "Alpha")
    mul = expr(m, unreal.MaterialExpressionMultiply, -250, 100)
    link(base, "", mul, "A")
    link(v1, "", mul, "B")
    mul2 = expr(m, unreal.MaterialExpressionMultiply, -100, 100)
    link(mul, "", mul2, "A")
    link(v2, "", mul2, "B")
    mel.connect_material_property(mul2, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(m, -200, 400, 0.85), "", unreal.MaterialProperty.MP_ROUGHNESS)
    # low specular: no grey sheen at grazing angles
    mel.connect_material_property(scalar(m, -200, 500, 0.2), "", unreal.MaterialProperty.MP_SPECULAR)
    mel.recompile_material(m)
    el.save_loaded_asset(m)
    return m


def concrete_material(name, color, joints, rough):
    path = MAT + "/" + name
    m = el.load_asset(path) or new_material(path)
    mel.delete_all_material_expressions(m)
    m.set_editor_property("two_sided", True)
    base = expr(m, unreal.MaterialExpressionConstant3Vector, -400, 0, constant=unreal.LinearColor(*color, 1))
    tex = expr(m, unreal.MaterialExpressionTextureSample, -700, 200,
               texture=el.load_asset("/Game/CitySampleBuildings/Textures/ConcreteDirty/T_ConcreteDirty_C"))
    link(world_xy(m, -900, 200, 600.0), "", tex, "UVs")
    v = expr(m, unreal.MaterialExpressionLinearInterpolate, -450, 200, const_a=0.9, const_b=1.1)
    link(tex, "G", v, "Alpha")
    col = expr(m, unreal.MaterialExpressionMultiply, -250, 0)
    link(base, "", col, "A")
    link(v, "", col, "B")
    out = col
    if joints:
        # paving joints: thin darker lines on the mesh UVs (1 unit = 1.5 m)
        tc = expr(m, unreal.MaterialExpressionTextureCoordinate, -900, 500)
        fr = expr(m, unreal.MaterialExpressionFrac, -750, 500)
        link(tc, "", fr, "")
        code = expr(m, unreal.MaterialExpressionCustom, -550, 500)
        code.set_editor_property("code", "float2 d = min(UV, 1 - UV); return 1 - 0.35 * (1 - smoothstep(0.0, 0.02, min(d.x, d.y)));")
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", "UV")
        code.set_editor_property("inputs", [ci])
        code.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        link(fr, "", code, "UV")
        j = expr(m, unreal.MaterialExpressionMultiply, -100, 0)
        link(col, "", j, "A")
        link(code, "", j, "B")
        out = j
    mel.connect_material_property(out, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(m, -200, 400, rough), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(m)
    el.save_loaded_asset(m)
    return m


if ONLY in (None, "materials", "tiles"):
    mats = {
        "Asphalt": asphalt_material(),
        "Curb": concrete_material("M_Reborn_Curb", (0.3, 0.3, 0.29), False, 0.75),
        "Sidewalk": concrete_material("M_Reborn_Sidewalk", (0.2, 0.2, 0.19), True, 0.8),
        "PaintWhite": el.load_asset(MAT + "/MI_Reborn_PaintWhite"),
        "PaintYellow": el.load_asset(MAT + "/MI_Reborn_PaintYellow"),
    }
    print("materials ready")

if ONLY in (None, "clear"):
    gone = 0
    for a in actors.get_all_level_actors():
        f = str(a.get_folder_path())
        if f.startswith("AtlasReborn/Roads") or f.startswith(FOLDER):
            actors.destroy_actor(a)
            gone += 1
    for a in find(label="PCG_Reborn_Streets"):
        c = a.get_component_by_class(unreal.PCGComponent)
        if c:
            c.cleanup(True)
    print("old road pieces removed:", gone)

if ONLY in (None, "tiles"):
    for a in actors.get_all_level_actors():
        if str(a.get_folder_path()).startswith(FOLDER):
            actors.destroy_actor(a)
    files = sorted(glob.glob(os.path.join(SRC, "*.fbx")))
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.filename = f
        t.destination_path = DST
        t.destination_name = os.path.splitext(os.path.basename(f))[0]
        t.replace_existing = True
        t.automated = True
        t.save = True
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    placed = 0
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        mesh = el.load_asset(DST + "/" + name)
        if not mesh:
            print("missing", name)
            continue
        for i, slot in enumerate(mesh.get_editor_property("static_materials")):
            sn = str(slot.get_editor_property("material_slot_name"))
            for k, m in mats.items():
                if sn.startswith(k):
                    mesh.set_material(i, m)
        bs = mesh.get_editor_property("body_setup")
        if bs:
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        el.save_loaded_asset(mesh)
        # tile corner from the name: SM_Road_T_p0250_m0500 -> (250, -500) m
        _, _, _, sx, sy = name.split("_")
        tx = float(sx[1:]) * (-1 if sx[0] == "m" else 1)
        ty = float(sy[1:]) * (-1 if sy[0] == "m" else 1)
        a = actors.spawn_actor_from_object(mesh, unreal.Vector(tx * 100, ty * 100, 0))
        a.set_actor_label(name.replace("SM_", ""))
        a.set_folder_path(FOLDER)
        c = a.static_mesh_component
        c.set_editor_property("cast_shadow", False)
        c.set_collision_profile_name("BlockAll")
        placed += 1
    print("road tiles placed", placed, "of", len(files))

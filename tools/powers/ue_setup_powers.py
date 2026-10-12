"""Editor step for the power system (run inside the open editor):

    python unreal/scripts/ue_exec.py - < tools/powers/ue_setup_powers.py

Before it, copy the data into the project (Unreal would try to import .json
and .png files under Content, so they get their own extensions):
  export_powers.py JSON -> Content/CoH/Data/Powers/<name>.cohdata
  export_icons.py PNGs  -> Content/CoH/Data/Icons/<name>.cohicon
The game reads both at runtime (importing 1,250 icons as assets takes over
an hour in the editor).

1. Creates M_CoH_PowerFX: unlit additive glow with Colour and Opacity
   parameters, used by the placeholder power effects (bolts, bursts, cones).
2. Places one CoHEnemySpawner in AtlasPark_Reborn (wandering faction groups)
   and saves the level.
"""
import unreal

el = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# 1. effect material
MAT = "/Game/CoH/FX/M_CoH_PowerFX"
if not el.does_asset_exist(MAT):
    m = tools.create_asset("M_CoH_PowerFX", "/Game/CoH/FX", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("two_sided", True)
    mel = unreal.MaterialEditingLibrary
    col = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -600, 0)
    col.set_editor_property("parameter_name", "Colour")
    col.set_editor_property("default_value", unreal.LinearColor(1, 0.5, 0.1, 1))
    op = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -600, 200)
    op.set_editor_property("parameter_name", "Opacity")
    op.set_editor_property("default_value", 1.0)
    glow = mel.create_material_expression(m, unreal.MaterialExpressionConstant, -600, 320)
    glow.set_editor_property("r", 6.0)
    # brighter at the rim: fresnel lifts the edges of spheres and cones
    fr = mel.create_material_expression(m, unreal.MaterialExpressionFresnel, -600, 420)
    add = mel.create_material_expression(m, unreal.MaterialExpressionAdd, -420, 420)
    base = mel.create_material_expression(m, unreal.MaterialExpressionConstant, -600, 520)
    base.set_editor_property("r", 0.35)
    mel.connect_material_expressions(fr, "", add, "A")
    mel.connect_material_expressions(base, "", add, "B")
    m1 = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -380, 0)
    m2 = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -240, 100)
    m3 = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -120, 200)
    mel.connect_material_expressions(col, "", m1, "A")
    mel.connect_material_expressions(glow, "", m1, "B")
    mel.connect_material_expressions(m1, "", m2, "A")
    mel.connect_material_expressions(op, "", m2, "B")
    mel.connect_material_expressions(m2, "", m3, "A")
    mel.connect_material_expressions(add, "", m3, "B")
    mel.connect_material_property(m3, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    el.save_loaded_asset(m)
    print("material created")

# 2. spawner in Atlas Park Reborn
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if world.get_path_name().startswith("/Game/AtlasReborn/AtlasPark_Reborn"):
    if not [a for a in actors.get_all_level_actors() if isinstance(a, unreal.CoHEnemySpawner)]:
        s = actors.spawn_actor_from_class(unreal.CoHEnemySpawner, unreal.Vector(0, 0, 500))
        s.set_actor_label("Reborn_EnemySpawner")
        s.set_folder_path("AtlasReborn/Gameplay")
        unreal.EditorLoadingAndSavingUtils.save_map(world, "/Game/AtlasReborn/AtlasPark_Reborn")
        print("spawner placed")
else:
    print("open AtlasPark_Reborn to place the spawner (current:", world.get_path_name(), ")")

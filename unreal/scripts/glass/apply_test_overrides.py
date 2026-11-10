"""Put one glass option on the TEST SET only, as per-actor material overrides.

  GLASS_OPTION = none | Reflective | Smudgy | Interior   (env var, default none)

Run with tools/reborn/ue/run.py-style env, e.g. from the coh-reborn repo:
  python -c "import os;print('import os\\nos.environ[\\'GLASS_OPTION\\']=\\'Smudgy\\'\\n'+open('unreal/scripts/glass/apply_test_overrides.py').read())" | python unreal/scripts/ue_exec.py -

Never touches the mesh assets or the original CoH material instances: it only writes
StaticMeshComponent.OverrideMaterials on the test actors (option "none" clears them).
Per-texture children live in /Game/GlassUpgrade/PerTexture (one per option x original texture).
"""
import json
import os
import unreal

OPTION = os.environ.get("GLASS_OPTION", "none")
# Existing per-texture children are reused as-is; GLASS_REFRESH=1 re-applies their parameters.
# (Every update/save of a material instance costs editor-thread work; an earlier version redid
# all of them on each run and a long recompile session ended in a Windows USER-object crash.)
REFRESH = os.environ.get("GLASS_REFRESH") == "1"
FOLDER = "/Game/GlassUpgrade"
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    r"C:\Users\rtcru\ClaudeProjects\coh-reborn-dm8n7k\unreal\scripts\glass"
MASKS = json.load(open(os.path.join(HERE, "window_masks.json")))

# The CoH towers are baked per map tile: one Nanite actor holds every building of a tile,
# so the smallest unit we can override without touching meshes is a tile actor.
TEST_ACTORS = ["Nanite_tile_2_3_Solid_01", "Nanite_tile_3_3_Solid_00"]
# Interior theme per actor -> Custom Primitive Data[0] (0 office, 1 residential, 2 retail), [1] = random seed.
# Tile 3_3 (centre + right towers) office; tile 2_3 (tall left tower) residential as a comparison demo.
THEMES = {"Nanite_tile_2_3_Solid_01": 1.0, "Nanite_tile_3_3_Solid_00": 0.0}
# GLASS_SCOPE=skyscrapers: every original Nanite tile actor with a skyscraper window (approved 2026-10-20)
# GLASS_SCOPE=all: every original Nanite tile actor with any WINDOWS material (approved 2026-10-21)
SCOPE = os.environ.get("GLASS_SCOPE", "test")
# original window MI -> (texture key in window_masks.json, panes across, panes down (0 = same), theme, extra)
# theme: -1 = per-actor Custom Primitive Data (THEMES), 0 office, 1 residential, 2 retail.
# extra: "masked" = original was alpha-cut (instance overrides blend mode to Masked), "mirror" = no rooms.
WINDOWS = {
    "x_deco_skyscraper_02_window_01": ("deco_skyscraper_02_window_01_b", 2, 0, -1, ""),
    "x_deco_skyscraper_03_window_01": ("deco_building_03_window_01_b", 2, 0, -1, ""),
    "x_deco_skyscraper_03_window_03": ("deco_building_03_window_03_b", 3, 0, -1, ""),
    "x_deco_skyscraper_08_window_01": ("deco_building_08_window_01_b", 1, 0, -1, ""),
    # low-rise and storefront windows (GLASS_SCOPE=all); skipped as not windows: ArchEnt lounge logo wall,
    # Storefront_Window_Metal (64 px noise), ofc1_windowframe (32 px noise), Auction House green glass
    "Store_Front_Window_2_tga": ("Store_Front_Window_2", 8, 2, 2, ""),
    "Store_Front_Window_3_tga": ("Store_Front_Window_3", 8, 2, 2, ""),
    "Store_Front_Window_4_tga": ("Store_Front_Window_4", 8, 2, 2, ""),
    "Store_Front_Stucco_1d_Window_1_tga": ("Store_Front_Stucco_1d_Window_1", 4, 2, 2, "masked"),
    "BrickBuild_Window_02_tga": ("BrickBuild_Window_02", 4, 2, 1, "masked"),
    "BrickBuild_Window_04_tga": ("BrickBuild_Window_04", 2, 2, 1, "masked"),
    "X_Praet_BrickC_Window1_LOD1": ("P_BrickC_Window_d", 2, 1, 1, ""),
    "X_Praet_BrickA_StoneWindow": ("P_BrickA_StoneWindow_d", 2, 2, 1, ""),
    "X_FW_BrickC_RndWin": ("Bld_SkyB_Base01_d", 2, 3, 0, ""),
    "X_ArchEnt_Window_01": ("Arch_Ent_Window_GlassWall_01", 4, 1, 0, ""),
    "X_ArchEnt_Window_02": ("Arch_Ent_Window_GlassCube_01", 2, 2, 0, ""),
    "x_p_warehouse_shipwindow01": ("p_warehouse_shipwindow01_b", 6, 6, 0, "mirror"),
}
SKYSCRAPERS = {k for k, v in WINDOWS.items() if v[3] == -1}
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def params(mi):
    tex = {str(p.parameter_info.name): p.parameter_value for p in mi.get_editor_property("texture_parameter_values")}
    vec = {str(p.parameter_info.name): p.parameter_value for p in mi.get_editor_property("vector_parameter_values")}
    return tex, vec


def child_for(option, orig):
    key, panes, panes_y, theme, extra = WINDOWS[orig.get_name()]
    name = "MI_Glass_%s_%s" % (option, key[:-2] if key.endswith("_b") else key)
    path = "%s/PerTexture/%s" % (FOLDER, name)
    if EAL.does_asset_exist(path) and not REFRESH:
        return unreal.load_asset(path)  # already set up: no update, no save, no shader work
    mi = unreal.load_asset(path) if EAL.does_asset_exist(path) else tools.create_asset(
        name, FOLDER + "/PerTexture", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, unreal.load_asset("%s/MI_Glass_%s" % (FOLDER, option)))
    tex, vec = params(orig)
    MEL.set_material_instance_texture_parameter_value(mi, "WindowTexture", tex["BaseColorTexture"])
    if tex.get("NormalTexture"):
        MEL.set_material_instance_texture_parameter_value(mi, "NormalTexture", tex["NormalTexture"])
    if tex.get("GlowTexture"):  # keep the original lit-window pattern for night
        MEL.set_material_instance_texture_parameter_value(mi, "GlowTexture", tex["GlowTexture"])
        gs = vec.get("GlowScale")
        if gs and (gs.r or gs.g):
            MEL.set_material_instance_vector_parameter_value(mi, "GlowUVScale", unreal.LinearColor(gs.r, gs.g, 0, 0))
        MEL.set_material_instance_scalar_parameter_value(mi, "GlowStrength", 1.5 if option != "Interior" else 0.5)
    m = MASKS[key]
    if m.get("key") == "texture":  # hand-painted mask (make_rect_masks.py, imported by import_masks.py)
        MEL.set_material_instance_scalar_parameter_value(mi, "UseMaskTexture", 1.0)
        MEL.set_material_instance_texture_parameter_value(mi, "PaneMaskTexture", unreal.load_asset(m["mask_texture"]))
    else:
        MEL.set_material_instance_vector_parameter_value(mi, "MaskWeights", unreal.LinearColor(*m["MaskWeights"]))
        for k in ("MaskThreshold", "MaskSoftness", "MaskInvert"):
            MEL.set_material_instance_scalar_parameter_value(mi, k, float(m[k]))
    MEL.set_material_instance_scalar_parameter_value(mi, "PanesPerTile", float(panes))
    MEL.set_material_instance_scalar_parameter_value(mi, "PanesPerTileY", float(panes_y))
    MEL.set_material_instance_scalar_parameter_value(mi, "ThemeOverride", float(theme))
    if extra == "mirror":
        MEL.set_material_instance_scalar_parameter_value(mi, "ReflectiveOnlyFraction", 1.0)
    if extra == "masked":  # keep the original alpha cut-outs
        o = mi.get_editor_property("base_property_overrides")
        o.set_editor_property("override_blend_mode", True)
        o.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        cut = {str(p.parameter_info.name): p.parameter_value for p in orig.get_editor_property("scalar_parameter_values")}
        o.set_editor_property("override_opacity_mask_clip_value", True)
        o.set_editor_property("opacity_mask_clip_value", float(cut.get("AlphaCutoff", 0.3)))
        mi.set_editor_property("base_property_overrides", o)
    MEL.update_material_instance(mi)
    EAL.save_loaded_asset(mi)
    return mi


if unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world() is None:
    raise RuntimeError("no editor world (map loading or saving?)")
done = []
touched = []
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    lab = a.get_actor_label()
    if SCOPE in ("skyscrapers", "all"):
        if not lab.startswith("Nanite_tile_"):
            continue
    elif lab not in TEST_ACTORS:
        continue
    comp = a.get_component_by_class(unreal.StaticMeshComponent)
    wanted = SKYSCRAPERS if SCOPE == "skyscrapers" else set(WINDOWS)
    if SCOPE != "test" and not any(
            (comp.get_material(i) and (comp.get_material(i).get_name() in wanted or
                                       comp.get_material(i).get_name().startswith("MI_Glass_")))
            for i in range(comp.get_num_materials())):
        continue
    touched.append(a)
    comp.modify()
    comp.set_editor_property("override_materials", [])  # back to the mesh's own materials
    comp.set_editor_property("custom_primitive_data", unreal.CustomPrimitiveData())
    if OPTION == "Interior":
        comp.set_custom_primitive_data_float(0, THEMES.get(a.get_actor_label(), 0.0))
        comp.set_custom_primitive_data_float(1, float(sum(map(ord, a.get_actor_label())) % 97))
    if OPTION != "none":
        for i in range(comp.get_num_materials()):
            orig = comp.get_material(i)
            if orig and orig.get_name() in (SKYSCRAPERS if SCOPE == "skyscrapers" else WINDOWS):
                comp.set_material(i, child_for(OPTION, orig))
                done.append("%s[%d] %s" % (a.get_actor_label(), i, orig.get_name()))
print("option", OPTION, "actors", len(touched), "slots", len(done))
print("overrides:", done)
if os.environ.get("GLASS_SAVE") == "1":  # save only the touched actors' external packages
    pk = [a.get_package() for a in touched]
    print("saved", unreal.EditorLoadingAndSavingUtils.save_packages(pk, True), [p.get_name() for p in pk])
if OPTION != "none" and not done:
    raise RuntimeError("test actors or window slots not found")

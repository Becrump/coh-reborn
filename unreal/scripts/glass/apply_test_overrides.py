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
FOLDER = "/Game/GlassUpgrade"
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    r"C:\Users\rtcru\ClaudeProjects\coh-reborn-dm8n7k\unreal\scripts\glass"
MASKS = json.load(open(os.path.join(HERE, "window_masks.json")))

# The CoH towers are baked per map tile: one Nanite actor holds every building of a tile,
# so the smallest unit we can override without touching meshes is a tile actor.
TEST_ACTORS = ["Nanite_tile_2_3_Solid_01", "Nanite_tile_3_3_Solid_00"]
# original window MI -> (base colour texture key in window_masks.json, panes per texture tile)
WINDOWS = {
    "x_deco_skyscraper_02_window_01": ("deco_skyscraper_02_window_01_b", 2),
    "x_deco_skyscraper_03_window_01": ("deco_building_03_window_01_b", 2),
    "x_deco_skyscraper_03_window_03": ("deco_building_03_window_03_b", 3),
    "x_deco_skyscraper_08_window_01": ("deco_building_08_window_01_b", 1),
}
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def params(mi):
    tex = {str(p.parameter_info.name): p.parameter_value for p in mi.get_editor_property("texture_parameter_values")}
    vec = {str(p.parameter_info.name): p.parameter_value for p in mi.get_editor_property("vector_parameter_values")}
    return tex, vec


def child_for(option, orig):
    key, panes = WINDOWS[orig.get_name()]
    name = "MI_Glass_%s_%s" % (option, key.replace("_b", ""))
    path = "%s/PerTexture/%s" % (FOLDER, name)
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
    MEL.set_material_instance_vector_parameter_value(mi, "MaskWeights", unreal.LinearColor(*m["MaskWeights"]))
    for k in ("MaskThreshold", "MaskSoftness", "MaskInvert"):
        MEL.set_material_instance_scalar_parameter_value(mi, k, float(m[k]))
    MEL.set_material_instance_scalar_parameter_value(mi, "PanesPerTile", float(panes))
    MEL.update_material_instance(mi)
    EAL.save_loaded_asset(mi)
    return mi


if unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world() is None:
    raise RuntimeError("no editor world (map loading or saving?)")
done = []
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    if a.get_actor_label() not in TEST_ACTORS:
        continue
    comp = a.get_component_by_class(unreal.StaticMeshComponent)
    comp.modify()
    comp.set_editor_property("override_materials", [])  # back to the mesh's own materials
    if OPTION != "none":
        for i in range(comp.get_num_materials()):
            orig = comp.get_material(i)
            if orig and orig.get_name() in WINDOWS:
                comp.set_material(i, child_for(OPTION, orig))
                done.append("%s[%d] %s" % (a.get_actor_label(), i, orig.get_name()))
print("option", OPTION, "overrides:", done)
if OPTION != "none" and not done:
    raise RuntimeError("test actors or window slots not found")

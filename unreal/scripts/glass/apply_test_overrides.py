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

# The CoH towers are baked per map tile: one Nanite actor holds every building of a tile,
# so the smallest unit we can override without touching meshes is a tile actor.
TEST_ACTORS = ["Nanite_tile_2_3_Solid_01", "Nanite_tile_3_3_Solid_00"]
# Interior theme per actor -> Custom Primitive Data[0] (0 office, 1 residential, 2 retail), [1] = random seed.
# Tile 3_3 (centre + right towers) office; tile 2_3 (tall left tower) residential as a comparison demo.
THEMES = {"Nanite_tile_2_3_Solid_01": 1.0, "Nanite_tile_3_3_Solid_00": 0.0}
# GLASS_SCOPE=skyscrapers: every original Nanite tile actor with a skyscraper window (approved 2026-10-20)
# GLASS_SCOPE=all: every original Nanite tile actor with any WINDOWS material (approved 2026-10-21)
SCOPE = os.environ.get("GLASS_SCOPE", "test")
# Window table lives in glass_map.json (shared with glaze_zone.py); per-texture instances via glass_common.
import sys
sys.path.insert(0, HERE)
sys.modules.pop("glass_common", None)
import glass_common as gc  # noqa: E402
WINDOWS = {k: (v["texture"], v["panes_x"], v["panes_y"], v["theme"], v["extra"]) for k, v in gc.MAP["windows"].items()}
SKYSCRAPERS = {k for k, v in WINDOWS.items() if v[3] == -1}
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def child_for(option, orig):
    k, v = gc.WINDOWS[gc.norm(orig.get_name())]
    new = []
    mi = gc.glass_child(option, orig, v, refresh=REFRESH, saved=new)
    for p in new:  # only instances created or refreshed on this run
        gc.EAL.save_loaded_asset(mi)
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

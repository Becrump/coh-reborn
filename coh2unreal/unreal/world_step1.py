"""One-world step 1 (docs/zones/city_playable.md): place Atlas and the shifted zones, Atlas's own sky layer off.

Run in the editor (python remote execution), editor otherwise idle:
  1. opens /Game/Zones/L_ParagonCity and loads its ZoneInstance_* Level Instance actors (so place_world.py
     updates them instead of adding duplicates);
  2. runs place_world.py with docs/zones/zone_offsets.json (ATLAS_LEVEL set: Atlas Park at 0,0);
  3. adds the data layer DL_AtlasStandaloneSky to the world with initial runtime state Unloaded, so Atlas's own
     sky, DayNight, life manager and PlayerStarts stay off in the world (they stay on when Atlas runs alone);
  4. saves only the world level's packages.
Env: CITY_REPO (repo root).
"""
import gc
import os
import sys

import unreal

REPO = os.environ["CITY_REPO"]
WORLD = "/Game/Zones/L_ParagonCity"
DL = "/Game/AtlasPark4/DataLayers/DL_AtlasStandaloneSky"


def log(msg):
    print("[world1] " + msg)


for k in ("last_traceback", "last_value", "last_type"):
    setattr(sys, k, None)
gc.collect()
lsub = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
w = ues.get_editor_world()
cur = w.get_path_name() if w else ""
del w
if not cur.startswith(WORLD):
    dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    if dirty:
        raise RuntimeError("unsaved maps open: %s" % dirty)
    lsub.load_level(WORLD)
wpl = unreal.WorldPartitionBlueprintLibrary
ids = [d.guid for d in wpl.get_actor_descs() if str(d.get_editor_property("label")).startswith("ZoneInstance_")]
if ids:
    wpl.load_actors(ids)
log("loaded %d existing zone instance actors" % len(ids))

src = os.path.join(REPO, "coh2unreal", "unreal", "place_world.py")
code = open(src).read().replace("unreal.get_editor_subsystem(\n            unreal.LevelEditorSubsystem).save_current_level()", "None")
sys.argv = ["place_world.py", os.path.join(REPO, "docs", "zones", "zone_offsets.json")]
exec(compile(code, "place_world.py", "exec"), {"__file__": src, "__name__": "__main__"})

asset = unreal.load_asset(DL)
if asset is None:
    log("data layer asset %s not found: Atlas sky stays on in the world" % DL)
else:
    dls = unreal.get_editor_subsystem(unreal.DataLayerEditorSubsystem)
    inst = None
    for i in dls.get_all_data_layers():
        try:
            if i.get_asset() == asset:
                inst = i
        except Exception:
            pass
    if inst is None:
        p = unreal.DataLayerCreationParameters()
        p.set_editor_property("data_layer_asset", asset)
        inst = dls.create_data_layer_instance(p)
    inst.set_editor_property("initial_runtime_state", unreal.DataLayerRuntimeState.UNLOADED)
    log("world data layer %s: initial runtime state %s" % (asset.get_name(), inst.get_editor_property("initial_runtime_state")))

E = unreal.EditorLoadingAndSavingUtils
keep = ("/Game/Zones/L_ParagonCity", "/Game/__ExternalActors__/Zones/L_ParagonCity", "/Game/__ExternalObjects__/Zones/L_ParagonCity")
dirty = E.get_dirty_content_packages() + E.get_dirty_map_packages()
mine = [p for p in dirty if p.get_name().startswith(keep)]
other = [p.get_name() for p in dirty if not p.get_name().startswith(keep)]
if mine:
    E.save_packages(mine, True)
log("saved %d world packages; other dirty left unsaved: %s" % (len(mine), other[:10]))
del mine, dirty
gc.collect()

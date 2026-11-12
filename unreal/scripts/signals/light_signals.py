"""Glowing, cycling traffic signals on every existing map and zone (asset level).

Every MaterialInstanceConstant in the project named traffic_light(.tga) or
traffic_light_pedestrian(.tga) is backed up to /Game/SignalUpgrade/OriginalBackup/...
and re-parented onto /Game/CoH/Materials/M_CoH_TrafficSignal (coh_materials.build_signal),
keeping its textures. Meshes keep their slots, so the Atlas Park Nanite tiles, the reference
map, Galaxy City and every zone imported from the shared library light up together.
New zone imports get the same through apply_tuning.py / the shared Atlas material.

Env:
  SIGNAL_DRY=1      only report what would change
  SIGNAL_REBUILD=1  rebuild the master in place (default: build only if missing)
  SIGNAL_LIFE=1     also point every CoHLifeManager in the open level at MPC_CoHSignals
                    (its SignalClock then drives the lamps; the level is left dirty, not saved)

Run once in the editor (never re-send after a lost connection):
  python unreal/scripts/ue_exec.py - < unreal/scripts/signals/light_signals.py
Rollback: re-parent an original to the parent of its OriginalBackup copy.
"""
import os
import sys

import unreal

REPO_UNREAL = r"C:/Users/rtcru/ClaudeProjects/coh-reborn/coh2unreal/unreal"
here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
for p in (os.path.join(here, "..", "..", "..", "coh2unreal", "unreal"), REPO_UNREAL):
    if os.path.exists(os.path.join(p, "coh_materials.py")):
        sys.path.insert(0, os.path.normpath(p))
        break
sys.modules.pop("coh_materials", None)  # the editor's Python lives on between runs
import coh_materials as cm  # noqa: E402

EAL = unreal.EditorAssetLibrary
DRY = os.environ.get("SIGNAL_DRY") == "1"
BACKUP = "/Game/SignalUpgrade/OriginalBackup"

reg = unreal.AssetRegistryHelpers.get_asset_registry()
flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "MaterialInstanceConstant")],
                      package_paths=["/Game"], recursive_paths=True)
found = []
for d in reg.get_assets(flt):
    path = str(d.package_name)
    if path.startswith("/Game/SignalUpgrade/") or "/OriginalBackup/" in path:
        continue
    ped = cm.signal_kind(str(d.asset_name))
    if ped is not None:
        found.append((path, ped))
print("signal materials found:", len(found))
for p, ped in found:
    print("  %s %s" % ("pedestrian" if ped else "vehicle   ", p))

if not DRY and found:
    path = cm.DIR + "/M_CoH_TrafficSignal"
    signal = cm.build_signal() if os.environ.get("SIGNAL_REBUILD") == "1" or not EAL.does_asset_exist(path) \
        else unreal.load_asset(path)
    to_save = []
    done = already = 0
    for p, ped in found:
        mi = unreal.load_asset(p)
        if mi.get_editor_property("parent") == signal:
            already += 1
            continue
        dst = BACKUP + p[len("/Game"):]
        if not EAL.does_asset_exist(dst):
            dup = EAL.duplicate_asset(p, dst)
            if dup:
                to_save.append(dup.get_package())
        cm.reparent(mi, signal, {"Pedestrian": ped})   # saves the instance itself
        done += 1
    if to_save:
        unreal.EditorLoadingAndSavingUtils.save_packages(to_save, True)
    print("re-parented", done, "already", already, "backups", len(to_save))

if os.environ.get("SIGNAL_LIFE") == "1" and not DRY:
    mpc = cm.signal_collection()
    asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in asub.get_all_level_actors():
        if a.get_class().get_name() == "CoHLifeManager":
            old = a.get_editor_property("signal_collection")
            a.set_editor_property("signal_collection", mpc)
            print("life manager", a.get_actor_label(), "SignalCollection", old and old.get_path_name(), "->",
                  mpc.get_path_name())

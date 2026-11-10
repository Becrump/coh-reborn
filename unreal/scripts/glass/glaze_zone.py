"""Give a zone's original window materials the new glass, at the asset level (no per-actor overrides).

Every MaterialInstanceConstant under the zone folder(s) whose name matches glass_map.json is backed up to
/Game/GlassUpgrade/OriginalBackup/... and then re-parented to its per-texture glass instance
(/Game/GlassUpgrade/PerTexture/MI_Glass_<Option>_<texture>, created on first use). Meshes keep their
default material slots, so every map and future zone that uses these materials gets the glass.

Env (or the first command-line argument for the path):
  GLASS_ZONE_PATH   content folder(s), ';'-separated, e.g. /Game/galaxy_city   (required)
  GLASS_OPTION      Interior (default) | Reflective | Smudgy
  GLASS_DRY=1       only report what would change (default 0)
  GLASS_SAVE=1      save the changed packages: originals, backups, new glass instances (default 1)

Run inside the editor (one call; never re-send it after a lost connection):
  python unreal/scripts/ue_exec.py - < <(echo "import os; os.environ['GLASS_ZONE_PATH']='/Game/galaxy_city'"; cat unreal/scripts/glass/glaze_zone.py)
Unmapped window-like names are only logged (add them to glass_map.json + window_masks.json, then re-run).
Rollback: re-parent an original to its OriginalBackup copy's parent (the backup keeps the old settings).
"""
import os
import sys

import unreal

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    r"C:\Users\rtcru\ClaudeProjects\coh-reborn-dm8n7k\unreal\scripts\glass"
sys.path.insert(0, HERE)
sys.modules.pop("glass_common", None)  # the editor's Python lives on between runs
import glass_common as gc  # noqa: E402

paths = os.environ.get("GLASS_ZONE_PATH") or (sys.argv[1] if len(sys.argv) > 1 else "")
if not paths:
    raise RuntimeError("set GLASS_ZONE_PATH to the zone's content folder")
OPTION = os.environ.get("GLASS_OPTION", "Interior")
DRY = os.environ.get("GLASS_DRY") == "1"
SAVE = os.environ.get("GLASS_SAVE", "1") == "1"

report = {"glass": [], "already": [], "skip": [], "pending": [], "unmapped": []}
to_save = []
for root in [p.strip() for p in paths.split(";") if p.strip()]:
    for asset_path in gc.EAL.list_assets(root, True, False):
        data = gc.EAL.find_asset_data(asset_path)
        if str(data.asset_class_path.asset_name) != "MaterialInstanceConstant":
            continue
        name = str(data.asset_name)
        if name.startswith("MI_Glass_") or "/GlassUpgrade/" in asset_path:
            continue
        kind, entry = gc.lookup(name)
        if kind is None:
            continue
        if kind != "glass":
            report[kind].append(name if kind != "skip" else "%s (%s)" % (name, entry))
            continue
        orig = unreal.load_asset(asset_path)
        parent = orig.get_editor_property("parent")
        if parent and parent.get_name().startswith("MI_Glass_"):
            report["already"].append(name)
            continue
        report["glass"].append(name)
        if DRY:
            continue
        gc.backup(orig, to_save)
        child = gc.glass_child(OPTION, orig, entry, saved=to_save)
        gc.MEL.set_material_instance_parent(orig, child)
        gc.MEL.update_material_instance(orig)
        to_save.append(orig.get_package())

for k, v in report.items():
    print("%-9s %3d  %s" % (k, len(v), ", ".join(sorted(v))))
if to_save and SAVE and not DRY:
    uniq = list({p.get_name(): p for p in to_save}.values())
    ok = unreal.EditorLoadingAndSavingUtils.save_packages(uniq, True)
    print("saved", ok, len(uniq), "packages")

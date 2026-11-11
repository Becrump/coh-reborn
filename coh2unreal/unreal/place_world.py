"""Puts every imported zone into one world at its place on the city map.

Run in the Unreal editor with the world level open (a World Partition
level, e.g. /Game/Zones/L_ParagonCity, made with File > New Level > Open
World or Empty Open World):
    py "<repo>/coh2unreal/unreal/place_world.py" "<repo>/docs/zones/zone_offsets.json"

Each zone stays its own level (/Game/Zones/<Name>/L_<Name>, at zone-local
coordinates, as the zone batch made it). This adds one Level Instance actor
per zone, at the zone's offset_m, with runtime behavior "Partitioned" so the
zone's actors stream with the world's grid (no loading screens). Moving a
zone later is a change to zone_offsets.json and a re-run: the zone levels
themselves are never edited.

Zone levels are found under /Game/Zones by name (lower case, letters and
digits only, "the" ignored), so "Founders' Falls" matches L_FoundersFalls.
Re-running updates the existing ZoneInstance_<id> actors instead of adding
more. Atlas Park (offset 0,0) is left out unless ATLAS_LEVEL is set below.
Saves only the current level. Pass --dry to list matches without changes.
"""
import json
import re
import sys

import unreal

ROOT = "/Game/Zones"
ATLAS_LEVEL = ""          # e.g. "/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite"
LABEL = "ZoneInstance_%s"
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def log(msg):
    unreal.log("[CoH world] " + msg)


def norm(s):
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    return s[3:] if s.startswith("the") else s


def zone_levels():
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath(
        "/Script/Engine", "World")], package_paths=[ROOT], recursive_paths=True)
    out = {}
    for d in reg.get_assets(flt):
        name = str(d.asset_name)
        if name.startswith("L_") and not name.endswith("Backup"):
            out[norm(name[2:])] = str(d.package_name)
    return out


def ue_location(offset_m):
    """Game x, z offset in meters -> Unreal cm (X = x, Y = -z)."""
    return unreal.Vector(offset_m[0] * 100.0, -offset_m[1] * 100.0, 0.0)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dry = "--dry" in sys.argv
    zones = json.load(open(args[0]))["zones"]
    levels = zone_levels()
    world = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem).get_editor_world()
    log("world level: " + world.get_path_name())
    existing = {a.get_actor_label(): a for a in asub.get_all_level_actors()
                if a.get_actor_label().startswith("ZoneInstance_")}
    placed, missing = 0, []
    for zid, z in sorted(zones.items()):
        if zid == "city_01_01":
            pkg = ATLAS_LEVEL
        else:
            pkg = levels.get(norm(z["name"]))
        if not pkg:
            missing.append("%s (%s)" % (z["name"], zid))
            continue
        loc = ue_location(z["offset_m"])
        log("%-20s %-45s at X %.0f m, Y %.0f m" % (
            z["name"], pkg, loc.x / 100, loc.y / 100))
        if dry:
            continue
        label = LABEL % zid
        a = existing.get(label)
        if a is None:
            a = asub.spawn_actor_from_class(unreal.LevelInstance, loc)
            a.set_actor_label(label)
            a.set_folder_path("Zones")
        else:
            a.set_actor_location(loc, False, False)
        a.set_editor_property("world_asset", unreal.load_asset(pkg))
        try:
            a.set_editor_property(
                "desired_runtime_behavior",
                unreal.LevelInstanceRuntimeBehavior.PARTITIONED)
        except Exception as e:  # property name differs by engine version
            log("could not set runtime behavior on %s: %s" % (label, e))
        placed += 1
    log("zones placed: %d; no level found for: %s" % (
        placed, ", ".join(missing) or "none"))
    if not dry and placed:
        unreal.get_editor_subsystem(
            unreal.LevelEditorSubsystem).save_current_level()


main()

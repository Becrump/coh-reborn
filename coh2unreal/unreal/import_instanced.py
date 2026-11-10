"""Replaces a merged-tile zone with separate objects (coh2unreal --instanced).

Run in the Unreal editor with the zone's level open:
    py "<out>/import_instanced.py"

1. Saves a backup copy of the current level.
2. Imports <name>.gltf (one mesh per CoH model) into CONTENT.
3. Points the new meshes' material slots at the existing, already-tuned
   material instances of the same name (MATERIALS), so every material fix
   made on the tile import carries over; Nanite and collision on.
4. Deletes the old tile actors and places the models from
   <name>_placements.json: models used up to ACTOR_LIMIT times as
   individual StaticMeshActors (selectable, movable); more often as one
   CoHInstances actor per model holding all copies. Night-only parts go on
   separate actors labelled ..._night so the day/night cycle switches them.
5. Removes models listed in statues.json "remove_models" (replaced statues).
Sky, lights, lamps, statues and the life manager are left as they are.
"""
import collections
import json
import os

import unreal

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() \
    else os.getcwd()
CONTENT = "/Game/AtlasPark3"
MATERIALS = "/Game/atlas_park/Materials"
ACTOR_LIMIT = 30

asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()
el = unreal.EditorAssetLibrary


def log(msg):
    unreal.log("[CoH import] " + msg)


def find(suffix):
    for f in os.listdir(HERE):
        if f.endswith(suffix):
            return os.path.join(HERE, f)
    return None


def backup_level():
    world = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem).get_editor_world()
    path = world.get_path_name().split(".")[0]
    dst = path + "_TilesBackup"
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    if not el.does_asset_exist(dst):
        el.duplicate_asset(path, dst)
    log("backup of the tile level: " + dst)


def import_library(gltf):
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", gltf)
    t.set_editor_property("destination_path", CONTENT)
    t.set_editor_property("automated", True)
    t.set_editor_property("replace_existing", True)
    t.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    meshes = {}
    for d in reg.get_assets_by_path(CONTENT, True):
        if str(d.asset_class_path.asset_name) == "StaticMesh":
            meshes[str(d.asset_name)] = d
    log("library: %d static meshes" % len(meshes))
    return meshes


def link_materials(meshes):
    tuned = {str(d.asset_name).lower(): d
             for d in reg.get_assets_by_path(MATERIALS, True)
             if str(d.asset_class_path.asset_name)
             == "MaterialInstanceConstant"}
    linked = new = 0
    with unreal.ScopedSlowTask(len(meshes), "Linking tuned materials") as task:
        task.make_dialog(False)
        for name, d in meshes.items():
            task.enter_progress_frame(1, name)
            mesh = d.get_asset()
            mats = mesh.get_editor_property("static_materials")
            changed = False
            for i, sm in enumerate(mats):
                mi = sm.get_editor_property("material_interface")
                if mi is None:
                    continue
                old = tuned.get(mi.get_name().lower())
                if old is not None and old.get_asset() != mi:
                    sm.set_editor_property("material_interface",
                                           old.get_asset())
                    mats[i] = sm
                    changed = True
                    linked += 1
                elif old is None:
                    new += 1
            if changed:
                mesh.set_editor_property("static_materials", mats)
            ns = mesh.get_editor_property("nanite_settings")
            ns.set_editor_property("enabled", True)
            mesh.set_editor_property("nanite_settings", ns)
            body = mesh.get_editor_property("body_setup")
            if body:
                body.set_editor_property(
                    "collision_trace_flag",
                    unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            el.save_loaded_asset(mesh, False)
    log("materials: %d slots linked to tuned instances, %d new" % (
        linked, new))


def clear_tiles():
    gone = 0
    for a in asub.get_all_level_actors():
        label = a.get_actor_label()
        if label.startswith("tile_") or (label == "atlas_park"
                                         and not isinstance(a, unreal.Light)):
            asub.destroy_actor(a)
            gone += 1
    log("removed %d tile actors" % gone)


def place(meshes, rows, remove):
    groups = collections.defaultdict(list)
    for r in rows:
        if r["m"] in remove:
            continue
        loc = unreal.Vector(*r["l"])
        p, y, rl = r["r"]
        t = unreal.Transform(loc, unreal.Rotator(rl, p, y),
                             unreal.Vector(*r["s"]))
        if r["day"]:
            groups[r["m"]].append(t)
        if r["night"]:
            groups[r["m"] + "_night"].append(t)
    actors = inst = 0
    missing = set()
    with unreal.ScopedSlowTask(len(groups), "Placing CoH objects") as task:
        task.make_dialog(False)
        for name, ts in sorted(groups.items()):
            task.enter_progress_frame(1, name)
            d = meshes.get(name)
            if d is None:
                missing.add(name)
                continue
            mesh = d.get_asset()
            folder = "Zone/Night" if name.endswith("_night") else (
                "Zone/Instanced" if len(ts) > ACTOR_LIMIT else "Zone/Objects")
            if len(ts) > ACTOR_LIMIT:
                a = asub.spawn_actor_from_class(unreal.CoHInstances,
                                                unreal.Vector(0, 0, 0))
                a.set_instances(mesh, ts)
                a.set_actor_label(name if name.endswith("_night")
                                  else name + "_x%d" % len(ts))
                a.set_folder_path(folder)
                inst += len(ts)
            else:
                for k, t in enumerate(ts):
                    a = asub.spawn_actor_from_object(
                        mesh, t.translation, t.rotation.rotator())
                    a.set_actor_scale3d(t.scale3d)
                    a.set_actor_label(name if name.endswith("_night")
                                      and len(ts) == 1 else
                                      "%s_%d" % (name, k) + (
                                          "_night" if name.endswith("_night")
                                          else ""))
                    a.set_folder_path(folder)
                    actors += 1
    log("placed %d single objects and %d instances (%d models missing: %s)"
        % (actors, inst, len(missing), sorted(missing)[:5]))


def main():
    gltf = find(".gltf")
    rows = json.load(open(find("_placements.json")))
    cfg = {}
    if find("statues.json"):
        cfg = json.load(open(find("statues.json")))
    remove = set()
    for s in cfg.get("statues", []):
        remove.update(s.get("remove_models", []))
    backup_level()
    meshes = import_library(gltf)
    link_materials(meshes)
    clear_tiles()
    place(meshes, rows, remove)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    log("done")


main()

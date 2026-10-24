"""Import upgraded characters into the open Unreal editor and place them.

Runs *inside* Unreal (Python Remote Execution via unreal/scripts/ue_exec.py).
run_upgrade.py writes a small wrapper that defines JOB and then executes
this file. JOB = {"items": [{"gltf": "...", "dest": "/Game/Upgraded/...",
"label": "Hellion_Boss_01", "place": [x, y, z, yaw] or null,
"folder": "Upgraded/Hellions"}], "save_level": true}

Each glTF is imported with Interchange, combining all costume pieces into a
single skeletal mesh per character (one asset, one actor). An actor with the
same label is replaced. Placed actors play their idle clip.
"""
import json

import unreal

EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
results = []
placed = False
for it in JOB["items"]:  # noqa: F821  (defined by the wrapper)
    dest = it["dest"]
    if unreal.EditorAssetLibrary.does_directory_exist(dest):
        for a in EAS.get_all_level_actors():
            if a.get_actor_label() == it["label"]:
                EAS.destroy_actor(a)
        unreal.EditorAssetLibrary.delete_directory(dest)
    pipe = unreal.InterchangeGenericAssetsPipeline()
    pipe.mesh_pipeline.combine_skeletal_meshes_behavior = \
        unreal.InterchangeCombineSkeletalMeshesBehavior.BY_SKELETON
    pipe.mesh_pipeline.import_static_meshes = False
    src = unreal.InterchangeManager.create_source_data(it["gltf"])
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    params.replace_existing = True
    params.override_pipelines.append(
        unreal.SoftObjectPath(pipe.get_path_name()))
    unreal.InterchangeManager.get_interchange_manager_scripted() \
        .import_asset(dest, src, params)
    assets = unreal.EditorAssetLibrary.list_assets(dest, recursive=True)

    def cls(p):
        return unreal.EditorAssetLibrary.find_asset_data(p) \
            .asset_class_path.asset_name
    sks = [p for p in assets if cls(p) == "SkeletalMesh"]
    anims = [p for p in assets if cls(p) == "AnimSequence"]
    res = {"label": it["label"], "dest": dest, "skeletal_meshes": sks,
           "anims": len(anims), "ok": len(sks) == 1 and len(anims) > 0}
    if sks and it.get("place"):
        x, y, z, yaw = it["place"]
        for a in EAS.get_all_level_actors():
            if a.get_actor_label() == it["label"]:
                EAS.destroy_actor(a)
        a = EAS.spawn_actor_from_class(
            unreal.SkeletalMeshActor, unreal.Vector(x, y, z),
            unreal.Rotator(roll=0, pitch=0, yaw=yaw))
        a.set_actor_label(it["label"])
        a.set_folder_path(it.get("folder", "Upgraded"))
        c = a.skeletal_mesh_component
        c.set_skeletal_mesh_asset(unreal.load_asset(sks[0]))
        idle = next((p for p in anims if "idle" in p.lower()), None)
        if idle:
            c.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
            c.override_animation_data(unreal.load_asset(idle), True, True,
                                      0.0, 1.0)
            c.set_update_animation_in_editor(True)
        res["actor"] = a.get_path_name()
        placed = True
    unreal.EditorAssetLibrary.save_directory(dest)
    results.append(res)
if placed and JOB.get("save_level", True):  # noqa: F821
    unreal.EditorLevelLibrary.save_current_level()
print("UE_RESULT " + json.dumps(results))

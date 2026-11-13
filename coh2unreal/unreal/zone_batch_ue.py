"""Editor side of the all-zones batch import (driven by tools/zones/import_zones.py).

Run one stage per remote-exec call; the driver sets ZONE_CFG (dict) and STAGE first:
    level    create/open the zone's World Partition level /Game/Zones/<Zone>/L_<Zone>
    meshes   import only models not yet in the shared library (materials/textures OFF)
    mats     import only materials not yet known (static meshes OFF) into the library
    link     point every new mesh slot at a material of the same name (Atlas tuned first)
    place    place the zone's placements json (clears this level's Zone/* actors first)
    sky      basic sun/atmosphere/sky light/fog/clouds/Lumen post process
    save     save only this zone's packages and new library assets (never save-all)
    shots    two high-res screenshots (overview, street level)
    stats    counts for the log
Shared library: models in MESH_DIRS (Galaxy's import seeds it), materials in MAT_DIRS. Nothing is
duplicated: a glTF is filtered by the driver to new models / new materials before import, and the
Interchange pipelines are told not to create materials (mesh pass) or meshes (material pass).
"""
import collections
import gc
import json
import os
import re
import sys
import time

import warnings

import unreal

# remote execution runs unattended, where a DeprecationWarning becomes an exception
warnings.simplefilter("ignore", DeprecationWarning)

CFG = globals().get("ZONE_CFG") or {}
STAGE = globals().get("STAGE", "")
LIB = "/Game/Zones/Library"
MESH_DIRS = ["/Game/Zones/GalaxyCity/galaxy_city/StaticMeshes", LIB + "/Meshes"]
MAT_DIRS = ["/Game/atlas_park/Materials", "/Game/Zones/GalaxyCity/galaxy_city/Materials", LIB + "/Materials"]
ACTOR_LIMIT = 30

asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
lsub = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary


def log(msg):
    print("[zone] " + msg)


def sanitize(name):
    """Unreal object name for a glTF name ('foo.tga' -> 'foo_tga')."""
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name)


def label(model):
    """same as setup_trees.mesh_label, so tree replacement finds the originals"""
    return "SM_" + "".join(c if c.isalnum() else "_" for c in model)


def zone_root():
    return "/Game/Zones/" + CFG["zone"]


def level_path():
    return zone_root() + "/L_" + CFG["zone"]


def world_path():
    w = ues.get_editor_world()
    p = w.get_path_name() if w else ""
    del w
    return p


def assets(path, cls):
    return [d for d in reg.get_assets_by_path(path, True) if str(d.asset_class_path.asset_name) == cls]


def mesh_index():
    out = {}
    for p in MESH_DIRS:
        for d in assets(p, "StaticMesh"):
            out.setdefault(str(d.asset_name), str(d.object_path) if hasattr(d, "object_path") else
                           "%s.%s" % (d.package_name, d.asset_name))
    return out


def mat_index():
    out = {}
    for p in MAT_DIRS:
        for d in assets(p, "MaterialInstanceConstant") + assets(p, "Material"):
            out.setdefault(str(d.asset_name).lower(), "%s.%s" % (d.package_name, d.asset_name))
    return out


def write_index():
    """library names for the driver's glTF filter"""
    json.dump({"meshes": sorted(mesh_index()), "materials": sorted(mat_index())},
              open(CFG["index_out"], "w"))
    log("index: written")


def ours(name):
    z = "Zones/" + CFG["zone"]
    return (name.startswith("/Game/" + z) or name.startswith(LIB) or name.startswith("/Game/CoH/Props") or
            name.startswith("/Game/__ExternalActors__/" + z) or name.startswith("/Game/__ExternalObjects__/" + z))


def save_ours():
    E = unreal.EditorLoadingAndSavingUtils
    dirty = E.get_dirty_content_packages() + E.get_dirty_map_packages()
    pk = [p for p in dirty if ours(p.get_name())]
    others = [p.get_name() for p in dirty if not ours(p.get_name())]
    if pk:
        E.save_packages(pk, True)
    log("save: %d zone/library packages saved; %d other dirty packages left unsaved %s"
        % (len(pk), len(others), others[:8]))
    del pk, dirty


def clear_python_refs():
    for k in ("last_traceback", "last_value", "last_type", "last_exc"):
        if hasattr(sys, k):
            setattr(sys, k, None)
    gc.collect()


# --------------------------------------------------------------- stages
def stage_level():
    clear_python_refs()
    lp = level_path()
    if world_path().startswith(lp):
        log("level: already open " + lp)
        return
    dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    if dirty:
        raise RuntimeError("unsaved maps open, refusing to switch level: %s" % dirty)
    if EAL.does_asset_exist(lp):
        lsub.load_level(lp)
    else:
        lsub.new_level(lp, True)
    log("level: now " + world_path())


def _pipelines(meshes, materials):
    """Interchange stack: default assets pipeline (+ glTF pipeline) with meshes/materials switched."""
    stack = unreal.InterchangePipelineStackOverride()
    base = unreal.load_asset("/Interchange/Pipelines/DefaultAssetsPipeline")
    p = unreal.new_object(type(base), outer=unreal.get_transient_package(), base_object=base) \
        if "base_object" in unreal.new_object.__doc__ else unreal.new_object(type(base))
    for sub, prop, val in (("mesh_pipeline", "import_static_meshes", meshes),
                           ("mesh_pipeline", "import_skeletal_meshes", False),
                           ("material_pipeline", "import_materials", materials),
                           ("material_pipeline", "texture_pipeline", None)):
        if val is None:
            continue
        getattr(p, sub).set_editor_property(prop, val)
    try:
        p.material_pipeline.texture_pipeline.set_editor_property("import_textures", materials)
    except Exception as e:
        log("pipeline: texture flag not set (%s)" % e)
    stack.add_pipeline(p)
    gl = unreal.load_asset("/Interchange/Pipelines/DefaultGLTFPipeline")
    if gl:
        stack.add_pipeline(gl)
    return stack


def _import(gltf, dest, meshes, materials):
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", gltf)
    t.set_editor_property("destination_path", dest)
    t.set_editor_property("automated", True)
    t.set_editor_property("replace_existing", False)
    t.set_editor_property("save", False)
    t.set_editor_property("options", _pipelines(meshes, materials))
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    return list(t.get_editor_property("imported_object_paths"))


def _drop_scene_actors(names):
    gone = 0
    for a in asub.get_all_level_actors():
        if a.get_actor_label() in names or a.get_actor_label().startswith(CFG["name"]):
            if not a.get_folder_path() or not str(a.get_folder_path()).startswith(("Zone", "Sky")):
                asub.destroy_actor(a)
                gone += 1
    return gone


def stage_meshes():
    gltf = CFG.get("new_meshes_gltf")
    if not gltf:
        log("meshes: nothing new")
        return
    t0 = time.time()
    got = _import(gltf, LIB + "/Meshes", True, False)
    _drop_scene_actors(set())
    made = collections.Counter(unreal.load_asset(p).get_class().get_name() for p in got[:5000])
    log("meshes: imported %d objects %s in %.0fs" % (len(got), dict(made), time.time() - t0))
    want = len(CFG.get("new_mesh_names", []))
    if want and not made.get("StaticMesh"):
        raise RuntimeError("expected %d new models, Interchange imported none" % want)


def stage_mats():
    gltf = CFG.get("new_mats_gltf")
    if not gltf:
        log("mats: nothing new")
        return
    t0 = time.time()
    got = _import(gltf, LIB + "/Materials", False, True)
    _drop_scene_actors(set())
    made = collections.Counter(unreal.load_asset(p).get_class().get_name() for p in got)
    log("mats: imported %d objects %s in %.0fs" % (len(got), dict(made), time.time() - t0))
    if not got:
        raise RuntimeError("expected %d new materials, Interchange imported none" % len(CFG.get("new_mat_names", [])))


def _kind(low, masked):
    low = low[3:] if low.startswith("mi_") else low
    if re.search(r"_+add(_+night)?$", low):
        return "additive"
    if re.search(r"_+(glow|night)$", low):
        return "glow"
    return "masked" if low in masked else None


def _fix_material(mi, kind):
    o = mi.get_editor_property("base_property_overrides")
    o.set_editor_property("override_two_sided", True)
    o.set_editor_property("two_sided", True)
    if kind == "masked":
        MEL.set_material_instance_scalar_parameter_value(mi, "AlphaMode", 1.0)
        MEL.set_material_instance_scalar_parameter_value(mi, "AlphaCutoff", 0.3)
        o.set_editor_property("override_blend_mode", True)
        o.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        o.set_editor_property("override_opacity_mask_clip_value", True)
        o.set_editor_property("opacity_mask_clip_value", 0.3)
    elif kind == "additive":
        MEL.set_material_instance_scalar_parameter_value(mi, "AlphaMode", 2.0)
        o.set_editor_property("override_blend_mode", True)
        o.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    mi.set_editor_property("base_property_overrides", o)
    MEL.update_material_instance(mi)


def stage_link():
    """new meshes: slot -> material of the same name; new library materials get the CoH blend fixes"""
    t0 = time.time()
    mats = mat_index()
    masked = {n.lower() for n in json.load(open(CFG["masked_json"]))} if CFG.get("masked_json") else set()
    new_names = set(CFG.get("new_mesh_names", []))
    linked = unlinked = 0
    missing = collections.Counter()
    for d in assets(LIB + "/Meshes", "StaticMesh"):
        if str(d.asset_name) not in new_names:
            continue
        mesh = d.get_asset()
        slots = mesh.get_editor_property("static_materials")
        for i, sm in enumerate(slots):
            want = str(sm.get_editor_property("material_slot_name")) or ""
            mi = sm.get_editor_property("material_interface")
            key = sanitize(want).lower()
            path = mats.get(key) or (mats.get(mi.get_name().lower()) if mi else None)
            if path:
                sm.set_editor_property("material_interface", unreal.load_asset(path))
                slots[i] = sm
                linked += 1
            else:
                unlinked += 1
                missing[want] += 1
        mesh.set_editor_property("static_materials", slots)
        ns = mesh.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", True)
        mesh.set_editor_property("nanite_settings", ns)
        body = mesh.get_editor_property("body_setup")
        if body:
            body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    fixed = collections.Counter()
    for name in CFG.get("new_mat_names", []):
        p = mats.get(sanitize(name).lower())
        if not p or not p.startswith(LIB):
            continue
        k = _kind(sanitize(name).lower(), masked)
        if k:
            _fix_material(unreal.load_asset(p), k)
            fixed[k] += 1
    log("link: %d slots linked, %d unlinked %s; new materials fixed %s (%.0fs)"
        % (linked, unlinked, missing.most_common(5), dict(fixed), time.time() - t0))


def stage_place():
    assert world_path().startswith(level_path()), "zone level not open"
    t0 = time.time()
    old = [a for a in asub.get_all_level_actors() if str(a.get_folder_path()).startswith("Zone")]
    for a in old:
        asub.destroy_actor(a)
    del old
    meshes = mesh_index()
    rows = json.load(open(CFG["placements"]))
    groups = collections.defaultdict(list)
    for r in rows:
        t = unreal.Transform(unreal.Vector(*r["l"]), unreal.Rotator(r["r"][2], r["r"][0], r["r"][1]),
                             unreal.Vector(*r["s"]))
        if r["day"]:
            groups[r["m"]].append(t)
        if r["night"]:
            groups[r["m"] + "_night"].append(t)
    del rows
    actors = inst = inst_actors = 0
    missing = set()
    with unreal.ScopedSlowTask(len(groups), "Placing " + CFG["zone"]) as task:
        task.make_dialog(False)
        for name, ts in sorted(groups.items()):
            task.enter_progress_frame(1)
            base = name[:-6] if name.endswith("_night") and name not in meshes else name
            path = meshes.get(base) or meshes.get(sanitize(base))
            if path is None:
                missing.add(base)
                continue
            mesh = unreal.load_asset(path)
            folder = "Zone/Night" if name.endswith("_night") else (
                "Zone/Instanced" if len(ts) > ACTOR_LIMIT else "Zone/Objects")
            if len(ts) > ACTOR_LIMIT:
                a = asub.spawn_actor_from_class(unreal.CoHInstances, unreal.Vector(0, 0, 0))
                a.set_instances(mesh, ts)
                a.set_actor_label(label(name) if name.endswith("_night") else label(name) + "_x%d" % len(ts))
                a.set_folder_path(folder)
                inst += len(ts)
                inst_actors += 1
            else:
                for k, t in enumerate(ts):
                    a = asub.spawn_actor_from_object(mesh, t.translation, t.rotation.rotator())
                    a.set_actor_scale3d(t.scale3d)
                    a.set_actor_label("%s_%d" % (label(name), k))
                    a.set_folder_path(folder)
                    actors += 1
    del groups
    log("place: %d single, %d instances in %d instance actors; %d models missing %s (%.0fs)"
        % (actors, inst, inst_actors, len(missing), sorted(missing)[:8], time.time() - t0))


def _spawn(cls, label, loc=unreal.Vector(0, 0, 0)):
    for a in asub.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    a = asub.spawn_actor_from_class(cls, loc)
    a.set_actor_label(label)
    a.set_folder_path("Sky")
    return a


def stage_sky():
    sun = _spawn(unreal.DirectionalLight, "Sun", unreal.Vector(0, 0, 5000))
    sun.set_actor_rotation(unreal.Rotator(0, -40, -60), False)
    sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    sc.set_editor_property("atmosphere_sun_light", True)
    sc.set_editor_property("intensity", 10.0)
    _spawn(unreal.SkyAtmosphere, "SkyAtmosphere")
    sky = _spawn(unreal.SkyLight, "SkyLight", unreal.Vector(0, 0, 5000))
    kc = sky.get_component_by_class(unreal.SkyLightComponent)
    kc.set_mobility(unreal.ComponentMobility.MOVABLE)
    kc.set_editor_property("real_time_capture", True)
    fog = _spawn(unreal.ExponentialHeightFog, "HeightFog")
    fog.get_component_by_class(unreal.ExponentialHeightFogComponent).set_editor_property("fog_density", 0.01)
    _spawn(unreal.VolumetricCloud, "Clouds")
    ppv = _spawn(unreal.PostProcessVolume, "PostProcess")
    ppv.set_editor_property("unbound", True)
    s = ppv.get_editor_property("settings")
    for prop, val in (("dynamic_global_illumination_method", unreal.DynamicGlobalIlluminationMethod.LUMEN),
                      ("reflection_method", unreal.ReflectionMethod.LUMEN),
                      ("auto_exposure_min_brightness", 2.0), ("auto_exposure_max_brightness", 14.0)):
        s.set_editor_property("override_" + prop, True)
        s.set_editor_property(prop, val)
    ppv.set_editor_property("settings", s)
    log("sky: ready")


def _bounds():
    xs, ys, zs = [], [], []
    for a in asub.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Zone") and not isinstance(a, unreal.CoHInstances):
            l = a.get_actor_location()
            xs.append(l.x); ys.append(l.y); zs.append(l.z)
    if not xs:
        return (-50000, -50000, 0, 50000, 50000, 3000)
    xs.sort(); ys.sort(); zs.sort(); n = len(xs)
    q = lambda a, f: a[int(f * (n - 1))]
    return (q(xs, .02), q(ys, .02), q(zs, .5), q(xs, .98), q(ys, .98), q(zs, .9))


def stage_shots():
    x0, y0, zmid, x1, y1, ztop = _bounds()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    span = max(x1 - x0, y1 - y0)
    w = ues.get_editor_world()
    shots = {
        "overview": (unreal.Vector(cx - span * 0.55, cy - span * 0.55, ztop + span * 0.55),
                     unreal.Rotator(roll=0, pitch=-35, yaw=45)),
        "street": (unreal.Vector(*CFG["street_cam"][:3]) if CFG.get("street_cam") else
                   unreal.Vector(cx, cy, zmid + 250), unreal.Rotator(roll=0, pitch=-3,
                   yaw=CFG["street_cam"][3] if CFG.get("street_cam") else 30)),
    }
    for name, (loc, rot) in shots.items():
        if name != CFG.get("shot"):
            continue
        ues.set_level_viewport_camera_info(loc, rot)
        out = "%s/%s_%s" % (CFG["shot_dir"].rstrip("/"), CFG["zone"], name)
        unreal.SystemLibrary.execute_console_command(w, 'HighResShot 1920x1080 filename="%s"' % out)
        log("shots: requested %s at %s" % (out, loc))
    del w


def stage_stats():
    acts = asub.get_all_level_actors()
    c = collections.Counter(type(a).__name__ for a in acts)
    n_inst = 0
    for a in acts:
        if isinstance(a, unreal.CoHInstances):
            for comp in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
                n_inst += comp.get_instance_count()
    stats = {"actors": len(acts), "instance_actors": c.get("CoHInstances", 0), "instances": n_inst,
             "classes": dict(c.most_common(6))}
    del acts
    json.dump(stats, open(CFG["stats_out"], "w"))
    log("stats: %s" % json.dumps(stats))


CELL_CM = 25600.0          # 256 m streaming chunks, same zone-local grid for every zone
CLUTTER_RADIUS_CM = 150.0  # meshes smaller than this (bounding sphere) count as clutter
CLUTTER_CULL_CM = 15000.0  # clutter disappears beyond 150 m


def _load_all_actors():
    """World Partition loads only some cells in the editor: load every actor of this level."""
    wpl = unreal.WorldPartitionBlueprintLibrary
    descs = wpl.get_actor_descs()
    guids = [d.guid for d in descs]
    if guids:
        wpl.load_actors(guids)
    return len(guids)


def _small(mesh):
    try:
        return mesh.get_bounds().sphere_radius < CLUTTER_RADIUS_CM
    except Exception:
        return False


def _instances(comp):
    out = []
    for i in range(comp.get_instance_count()):
        t = comp.get_instance_transform(i, True)
        if isinstance(t, tuple):
            t = t[-1]
        out.append(t)
    return out


def stage_split():
    """Split whole-zone instance actors into 256 m chunks (ISM_<model>_<cx>_<cy>) and cull small clutter."""
    assert world_path().startswith(level_path()), "zone level not open"
    t0 = time.time()
    n_descs = _load_all_actors()
    acts = asub.get_all_level_actors()
    big = [a for a in acts if isinstance(a, unreal.CoHInstances)
           and not a.get_actor_label().startswith("ISM_")]
    singles = [a for a in acts if isinstance(a, unreal.StaticMeshActor)
               and str(a.get_folder_path()).startswith("Zone")]
    before = len(acts)
    del acts
    chunks = culled = 0
    with unreal.ScopedSlowTask(len(big), "Splitting " + CFG["zone"]) as task:
        task.make_dialog(False)
        for a in big:
            task.enter_progress_frame(1)
            comp = a.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent) or \
                a.get_component_by_class(unreal.InstancedStaticMeshComponent)
            mesh = comp.get_editor_property("static_mesh") if comp else None
            if mesh is None:
                continue
            cells = collections.defaultdict(list)
            for t in _instances(comp):
                l = t.translation
                cells[(int(l.x // CELL_CM), int(l.y // CELL_CM))].append(t)
            label = re.sub(r"_x\d+$", "", a.get_actor_label())
            label = label[3:] if label.startswith("SM_") else label
            folder = a.get_folder_path()
            small = _small(mesh)
            for (cx, cy), ts in cells.items():
                c = asub.spawn_actor_from_class(unreal.CoHInstances, unreal.Vector(0, 0, 0))
                c.set_instances(mesh, ts)
                c.set_actor_label("ISM_%s_%d_%d" % (label, cx, cy))
                c.set_folder_path(folder)
                if small:
                    ic = c.get_component_by_class(unreal.InstancedStaticMeshComponent)
                    ic.set_editor_property("instance_start_cull_distance", int(CLUTTER_CULL_CM * 0.8))
                    ic.set_editor_property("instance_end_cull_distance", int(CLUTTER_CULL_CM))
                    culled += 1
                chunks += 1
            asub.destroy_actor(a)
    single_culled = 0
    for a in singles:
        sc = a.static_mesh_component
        m = sc.get_editor_property("static_mesh")
        if m and _small(m):
            sc.set_editor_property("ld_max_draw_distance", CLUTTER_CULL_CM)
            single_culled += 1
    del big, singles
    after = len(asub.get_all_level_actors())
    json.dump({"actors_before": before, "actors_after": after, "chunks": chunks,
               "clutter_chunks_culled": culled, "clutter_singles_culled": single_culled},
              open(CFG["split_out"], "w"))
    log("split: %d actor descs loaded; actors %d -> %d; %d chunks (%d clutter-culled), %d small singles culled (%.0fs)"
        % (n_descs, before, after, chunks, culled, single_culled, time.time() - t0))


{"split": stage_split, "index": write_index, "level": stage_level, "meshes": stage_meshes, "mats": stage_mats,
 "link": stage_link, "place": stage_place, "sky": stage_sky, "save": save_ours,
 "shots": stage_shots, "stats": stage_stats}[STAGE]()
clear_python_refs()

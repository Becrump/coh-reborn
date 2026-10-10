"""Sets up an imported City of Heroes zone in Unreal 5.8.

Run in the Unreal editor after importing <name>.gltf into an open level:
    py "C:/path/to/out/atlas_park/setup_level.py"
    py "C:/path/to/out/atlas_park/setup_level.py" --hour 21   (preview a time)

What it does:
1. Materials: cutouts -> Masked, __ADD -> Additive, glow -> two-sided.
2. Sky: sun, sky atmosphere, real-time sky light, height fog, clouds and a
   Lumen post-process volume (one of each; existing ones are reused).
3. Lights: spawns the zone's CoH point lights if the import didn't, and
   replaces CoH street lamps with modern lamp models and real spotlights.
4. Day/night: a looping Level Sequence (1 game hour = 1 real minute) built
   from the zone's own CoH time-of-day keys: sun angle/colour, ambient, fog,
   and the night-only tiles (lit windows) switched on at lamp-light time.

Safe to run again; it updates what it made before. Options:
    --hour H   only set the editor view to game hour H
    --clean    remove everything this script made (keeps the import)
    --only S   run only these steps (comma list): materials, turf, bronze,
               statues, props, daynight (sky, moon, stars and the cycle)
    --force    run even if the level was imported from another export
"""
import json
import math
import os
import re
import sys

import unreal

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() \
    else os.getcwd()
SEQ_DIR = "/Game/CoH"
SEQ_NAME = "DayNight"
FPS = 30
MINUTES_PER_HOUR = 1.0          # real minutes per game hour
PLAY_RATE = 2.0                 # 2 game hours per real minute; full day = 12 minutes
START_HOUR = 10.0               # game time when the sequence starts
SUN_LUX = 10.0                  # sun at CoH diffuse 255
SKY_INTENSITY = 12.0            # sky light at CoH ambient 255 (fill for shade; CoH faked the rest)
MOON_LUX = 1.2                  # full moonlight: enough to see by
MOON_COLOR = (0.72, 0.82, 1.0)  # cool blue-white
STAR_STRENGTH = 3.0             # star dome brightness at full night
NIGHT_FADE_H = 0.75
# statue/City Hall floods and braziers: on before dusk, unlike the CoH street
# lamps (which come on after sunset); (off hour, on hour)
FEATURE_LIGHT_TIME = (6.0, 18.0)
# street lamps and night windows: CoH's own times (4.8 off, 19.5 on) leave
# the streets dark for the last hour before our sunrise, so cover the whole
# dark period: (off hour, on hour). None = use the zone's sky file.
LAMP_TIME = (6.25, 18.75)
FEATURE_PREFIXES = ("StatueLight_", "Fire_")             # hours to fade night in/out at lamp times
RESERVED_LABELS = {"Moon", "StarDome"}
FT_TO_CM = 30.48

actors_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def log(msg):
    unreal.log("[CoH setup] " + msg)


def load_json(suffix):
    for f in os.listdir(HERE):
        if f.endswith(suffix):
            with open(os.path.join(HERE, f)) as fh:
                return json.load(fh)
    return None


# ----------------------------------------------------------- 1. materials
def try_set(obj, prop, value):
    """set_editor_property that logs instead of stopping the script when a
    property was renamed in this engine version."""
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception as e:
        unreal.log_warning("[CoH setup] skipped %s.%s: %s" % (
            obj.get_class().get_name(), prop, e))
        return False


# Interchange's glTF master (M_GLTF) gates opacity with its AlphaMode
# parameter (0 opaque, 1 mask, 2 blend); the blend mode alone is not enough.
ALPHA_MASK, ALPHA_BLEND = 1.0, 2.0
_ADD = re.compile(r"_+add(_+night)?$")
_GLOW = re.compile(r"_+(glow|night)$")


def _norm_name(name):
    low = name.lower()
    return low[3:] if low.startswith("mi_") else low


def fix_materials():
    masked = {n.lower() for n in (load_json("masked_materials.json") or [])}
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath(
        "/Script/Engine", "MaterialInstanceConstant")],
        package_paths=["/Game"], recursive_paths=True)
    mel = unreal.MaterialEditingLibrary
    counts = {"masked": 0, "additive": 0, "glow": 0}
    for data in reg.get_assets(flt):
        low = _norm_name(str(data.asset_name))
        if _ADD.search(low):
            kind = "additive"
        elif _GLOW.search(low):
            kind = "glow"
        elif low in masked:
            kind = "masked"
        else:
            continue
        mi = data.get_asset()
        o = mi.get_editor_property("base_property_overrides")
        o.set_editor_property("override_two_sided", True)
        o.set_editor_property("two_sided", True)
        if kind == "masked":
            mel.set_material_instance_scalar_parameter_value(
                mi, "AlphaMode", ALPHA_MASK)
            mel.set_material_instance_scalar_parameter_value(
                mi, "AlphaCutoff", 0.3)
            o.set_editor_property("override_blend_mode", True)
            o.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
            o.set_editor_property("override_opacity_mask_clip_value", True)
            o.set_editor_property("opacity_mask_clip_value", 0.3)
        elif kind == "additive":
            mel.set_material_instance_scalar_parameter_value(
                mi, "AlphaMode", ALPHA_BLEND)
            o.set_editor_property("override_blend_mode", True)
            o.set_editor_property("blend_mode",
                                  unreal.BlendMode.BLEND_ADDITIVE)
        mi.set_editor_property("base_property_overrides", o)
        mel.update_material_instance(mi)
        unreal.EditorAssetLibrary.save_loaded_asset(mi, False)
        counts[kind] += 1
    log("materials: %(masked)d masked, %(additive)d additive, "
        "%(glow)d glowing" % counts)
    if not counts["additive"]:
        sample = [str(d.asset_name) for d in reg.get_assets(flt)
                  if "add" in str(d.asset_name).lower()][:10]
        unreal.log_warning("[CoH setup] no additive materials matched; "
                           "names containing 'add': %s" % sample)


# ----------------------------------------------------------------- 2. sky
def find_or_spawn(cls, label, loc=unreal.Vector(0, 0, 0)):
    """The actor with this label, else the first of this class that isn't
    another named CoH actor (so the Sun lookup never grabs the Moon)."""
    actors = [a for a in actors_sub.get_all_level_actors()
              if isinstance(a, cls)]
    for a in actors:
        if a.get_actor_label() == label:
            return a
    if label not in RESERVED_LABELS:    # reserved ones always get their own
        for a in actors:
            if a.get_actor_label() not in RESERVED_LABELS:
                return a
    a = actors_sub.spawn_actor_from_class(cls, loc)
    a.set_actor_label(label)
    a.set_folder_path("CoH/Sky")
    return a


MPC_PATH = "/Game/CoH/Materials/MPC_CoH"
STARS_MAT = "/Game/CoH/Materials/M_CoH_Stars"


def _stars_material(tex):
    """Unlit additive dome material: stars x StarStrength x MPC Night."""
    mel = unreal.MaterialEditingLibrary
    if unreal.EditorAssetLibrary.does_asset_exist(STARS_MAT):
        m = unreal.load_asset(STARS_MAT)
        mel.delete_all_material_expressions(m)
    else:
        folder, name = STARS_MAT.rsplit("/", 1)
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, folder, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("shading_model",
                          unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("two_sided", True)
    for prop in ("use_translucency_vertex_fog", "apply_fogging",
                 "compute_fog_per_pixel"):
        try_set(m, prop, False)
    t = mel.create_material_expression(
        m, unreal.MaterialExpressionTextureSampleParameter2D, -600, 0)
    t.set_editor_property("parameter_name", "StarTexture")
    t.set_editor_property("texture", tex)
    night = mel.create_material_expression(
        m, unreal.MaterialExpressionCollectionParameter, -600, 250)
    night.set_editor_property("collection", unreal.load_asset(MPC_PATH))
    night.set_editor_property("parameter_name", "Night")
    k = mel.create_material_expression(
        m, unreal.MaterialExpressionScalarParameter, -600, 350)
    k.set_editor_property("parameter_name", "StarStrength")
    k.set_editor_property("default_value", STAR_STRENGTH)
    a = mel.create_material_expression(
        m, unreal.MaterialExpressionMultiply, -300, 0)
    mel.connect_material_expressions(t, "RGB", a, "A")
    mel.connect_material_expressions(night, "", a, "B")
    b = mel.create_material_expression(
        m, unreal.MaterialExpressionMultiply, -150, 0)
    mel.connect_material_expressions(a, "", b, "A")
    mel.connect_material_expressions(k, "", b, "B")
    mel.connect_material_property(b, "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    unreal.EditorAssetLibrary.save_loaded_asset(m, False)
    return m


def setup_night_sky():
    """Moon (second atmosphere light, cool and dim, opposite the sun) and a
    star dome that fades in with MPC_CoH.Night."""
    moon = find_or_spawn(unreal.DirectionalLight, "Moon",
                         unreal.Vector(0, 0, 6000))
    mc = moon.get_component_by_class(unreal.DirectionalLightComponent)
    mc.set_mobility(unreal.ComponentMobility.MOVABLE)
    try_set(mc, "atmosphere_sun_light", True)
    try_set(mc, "atmosphere_sun_light_index", 1)
    try_set(mc, "light_source_angle", 1.2)       # visible moon disc size
    try_set(mc, "cast_shadows", True)
    try_set(mc, "use_temperature", False)
    mc.set_light_color(unreal.LinearColor(*MOON_COLOR, 1))
    mc.set_intensity(0.0)

    src = os.path.join(HERE, "stars.png")
    if not os.path.exists(src):
        log("night sky: moon ready; no stars.png (run make_stars.py)")
        return moon
    tex = _import_texture(src, "/Game/CoH/Sky", "T_Stars")
    try_set(tex, "lod_group", unreal.TextureGroup.TEXTUREGROUP_SKYBOX)
    mat = _stars_material(tex)
    mesh = (unreal.load_asset("/Engine/EngineSky/SM_SkySphere")
            or unreal.load_asset("/Engine/BasicShapes/Sphere"))
    dome = find_or_spawn(unreal.StaticMeshActor, "StarDome")
    if dome.get_actor_label() != "StarDome":     # found a tile, not ours
        dome = actors_sub.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 0))
        dome.set_actor_label("StarDome")
        dome.set_folder_path("CoH/Sky")
    c = dome.static_mesh_component
    c.set_static_mesh(mesh)
    c.set_material(0, mat)
    radius = mesh.get_bounding_box().max.x or 50.0
    s = 2.0e6 / radius                            # ~20 km dome
    dome.set_actor_scale3d(unreal.Vector(s, s, s))
    for prop, v in (("cast_shadow", False),
                    ("affect_distance_field_lighting", False),
                    ("affect_dynamic_indirect_lighting", False),
                    ("visible_in_ray_tracing", False),
                    ("visible_in_reflection_captures", False)):
        try_set(c, prop, v)
    c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    log("night sky: moon + star dome ready")
    return moon


def setup_sky():
    sun = find_or_spawn(unreal.DirectionalLight, "Sun",
                        unreal.Vector(0, 0, 5000))
    sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    try_set(sc, "atmosphere_sun_light", True)
    try_set(sc, "atmosphere_sun_light_index", 0)
    try_set(sc, "use_temperature", False)
    try_set(sc, "light_source_angle", 0.5357)
    try_set(sc, "cast_shadows", True)
    # more sunlight bounced by Lumen so shade picks up colour and light
    try_set(sc, "indirect_lighting_intensity", 1.6)
    find_or_spawn(unreal.SkyAtmosphere, "SkyAtmosphere")
    sky = find_or_spawn(unreal.SkyLight, "SkyLight",
                        unreal.Vector(0, 0, 5000))
    kc = sky.get_component_by_class(unreal.SkyLightComponent)
    kc.set_mobility(unreal.ComponentMobility.MOVABLE)
    try_set(kc, "real_time_capture", True)
    fog = find_or_spawn(unreal.ExponentialHeightFog, "HeightFog")
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    try_set(fc, "fog_density", 0.01)
    try_set(fc, "enable_volumetric_fog", True)
    find_or_spawn(unreal.VolumetricCloud, "Clouds")
    ppv = find_or_spawn(unreal.PostProcessVolume, "PostProcess")
    try_set(ppv, "unbound", True)
    s = ppv.get_editor_property("settings")
    for prop, val in (
            ("dynamic_global_illumination_method",
             unreal.DynamicGlobalIlluminationMethod.LUMEN),
            ("reflection_method", unreal.ReflectionMethod.LUMEN),
            # keep nights dark instead of auto-brightening them
            ("auto_exposure_min_brightness", 2.0),
            ("auto_exposure_max_brightness", 14.0)):
        if try_set(s, "override_" + prop, True):
            try_set(s, prop, val)
    ppv.set_editor_property("settings", s)
    log("sky actors ready")
    return sun, sky, fog


# -------------------------------------------------------------- 3. lights
# CoH's Omni lights were fill light standing in for global illumination
# (Lumen does that now); most light building interiors, and there are
# thousands per zone, which bogs the editor down. Off unless asked for.
SPAWN_COH_LIGHTS = False


def setup_lights():
    existing = [a for a in actors_sub.get_all_level_actors()
                if isinstance(a, unreal.PointLight)
                and a.get_actor_label().startswith("omni_")]
    if not SPAWN_COH_LIGHTS:
        with unreal.ScopedSlowTask(len(existing), "Removing CoH fill lights") \
                as task:
            task.make_dialog(False)
            for a in existing:
                task.enter_progress_frame(1)
                actors_sub.destroy_actor(a)
        log("lights: CoH fill lights off (%d removed); lighting comes from "
            "sun, sky, Lumen and street lamps" % len(existing))
        return []
    if existing:
        for a in existing:
            a.set_folder_path("CoH/Lights")
            try_set(a.light_component, "cast_shadows", False)
        log("lights: %d imported point lights found" % len(existing))
        return existing
    rows = load_json("_lights.json") or []
    made = []
    for r in rows:
        x, y, z = r["pos"]           # glTF metres, Y up
        loc = unreal.Vector(x * 100, z * 100, y * 100)
        a = actors_sub.spawn_actor_from_class(unreal.PointLight, loc)
        a.set_actor_label(r["name"])
        a.set_folder_path("CoH/Lights")
        c = a.light_component
        c.set_mobility(unreal.ComponentMobility.MOVABLE)
        try_set(c, "intensity_units", unreal.LightUnits.CANDELAS)
        c.set_intensity(r["intensity"])
        c.set_light_color(unreal.LinearColor(*r["color"], 1.0))
        c.set_attenuation_radius(r["range"] * 100)
        try_set(c, "cast_shadows", False)
        made.append(a)
    log("lights: spawned %d point lights" % len(made))
    return made


# ---------------------------------------------------------- 1b. lawn turf
TURF_DIR = "/Game/CoH/Turf"


def _import_texture(path, dest, name, srgb=True, normal=False):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", path)
    task.set_editor_property("destination_path", dest)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex = unreal.EditorAssetLibrary.load_asset(dest + "/" + name)
    if tex is not None:
        try_set(tex, "srgb", srgb)
        if normal:
            try_set(tex, "compression_settings",
                    unreal.TextureCompressionSettings.TC_NORMALMAP)
        try_set(tex, "lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        unreal.EditorAssetLibrary.save_loaded_asset(tex, False)
    return tex


def setup_turf():
    """Swaps the lawn materials' blurry CoH texture for the turf set
    (turf_basecolor/normal/mr.png from make_turf.py) tiled per turf.json."""
    cfg = load_json("turf.json")
    if not cfg or not os.path.exists(os.path.join(HERE,
                                                  "turf_basecolor.png")):
        return
    tex = {
        "BaseColorTexture": _import_texture(
            os.path.join(HERE, "turf_basecolor.png"), TURF_DIR, "T_Turf_D"),
        "NormalTexture": _import_texture(
            os.path.join(HERE, "turf_normal.png"), TURF_DIR, "T_Turf_N",
            srgb=False, normal=True),
        "MetallicRoughnessTexture": _import_texture(
            os.path.join(HERE, "turf_mr.png"), TURF_DIR, "T_Turf_MR",
            srgb=False),
    }
    switches = {"BaseColorTexture": "bHasBaseColorTexture",
                "NormalTexture": "bHasNormalTexture",
                "MetallicRoughnessTexture": "bHasMetallicRoughnessTexture"}
    scales = {k.lower(): v for k, v in cfg["materials"].items()}
    mel = unreal.MaterialEditingLibrary
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath(
        "/Script/Engine", "MaterialInstanceConstant")],
        package_paths=["/Game"], recursive_paths=True)
    done = 0
    for data in reg.get_assets(flt):
        scale = scales.get(_norm_name(str(data.asset_name)))
        if scale is None:
            continue
        mi = data.get_asset()
        for param, t in tex.items():
            if t is None:
                continue
            try:
                mel.set_material_instance_static_switch_parameter_value(
                    mi, switches[param], True)
            except Exception as e:
                unreal.log_warning("[CoH setup] switch %s: %s" % (
                    switches[param], e))
            mel.set_material_instance_texture_parameter_value(mi, param, t)
            mel.set_material_instance_vector_parameter_value(
                mi, param + "_OffsetScale",
                unreal.LinearColor(0, 0, scale, scale))
        for p, v in (("MetallicFactor", 1.0), ("RoughnessFactor", 1.0),
                     ("NormalScale", 1.0)):
            mel.set_material_instance_scalar_parameter_value(mi, p, v)
        mel.set_material_instance_vector_parameter_value(
            mi, "BaseColorFactor", unreal.LinearColor(1, 1, 1, 1))
        mel.update_material_instance(mi)
        unreal.EditorAssetLibrary.save_loaded_asset(mi, False)
        done += 1
    log("turf: %d lawn materials now use the turf textures (%.1f m tiles)"
        % (done, cfg.get("tile_meters", 0)))


# --------------------------------------------------------- 1c. bronze
# Material name prefixes -> (linear base colour, roughness). Polished
# bronze: metallic, warm, fairly glossy so Lumen reflects the sky in it.
BRONZE = {
    "x_male_statue_atlas_globe": ((0.86, 0.62, 0.34), 0.22),
    "x_male_statue_atlas": ((0.80, 0.52, 0.26), 0.30),
}


def setup_bronze():
    mel = unreal.MaterialEditingLibrary
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath(
        "/Script/Engine", "MaterialInstanceConstant")],
        package_paths=["/Game"], recursive_paths=True)
    done = 0
    for data in reg.get_assets(flt):
        low = _norm_name(str(data.asset_name))
        match = next((v for k, v in BRONZE.items() if low.startswith(k)),
                     None)
        if match is None:
            continue
        (r, g, b), rough = match
        mi = data.get_asset()
        # solid metal colour; keep the normal map for surface detail
        try:
            mel.set_material_instance_static_switch_parameter_value(
                mi, "bHasBaseColorTexture", False)
            mel.set_material_instance_static_switch_parameter_value(
                mi, "bHasMetallicRoughnessTexture", False)
        except Exception as e:
            unreal.log_warning("[CoH setup] bronze switches: %s" % e)
        mel.set_material_instance_vector_parameter_value(
            mi, "BaseColorFactor", unreal.LinearColor(r, g, b, 1))
        mel.set_material_instance_scalar_parameter_value(
            mi, "MetallicFactor", 1.0)
        mel.set_material_instance_scalar_parameter_value(
            mi, "RoughnessFactor", rough)
        mel.update_material_instance(mi)
        unreal.EditorAssetLibrary.save_loaded_asset(mi, False)
        done += 1
    log("bronze: %d statue materials set to polished bronze" % done)


# ------------------------------------------------------- 1d. statue swaps
INVISIBLE_MAT = "/Game/CoH/Materials/M_Invisible"


def _invisible_material():
    mel = unreal.MaterialEditingLibrary
    if unreal.EditorAssetLibrary.does_asset_exist(INVISIBLE_MAT):
        return unreal.load_asset(INVISIBLE_MAT)
    folder, name = INVISIBLE_MAT.rsplit("/", 1)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    c = mel.create_material_expression(
        mat, unreal.MaterialExpressionConstant, -200, 0)
    c.set_editor_property("r", 0.0)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat, False)
    return mat


def setup_statues():
    """Replaces baked-in CoH statues with new models (statues.json): the
    old one's material slots on its tile get an invisible material (the
    imported assets stay untouched), and the new mesh is placed with
    Nanite on."""
    cfg = load_json("statues.json")
    if not cfg:
        return
    invisible = _invisible_material()
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    tiles = [a for a in actors_sub.get_all_level_actors()
             if isinstance(a, unreal.StaticMeshActor)
             and a.get_actor_label().startswith("tile_")]
    for s in cfg["statues"]:
        hide = {m.lower() for m in s.get("hide_materials", [])}
        hidden = 0
        for t in tiles:
            comp = t.static_mesh_component
            for i in range(comp.get_num_materials()):
                m = comp.get_material(i)
                if m and _norm_name(m.get_name()) in hide:
                    comp.set_material(i, invisible)
                    hidden += 1
        meshes = [d for d in reg.get_assets_by_path(s["content"], True)
                  if str(d.asset_class_path.asset_name) == "StaticMesh"]
        if not meshes and os.path.exists(s["source"]):
            task = unreal.AssetImportTask()
            task.set_editor_property("filename", s["source"])
            task.set_editor_property("destination_path", s["content"])
            task.set_editor_property("automated", True)
            task.set_editor_property("replace_existing", True)
            task.set_editor_property("save", True)
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(
                [task])
            meshes = [d for d in reg.get_assets_by_path(s["content"], True)
                      if str(d.asset_class_path.asset_name) == "StaticMesh"]
        if not meshes:
            unreal.log_warning("[CoH setup] statue %s: no mesh at %s" % (
                s["label"], s["source"]))
            continue
        mesh = meshes[0].get_asset()
        ns = mesh.get_editor_property("nanite_settings")
        if not ns.get_editor_property("enabled"):
            ns.set_editor_property("enabled", True)
            mesh.set_editor_property("nanite_settings", ns)
            unreal.EditorAssetLibrary.save_loaded_asset(mesh, False)
        for a in actors_sub.get_all_level_actors():
            if a.get_actor_label() == s["label"]:
                actors_sub.destroy_actor(a)
        a = actors_sub.spawn_actor_from_object(
            mesh, unreal.Vector(*s["location_cm"]),
            unreal.Rotator(0, 0, s.get("yaw", 0)))
        a.set_actor_label(s["label"])
        a.set_folder_path("CoH/Props")
        a.set_actor_scale3d(unreal.Vector(s["scale"], s["scale"],
                                          s["scale"]))
        log("statue: %s placed, %d old material slots hidden" % (
            s["label"], hidden))


# ------------------------------------------------------ 3c. statue uplights
def setup_statue_lights():
    """Warm ground spotlights aimed up at the statues (uplights.json); on at
    night with the street lamps."""
    cfg = load_json("uplights.json")
    if not cfg:
        return
    for a in actors_sub.get_all_level_actors():
        if a.get_actor_label().startswith(("StatueLight_", "ArchLight_")):
            actors_sub.destroy_actor(a)
    made = 0
    for st in cfg["statues"]:
        cx, cy, cz = st["p"]
        target = unreal.Vector(cx, cy, cz + st["aim_height"])
        n = st.get("count", 2)
        for k in range(n):
            ang = 2 * math.pi * k / n + math.pi / 4
            pos = unreal.Vector(cx + math.cos(ang) * st["radius"],
                                cy + math.sin(ang) * st["radius"], cz + 30)
            rot = unreal.MathLibrary.find_look_at_rotation(pos, target)
            lt = actors_sub.spawn_actor_from_class(unreal.SpotLight, pos, rot)
            lt.set_actor_label("StatueLight_%s_%d" % (st["name"], k))
            lt.set_folder_path("CoH/StatueLights")
            c = lt.get_component_by_class(unreal.SpotLightComponent)
            c.set_mobility(unreal.ComponentMobility.MOVABLE)
            try_set(c, "intensity_units", unreal.LightUnits.CANDELAS)
            c.set_intensity(st["candela"])
            try_set(c, "use_temperature", True)
            try_set(c, "temperature", 4200.0)
            c.set_outer_cone_angle(st["cone"])
            c.set_inner_cone_angle(st["cone"] * 0.6)
            c.set_attenuation_radius(st["radius"] * 2 + st["aim_height"] * 2)
            try_set(c, "cast_shadows", True)
            made += 1
    # architectural floodlights: explicit position and aim point
    for fl in cfg.get("floods", []):
        pos = unreal.Vector(*fl["p"])
        rot = unreal.MathLibrary.find_look_at_rotation(
            pos, unreal.Vector(*fl["target"]))
        lt = actors_sub.spawn_actor_from_class(unreal.SpotLight, pos, rot)
        # "always": architectural light that stays on by day (e.g. under a
        # porch roof); ArchLight_ actors are not switched by the cycle
        always = fl.get("always", False)
        lt.set_actor_label(("ArchLight_" if always else "StatueLight_")
                           + fl["name"])
        lt.set_folder_path("CoH/ArchLights" if always
                           else "CoH/StatueLights")
        c = lt.get_component_by_class(unreal.SpotLightComponent)
        c.set_mobility(unreal.ComponentMobility.MOVABLE)
        try_set(c, "intensity_units", unreal.LightUnits.CANDELAS)
        c.set_intensity(fl["candela"])
        try_set(c, "use_temperature", True)
        try_set(c, "temperature", 3200.0 if always else 4500.0)
        c.set_outer_cone_angle(fl["cone"])
        # architectural washes get a soft edge (small hot centre)
        c.set_inner_cone_angle(10.0 if always else fl["cone"] * 0.55)
        c.set_attenuation_radius(fl.get("radius", 12000))
        try_set(c, "cast_shadows", fl.get("shadows", True))
        made += 1
    log("statue uplights and floodlights: %d lights (on at night)" % made)


# --------------------------------------------------------- 3b. lamp props
PROPS_DIR = "/Game/CoH/Props"
LAMP_MODELS = {"street": "modern_streetlight", "parking": "modern_parkinglight"}
# where each model's LED panel is, from its pole base (cm, arm along +X)
LAMP_HEAD_CM = {"street": (124.0, 0.0, 655.0), "parking": (0.0, 0.0, 745.0)}
LAMP_CANDELA = {"street": 2500.0, "parking": 4000.0, "traffic": 2500.0}
LAMP_KELVIN = 3300.0            # warm, close to CoH's yellow lamps
LAMP_SHADOWS = False            # True looks better but costs frame rate


def import_lamp_mesh(model):
    reg = unreal.AssetRegistryHelpers.get_asset_registry()

    def find():
        flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath(
            "/Script/Engine", "StaticMesh")], package_paths=[PROPS_DIR],
            recursive_paths=True)
        for d in reg.get_assets(flt):
            if model in str(d.asset_name).lower():
                return d.get_asset()
        return None

    mesh = find()
    src = os.path.join(HERE, model + ".glb")
    if mesh is None and os.path.exists(src):
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", src)
        task.set_editor_property("destination_path", PROPS_DIR + "/" + model)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        mesh = find()
    return mesh


def setup_props():
    props = load_json("_props.json") or []
    if not props:
        return
    for a in actors_sub.get_all_level_actors():
        if a.get_actor_label().startswith("Lamp_"):
            actors_sub.destroy_actor(a)
    meshes = {k: import_lamp_mesh(m) for k, m in LAMP_MODELS.items()}
    made = lights = 0
    with unreal.ScopedSlowTask(len(props), "Placing street lamps") as task:
        task.make_dialog(False)
        for n, p in enumerate(props):
            task.enter_progress_frame(1)
            bx, by, bz = p["base"]                     # glTF metres, Y up
            base = unreal.Vector(bx * 100, bz * 100, by * 100)
            fx, fz = p["facing"]
            yaw = math.degrees(math.atan2(fz, fx))
            kind = p["kind"]
            if p["keep_pole"]:
                hx, hy, hz = p["head"]
                head = unreal.Vector(hx * 100, hz * 100, hy * 100 - 20)
                kind = "traffic"
            else:
                mesh = meshes.get(kind)
                if mesh is not None:
                    a = actors_sub.spawn_actor_from_object(
                        mesh, base, unreal.Rotator(0, 0, yaw))
                    a.set_actor_label("Lamp_%d" % n)
                    a.set_folder_path("CoH/StreetLights")
                    made += 1
                ox, oy, oz = LAMP_HEAD_CM[kind]
                r = math.radians(yaw)
                head = unreal.Vector(base.x + ox * math.cos(r) - oy * math.sin(r),
                                     base.y + ox * math.sin(r) + oy * math.cos(r),
                                     base.z + oz - 8)
            lt = actors_sub.spawn_actor_from_class(
                unreal.SpotLight, head, unreal.Rotator(0, -90, yaw))
            lt.set_actor_label("Lamp_Light_%d" % n)
            lt.set_folder_path("CoH/StreetLights")
            c = lt.get_component_by_class(unreal.SpotLightComponent)
            c.set_mobility(unreal.ComponentMobility.MOVABLE)
            try_set(c, "intensity_units", unreal.LightUnits.CANDELAS)
            c.set_intensity(LAMP_CANDELA[kind])
            try_set(c, "use_temperature", True)
            try_set(c, "temperature", LAMP_KELVIN)
            c.set_outer_cone_angle(65)
            c.set_inner_cone_angle(35)
            c.set_attenuation_radius(2000)
            try_set(c, "cast_shadows", LAMP_SHADOWS)
            lights += 1
    log("street lamps: %d new lamp models, %d lights (on at night)" % (
        made, lights))


# ---------------------------------------------------------- 4. day/night
def sample(keys, hour, field, default):
    """Linear interpolation between CoH keys, wrapping around midnight."""
    ks = [k for k in keys if field in k]
    if not ks:
        return default
    times = [k["time"] % 24 for k in ks]
    order = sorted(range(len(ks)), key=lambda i: times[i])
    ks = [ks[i] for i in order]
    times = [times[i] for i in order]
    for i in range(len(ks)):
        t0, t1 = times[i], times[(i + 1) % len(ks)]
        span = (t1 - t0) % 24 or 24
        if (hour - t0) % 24 <= span:
            f = ((hour - t0) % 24) / span
            a, b = ks[i][field], ks[(i + 1) % len(ks)][field]
            if isinstance(a, list):
                return [x + (y - x) * f for x, y in zip(a, b)]
            return a + (b - a) * f
    return ks[0][field]


def sun_pitch(hour, rise=5.0, set_=19.0):
    """Unreal pitch: negative points down (sun up), positive = below
    horizon, so the sky atmosphere goes dark at night."""
    if rise <= hour <= set_:
        elev = 75.0 * math.sin(math.pi * (hour - rise) / (set_ - rise))
    else:
        night = (hour - set_) % 24
        elev = -30.0 * math.sin(math.pi * night / (24 - (set_ - rise)))
    return -elev


def lum(rgb):
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0


def norm(rgb):
    peak = max(max(rgb), 1.0)
    return [c / peak for c in rgb]


def state_at(sky, hour):
    keys = sky["keys"]
    pitch = sun_pitch(hour)
    sun_rgb = sample(keys, hour, "sun", [255, 255, 255])
    amb = sample(keys, hour, "ambient", [100, 100, 160])
    fog = sample(keys, hour, "fog", [61, 135, 179])
    fog_dist = sample(keys, hour, "fog_dist_ft", [800, 1780])
    on, off = LAMP_TIME or sky.get("lamp_light_time") or [4.8, 19.5]
    # 0 by day, 1 by night, fading over NIGHT_FADE_H around lamp times
    to_on = (hour - on) % 24            # hours since lamps went off (dawn)
    to_off = (hour - off) % 24          # hours since lamps came on (dusk)
    if to_off < NIGHT_FADE_H:
        night_f = to_off / NIGHT_FADE_H
    elif to_on < NIGHT_FADE_H:
        night_f = 1 - to_on / NIGHT_FADE_H
    else:
        night_f = 0.0 if on <= hour < off else 1.0
    return {
        "night_f": night_f,
        "moon_pitch": -1.5 * pitch,
        "moon_lux": MOON_LUX * night_f if pitch > 0 else 0.0,
        "pitch": pitch,
        "sun_color": norm(sun_rgb),
        "sun_lux": SUN_LUX * lum(sun_rgb) if pitch < 0 else 0.0,
        "sky_color": norm(amb),
        # at night keep a cool moonlit floor so shade isn't pure black
        "sky_intensity": SKY_INTENSITY * max(lum(amb), 0.05 + 0.15 * night_f),
        "fog_color": [c / 255.0 for c in fog],
        "fog_start": fog_dist[0] * FT_TO_CM,
        "night": not (on <= hour < off),
    }


# statue/City Hall floods and brazier fires stay lit around the clock
ALWAYS_ON_PREFIXES = ("StatueLight_", "Fire_")


def night_actors():
    out = []
    for a in actors_sub.get_all_level_actors():
        label = a.get_actor_label()
        if label.startswith(ALWAYS_ON_PREFIXES):
            a.set_actor_hidden_in_game(False)
            a.set_is_temporarily_hidden_in_editor(False)
            continue
        if label.endswith("_night") or label.startswith("Lamp_Light_"):
            out.append(a)
    return out


def apply_state(st, sun, sky, fog, nights, moon=None):
    sun.set_actor_rotation(unreal.Rotator(0, st["pitch"], -40), False)
    if moon is not None:
        moon.set_actor_rotation(unreal.Rotator(0, st["moon_pitch"], 140), False)
        mc = moon.get_component_by_class(unreal.DirectionalLightComponent)
        mc.set_intensity(st["moon_lux"])
    mpc = unreal.load_asset(MPC_PATH)
    if mpc:
        world = unreal.get_editor_subsystem(
            unreal.UnrealEditorSubsystem).get_editor_world()
        unreal.MaterialLibrary.set_scalar_parameter_value(
            world, mpc, "Night", st["night_f"])
    sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    sc.set_intensity(st["sun_lux"])
    sc.set_light_color(unreal.LinearColor(*st["sun_color"], 1))
    kc = sky.get_component_by_class(unreal.SkyLightComponent)
    kc.set_intensity(st["sky_intensity"])
    kc.set_light_color(unreal.LinearColor(*st["sky_color"], 1))
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    try_set(fc, "fog_inscattering_luminance",
            unreal.LinearColor(*st["fog_color"], 1))
    try_set(fc, "start_distance", st["fog_start"])
    for a in nights:
        a.set_actor_hidden_in_game(not st["night"])
        a.set_is_temporarily_hidden_in_editor(not st["night"])


def _channels(section, cls=None):
    try:
        return section.get_all_channels()
    except AttributeError:
        return section.get_channels_by_type(cls)


def _key_color(binding, prop, frames_values):
    tr = binding.add_track(unreal.MovieSceneColorTrack)
    tr.set_property_name_and_path(prop, prop)
    sec = tr.add_section()
    sec.set_range(0, frames_values[-1][0])
    ch = _channels(sec)
    for f, (r, g, b) in frames_values:
        for c, v in zip(ch[:3], (r, g, b)):
            c.add_key(unreal.FrameNumber(f), v)
        ch[3].add_key(unreal.FrameNumber(f), 1.0)


def _key_float(binding, prop, frames_values):
    tr = binding.add_track(unreal.MovieSceneFloatTrack)
    tr.set_property_name_and_path(prop, prop)
    sec = tr.add_section()
    sec.set_range(0, frames_values[-1][0])
    ch = _channels(sec)[0]
    for f, v in frames_values:
        ch.add_key(unreal.FrameNumber(f), v)


def build_sequence(sky_data, sun, sky, fog, nights, moon=None):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    path = SEQ_DIR + "/" + SEQ_NAME
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        # refill in place: the DayNightCycle actor keeps pointing at it
        seq = unreal.load_asset(path)
        for b in list(seq.get_bindings()):
            b.remove()
        for t in list(seq.get_tracks()):
            seq.remove_track(t)
    else:
        seq = tools.create_asset(SEQ_NAME, SEQ_DIR, unreal.LevelSequence,
                                 unreal.LevelSequenceFactoryNew())
    frames_per_hour = int(FPS * 60 * MINUTES_PER_HOUR)
    end = 24 * frames_per_hour
    seq.set_display_rate(unreal.FrameRate(FPS, 1))
    seq.set_tick_resolution(unreal.FrameRate(FPS, 1))
    seq.set_playback_start(0)
    seq.set_playback_end(end)

    # frame 0 is START_HOUR; keys every half hour around the clock
    steps = [h / 2.0 for h in range(49)]
    states = [(int(h * frames_per_hour),
               state_at(sky_data, (START_HOUR + h) % 24)) for h in steps]

    # sun rotation
    sb = seq.add_possessable(sun)
    tr = sb.add_track(unreal.MovieScene3DTransformTrack)
    sec = tr.add_section()
    sec.set_range(0, end)
    ch = _channels(sec)
    loc = sun.get_actor_location()
    for f, st in states:
        for i, v in enumerate((loc.x, loc.y, loc.z, 0.0, st["pitch"], -40.0,
                               1.0, 1.0, 1.0)):
            ch[i].add_key(unreal.FrameNumber(f), v)

    scb = seq.add_possessable(
        sun.get_component_by_class(unreal.DirectionalLightComponent))
    _key_float(scb, "Intensity", [(f, s["sun_lux"]) for f, s in states])
    _key_color(scb, "LightColor", [(f, s["sun_color"]) for f, s in states])
    kcb = seq.add_possessable(
        sky.get_component_by_class(unreal.SkyLightComponent))
    _key_float(kcb, "Intensity", [(f, s["sky_intensity"]) for f, s in states])
    _key_color(kcb, "LightColor", [(f, s["sky_color"]) for f, s in states])
    if moon is not None:
        mb = seq.add_possessable(moon)
        mt = mb.add_track(unreal.MovieScene3DTransformTrack)
        msec = mt.add_section()
        msec.set_range(0, end)
        mch = _channels(msec)
        mloc = moon.get_actor_location()
        for f, st in states:
            for i, v in enumerate((mloc.x, mloc.y, mloc.z, 0.0,
                                   st["moon_pitch"], 140.0, 1.0, 1.0, 1.0)):
                mch[i].add_key(unreal.FrameNumber(f), v)
        mcb = seq.add_possessable(
            moon.get_component_by_class(unreal.DirectionalLightComponent))
        _key_float(mcb, "Intensity", [(f, s["moon_lux"]) for f, s in states])
    # MPC_CoH.Night: window glow and stars fade with it
    mpc = unreal.load_asset(MPC_PATH)
    if mpc:
        try:
            nt = seq.add_track(unreal.MovieSceneMaterialParameterCollectionTrack)
            nt.set_editor_property("mpc", mpc)
            ns = nt.add_section()
            ns.set_range(0, end)
            fine = [(int(h / 4.0 * frames_per_hour),
                     state_at(sky_data, (START_HOUR + h / 4.0) % 24)["night_f"])
                    for h in range(97)]                # every 15 minutes
            for f, v in fine:
                ns.add_scalar_parameter_key("Night", unreal.FrameNumber(f), v)
        except Exception as e:
            unreal.log_warning("[CoH setup] Night track: %s" % e)
    fcb = seq.add_possessable(
        fog.get_component_by_class(unreal.ExponentialHeightFogComponent))
    _key_color(fcb, "FogInscatteringLuminance",
               [(f, s["fog_color"]) for f, s in states])
    _key_float(fcb, "StartDistance", [(f, s["fog_start"]) for f, s in states])

    # night-only tiles: visibility switches at lamp-light time
    on, off = LAMP_TIME or sky_data.get("lamp_light_time") or [4.8, 19.5]
    def frame_of(hour):
        return int(((hour - START_HOUR) % 24) * frames_per_hour)
    def switches_for(a):
        lo, lf = (FEATURE_LIGHT_TIME if a.get_actor_label().startswith(
            FEATURE_PREFIXES) else (on, off))
        lit = not (lo <= START_HOUR < lf)
        return sorted([(0, lit), (frame_of(lo), False), (frame_of(lf), True)])
    for a in nights:
        switches = switches_for(a)
        b = seq.add_possessable(a)
        vt = b.add_track(unreal.MovieSceneVisibilityTrack)
        vt.set_property_name_and_path("bHiddenInGame", "bHiddenInGame")
        vs = vt.add_section()
        vs.set_range(0, end)
        vc = _channels(vs)[0]
        for f, visible in switches:
            # the channel stores "hidden"
            vc.add_key(unreal.FrameNumber(f), not visible)
    unreal.EditorAssetLibrary.save_loaded_asset(seq, False)

    player = None
    for a in actors_sub.get_all_level_actors():
        if isinstance(a, unreal.LevelSequenceActor) and \
                a.get_actor_label() == "DayNightCycle":
            player = a
    if player is None:
        player = actors_sub.spawn_actor_from_class(unreal.LevelSequenceActor,
                                                   unreal.Vector(0, 0, 0))
        player.set_actor_label("DayNightCycle")
        player.set_folder_path("CoH/Sky")
    player.set_sequence(seq)
    ps = player.get_editor_property("playback_settings")
    try_set(ps, "auto_play", True)
    try_set(ps, "loop_count", unreal.MovieSceneSequenceLoopCount(value=-1))
    try_set(ps, "play_rate", PLAY_RATE)
    try_set(player, "playback_settings", ps)
    try_set(player, "auto_play", True)
    log("day/night: %s, %d min loop, %d night actors" % (
        path, int(24 * MINUTES_PER_HOUR), len(nights)))


def clean():
    """Removes everything this script made (CoH/... outliner folders and
    labels), leaving the imported tiles."""
    gone = 0
    for a in actors_sub.get_all_level_actors():
        folder = str(a.get_folder_path())
        label = a.get_actor_label()
        if folder.startswith("CoH") or label.startswith(("omni_", "Lamp_")) \
                or label == "DayNightCycle":
            actors_sub.destroy_actor(a)
            gone += 1
    log("clean: removed %d actors made by this script" % gone)


def check_import():
    """True if the level's tiles came from the .gltf next to this script.
    Running against a different export (e.g. an older one) doubles the
    street lamps and misses the material fixes."""
    tiles = [a for a in actors_sub.get_all_level_actors()
             if isinstance(a, unreal.StaticMeshActor)
             and a.get_actor_label().startswith("tile_")]
    if not tiles and any(str(a.get_folder_path()).startswith("Zone")
                         for a in actors_sub.get_all_level_actors()):
        return True     # separate-objects import (import_instanced.py)
    if not tiles:
        unreal.log_error("[CoH setup] no imported tile_ actors in this level;"
                         " import the .gltf in %s first" % HERE)
        return False
    here = os.path.normcase(os.path.normpath(HERE))
    for a in tiles[:5]:
        mesh = a.static_mesh_component.get_editor_property("static_mesh")
        try:
            src = mesh.get_editor_property("asset_import_data") \
                .get_first_filename()
        except Exception:
            src = ""
        if src:
            if os.path.normcase(os.path.normpath(os.path.dirname(src))) \
                    != here:
                unreal.log_error(
                    "[CoH setup] this level was imported from %s, but this "
                    "script belongs to %s. Delete the imported actors and "
                    "the import's content folder, import the .gltf from %s, "
                    "then run this again (or add --force)."
                    % (src, HERE, HERE))
                return False
            return True
    # couldn't read the source file: fall back to what the import contains
    if load_json("_props.json") and not any(
            a.get_actor_label().endswith("_night")
            for a in actors_sub.get_all_level_actors()):
        unreal.log_error("[CoH setup] no tile_*_night actors: this looks like"
                         " an older export. Import the .gltf from %s (or add"
                         " --force)." % HERE)
        return False
    return True


def daynight():
    """Sky actors, moon + stars, editor view at START_HOUR, and a rebuilt
    DayNight sequence (without touching materials, lamps or the import)."""
    sky_data = load_json("_sky.json") or {"keys": [],
                                          "lamp_light_time": [4.8, 19.5]}
    sun, sky, fog = setup_sky()
    moon = setup_night_sky()
    nights = night_actors()
    apply_state(state_at(sky_data, START_HOUR), sun, sky, fog, nights, moon)
    build_sequence(sky_data, sun, sky, fog, nights, moon)


ONLY_STEPS = {"materials": lambda: fix_materials(),
              "daynight": lambda: daynight(),
              "statuelights": lambda: setup_statue_lights(),
              "turf": lambda: setup_turf(),
              "bronze": lambda: setup_bronze(),
              "statues": lambda: setup_statues(),
              "props": lambda: setup_props()}


def main():
    if "--clean" in sys.argv:
        clean()
        return
    if "--only" in sys.argv:
        for step in sys.argv[sys.argv.index("--only") + 1].split(","):
            if step in ONLY_STEPS:
                ONLY_STEPS[step]()
            else:
                unreal.log_error("[CoH setup] unknown step %r; steps: %s"
                                 % (step, ", ".join(ONLY_STEPS)))
        return
    hour = None
    if "--hour" in sys.argv:
        hour = float(sys.argv[sys.argv.index("--hour") + 1]) % 24
    if hour is None and "--force" not in sys.argv and not check_import():
        return
    sky_data = load_json("_sky.json") or {"keys": [],
                                          "lamp_light_time": [4.8, 19.5]}
    if hour is None:
        fix_materials()
        setup_turf()
        setup_bronze()
        setup_statues()
    sun, sky, fog = setup_sky()
    moon = setup_night_sky() if hour is None else next(
        (a for a in actors_sub.get_all_level_actors()
         if a.get_actor_label() == "Moon"), None)
    if hour is None:
        setup_lights()
        setup_props()
        setup_statue_lights()
    nights = night_actors()
    preview = START_HOUR if hour is None else hour
    apply_state(state_at(sky_data, preview), sun, sky, fog, nights, moon)
    if hour is None:
        build_sequence(sky_data, sun, sky, fog, nights, moon)
    log("done; editor view set to %02d:%02d" % (int(preview),
                                                int(preview % 1 * 60)))


main()

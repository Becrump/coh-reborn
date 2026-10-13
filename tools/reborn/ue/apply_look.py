"""Step: give AtlasPark_Reborn the old Atlas Park look (AtlasPark4).

Copied from the old map (values read with dump_look.py):
  post process   exposure 2..14 (no other exposure overrides), Lumen GI and
                 reflections, MI_CoH_Comic at weight 1 - the old volume had
                 no colour grading, saturation or bloom overrides, so its
                 saturation (1.08) comes from the comic material
  sun            10 lux at CoH sun colour, indirect x1.6, source angle 0.54,
                 shadows to 400 m, no colour temperature
  sky light      intensity 12 x CoH ambient, black lower hemisphere
  moon           1.2 lux at night, cool blue-white, 1.2 degree disc
  stars          star dome (M_CoH_Stars on the sky sphere, ~20 km)
  fog            density 0.01 starting 244 m out, volumetric, CoH fog colour
  atmosphere     planet top at the world origin, clouds traced to 50 km
  day / night    LS_Reborn_DayNight re-keyed with the old map's states
                 (CoH sky keys from atlas_park_sky.json): sun / moon angle,
                 intensity and colour, sky light, fog, and Night on both
                 MPC_Reborn (windows, lamps) and MPC_CoH (stars)
Also makes MI_CoH_Comic_Strong (the F10 menu's "strong comic"; the old
MI_CoH_Comic stays as "light comic"; build_comic_grade.py makes "vibrant").

Night lighting pass (on top of the old map's values, which left night too
dark to read):
  night floor    moon 4 lux, sky light at least 35% with a blue-grey tint,
                 (exposure floor stays EV 2: lower makes night look like day)
  fog            thin by day (0.004, starting 400 m out, far buildings keep
                 their colour), denser at night (0.02 from the camera) with
                 forward-scattering volumetric fog: lamp cones and glow
  bloom          intensity 1.0 (lamps, windows, signals, signs)
  street lamps   warm (the colour was in BGR order: they shone blue-white),
                 40 cm source / 60 cm soft radius, 36 m reach, volumetric
                 scattering x4
Safe to run again.
"""
import json
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
SKY_JSON = r"C:\Users\rtcru\CoHReborn\out\atlas_park_v5\atlas_park_sky.json"
COMIC = "/Game/CoH/Materials/MI_CoH_Comic"
COMIC_STRONG = "/Game/CoH/Materials/MI_CoH_Comic_Strong"
STRONG = {   # paint smoothing flattens texture noise; firmer ink on real edges only
    "PaintRadius": 4.0, "Bands": 5.0, "BandStrength": 0.12, "Saturation": 1.08,
    "LineThickness": 0.8, "LineStrength": 0.75, "DepthSensitivity": 4.0,
    "NormalSensitivity": 0.5, "InkDarkness": 0.3, "Brightness": 1.06, "LineFadeDistance": 30000.0,
}
# old map constants (coh2unreal/unreal/setup_level.py). The old sun was
# 10 lux; City Sample's windows and lamps are calibrated for real daylight
# and glow at full strength under a 10 lux sun, so the sun keeps the old
# map's ratios (to sky light, colours) at x7500 = 75,000 lux, and the top of
# the exposure range moves up by the same factor (log2 7500 = 12.9 EV): the
# day picture matches the old map. Night is unchanged (moon 1.2 lux, the
# exposure floor of 2 keeps nights dark), as on the old map.
DAY_SCALE = 7500.0
SUN_LUX, SKY_INTENSITY, MOON_LUX = 10.0 * DAY_SCALE, 12.0, 4.0
MOON_COLOR = (0.72, 0.82, 1.0)
NIGHT_SKY_FLOOR, NIGHT_SKY_TINT = 0.35, (0.55, 0.66, 0.88)     # blue-grey readable dark
FOG_DAY, FOG_NIGHT, FOG_DAY_START = 0.004, 0.02, 40000.0
EXPOSURE_FLOOR = 2.0                 # with the brighter moon and sky floor: blue-grey, readable
DEFAULT_COMIC = "/Game/CoH/Materials/MI_CoH_Comic_Vibrant"
LAMP_TIME, NIGHT_FADE_H, FT_TO_CM = (6.25, 18.75), 0.75, 30.48


def try_set(obj, prop, v):
    try:
        obj.set_editor_property(prop, v)
        return True
    except Exception as e:
        print("skip", prop, e)
        return False


# ---------------------------------------------------------------- comic MIs
mel = unreal.MaterialEditingLibrary
light = unreal.load_asset(COMIC)
assert light, COMIC
if not el.does_asset_exist(COMIC_STRONG):
    f, n = COMIC_STRONG.rsplit("/", 1)
    strong = tools.create_asset(n, f, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
else:
    strong = unreal.load_asset(COMIC_STRONG)
mel.set_material_instance_parent(strong, light.get_editor_property("parent"))
for k, v in STRONG.items():
    mel.set_material_instance_scalar_parameter_value(strong, k, v)
mel.update_material_instance(strong)
el.save_loaded_asset(strong, False)

# ---------------------------------------------------------------- post process
ppv = find(label="Reborn_PostProcess")[0]
ppv.modify()
s = ppv.get_editor_property("settings")
for k in dir(s):                     # only what the old volume overrode
    if k.startswith("override_"):
        try:
            if s.get_editor_property(k):
                s.set_editor_property(k, False)
        except Exception:
            pass
for prop, v in (("auto_exposure_min_brightness", EXPOSURE_FLOOR), ("bloom_intensity", 1.0), ("auto_exposure_max_brightness", 14.0 + math.log2(DAY_SCALE)),
                ("dynamic_global_illumination_method", unreal.DynamicGlobalIlluminationMethod.LUMEN),
                ("reflection_method", unreal.ReflectionMethod.LUMEN)):
    s.set_editor_property("override_" + prop, True)
    s.set_editor_property(prop, v)
wb = s.get_editor_property("weighted_blendables")
b = unreal.WeightedBlendable()
b.set_editor_property("weight", 1.0)
b.set_editor_property("object", unreal.load_asset(DEFAULT_COMIC) or light)
wb.set_editor_property("array", [b])
s.set_editor_property("weighted_blendables", wb)
ppv.set_editor_property("settings", s)

# ---------------------------------------------------------------- sky actors
lights = find(cls=unreal.DirectionalLight)
moon = next(a for a in lights if a.get_actor_label() == "Reborn_Moon")
sun = next(a for a in lights if a is not moon)
sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
for p, v in (("use_temperature", False), ("indirect_lighting_intensity", 1.6), ("light_source_angle", 0.5357),
             ("dynamic_shadow_distance_movable_light", 40000.0), ("atmosphere_sun_light", True),
             ("atmosphere_sun_light_index", 0), ("forward_shading_priority", 0)):
    try_set(sc, p, v)
mc = moon.get_component_by_class(unreal.DirectionalLightComponent)
for p, v in (("use_temperature", False), ("light_source_angle", 1.2), ("cast_shadows", True),
             ("atmosphere_sun_light", True), ("atmosphere_sun_light_index", 1), ("forward_shading_priority", 0)):
    try_set(mc, p, v)
mc.set_light_color(unreal.LinearColor(*MOON_COLOR, 1))
sky = find(cls=unreal.SkyLight)[0]
kc = sky.get_component_by_class(unreal.SkyLightComponent)
try_set(kc, "real_time_capture", True)
try_set(kc, "lower_hemisphere_is_black", True)
fog = find(cls=unreal.ExponentialHeightFog)[0]
fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
for p, v in (("fog_density", FOG_DAY), ("fog_height_falloff", 0.2), ("enable_volumetric_fog", True), ("fog_max_opacity", 1.0),
             ("volumetric_fog_scattering_distribution", 0.6), ("volumetric_fog_extinction_scale", 1.0),
             ("volumetric_fog_distance", 8000.0)):
    try_set(fc, p, v)

# street lamps: warm, soft and spilling (the blueprint the PCG streets spawn)
lamp_bp = el.load_asset(ROOT + "/Roads/BP_RebornStreetLamp")
if lamp_bp:
    ss = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    for h in ss.k2_gather_subobject_data_for_blueprint(lamp_bp):
        o = lib.get_object(lib.get_data(h))
        if isinstance(o, unreal.SpotLightComponent):
            for p2, v2 in (("light_color", unreal.Color(r=255, g=196, b=140, a=255)), ("source_radius", 40.0),
                           ("soft_source_radius", 60.0), ("attenuation_radius", 3600.0),
                           ("volumetric_scattering_intensity", 4.0), ("inner_cone_angle", 35.0), ("outer_cone_angle", 66.0)):
                try_set(o, p2, v2)
    unreal.BlueprintEditorLibrary.compile_blueprint(lamp_bp)
    el.save_loaded_asset(lamp_bp, False)
else:
    print("no BP_RebornStreetLamp found")
for a in find(cls=unreal.SkyAtmosphere):
    try_set(a.get_component_by_class(unreal.SkyAtmosphereComponent), "transform_mode",
            unreal.SkyAtmosphereTransformMode.PLANET_TOP_AT_ABSOLUTE_WORLD_ORIGIN)
for a in find(cls=unreal.VolumetricCloud):
    try_set(a.get_component_by_class(unreal.VolumetricCloudComponent), "tracing_max_distance", 50.0)
# star dome: the old map's sky sphere with the CoH stars (Reborn had the
# engine's simple sky dome there)
stars_mat = unreal.load_asset("/Game/CoH/Materials/M_CoH_Stars")
dome = next((a for a in find(cls=unreal.StaticMeshActor) if a.get_actor_label() in ("StarDome", "SM_SkySphere")), None)
if dome is None:
    dome = actors.spawn_actor_from_object(unreal.load_asset("/Engine/EngineSky/SM_SkySphere"), unreal.Vector(0, 0, 0))
dome.set_actor_label("StarDome")
dome.set_folder_path("AtlasReborn/Lighting")
dc = dome.static_mesh_component
dc.set_static_mesh(unreal.load_asset("/Engine/EngineSky/SM_SkySphere"))
dc.set_material(0, stars_mat)
dome.set_actor_location(unreal.Vector(0, 0, 0), False, False)
dome.set_actor_scale3d(unreal.Vector(488.28125, 488.28125, 488.28125))
for p, v in (("cast_shadow", False), ("affect_distance_field_lighting", False), ("affect_dynamic_indirect_lighting", False),
             ("visible_in_ray_tracing", False), ("visible_in_reflection_captures", False)):
    try_set(dc, p, v)
dc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)


# ---------------------------------------------------------------- day / night
def sample(keys, hour, field, default):
    ks = [k for k in keys if field in k]
    if not ks:
        return default
    ks = sorted(ks, key=lambda k: k["time"] % 24)
    times = [k["time"] % 24 for k in ks]
    for i in range(len(ks)):
        t0, t1 = times[i], times[(i + 1) % len(ks)]
        span = (t1 - t0) % 24 or 24
        if (hour - t0) % 24 <= span:
            f = ((hour - t0) % 24) / span
            a, b2 = ks[i][field], ks[(i + 1) % len(ks)][field]
            if isinstance(a, list):
                return [x + (y - x) * f for x, y in zip(a, b2)]
            return a + (b2 - a) * f
    return ks[0][field]


def sun_pitch(hour, rise=5.0, set_=19.0):
    if rise <= hour <= set_:
        elev = 75.0 * math.sin(math.pi * (hour - rise) / (set_ - rise))
    else:
        elev = -30.0 * math.sin(math.pi * ((hour - set_) % 24) / (24 - (set_ - rise)))
    return -elev


def lum(rgb):
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0


def norm(rgb):
    peak = max(max(rgb), 1.0)
    return [c / peak for c in rgb]


def state_at(sky_data, hour):
    keys = sky_data["keys"]
    pitch = sun_pitch(hour)
    sun_rgb = sample(keys, hour, "sun", [255, 255, 255])
    amb = sample(keys, hour, "ambient", [100, 100, 160])
    fogc = sample(keys, hour, "fog", [61, 135, 179])
    fog_dist = sample(keys, hour, "fog_dist_ft", [800, 1780])
    on, off = LAMP_TIME
    to_on, to_off = (hour - on) % 24, (hour - off) % 24
    if to_off < NIGHT_FADE_H:
        night_f = to_off / NIGHT_FADE_H
    elif to_on < NIGHT_FADE_H:
        night_f = 1 - to_on / NIGHT_FADE_H
    else:
        night_f = 0.0 if on <= hour < off else 1.0
    return {"night_f": night_f, "moon_pitch": -1.5 * pitch, "moon_lux": MOON_LUX * night_f,
            "pitch": pitch, "sun_color": norm(sun_rgb), "sun_lux": SUN_LUX * lum(sun_rgb) if pitch < 0 else 0.0,
            "sky_color": [a + (b - a) * night_f for a, b in zip(norm(amb), NIGHT_SKY_TINT)],
            "sky_intensity": SKY_INTENSITY * max(lum(amb), 0.05 + NIGHT_SKY_FLOOR * night_f),
            "fog_color": [c / 255.0 for c in fogc],
            "fog_start": max(fog_dist[0] * FT_TO_CM, FOG_DAY_START) * (1 - night_f),
            "fog_density": FOG_DAY + (FOG_NIGHT - FOG_DAY) * night_f}


sky_data = json.load(open(SKY_JSON))
MPC_R = unreal.load_asset(ROOT + "/Materials/MPC_Reborn")
MPC_C = unreal.load_asset("/Game/CoH/Materials/MPC_CoH")


def apply_state(st):
    """editor preview of one moment"""
    sun.set_actor_rotation(unreal.Rotator(0, st["pitch"], -40), False)
    moon.set_actor_rotation(unreal.Rotator(0, st["moon_pitch"], 140), False)
    mc.set_intensity(st["moon_lux"])
    sc.set_intensity(st["sun_lux"])
    sc.set_light_color(unreal.LinearColor(*st["sun_color"], 1))
    kc.set_intensity(st["sky_intensity"])
    kc.set_light_color(unreal.LinearColor(*st["sky_color"], 1))
    kc.recapture_sky()               # the editor's real-time capture lags behind in a background window
    try_set(fc, "fog_inscattering_luminance", unreal.LinearColor(*st["fog_color"], 1))
    try_set(fc, "start_distance", st["fog_start"])
    try_set(fc, "fog_density", st["fog_density"])
    w = world()
    for m in (MPC_R, MPC_C):
        if m:
            unreal.MaterialLibrary.set_scalar_parameter_value(w, m, "Night", st["night_f"])


def build_sequence():
    FPS, MINUTES = 30, 24
    FRAMES = FPS * 60 * MINUTES               # frame 0 = 00:00, 1 real minute = 1 game hour
    per_hour = FRAMES // 24
    seq = el.load_asset(ROOT + "/LS_Reborn_DayNight")
    for bd in list(seq.get_bindings()):
        bd.remove()
    for t in list(seq.get_tracks()):
        seq.remove_track(t)
    seq.set_playback_start(0)
    seq.set_playback_end(FRAMES)
    states = [(int(h / 2.0 * per_hour), state_at(sky_data, (h / 2.0) % 24)) for h in range(49)]

    def chans(sec):
        return sec.get_all_channels()

    def transform(actor, fn):
        bd = seq.add_possessable(actor)
        tr = bd.add_track(unreal.MovieScene3DTransformTrack)
        sec = tr.add_section()
        sec.set_range(0, FRAMES)
        ch = chans(sec)
        loc = actor.get_actor_location()
        for f, st in states:
            for i, v in enumerate((loc.x, loc.y, loc.z) + fn(st) + (1.0, 1.0, 1.0)):
                ch[i].add_key(unreal.FrameNumber(f), v)

    def key_float(bd, prop, vals):
        tr = bd.add_track(unreal.MovieSceneFloatTrack)
        tr.set_property_name_and_path(prop, prop)
        sec = tr.add_section()
        sec.set_range(0, FRAMES)
        ch = chans(sec)[0]
        for f, v in vals:
            ch.add_key(unreal.FrameNumber(f), v)

    def key_color(bd, prop, vals):
        tr = bd.add_track(unreal.MovieSceneColorTrack)
        tr.set_property_name_and_path(prop, prop)
        sec = tr.add_section()
        sec.set_range(0, FRAMES)
        ch = chans(sec)
        for f, (r, g, b3) in vals:
            for c, v in zip(ch[:3], (r, g, b3)):
                c.add_key(unreal.FrameNumber(f), v)
            ch[3].add_key(unreal.FrameNumber(f), 1.0)

    transform(sun, lambda st: (0.0, st["pitch"], -40.0))
    transform(moon, lambda st: (0.0, st["moon_pitch"], 140.0))
    scb = seq.add_possessable(sc)
    key_float(scb, "Intensity", [(f, s2["sun_lux"]) for f, s2 in states])
    key_color(scb, "LightColor", [(f, s2["sun_color"]) for f, s2 in states])
    mcb = seq.add_possessable(mc)
    key_float(mcb, "Intensity", [(f, s2["moon_lux"]) for f, s2 in states])
    kcb = seq.add_possessable(kc)
    key_float(kcb, "Intensity", [(f, s2["sky_intensity"]) for f, s2 in states])
    key_color(kcb, "LightColor", [(f, s2["sky_color"]) for f, s2 in states])
    fcb = seq.add_possessable(fc)
    key_color(fcb, "FogInscatteringLuminance", [(f, s2["fog_color"]) for f, s2 in states])
    key_float(fcb, "StartDistance", [(f, s2["fog_start"]) for f, s2 in states])
    key_float(fcb, "FogDensity", [(f, s2["fog_density"]) for f, s2 in states])
    fine = [(int(q / 4.0 * per_hour), state_at(sky_data, (q / 4.0) % 24)["night_f"]) for q in range(97)]
    for m in (MPC_R, MPC_C):
        if not m:
            continue
        nt = seq.add_track(unreal.MovieSceneMaterialParameterCollectionTrack)
        nt.set_editor_property("mpc", m)
        ns = nt.add_section()
        ns.set_range(0, FRAMES)
        for f, v in fine:
            ns.add_scalar_parameter_key("Night", unreal.FrameNumber(f), v)
    el.save_loaded_asset(seq, False)


HOUR = float(os.environ.get("REBORN_LOOK_HOUR", "10"))
if os.environ.get("REBORN_LOOK_PREVIEW_ONLY") != "1":
    build_sequence()
apply_state(state_at(sky_data, HOUR))
print("old Atlas Park look applied; preview at %.1f h" % HOUR)

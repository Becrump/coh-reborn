"""Dump the lighting / post-process look of the open level to JSON.

    REBORN_LOOK_OUT=<file.json> python ue/run.py dump_look.py

Records every overridden post-process setting (and its blendables), the sky
light, directional lights (sun, moon), sky atmosphere, height fog, clouds,
star dome and day/night sequence actors, so a look can be copied between
levels with apply_look.py.
"""
import json
import os

import unreal

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
OUT = os.environ.get("REBORN_LOOK_OUT", os.path.join(os.environ.get("TEMP", "."), "look.json"))


def val(v):
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if isinstance(v, unreal.Enum) or hasattr(v, "name") and isinstance(getattr(v, "value", None), int):
        return {"enum": type(v).__name__, "name": v.name}
    if isinstance(v, unreal.Object):
        return {"object": v.get_path_name()}
    if isinstance(v, (list, tuple, unreal.Array)):
        return [val(x) for x in v]
    if isinstance(v, unreal.StructBase):
        d = {"struct": type(v).__name__}
        for k in dir(v):
            if k.startswith("_"):
                continue
            try:
                x = v.get_editor_property(k)
            except Exception:
                continue
            d[k] = val(x)
        return d
    return str(v)


def props(obj, names):
    d = {}
    for n in names:
        try:
            d[n] = val(obj.get_editor_property(n))
        except Exception:
            pass
    return d


def pp_settings(s):
    d = {}
    for k in dir(s):
        if not k.startswith("override_"):
            continue
        try:
            if not s.get_editor_property(k):
                continue
            name = k[len("override_"):]
            d[name] = val(s.get_editor_property(name))
        except Exception as e:
            d[k] = "ERR %s" % e
    wb = s.get_editor_property("weighted_blendables").get_editor_property("array")
    d["__blendables"] = [{"object": b.get_editor_property("object").get_path_name() if b.get_editor_property("object") else None,
                          "weight": b.get_editor_property("weight")} for b in wb]
    return d


LIGHT = ["intensity", "intensity_units", "light_color", "use_temperature", "temperature", "indirect_lighting_intensity",
         "volumetric_scattering_intensity", "light_source_angle", "light_source_soft_angle", "cast_shadows",
         "atmosphere_sun_light", "atmosphere_sun_light_index", "forward_shading_priority", "mobility",
         "dynamic_shadow_distance_movable_light", "cascade_distribution_exponent", "dynamic_shadow_cascades",
         "specular_scale", "cast_cloud_shadows", "cloud_scattered_luminance_scale"]
SKY = ["intensity", "light_color", "real_time_capture", "source_type", "cubemap", "lower_hemisphere_is_black",
       "lower_hemisphere_color", "indirect_lighting_intensity", "volumetric_scattering_intensity", "sky_distance_threshold",
       "cubemap_resolution", "mobility", "occlusion_max_distance", "min_occlusion", "occlusion_tint", "cast_shadows"]
FOG = ["fog_density", "fog_height_falloff", "fog_inscattering_luminance", "fog_inscattering_color", "fog_max_opacity",
       "start_distance", "enable_volumetric_fog", "volumetric_fog_scattering_distribution", "volumetric_fog_albedo",
       "volumetric_fog_extinction_scale", "volumetric_fog_distance", "directional_inscattering_luminance",
       "second_fog_data", "sky_atmosphere_ambient_contribution_color_scale"]
ATM = ["rayleigh_scattering_scale", "rayleigh_scattering", "rayleigh_exponential_distribution", "mie_scattering_scale",
       "mie_absorption_scale", "mie_anisotropy", "mie_exponential_distribution", "multi_scattering_factor",
       "sky_luminance_factor", "aerial_pespective_view_distance_scale", "height_fog_contribution", "ground_albedo",
       "atmosphere_height", "transform_mode", "sky_and_aerial_perspective_luminance_factor"]

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
out = {"level": world.get_path_name(), "post_process": [], "sky_light": [], "directional": [], "fog": [], "atmosphere": [],
       "clouds": [], "star_dome": [], "sequences": [], "mpc": {}}
for a in actors.get_all_level_actors():
    lab = a.get_actor_label()
    if isinstance(a, unreal.PostProcessVolume):
        out["post_process"].append({"label": lab, "unbound": a.get_editor_property("unbound"),
                                    "priority": a.get_editor_property("priority"),
                                    "blend_weight": a.get_editor_property("blend_weight"),
                                    "enabled": a.get_editor_property("enabled"),
                                    "settings": pp_settings(a.get_editor_property("settings"))})
    elif isinstance(a, unreal.SkyLight):
        out["sky_light"].append({"label": lab, **props(a.get_component_by_class(unreal.SkyLightComponent), SKY)})
    elif isinstance(a, unreal.DirectionalLight):
        c = a.get_component_by_class(unreal.DirectionalLightComponent)
        out["directional"].append({"label": lab, "rotation": val(a.get_actor_rotation()), **props(c, LIGHT)})
    elif isinstance(a, unreal.ExponentialHeightFog):
        out["fog"].append({"label": lab, **props(a.get_component_by_class(unreal.ExponentialHeightFogComponent), FOG)})
    elif isinstance(a, unreal.SkyAtmosphere):
        out["atmosphere"].append({"label": lab, **props(a.get_component_by_class(unreal.SkyAtmosphereComponent), ATM)})
    elif isinstance(a, unreal.VolumetricCloud):
        out["clouds"].append({"label": lab, **props(a.get_component_by_class(unreal.VolumetricCloudComponent),
                                                     ["layer_bottom_altitude", "layer_height", "material", "tracing_max_distance"])})
    elif isinstance(a, unreal.LevelSequenceActor):
        out["sequences"].append({"label": lab, "sequence": a.get_sequence().get_path_name() if a.get_sequence() else None})
    elif ("Star" in lab or "Sky" in lab) and a.get_component_by_class(unreal.StaticMeshComponent):
        c = a.get_component_by_class(unreal.StaticMeshComponent)
        out["star_dome"].append({"label": lab, "mesh": val(c.get_editor_property("static_mesh")),
                                 "materials": [val(m) for m in c.get_materials()], "scale": val(a.get_actor_scale3d()),
                                 "location": val(a.get_actor_location())})
for path in ("/Game/CoH/MPC_CoH", "/Game/CoH/Materials/MPC_CoH", "/Game/AtlasReborn/Materials/MPC_Reborn"):
    m = unreal.EditorAssetLibrary.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if m:
        out["mpc"][path] = {"scalars": [{"name": str(p.get_editor_property("parameter_name")), "default": p.get_editor_property("default_value")}
                                        for p in m.get_editor_property("scalar_parameters")]}
json.dump(out, open(OUT, "w"), indent=1, default=str)
print("look dumped", OUT, {k: len(v) for k, v in out.items() if isinstance(v, (list, dict))})

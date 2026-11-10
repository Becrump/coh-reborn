"""Shared helpers for the window glass scripts (run inside the Unreal editor).

glass_map.json   original window material -> texture key, panes, theme, extra (masked / mirror)
window_masks.json texture key -> colour-key mask settings or a hand-painted mask texture
"""
import json
import os
import re

import unreal

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    r"C:\Users\rtcru\ClaudeProjects\coh-reborn-dm8n7k\unreal\scripts\glass"
FOLDER = "/Game/GlassUpgrade"
MAP = json.load(open(os.path.join(HERE, "glass_map.json")))
MASKS = json.load(open(os.path.join(HERE, "window_masks.json")))
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
WINDOWISH = re.compile(r"win|glass|reflect", re.I)


def norm(name):
    """Match key for a material name: case, a leading 'x_', '.tga'/'_tga' and '__GLASS' don't matter."""
    n = name.lower()
    n = re.sub(r"__glass$", "", n)
    n = re.sub(r"[._]tga$", "", n)
    return re.sub(r"^x_", "", n)


WINDOWS = {norm(k): (k, v) for k, v in MAP["windows"].items()}
SKIP = {norm(k): v for k, v in MAP["skip"].items()}
PENDING = {norm(k) for k in MAP.get("pending_galaxy_city", {})}


def lookup(material_name):
    """-> ('glass', entry) | ('skip', reason) | ('pending', None) | ('unmapped', None) | (None, None)"""
    k = norm(material_name)
    if k in WINDOWS:
        return "glass", WINDOWS[k][1]
    if k in SKIP:
        return "skip", SKIP[k]
    if k in PENDING:
        return "pending", None
    return ("unmapped", None) if WINDOWISH.search(material_name) else (None, None)


def _params(mi):
    tex = {str(p.parameter_info.name): p.parameter_value for p in mi.get_editor_property("texture_parameter_values")}
    vec = {str(p.parameter_info.name): p.parameter_value for p in mi.get_editor_property("vector_parameter_values")}
    sca = {str(p.parameter_info.name): p.parameter_value for p in mi.get_editor_property("scalar_parameter_values")}
    return tex, vec, sca


def glass_child(option, orig, entry, refresh=False, saved=None):
    """Per-texture glass instance for an original window MI (created once, then reused as-is).
    Returns the MI; appends its package to `saved` when it was created or refreshed."""
    key = entry["texture"]
    name = "MI_Glass_%s_%s" % (option, key[:-2] if key.endswith("_b") else key)
    path = "%s/PerTexture/%s" % (FOLDER, name)
    if EAL.does_asset_exist(path) and not refresh:
        return unreal.load_asset(path)  # no update, no save, no shader work
    mi = unreal.load_asset(path) if EAL.does_asset_exist(path) else TOOLS.create_asset(
        name, FOLDER + "/PerTexture", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, unreal.load_asset("%s/MI_Glass_%s" % (FOLDER, option)))
    tex, vec, sca = _params(orig)
    MEL.set_material_instance_texture_parameter_value(mi, "WindowTexture", tex["BaseColorTexture"])
    if tex.get("NormalTexture"):
        MEL.set_material_instance_texture_parameter_value(mi, "NormalTexture", tex["NormalTexture"])
    if tex.get("GlowTexture"):  # keep the original lit-window pattern for night
        MEL.set_material_instance_texture_parameter_value(mi, "GlowTexture", tex["GlowTexture"])
        gs = vec.get("GlowScale")
        if gs and (gs.r or gs.g):
            MEL.set_material_instance_vector_parameter_value(mi, "GlowUVScale", unreal.LinearColor(gs.r, gs.g, 0, 0))
        MEL.set_material_instance_scalar_parameter_value(mi, "GlowStrength", 1.5 if option != "Interior" else 0.5)
    m = MASKS[key]
    if m.get("key") == "texture":  # hand-painted mask (make_rect_masks.py + import_masks.py)
        MEL.set_material_instance_scalar_parameter_value(mi, "UseMaskTexture", 1.0)
        MEL.set_material_instance_texture_parameter_value(mi, "PaneMaskTexture", unreal.load_asset(m["mask_texture"]))
    else:
        MEL.set_material_instance_vector_parameter_value(mi, "MaskWeights", unreal.LinearColor(*m["MaskWeights"]))
        for k in ("MaskThreshold", "MaskSoftness", "MaskInvert"):
            MEL.set_material_instance_scalar_parameter_value(mi, k, float(m[k]))
    MEL.set_material_instance_scalar_parameter_value(mi, "PanesPerTile", float(entry["panes_x"]))
    MEL.set_material_instance_scalar_parameter_value(mi, "PanesPerTileY", float(entry["panes_y"]))
    MEL.set_material_instance_scalar_parameter_value(mi, "ThemeOverride", float(entry["theme"]))
    if entry["extra"] == "mirror":
        MEL.set_material_instance_scalar_parameter_value(mi, "ReflectiveOnlyFraction", 1.0)
    if entry["extra"] == "masked":  # keep the original alpha cut-outs
        o = mi.get_editor_property("base_property_overrides")
        o.set_editor_property("override_blend_mode", True)
        o.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        o.set_editor_property("override_opacity_mask_clip_value", True)
        o.set_editor_property("opacity_mask_clip_value", float(sca.get("AlphaCutoff", 0.3)))
        mi.set_editor_property("base_property_overrides", o)
    MEL.update_material_instance(mi)
    if saved is not None:
        saved.append(mi.get_package())
    return mi


def backup(orig, saved=None):
    """Copy an original MI to /Game/GlassUpgrade/OriginalBackup/<its folder> once (rollback source)."""
    src = orig.get_path_name().split(".")[0]
    dst = FOLDER + "/OriginalBackup" + src[len("/Game"):]
    if not EAL.does_asset_exist(dst):
        dup = EAL.duplicate_asset(src, dst)
        if saved is not None and dup:
            saved.append(dup.get_package())
    return dst

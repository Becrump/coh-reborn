"""Shared helpers for the Atlas Park Reborn Unreal scripts (run inside the editor)."""
import json
import os

import unreal

ROOT = "/Game/AtlasReborn"
MAP = ROOT + "/AtlasPark_Reborn"
OUT = os.environ.get("ATLAS_REBORN_OUT", r"C:\Users\rtcru\CoHReborn\out\atlas_reborn")

el = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
mel = unreal.MaterialEditingLibrary


def layout():
    with open(os.path.join(OUT, "layout.json")) as f:
        return json.load(f)


def world():
    return editor.get_editor_world()


def require_map():
    path = world().get_path_name()
    assert path.startswith(MAP), "open %s first (current: %s)" % (MAP, path)
    assert editor.get_game_world() is None, "stop Play-In-Editor first"


def find(label=None, cls=None):
    out = []
    for a in actors.get_all_level_actors():
        if cls and not isinstance(a, cls):
            continue
        if label and a.get_actor_label() != label:
            continue
        out.append(a)
    return out


def import_texture(src, dest_dir, name, srgb=True, nearest=False, mips=True,
                   compression=None):
    task = unreal.AssetImportTask()
    task.filename = src
    task.destination_path = dest_dir
    task.destination_name = name
    task.replace_existing = True
    task.automated = True
    task.save = False
    tools.import_asset_tasks([task])
    tex = el.load_asset(dest_dir + "/" + name)
    tex.set_editor_property("srgb", srgb)
    if nearest:
        tex.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)
    if not mips:
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("never_stream", True)
    if compression is not None:
        tex.set_editor_property("compression_settings", compression)
    el.save_loaded_asset(tex)
    return tex


def new_material(path):
    if el.does_asset_exist(path):
        el.delete_asset(path)
    d, n = path.rsplit("/", 1)
    return tools.create_asset(n, d, unreal.Material, unreal.MaterialFactoryNew())


def expr(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, a_out, b, b_in):
    assert mel.connect_material_expressions(a, a_out, b, b_in), (a, a_out, b, b_in)


def mark_spline_edited(s):
    """Keep script-made points: a Blueprint's spline component is rebuilt from
    its defaults on load / Play unless it is flagged as edited."""
    s.set_editor_property("spline_has_been_edited", True)

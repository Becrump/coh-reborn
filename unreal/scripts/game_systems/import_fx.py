"""Step 5 (docs/power-effects.md): the original effects' textures and sounds,
and the master particle materials the C++ effect player (CoHEffects.cpp) uses.

Globals:
  GS_STEP    'materials'  M_CoHParticle_Additive / _Normal / _Multiply /
                          _Subtractive / _Premultiplied in /Game/CoH/FX/Particle
                          (unlit, two-sided, texture parameter "Tex" x vertex colour)
             'assets'     textures -> /Game/CoH/FX/Textures, sounds -> /Game/CoH/FX/Sounds
  GS_POWERS  power name prefixes whose effects to import (None: every power)
  GS_BATCH   textures / sounds per batch (a save after each), default 100

Asset names: the file stem, lower case, anything but letters, digits and _
as _ (the same rule as AssetName() in CoHEffects.cpp). Each PNG is checked
with PIL first (opens, non-empty, 8-bit RGB/RGBA; converted otherwise) and
names that exist as anything but a Texture2D / SoundWave are skipped and
logged. Only the packages this script creates are saved.
"""
import json
import os
import re
import tempfile
import unreal

LIBS = [r"C:\Users\rtcru\CoHReborn\out\fx", r"C:\Users\rtcru\CoHReborn\out\enemies\fx"]
TEX = "/Game/CoH/FX/Textures"
SND = "/Game/CoH/FX/Sounds"
MAT = "/Game/CoH/FX/Particle"
el = unreal.EditorAssetLibrary
step = globals().get("GS_STEP", "assets")
batch = int(globals().get("GS_BATCH") or 100)


def asset_name(f):
    return re.sub(r"[^a-z0-9_]", "_", os.path.splitext(os.path.basename(f))[0].lower())


def make_materials():
    mel = unreal.MaterialEditingLibrary
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    modes = {"Additive": unreal.BlendMode.BLEND_ADDITIVE, "Normal": unreal.BlendMode.BLEND_TRANSLUCENT,
             "Multiply": unreal.BlendMode.BLEND_MODULATE, "Subtractive": unreal.BlendMode.BLEND_MODULATE,
             "Premultiplied": unreal.BlendMode.BLEND_ALPHA_COMPOSITE}
    made = []
    for mode, blend in modes.items():
        name = "M_CoHParticle_" + mode
        if el.does_asset_exist(MAT + "/" + name):
            continue
        m = tools.create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())
        m.set_editor_property("blend_mode", blend)
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        m.set_editor_property("two_sided", True)
        tex = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -700, 0)
        tex.set_editor_property("parameter_name", "Tex")
        tex.set_editor_property("texture", unreal.load_asset("/Engine/EngineResources/WhiteSquareTexture"))
        vc = mel.create_material_expression(m, unreal.MaterialExpressionVertexColor, -700, 300)
        rgb = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -400, 0)
        mel.connect_material_expressions(tex, "RGB", rgb, "A")
        mel.connect_material_expressions(vc, "", rgb, "B")
        a = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -400, 300)
        mel.connect_material_expressions(tex, "A", a, "A")
        mel.connect_material_expressions(vc, "A", a, "B")
        if mode == "Additive":
            out = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -200, 0)
            mel.connect_material_expressions(rgb, "", out, "A")
            mel.connect_material_expressions(a, "", out, "B")
            mel.connect_material_property(out, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        elif mode in ("Multiply", "Subtractive"):
            # modulate: the scene times the colour, faded towards white by
            # alpha; subtractive darkens by the colour instead
            one = mel.create_material_expression(m, unreal.MaterialExpressionConstant, -400, 150)
            one.set_editor_property("r", 1.0)
            src = rgb
            if mode == "Subtractive":
                sub = mel.create_material_expression(m, unreal.MaterialExpressionOneMinus, -300, 0)
                mel.connect_material_expressions(rgb, "", sub, "")
                src = sub
            lerp = mel.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -200, 0)
            mel.connect_material_expressions(one, "", lerp, "A")
            mel.connect_material_expressions(src, "", lerp, "B")
            mel.connect_material_expressions(a, "", lerp, "Alpha")
            mel.connect_material_property(lerp, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        else:
            mel.connect_material_property(rgb, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
            mel.connect_material_property(a, "", unreal.MaterialProperty.MP_OPACITY)
        mel.recompile_material(m)      # one compile per new (small) material, once
        el.save_loaded_asset(m, False)
        made.append(name)
    print("MATERIALS", made or "all there")


def power_fx_roots(p):
    """Every effect file a power names: its *FX keys and those of each
    customizable theme (nested under "themes")."""
    out = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.endswith("FX") and isinstance(v, str):
                    out.append(v.lower())
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(p)
    return out


def wanted():
    """Textures and sounds the chosen powers' effects use (child effects included)."""
    prefixes = globals().get("GS_POWERS")
    tex, snd = {}, {}
    for lib_dir in LIBS:
        lib = json.load(open(os.path.join(lib_dir, "fx_library.json")))
        pfx = json.load(open(os.path.join(lib_dir, "power_fx.json")))
        todo = []
        for pname, p in pfx.items():
            if prefixes and not any(pname.startswith(x) for x in prefixes):
                continue
            todo += power_fx_roots(p)
        seen = set()
        while todo:
            f = todo.pop()
            if f in seen or f not in lib["fx"]:
                continue
            seen.add(f)
            for c in lib["fx"][f]["conditions"]:
                for ev in c["events"]:
                    if ev.get("childfx"):
                        todo.append(ev["childfx"].lower())
                    for s in ev.get("sounds", []):
                        info = lib["sounds"].get(s["name"].lower())
                        if info:
                            snd[asset_name(info["file"])] = os.path.join(lib_dir, info["file"])
                    for part in ev.get("parts", []):
                        pi = lib["parts"].get(part)
                        if not pi:
                            continue
                        t = (pi.get("TextureName") or "").lower()
                        info = lib["textures"].get(t) or lib["textures"].get(t + ".tga")
                        if info:
                            tex[asset_name(info["png"])] = os.path.join(lib_dir, info["png"])
    return tex, snd


def checked_png(path):
    try:
        from PIL import Image
    except ImportError:
        # the editor's Python has no PIL: read the PNG header (IHDR) instead
        import struct
        with open(path, "rb") as f:
            head = f.read(33)
        if len(head) < 33 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
            return None, "not a PNG"
        w, h, depth, ctype = struct.unpack(">IIBB", head[16:26])
        if w <= 0 or h <= 0:
            return None, "empty"
        if depth != 8 or ctype not in (2, 6):
            return None, "depth %d colour type %d (convert first)" % (depth, ctype)
        return path, None
    try:
        im = Image.open(path)
        im.load()
    except Exception as e:
        return None, "unreadable (%s)" % e
    if im.width <= 0 or im.height <= 0:
        return None, "empty"
    if im.mode in ("RGB", "RGBA"):
        return path, None
    out = os.path.join(tempfile.gettempdir(), "coh_fx_png", os.path.basename(path))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.convert("RGBA").save(out)
    return out, None


def import_files(items, dest, kind):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    names = sorted(items)
    skipped, done = [], 0
    for b in range(0, len(names), batch):
        tasks = []
        for n in names[b:b + batch]:
            path = dest + "/" + n
            if el.does_asset_exist(path):
                cls = str(el.find_asset_data(path).asset_class_path.asset_name)
                if cls not in ("Texture2D", "SoundWave"):
                    skipped.append("%s exists as %s" % (n, cls))
                continue
            src = items[n]
            if kind == "texture":
                src, why = checked_png(src)
                if not src:
                    skipped.append("%s %s" % (n, why))
                    continue
            elif not os.path.exists(src):
                skipped.append("%s missing file" % n)
                continue
            t = unreal.AssetImportTask()
            t.set_editor_property("filename", src)
            t.set_editor_property("destination_path", dest)
            t.set_editor_property("destination_name", n)
            t.set_editor_property("automated", True)
            t.set_editor_property("replace_existing", False)
            t.set_editor_property("save", True)
            tasks.append(t)
        if tasks:
            tools.import_asset_tasks(tasks)
            done += len(tasks)
        print("  %s batch %d: %d imported so far" % (kind, b // batch + 1, done))
    for s in skipped:
        print("  skipped", s)
    return done


def make_geom_material():
    """M_CoHGeom: lit, opaque, texture parameter "Tex", for effect models
    (weapons in hand, beams)."""
    name = "M_CoHGeom"
    if el.does_asset_exist(MAT + "/" + name) or unreal.load_asset(MAT + "/" + name + "." + name):
        print("have", name)
        return
    mel = unreal.MaterialEditingLibrary
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("two_sided", True)
    tex = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -500, 0)
    tex.set_editor_property("parameter_name", "Tex")
    tex.set_editor_property("texture", unreal.load_asset("/Engine/EngineResources/WhiteSquareTexture"))
    mel.connect_material_property(tex, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    rough = mel.create_material_expression(m, unreal.MaterialExpressionConstant, -500, 250)
    rough.set_editor_property("r", 0.55)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(m)
    el.save_loaded_asset(m, False)
    print("MATERIAL", name)


def import_geoms():
    """Visible effect models the chosen powers use (weapons first), as static
    meshes in /Game/CoH/FX/Geoms, and their textures."""
    prefixes = globals().get("GS_POWERS")
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    tex = {}
    done = 0
    for lib_dir in LIBS:
        lib = json.load(open(os.path.join(lib_dir, "fx_library.json")))
        pfx = json.load(open(os.path.join(lib_dir, "power_fx.json")))
        todo, seen, models = [], set(), set()
        for pname, p in pfx.items():
            if prefixes and not any(pname.startswith(x) for x in prefixes):
                continue
            todo += power_fx_roots(p)
        while todo:
            f = todo.pop()
            if f in seen or f not in lib["fx"]:
                continue
            seen.add(f)
            for c in lib["fx"][f]["conditions"]:
                for ev in c["events"]:
                    if ev.get("childfx"):
                        todo.append(ev["childfx"].lower())
                    for g in ev.get("geoms", []):
                        info = lib["geoms"].get(g.lower())
                        if info and info.get("mesh"):
                            models.add(g.lower())
        for g in sorted(models):
            info = lib["geoms"][g]
            n = asset_name(info["mesh"])
            for t in info.get("textures", []):
                ti = lib["textures"].get(t.lower()) or lib["textures"].get(t.lower() + ".tga")
                if ti:
                    tex[asset_name(ti["png"])] = os.path.join(lib_dir, ti["png"])
            if el.does_asset_exist(GEO + "/" + n):
                continue
            pipe = unreal.InterchangeGenericAssetsPipeline()
            pipe.set_editor_property("scene_name_sub_folder", False)
            pipe.set_editor_property("asset_type_sub_folders", False)
            mesh = pipe.get_editor_property("mesh_pipeline")
            mesh.set_editor_property("import_skeletal_meshes", False)
            mesh.set_editor_property("import_static_meshes", True)
            params = unreal.ImportAssetParameters()
            params.set_editor_property("is_automated", True)
            params.set_editor_property("replace_existing", False)
            params.set_editor_property("override_pipelines", [unreal.SoftObjectPath(pipe.get_path_name())])
            # the asset takes the file's name, which is already the asset name
            try:
                mgr.import_asset(GEO, unreal.InterchangeManager.create_source_data(os.path.join(lib_dir, info["mesh"])), params)
            except Exception as e:
                print("  warn", n, str(e)[:160])
            if el.does_asset_exist(GEO + "/" + n):
                el.save_asset(GEO + "/" + n, False)
                done += 1
            else:
                print("  missing after import", n)
    for d in ("/_import", "/_test"):
        if el.does_directory_exist(GEO + d):
            el.delete_directory(GEO + d)
    print("GEOMS imported", done)
    print("GEOM TEXTURES", import_files(tex, TEX, "texture"))


GEO = "/Game/CoH/FX/Geoms"
if step == "materials":
    make_materials()
elif step == "geoms":
    make_geom_material()
    import_geoms()
else:
    tex, snd = wanted()
    print("FX ASSETS wanted: %d textures, %d sounds" % (len(tex), len(snd)))
    nt = import_files(tex, TEX, "texture")
    ns = import_files(snd, SND, "sound")
    print("FX ASSETS imported: %d textures, %d sounds" % (nt, ns))

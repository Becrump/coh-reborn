"""Applies the hand-tuned material and scene fixes to a fresh zone import.

Run in the Unreal editor after setup_level.py, with the zone's level open:
    py "<out>/apply_tuning.py"

setup_level.py does the generic steps; this script does the ones worked out
by eye on Atlas Park, so a re-import gets them back in one go:
1. Moves the imported material instances onto the CoH masters
   (coh_materials.py): cutouts and road lines -> M_CoH_Masked, additive
   layers -> M_CoH_Additive, lawns and detail/night-glow layers ->
   M_CoH_Surface, grass decals -> M_CoH_Decal, water -> M_CoH_Water.
2. Per-material tweaks: glossy windows, window glow strength, War Wall
   dimmed at night, faint caustics, City Hall trim without glow, interior
   cube-map boxes hidden.
3. Scene: fountain effects (fountains.json) and the city-life manager
   (traffic, crowds, monorail, blimp, drones from <name>_life.json).
Safe to run again. Masters are built only if missing (pass --rebuild to
rebuild them in place).
"""
import json
import os
import re
import sys

import unreal

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() \
    else os.getcwd()
REPO_UNREAL = r"C:/Users/rtcru/ClaudeProjects/coh-reborn/coh2unreal/unreal"
for p in (HERE, REPO_UNREAL):
    if os.path.exists(os.path.join(p, "coh_materials.py")):
        sys.path.insert(0, p)
        break
import coh_materials as cm  # noqa: E402

mel = unreal.MaterialEditingLibrary
el = unreal.EditorAssetLibrary
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()
MASTERS = "/Game/CoH/Materials"

ROAD_LINES = ("street_whiteline_broken", "street_whiteline",
              "street_whiteline_edge", "street_yellowline")
# decals and glass that need a real cutout
CUTOUTS = """x_ap_automark_decals_01 x_ap_crack_decal_01 x_ap_grime_decal_01
x_ap_grime_decal_dark_01 x_ap_treelroots01 x_archent_com_logo_01
x_archent_int_computerbank_glass x_archent_int_computerbank_screen
x_archent_int_reactor_glassfloor_01 x_archent_int_window_cube
x_auctionhouseglass x_auctionhousetext x_deco_building_07_skylight
x_deco_building_10_sturcture_01 x_deco_skyscraper_07_shadowplane
x_dirty_ground x_fw_metalstruts x_ot_shotgun_light_01
x_p_abandoned_office_decal_stain_01 x_p_abandoned_office_decal_stain_02
x_p_abandoned_office_decal_stain_03 x_p_chairback01 x_p_ironfencing
x_p_railingglass x_p_tabletops x_p_warehouse_forklift
x_praet_road_benches_a x_semi_trailer01 x_semi_wheel01 x_sign_vri_glow
x_torn_posters x_vanguard_catwalks x_vanguard_rec_ring""".split()
NOT_MASKED = {"x_male_statue_atlas_01"}     # base alpha is a shine mask
# oceanbase is the canal/pond BED under the water surface: a normal surface
WATER = ("calmwater_1_tga", "newwater4_tga",
         "fountain_pattern01_tga", "fountain_pattern01b_tga",
         "newwater4_tga__WATERTOP")
HIDE_SLOTS = {"x_archent_int_window_cube", "portal_door1_tga"}
GLOW_STRENGTH = 25.0
WINDOW_ROUGHNESS = 0.12
CARS = ["car_sedan", "car_sedan_sports", "car_suv", "car_suv_luxury",
        "car_taxi", "car_taxi", "car_police", "car_van",
        "car_hatchback_sports", "car_delivery", "car_truck",
        "car_ambulance", "car_garbage_truck", "car_sedan"]
MANNEQUINS = "/Game/Characters/Mannequins/"


def log(msg):
    unreal.log("[CoH tuning] " + msg)


def find(suffix):
    for f in os.listdir(HERE):
        if f.endswith(suffix):
            return os.path.join(HERE, f)
    return None


def tiles():
    return [a for a in asub.get_all_level_actors()
            if isinstance(a, unreal.StaticMeshActor)
            and a.get_actor_label().startswith("tile_")]


def material_folder():
    """The Materials folder most of this level's tile slots use (a re-import
    can leave a second copy of the materials that nothing renders with)."""
    import collections
    count = collections.Counter()
    for a in tiles():
        c = a.static_mesh_component
        for i in range(c.get_num_materials()):
            m = c.get_material(i)
            if m and isinstance(m, unreal.MaterialInstanceConstant):
                count[m.get_path_name().rsplit("/", 1)[0]] += 1
    if not count:
        raise RuntimeError("no imported tiles found in this level")
    return count.most_common(1)[0][0]


def master(name, build, *args):
    path = "%s/%s" % (MASTERS, name)
    if "--rebuild" in sys.argv or not el.does_asset_exist(path):
        return build(*args)
    return unreal.load_asset(path)


def save(mi):
    mel.update_material_instance(mi)
    el.save_loaded_asset(mi, False)


# ------------------------------------------------------------ materials
def tune_materials(folder):
    textures = folder.rsplit("/", 1)[0] + "/Textures"
    by_name = {str(d.asset_name).lower(): d
               for d in reg.get_assets_by_path(folder, True)
               if str(d.asset_class_path.asset_name)
               == "MaterialInstanceConstant"}
    cm.night_collection()
    masked = master("M_CoH_Masked", cm.build_masked)
    surface = master("M_CoH_Surface", cm.build_surface)
    decal = master("M_CoH_Decal", cm.build_decal)
    additive = master("M_CoH_Additive", cm.build_additive)
    water_n = unreal.load_asset("/Game/CoH/Water/T_Water_N")
    if water_n is None and find("water_normal.png"):
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", find("water_normal.png"))
        t.set_editor_property("destination_path", "/Game/CoH/Water")
        t.set_editor_property("destination_name", "T_Water_N")
        for k in ("automated", "replace_existing", "save"):
            t.set_editor_property(k, True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
        water_n = unreal.load_asset("/Game/CoH/Water/T_Water_N")
        water_n.set_editor_property(
            "compression_settings",
            unreal.TextureCompressionSettings.TC_NORMALMAP)
        water_n.set_editor_property("srgb", False)
        el.save_loaded_asset(water_n, False)
    water = master("M_CoH_Water", cm.build_water, water_n)

    def get(name):
        d = by_name.get(name.lower())
        return d.get_asset() if d else None

    stats = dict.fromkeys(("lines", "additive", "masked", "lawns", "decals",
                           "layers", "detail", "glow", "water"), 0)
    masked_names = {n.lower() for n in json.load(
        open(find("masked_materials.json")))} if find(
        "masked_materials.json") else set()
    with unreal.ScopedSlowTask(len(by_name), "CoH material tuning") as task:
        task.make_dialog(False)
        for low, d in by_name.items():
            task.enter_progress_frame(1, low)
            if re.search(r"_+add(_+night)?$", low):
                mi = d.get_asset()
                if mi.parent != additive:
                    cm.reparent(mi, additive, {"EmissiveStrength": 1.0})
                stats["additive"] += 1
            elif (low in masked_names or low in CUTOUTS) \
                    and low not in NOT_MASKED:
                mi = d.get_asset()
                if mi.parent != masked:
                    cm.reparent(mi, masked)
                stats["masked"] += 1
    for n in ROAD_LINES:
        mi, tex = get(n + "_tga"), unreal.load_asset("%s/%s" % (textures, n))
        if mi:
            cm.reparent(mi, masked, {"BaseColorTexture": tex} if tex else None)
            stats["lines"] += 1
    turf = json.load(open(find("turf.json"))) if find("turf.json") else {}
    for n in turf.get("materials", {}):
        mi = get(n)
        if mi and mi.parent != surface:
            cm.reparent(mi, surface)
            stats["lawns"] += 1
    turf_d = unreal.load_asset("/Game/CoH/Turf/T_Turf_D")
    turf_n = unreal.load_asset("/Game/CoH/Turf/T_Turf_N")
    for i in (1, 2, 3, 4):
        mi = get("x_AP_grass_decal_0%d" % i)
        if not mi or mi.parent == decal or not turf_d:
            continue
        mask = mel.get_material_instance_texture_parameter_value(
            mi, "BaseColorTexture")
        tile = unreal.LinearColor(0, 0, 12.1, 12.1)
        cm.reparent(mi, decal, {
            "BaseColorTexture": turf_d, "OpacityTexture": mask,
            "BaseColorTexture_OffsetScale": tile, "NormalTexture": turf_n,
            "NormalTexture_OffsetScale": tile,
            "OpacityTexture_OffsetScale": unreal.LinearColor(0, 0, 1, 1),
            "BaseColorFactor": unreal.LinearColor(0.85, 0.95, 0.8, 1)})
        mel.set_material_instance_static_switch_parameter_value(
            mi, "bHasNormalTexture", True)
        save(mi)
        stats["decals"] += 1
    # detail and night-glow layers
    layers = json.load(open(find("_layers.json"))) if find("_layers.json") \
        else {}
    pngs = sorted({v for e in layers.values() for k, v in e.items()
                   if k in ("detail", "glow", "glow_mask")})
    missing = [r for r in pngs if not el.does_asset_exist(
        "/Game/CoH/Layers/" + os.path.splitext(os.path.basename(r))[0])]
    if missing:
        tasks = []
        for rel in missing:
            t = unreal.AssetImportTask()
            t.set_editor_property("filename", os.path.join(HERE, rel))
            t.set_editor_property("destination_path", "/Game/CoH/Layers")
            for k in ("automated", "replace_existing", "save"):
                t.set_editor_property(k, True)
            tasks.append(t)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    tex = {r: unreal.load_asset("/Game/CoH/Layers/" + os.path.splitext(
        os.path.basename(r))[0]) for r in pngs}
    with unreal.ScopedSlowTask(len(layers), "CoH detail and glow layers") \
            as task:
        task.make_dialog(False)
        for name, e in layers.items():
            task.enter_progress_frame(1, name)
            mi = get(name)
            if mi is None or "__" in name:
                continue
            pname = mi.parent.get_name() if mi.parent else ""
            if pname == "M_GLTF":
                cm.reparent(mi, surface)
            elif pname not in ("M_CoH_Surface", "M_CoH_Masked"):
                continue
            stats["layers"] += 1
            if e.get("detail") and tex.get(e["detail"]):
                mel.set_material_instance_static_switch_parameter_value(
                    mi, "bHasDetailTexture", True)
                mel.set_material_instance_texture_parameter_value(
                    mi, "DetailTexture", tex[e["detail"]])
                su, sv = e.get("detail_scale", [1, 1])
                mel.set_material_instance_vector_parameter_value(
                    mi, "DetailScale", unreal.LinearColor(su, sv, 0, 0))
                stats["detail"] += 1
            if e.get("glow") and tex.get(e["glow"]):
                mel.set_material_instance_static_switch_parameter_value(
                    mi, "bHasGlowTexture", True)
                mel.set_material_instance_texture_parameter_value(
                    mi, "GlowTexture", tex[e["glow"]])
                mel.set_material_instance_scalar_parameter_value(
                    mi, "GlowStrength", GLOW_STRENGTH)
                gu, gv = e.get("glow_scale", [1, 1])
                mel.set_material_instance_vector_parameter_value(
                    mi, "GlowScale", unreal.LinearColor(gu, gv, 0, 0))
                mask = tex.get(e.get("glow_mask"))
                if mask:
                    mel.set_material_instance_texture_parameter_value(
                        mi, "GlowMask", mask)
                    mel.set_material_instance_scalar_parameter_value(
                        mi, "GlowMaskAlpha",
                        1.0 if e.get("glow_mask_alpha") else 0.0)
                    mel.set_material_instance_scalar_parameter_value(
                        mi, "GlowMaskInvert",
                        1.0 if e.get("glow_mask_invert") else 0.0)
                stats["glow"] += 1
            if re.search(r"window|glass", name, re.I) \
                    and mi.parent == surface:
                mel.set_material_instance_scalar_parameter_value(
                    mi, "RoughnessFactor", WINDOW_ROUGHNESS)
            save(mi)
    for low, d in by_name.items():      # windows without a layer entry
        if re.search(r"window|glass", low) and "__" not in low:
            mi = d.get_asset()
            if mi.parent == surface:
                mel.set_material_instance_scalar_parameter_value(
                    mi, "RoughnessFactor", WINDOW_ROUGHNESS)
                save(mi)
    bed = get("oceanbase_tga")
    if bed:
        if bed.parent != surface:
            cm.reparent(bed, surface)
        mel.set_material_instance_vector_parameter_value(
            bed, "BaseColorFactor", unreal.LinearColor(0.45, 0.42, 0.33, 1))
        mel.set_material_instance_scalar_parameter_value(
            bed, "RoughnessFactor", 0.9)
        save(bed)
    for n in WATER:
        mi = get(n)
        if not mi:
            continue
        if mi.parent != water:
            cm.reparent(mi, water)
        save(mi)
        stats["water"] += 1
    # one-off looks
    for low, d in by_name.items():
        if re.search(r"warzone|nbrhood", low) and re.search(r"_+add", low):
            mi = d.get_asset()
            mel.set_material_instance_scalar_parameter_value(
                mi, "NightScale", 0.3)
            save(mi)
    mi = get("calmwater_caustics1_tga__ADD")
    if mi:
        mel.set_material_instance_scalar_parameter_value(
            mi, "EmissiveStrength", 0.12)
        save(mi)
    mi = get("X_AP_CityHall_Details_01")
    if mi and mi.parent == surface:
        mel.set_material_instance_static_switch_parameter_value(
            mi, "bHasGlowTexture", False)
        save(mi)
    log("materials: %s" % stats)


def hide_slots():
    inv = unreal.load_asset("/Game/CoH/Materials/M_Invisible")
    n = 0
    for a in tiles():
        c = a.static_mesh_component
        for i in range(c.get_num_materials()):
            m = c.get_material(i)
            if inv and m and m.get_name().lower() in HIDE_SLOTS:
                c.set_material(i, inv)
                n += 1
    log("hidden interior cube-map slots: %d" % n)


# ---------------------------------------------------------------- scene
def fountains():
    path = find("fountains.json")
    ns = unreal.load_asset("/Game/CoH/FX/NS_CoH_Fountain")
    if not path:
        return
    if ns is None:
        el.duplicate_asset(
            "/Niagara/DefaultAssets/Templates/Systems/FountainLightweight",
            "/Game/CoH/FX/NS_CoH_Fountain")
        ns = unreal.load_asset("/Game/CoH/FX/NS_CoH_Fountain")
    for a in asub.get_all_level_actors():
        if a.get_actor_label().startswith("Fountain_"):
            asub.destroy_actor(a)
    fx = json.load(open(path))
    for i, e in enumerate(fx):
        name = e["fx"].rsplit("/", 1)[-1].lower()
        s = 2.2 if "large" in name else (0.8 if "stream" in name else 1.4)
        a = asub.spawn_actor_from_class(unreal.NiagaraActor,
                                        unreal.Vector(*e["p"]))
        a.niagara_component.set_asset(ns)
        a.set_actor_scale3d(unreal.Vector(s, s, s))
        a.set_actor_label("Fountain_%d" % i)
        a.set_folder_path("CoH/Fountains")
    log("fountains: %d" % len(fx))


def life():
    path = find("_life.json")
    if not path or not hasattr(unreal, "CoHLifeManager"):
        log("life manager skipped (no _life.json or C++ module not loaded)")
        return

    def mesh(name):
        for d in reg.get_assets_by_path("/Game/CoH/Vehicles/" + name, True):
            if str(d.asset_class_path.asset_name) == "StaticMesh":
                return d.get_asset()
    for a in asub.get_all_level_actors():
        if isinstance(a, unreal.CoHLifeManager):
            asub.destroy_actor(a)
    m = asub.spawn_actor_from_class(unreal.CoHLifeManager,
                                    unreal.Vector(0, 0, 0))
    m.set_actor_label("CoHLife")
    m.set_folder_path("CoH")
    fp = unreal.FilePath()
    fp.set_editor_property("file_path", path.replace("\\", "/"))
    m.set_editor_property("life_json", fp)
    m.set_editor_property("civilian_meshes", [
        unreal.load_asset(MANNEQUINS + "Meshes/SKM_Manny_Simple"),
        unreal.load_asset(MANNEQUINS + "Meshes/SKM_Quinn_Simple")])
    m.set_editor_property("walk_anim", unreal.load_asset(
        MANNEQUINS + "Anims/Unarmed/Walk/MF_Unarmed_Walk_Fwd"))
    m.set_editor_property("idle_anim", unreal.load_asset(
        MANNEQUINS + "Anims/Unarmed/MM_Idle"))
    m.set_editor_property("run_anim", unreal.load_asset(
        MANNEQUINS + "Anims/Unarmed/Jog/MF_Unarmed_Jog_Fwd"))
    m.set_editor_property("car_meshes", [mesh(c) for c in CARS])
    m.set_editor_property("monorail_mesh", mesh("monorail_car"))
    m.set_editor_property("blimp_mesh", mesh("blimp"))
    m.set_editor_property("drone_mesh", mesh("police_drone"))
    try:
        m.set_editor_property("night_collection",
                              unreal.load_asset(cm.MPC_PATH))
    except Exception as e:
        unreal.log_warning("[CoH tuning] night_collection: %s" % e)
    log("life manager placed (%s)" % os.path.basename(path))


def main():
    folder = material_folder()
    log("imported materials: " + folder)
    tune_materials(folder)
    hide_slots()
    fountains()
    life()
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    log("done")


main()

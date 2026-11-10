"""Builds the City Sample parked-car kit for Atlas Park (run inside the editor).

For each City Sample vehicle it merges the Nanite body (No_Wheel), the four
wheels, the brake pads and the window shell (All_Trans, with translucent
glass swapped for City Sample's own opaque dark glass) into ONE Nanite
static mesh with a box collision, so a parked car is a single physics
component instead of seven, and the 1.3-3.2 M triangle non-Nanite _LOD
meshes are never used. Also makes paint colour variants (MI children of
each vehicle's car-paint MI, BaseColor only).

Output: /Game/AtlasPark4/CitySampleCars/Meshes/SM_CSCar_<vehicle>
        /Game/AtlasPark4/CitySampleCars/Paint/MI_CSCar_<vehicle>_<colour>
        kit.json next to this script (mesh path, paint slot, colours, size)
Only the new assets are saved. Temporary part actors are destroyed unsaved.
"""
import json
import os
import unreal

ROOT = "/Game/AtlasPark4/CitySampleCars"
CS = "/Game/CitySampleVehicles"
# vehicle folder, mesh stem (vehCar_vehicle02 ...), recolour?
VEHICLES = [
    ("vehicle01_Van", "vehVan_vehicle01", True),
    ("vehicle02_Car", "vehCar_vehicle02", True),
    ("vehicle03_Car", "vehCar_vehicle03", True),
    ("vehicle04_Truck", "vehTruck_vehicle04", True),
    ("vehicle05_Car", "vehCar_vehicle05", True),
    ("vehicle06_Car", "vehCar_vehicle06", True),
    ("vehicle07_Car", "vehCar_vehicle07", True),
    ("vehicle09_Van", "vehVan_vehicle09", True),
    ("vehicle12_Car", "vehCar_vehicle12", True),
    ("vehicle13_Car", "vehCar_vehicle13", False),   # police livery: keep
]
COLOURS = {   # linear BaseColor
    "White": (0.80, 0.80, 0.78), "Black": (0.012, 0.012, 0.014),
    "Silver": (0.34, 0.35, 0.37), "Red": (0.42, 0.02, 0.02),
    "Navy": (0.015, 0.035, 0.17), "Green": (0.025, 0.10, 0.045),
    "Yellow": (0.70, 0.42, 0.02), "Maroon": (0.18, 0.015, 0.03),
    "Blue": (0.07, 0.22, 0.52),
}
DARK_GLASS = CS + "/Material/MI/MI_Veh_GlassDarkOpaque"
LIGHT = CS + "/Material/MI/MI_Veh_Light"

eas = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def log(*a):
    unreal.log("cs_kit: " + " ".join(str(x) for x in a))
    print(*a)


def is_translucent(mat):
    base = mat.get_base_material() if mat else None
    return base is not None and base.get_editor_property("blend_mode") in (
        unreal.BlendMode.BLEND_TRANSLUCENT, unreal.BlendMode.BLEND_ADDITIVE,
        unreal.BlendMode.BLEND_MODULATE)


def opaque_for(slot, mat):
    if not is_translucent(mat):
        return None
    s = str(slot).lower()
    if "amber" in s or "red" in s or "bulb" in s or "light" in s:
        return eas.load_asset(LIGHT)
    return eas.load_asset(DARK_GLASS)


def parts(folder, stem):
    mesh = CS + "/%s/Mesh/" % folder
    names = ["SM_%s_No_Wheel" % stem, "SM_All_Trans_%s" % stem,
             "SM_Wheel_Front_L_%s" % stem, "SM_Wheel_Front_R_%s" % stem,
             "SM_Wheel_Rear_L_%s" % stem, "SM_Wheel_Rear_R_%s" % stem,
             "SM_Brake_Pad_L_%s" % stem, "SM_Brake_Pad_R_%s" % stem]
    return [eas.load_asset(mesh + n) for n in names if eas.does_asset_exist(mesh + n)]


def paint_mi(body):
    for s in body.static_materials:
        if "carpaint" in str(s.material_slot_name).lower():
            return s.material_interface
    return None


def build(folder, stem, recolour):
    out = ROOT + "/Meshes/SM_CSCar_" + folder
    meshes = parts(folder, stem)
    body = meshes[0]
    temp = []
    for m in meshes:
        a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        c = a.static_mesh_component
        c.set_static_mesh(m)
        for i, s in enumerate(m.static_materials):
            rep = opaque_for(s.material_slot_name, s.material_interface)
            if rep:
                c.set_material(i, rep)
        temp.append(a)
    try:
        st = unreal.MeshMergingSettings()
        st.set_editor_property("merge_materials", False)
        st.set_editor_property("pivot_type", unreal.MeshMergePivotType.CUSTOM)
        st.set_editor_property("custom_pivot_location", unreal.Vector(0, 0, 0))
        st.set_editor_property("merge_physics_data", False)
        st.set_editor_property("lod_selection_type", unreal.MeshLODSelectionType.SPECIFIC_LOD)
        st.set_editor_property("specific_lod", 0)
        opt = unreal.MergeStaticMeshActorsOptions()
        opt.set_editor_property("destroy_source_actors", False)
        opt.set_editor_property("spawn_merged_actor", False)
        # the merge prefixes the last path part with SM_
        opt.set_editor_property("base_package_name", ROOT + "/Meshes/CSCar_" + folder)
        opt.set_editor_property("mesh_merging_settings", st)
        if eas.does_asset_exist(out):
            eas.delete_asset(out)
        ns = st.get_editor_property("nanite_settings")
        ns.enabled = True
        st.set_editor_property("nanite_settings", ns)
        ok = sme.merge_static_mesh_actors(temp, opt)
    finally:
        for a in temp:
            actors.destroy_actor(a)
    merged = eas.load_asset(out)
    if not merged:
        raise RuntimeError("merge failed for " + folder + " " + str(ok))
    ns = merged.get_editor_property("nanite_settings")
    ns.enabled = True
    merged.set_editor_property("nanite_settings", ns)
    sme.remove_collisions(merged)
    sme.add_simple_collisions(merged, unreal.ScriptCollisionShapeType.BOX)
    bs = merged.get_editor_property("body_setup")
    bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    merged.set_editor_property("body_setup", bs)
    eas.save_loaded_asset(merged, False)
    paint = paint_mi(body)
    slot = -1
    for i, s in enumerate(merged.static_materials):
        if paint and s.material_interface == paint:
            slot = i
    colours = {}
    if recolour and paint and slot >= 0:
        for name, rgb in COLOURS.items():
            mi_path = "%s/Paint/MI_CSCar_%s_%s" % (ROOT, folder, name)
            mi = eas.load_asset(mi_path) if eas.does_asset_exist(mi_path) else tools.create_asset(
                mi_path.rsplit("/", 1)[1], mi_path.rsplit("/", 1)[0], unreal.MaterialInstanceConstant,
                unreal.MaterialInstanceConstantFactoryNew())
            mi.set_editor_property("parent", paint)
            mel.set_material_instance_vector_parameter_value(mi, "BaseColor", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 0.0))
            mel.update_material_instance(mi)
            eas.save_loaded_asset(mi, False)
            colours[name] = mi.get_path_name()
    b = merged.get_bounding_box()
    log(folder, "tris", merged.get_num_triangles(0), "slots", len(merged.static_materials), "paint slot", slot,
        "size", round(b.max.x - b.min.x), round(b.max.y - b.min.y), round(b.max.z - b.min.z))
    return dict(mesh=merged.get_path_name(), paint_slot=slot, colours=colours,
                min=[b.min.x, b.min.y, b.min.z], max=[b.max.x, b.max.y, b.max.z])


kit = {}
only = os.environ.get("CSKIT_ONLY")
for folder, stem, recolour in VEHICLES:
    if only and folder != only:
        continue
    kit[folder] = build(folder, stem, recolour)
here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "kit.json")
old = json.load(open(path)) if os.path.exists(path) else {}
old.update(kit)
json.dump(old, open(path, "w"), indent=1)
log("kit written", path, len(old))

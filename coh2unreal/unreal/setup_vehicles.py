"""Swaps the living city's placeholder cars for the Vehicle Variety Pack.

Run in the Unreal editor (pack added to the project from Fab):
    py "<repo>/coh2unreal/unreal/setup_vehicles.py"

1. M_CoH_CarPaint: the pack's body material (diffuse, ORM, lights) with the
   paint recoloured. Paint is found by colour saturation, so chrome, glass,
   rubber and trim (all near-grey) keep their look; PaintColor sets the new
   colour, keeping the original shading.
2. Colour variants: a copy of each static car mesh per paint colour under
   /Game/CoH/Vehicles/VVP, Nanite on (the body has ~50-100k triangles and
   traffic draws hundreds), glass left as the pack made it.
3. Points the CoHLife manager's car list at the variants, weighted towards
   everyday colours, with yellow hatchbacks as taxis.
"""
import unreal

PACK = "/Game/VehicleVarietyPack"
OUT = "/Game/CoH/Vehicles/VVP"
MASTER = "/Game/CoH/Materials/M_CoH_CarPaint"
# mesh -> body slot, body material
CARS = {
    "SM_Hatchback": ("M_Hatchback_BODY", "Hatchback/M_Hatchback_Body"),
    "SM_SUV": ("M_Main", "SUV/M_SUV_Body"),
    "SM_SportsCar": ("Mi_SportsCar_Body", "SportsCar/M_SportsCar_Body"),
    "SM_Pickup": ("Pickup_Body", "Pickup/M_Pickup_Body"),
    "SM_Truck_Box": ("M_Truck_Body", "BoxTruck/M_BoxTruck_Body"),
}
# linear paint colours
PAINT = {
    "White": (0.80, 0.80, 0.78), "Black": (0.015, 0.015, 0.018),
    "Silver": (0.45, 0.46, 0.48), "Navy": (0.02, 0.05, 0.16),
    "Red": (0.45, 0.02, 0.02), "Green": (0.03, 0.12, 0.05),
    "Taxi": (0.75, 0.50, 0.02),
}
# which colours each body gets (box trucks are fleet white/silver)
COLOURS = {
    "SM_Hatchback": ["White", "Silver", "Red", "Navy", "Taxi"],
    "SM_SUV": ["Black", "White", "Silver", "Navy"],
    "SM_SportsCar": ["Red", "Black", "Silver"],
    "SM_Pickup": ["White", "Green", "Black", "Silver"],
    "SM_Truck_Box": ["White", "Silver"],
}
# traffic mix: (mesh, colour, weight)
MIX = [("SM_Hatchback", c, 3) for c in ("White", "Silver", "Red", "Navy")] + \
      [("SM_Hatchback", "Taxi", 3)] + \
      [("SM_SUV", c, 3) for c in COLOURS["SM_SUV"]] + \
      [("SM_SportsCar", c, 1) for c in COLOURS["SM_SportsCar"]] + \
      [("SM_Pickup", c, 2) for c in COLOURS["SM_Pickup"]] + \
      [("SM_Truck_Box", c, 1) for c in COLOURS["SM_Truck_Box"]]

mel = unreal.MaterialEditingLibrary
el = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def log(msg):
    unreal.log("[CoH vehicles] " + msg)


def node(m, cls, x, y, **props):
    n = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n


def connect(a, out, b, inp):
    if not mel.connect_material_expressions(a, out, b, inp):
        raise RuntimeError("connect %s.%s -> %s.%s" % (
            a.get_class().get_name(), out, b.get_class().get_name(), inp))


# defaults: the hatchback's own textures (right colour space for each)
DEFAULT_TEX = PACK + "/Textures/Hatchback/TX_Hatchback_%s_0"


def tex_param(m, name, x, y, default, srgb=True):
    t = node(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y,
             parameter_name=name, texture=unreal.load_asset(
                 DEFAULT_TEX % default))
    t.set_editor_property(
        "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if srgb
        else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    return t


def build_master():
    folder, name = MASTER.rsplit("/", 1)
    if el.does_asset_exist(MASTER):
        m = unreal.load_asset(MASTER)
        mel.delete_all_material_expressions(m)
    else:
        m = tools.create_asset(name, folder, unreal.Material,
                               unreal.MaterialFactoryNew())
    m.set_editor_property("used_with_instanced_static_meshes", True)
    m.set_editor_property("used_with_nanite", True)
    diff = tex_param(m, "Diffuse", -1400, -200, "Diffuse")
    orm = tex_param(m, "ORM", -1400, 200, "ORM", srgb=False)
    emm = tex_param(m, "Emissive", -1400, 500, "EMM")
    # saturation of the original colour -> paint mask
    rgb = diff
    mx = node(m, unreal.MaterialExpressionMax, -1100, -350)
    mn = node(m, unreal.MaterialExpressionMin, -1100, -250)
    def channel(y, **on):
        flags = dict(r=False, g=False, b=False, a=False)
        flags.update(on)
        return node(m, unreal.MaterialExpressionComponentMask, -1250, y,
                    **flags)
    r, g, b = channel(-400, r=True), channel(-330, g=True), channel(-260, b=True)
    for c in (r, g, b):
        connect(rgb, "RGB", c, "")
    mx2 = node(m, unreal.MaterialExpressionMax, -1000, -350)
    mn2 = node(m, unreal.MaterialExpressionMin, -1000, -250)
    connect(r, "", mx, "A"); connect(g, "", mx, "B")
    connect(mx, "", mx2, "A"); connect(b, "", mx2, "B")
    connect(r, "", mn, "A"); connect(g, "", mn, "B")
    connect(mn, "", mn2, "A"); connect(b, "", mn2, "B")
    sat = node(m, unreal.MaterialExpressionSubtract, -900, -300)
    connect(mx2, "", sat, "A"); connect(mn2, "", sat, "B")
    gain = node(m, unreal.MaterialExpressionScalarParameter, -900, -180,
                parameter_name="MaskGain", default_value=6.0)
    mul = node(m, unreal.MaterialExpressionMultiply, -800, -300)
    connect(sat, "", mul, "A"); connect(gain, "", mul, "B")
    mask = node(m, unreal.MaterialExpressionSaturate, -700, -300)
    connect(mul, "", mask, "")
    # keep the shading: new colour x (brightness / brightness of paint)
    lum = node(m, unreal.MaterialExpressionDotProduct, -1000, -50)
    connect(rgb, "RGB", lum, "A")
    w = node(m, unreal.MaterialExpressionConstant3Vector, -1150, 30,
             constant=unreal.LinearColor(0.3, 0.59, 0.11, 0))
    connect(w, "", lum, "B")
    ref = node(m, unreal.MaterialExpressionScalarParameter, -1000, 60,
               parameter_name="PaintReference", default_value=0.25)
    shade = node(m, unreal.MaterialExpressionDivide, -850, -20)
    connect(lum, "", shade, "A"); connect(ref, "", shade, "B")
    paint = node(m, unreal.MaterialExpressionVectorParameter, -850, 80,
                 parameter_name="PaintColor",
                 default_value=unreal.LinearColor(0.8, 0.8, 0.78, 1))
    newc = node(m, unreal.MaterialExpressionMultiply, -700, 0)
    connect(paint, "", newc, "A"); connect(shade, "", newc, "B")
    final = node(m, unreal.MaterialExpressionLinearInterpolate, -500, -150)
    connect(rgb, "RGB", final, "A"); connect(newc, "", final, "B")
    connect(mask, "", final, "Alpha")
    mel.connect_material_property(final, "",
                                  unreal.MaterialProperty.MP_BASE_COLOR)
    # ORM: R occlusion, G roughness, B metallic (as the pack wires it)
    mel.connect_material_property(orm, "G", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(orm, "B", unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(orm, "R",
                                  unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    ei = node(m, unreal.MaterialExpressionScalarParameter, -1100, 650,
              parameter_name="EmissiveIntensity", default_value=1.0)
    em = node(m, unreal.MaterialExpressionMultiply, -900, 550)
    connect(emm, "RGB", em, "A"); connect(ei, "", em, "B")
    mel.connect_material_property(em, "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    el.save_loaded_asset(m, False)
    return m


def source_textures(mat):
    """Diffuse, ORM and emissive textures of one of the pack's body
    materials, read from its graph."""
    out = {}
    base = mel.get_material_property_input_node(
        mat, unreal.MaterialProperty.MP_BASE_COLOR)
    out["Diffuse"] = base.get_editor_property("texture")
    rough = mel.get_material_property_input_node(
        mat, unreal.MaterialProperty.MP_ROUGHNESS)
    out["ORM"] = rough.get_editor_property("texture")
    em = mel.get_material_property_input_node(
        mat, unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for i in mel.get_inputs_for_material_expression(mat, em):
        if isinstance(i, unreal.MaterialExpressionTextureBase):
            out["Emissive"] = i.get_editor_property("texture")
    return out


def main():
    master = build_master()
    made = {}
    for mesh_name, (slot, body) in CARS.items():
        src = unreal.load_asset("%s/Meshes/%s" % (PACK, mesh_name))
        texs = source_textures(unreal.load_asset(
            "%s/Materials/%s" % (PACK, body)))
        for colour in COLOURS[mesh_name]:
            short = mesh_name[3:]
            mi_path = "%s/MI_%s_%s" % (OUT, short, colour)
            if el.does_asset_exist(mi_path):
                mi = unreal.load_asset(mi_path)
            else:
                mi = tools.create_asset(
                    "MI_%s_%s" % (short, colour), OUT,
                    unreal.MaterialInstanceConstant,
                    unreal.MaterialInstanceConstantFactoryNew())
            mel.set_material_instance_parent(mi, master)
            for p, t in texs.items():
                mel.set_material_instance_texture_parameter_value(mi, p, t)
            mel.set_material_instance_vector_parameter_value(
                mi, "PaintColor", unreal.LinearColor(*PAINT[colour], 1))
            mel.update_material_instance(mi)
            el.save_loaded_asset(mi, False)
            path = "%s/SM_%s_%s" % (OUT, short, colour)
            if not el.does_asset_exist(path):
                el.duplicate_asset(src.get_path_name().split(".")[0], path)
            mesh = unreal.load_asset(path)
            mats = mesh.get_editor_property("static_materials")
            for i, s in enumerate(mats):
                if str(s.get_editor_property("material_slot_name")) == slot:
                    s.set_editor_property("material_interface", mi)
                    mats[i] = s
            mesh.set_editor_property("static_materials", mats)
            ns = mesh.get_editor_property("nanite_settings")
            ns.set_editor_property("enabled", True)
            mesh.set_editor_property("nanite_settings", ns)
            el.save_loaded_asset(mesh, False)
            made[(mesh_name, colour)] = mesh
    log("car variants: %d" % len(made))
    cars = []
    for mesh_name, colour, weight in MIX:
        cars += [made[(mesh_name, colour)]] * weight
    for a in asub.get_all_level_actors():
        if hasattr(unreal, "CoHLifeManager") and \
                isinstance(a, unreal.CoHLifeManager):
            a.set_editor_property("car_meshes", cars)
            log("CoHLife now draws %d variants (%d weighted entries)" % (
                len(made), len(cars)))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


main()

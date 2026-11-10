"""Gives the statue/floodlight/porch spotlights a visible fixture.

Run in the Unreal editor after setup_level (which spawns the lights) and
make_fixtures.py:
    py "<repo>/coh2unreal/unreal/setup_fixtures.py" "<out folder>"

For every StatueLight_* (on at night) and ArchLight_* (always on) spotlight:
a lamp can aimed like the light, with its lens at the light, and a post down
to the ground under it. Lens glow follows the night (MPC_CoH.Night) for the
night lights and stays lit for the always-on ones. Safe to run again.
"""
import os
import sys

import unreal

CONTENT = "/Game/CoH/Props/Fixtures"
SIZE = 1.8      # props read small at CoH's heroic scale; 1 = real 28 cm can
MPC = "/Game/CoH/Materials/MPC_CoH"
el = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def log(msg):
    unreal.log("[CoH fixtures] " + msg)


def node(m, cls, x, y, **props):
    n = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n


def material(path, build):
    folder, name = path.rsplit("/", 1)
    if el.does_asset_exist(path):
        m = unreal.load_asset(path)
        mel.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, folder, unreal.Material, unreal.MaterialFactoryNew())
    build(m)
    mel.recompile_material(m)
    el.save_loaded_asset(m, False)
    return m


def body(m):
    mel.connect_material_property(
        node(m, unreal.MaterialExpressionConstant3Vector, -300, 0,
             constant=unreal.LinearColor(0.03, 0.03, 0.032, 1)), "",
        unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(
        node(m, unreal.MaterialExpressionConstant, -300, 100, r=0.8), "",
        unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(
        node(m, unreal.MaterialExpressionConstant, -300, 200, r=0.45), "",
        unreal.MaterialProperty.MP_ROUGHNESS)


def lens(night_only):
    def build(m):
        col = node(m, unreal.MaterialExpressionConstant3Vector, -500, 0,
                   constant=unreal.LinearColor(1.0, 0.85, 0.6, 1))
        k = node(m, unreal.MaterialExpressionConstant, -500, 100, r=25.0)
        glow = node(m, unreal.MaterialExpressionMultiply, -300, 50)
        mel.connect_material_expressions(col, "", glow, "A")
        mel.connect_material_expressions(k, "", glow, "B")
        out = glow
        if night_only:
            night = node(m, unreal.MaterialExpressionCollectionParameter,
                         -500, 200, collection=unreal.load_asset(MPC),
                         parameter_name="Night")
            on = node(m, unreal.MaterialExpressionLinearInterpolate,
                      -150, 100)
            mel.connect_material_expressions(
                node(m, unreal.MaterialExpressionConstant, -300, 200,
                     r=0.02), "", on, "A")
            mel.connect_material_expressions(
                node(m, unreal.MaterialExpressionConstant, -300, 260,
                     r=1.0), "", on, "B")
            mel.connect_material_expressions(night, "", on, "Alpha")
            out = node(m, unreal.MaterialExpressionMultiply, 0, 50)
            mel.connect_material_expressions(glow, "", out, "A")
            mel.connect_material_expressions(on, "", out, "B")
        mel.connect_material_property(
            node(m, unreal.MaterialExpressionConstant3Vector, -300, -150,
                 constant=unreal.LinearColor(0.6, 0.6, 0.55, 1)), "",
            unreal.MaterialProperty.MP_BASE_COLOR)
        mel.connect_material_property(
            node(m, unreal.MaterialExpressionConstant, -300, -60, r=0.1), "",
            unreal.MaterialProperty.MP_ROUGHNESS)
        mel.connect_material_property(
            out, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    return build


def import_mesh(folder, name):
    dest = "%s/%s" % (CONTENT, name)
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    found = [d for d in reg.get_assets_by_path(dest, True)
             if str(d.asset_class_path.asset_name) == "StaticMesh"]
    if not found:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename",
                              os.path.join(folder, "fixtures", name + ".glb"))
        t.set_editor_property("destination_path", dest)
        for k in ("automated", "replace_existing", "save"):
            t.set_editor_property(k, True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
        found = [d for d in reg.get_assets_by_path(dest, True)
                 if str(d.asset_class_path.asset_name) == "StaticMesh"]
    return found[0].get_asset()


def variant(mesh, path, slot_mats):
    """Copy of `mesh` with materials per slot name (night/always lens)."""
    if not el.does_asset_exist(path):
        el.duplicate_asset(mesh.get_path_name().split(".")[0], path)
    m = unreal.load_asset(path)
    mats = m.get_editor_property("static_materials")
    for i, s in enumerate(mats):
        name = str(s.get_editor_property("material_slot_name")).lower()
        for key, mt in slot_mats.items():
            if key in name:
                s.set_editor_property("material_interface", mt)
                mats[i] = s
    m.set_editor_property("static_materials", mats)
    el.save_loaded_asset(m, False)
    return m


def main():
    folder = [a for a in sys.argv[1:] if not a.startswith("-")][0]
    m_body = material("/Game/CoH/Materials/M_CoH_FixtureBody", body)
    m_night = material("/Game/CoH/Materials/M_CoH_FixtureLensNight",
                       lens(True))
    m_always = material("/Game/CoH/Materials/M_CoH_FixtureLens",
                        lens(False))
    head = import_mesh(folder, "fixture_head")
    post = import_mesh(folder, "fixture_post")
    head_night = variant(head, CONTENT + "/SM_FixtureHead_Night",
                         {"body": m_body, "lens": m_night})
    head_always = variant(head, CONTENT + "/SM_FixtureHead_Always",
                          {"body": m_body, "lens": m_always})
    post_m = variant(post, CONTENT + "/SM_FixturePost", {"body": m_body})
    world = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem).get_editor_world()
    for a in asub.get_all_level_actors():
        if a.get_actor_label().startswith("Fixture_"):
            asub.destroy_actor(a)
    lights = [a for a in asub.get_all_level_actors()
              if a.get_actor_label().startswith(("StatueLight_",
                                                 "ArchLight_"))]
    n = 0
    for lt in lights:
        p = lt.get_actor_location()
        r = lt.get_actor_rotation()
        always = True       # feature lights are on around the clock
        h = asub.spawn_actor_from_object(
            head_always if always else head_night, p, r)
        h.set_actor_scale3d(unreal.Vector(SIZE, SIZE, SIZE))
        h.set_actor_label("Fixture_" + lt.get_actor_label())
        h.set_folder_path("CoH/Fixtures")
        h.static_mesh_component.set_collision_enabled(
            unreal.CollisionEnabled.NO_COLLISION)
        hit = unreal.SystemLibrary.line_trace_single(
            world, p - unreal.Vector(0, 0, 5), p - unreal.Vector(0, 0, 3000),
            unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
            unreal.DrawDebugTrace.NONE, True)
        if hit:
            gz = hit.to_tuple()[4].z
            gap = (p.z - 12 * SIZE) - gz
            if gap > 2:
                b = asub.spawn_actor_from_object(
                    post_m, unreal.Vector(p.x, p.y, gz),
                    unreal.Rotator(0, 0, r.yaw))
                b.set_actor_scale3d(unreal.Vector(SIZE, SIZE, gap / 100.0))
                b.set_actor_label("Fixture_post_" + lt.get_actor_label())
                b.set_folder_path("CoH/Fixtures")
                b.static_mesh_component.set_collision_enabled(
                    unreal.CollisionEnabled.NO_COLLISION)
        n += 1
    log("fixtures on %d lights" % n)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()


main()

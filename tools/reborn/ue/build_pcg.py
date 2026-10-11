"""Step 5: author the PCG graphs and generate the city.

PCG_Reborn_Buildings  for every lot bucket: read the bucket's lot markers,
                      pick one of the bucket's City Sample buildings at
                      random (weighted equally), sometimes turn it 180
                      degrees, and spawn it.
PCG_Reborn_Planting   for woods / park woods / parks: sample the zone
                      splines, drop the points onto the landscape, thin
                      them, and spawn Megaplant trees (instanced skinned
                      meshes, so they keep their wind) plus shrubs.
Each graph runs from a PCG volume covering the whole landscape.

    ue_exec.py build_pcg.py --file            (both)
    REBORN_PCG=buildings|planting to run one."""
import json
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
plan = json.load(open(os.path.join(OUT, "lots_plan.json")))
PCG = ROOT + "/PCG"
ONLY = os.environ.get("REBORN_PCG", "")


def new_graph(name):
    path = PCG + "/" + name
    g = el.load_asset(path)
    if g:
        for n in list(g.nodes):
            g.remove_node(n)
    else:
        g = tools.create_asset(name, PCG, unreal.PCGGraph, unreal.PCGGraphFactory())
    return g


def node(g, cls, x, y, **props):
    n, s = g.add_node_of_type(cls)
    n.set_node_position(x, y)
    for k, v in props.items():
        s.set_editor_property(k, v)
    return n, s


def edge(g, a, apin, b, bpin):
    assert g.add_edge(a, apin, b, bpin), (a, apin, b, bpin)


def selector_text(settings, prop, text):
    sel = settings.get_editor_property(prop)
    assert sel.import_text("PCGBegin(%s)PCGEnd" % text), text
    settings.set_editor_property(prop, sel)


def by_tag(settings, tag):
    sel = settings.get_editor_property("actor_selector")
    sel.set_editor_property("actor_filter", unreal.PCGActorFilter.ALL_WORLD_ACTORS)
    sel.set_editor_property("actor_selection", unreal.PCGActorSelection.BY_TAG)
    sel.set_editor_property("actor_selection_tag", tag)
    sel.set_editor_property("select_multiple", True)
    sel.set_editor_property("must_overlap_self", False)
    settings.set_editor_property("actor_selector", sel)


def set_const(t, kind, value):
    """fill a PCGMetadataTypesConstantStruct"""
    T = unreal.PCGMetadataTypes
    if kind in ("class", "object"):
        # soft paths do not survive Merge Attributes / Match And Set here;
        # strings do, and the spawners convert them back to paths
        t.set_editor_property("type", T.STRING)
        t.set_editor_property("string_value", value)
    elif kind == "rotator":
        t.set_editor_property("type", T.ROTATOR)
        t.set_editor_property("rotator_value", unreal.Rotator(yaw=value))
    return t


def param_set(g, x, y, entries):
    """one attribute-set entry per dict {name: (kind, value)}, merged into one set"""
    merge, _ = node(g, unreal.PCGMergeAttributesSettings, x + 600, y)
    for i, ent in enumerate(entries):
        items = list(ent.items())
        name, (kind, value) = items[0]
        n, st = node(g, unreal.PCGCreateAttributeSetSettings, x, y + i * 140)
        st.set_editor_property("attribute_types", set_const(st.get_editor_property("attribute_types"), kind, value))
        selector_text(st, "output_target", name)
        prev = n
        for name, (kind, value) in items[1:]:
            a, sa = node(g, unreal.PCGAddAttributeSettings, x + 300, y + i * 140)
            sa.set_editor_property("attribute_types", set_const(sa.get_editor_property("attribute_types"), kind, value))
            selector_text(sa, "output_target", name)
            edge(g, prev, "Out", a, "In")
            prev = a
        edge(g, prev, "Out", merge, "In")
    return merge


def cast(g, src, src_pin, x, y, attr, kind):
    """string attribute -> soft class / object path for the spawners"""
    n, s = node(g, unreal.PCGAttributeCastSettings, x, y,
                output_type=unreal.PCGMetadataTypes.SOFT_CLASS_PATH if kind == "class"
                else unreal.PCGMetadataTypes.SOFT_OBJECT_PATH)
    selector_text(s, "input_source", attr)
    selector_text(s, "output_target", attr)
    edge(g, src, src_pin, n, "In")
    return n


def pick(g, src, src_pin, x, y, entries, seed):
    """give every point a random entry of the set (Match And Set, no matching key)"""
    ps = param_set(g, x, y + 200, entries)
    m, ms = node(g, unreal.PCGMatchAndSetAttributesSettings, x + 900, y, seed=seed)
    edge(g, src, src_pin, m, "In")
    edge(g, ps, "Out", m, "Match Data")
    return m


def volume(label, g):
    for a in find(label=label):
        actors.destroy_actor(a)
    el.save_loaded_asset(g)
    L = layout()["landscape"]
    span = (L["verts"] - 1) * L["scale"][0]
    c = unreal.Vector(L["origin_cm"][0] + span / 2, L["origin_cm"][1] + span / 2, 0)
    v = actors.spawn_actor_from_class(unreal.PCGVolume, c)
    v.set_actor_label(label)
    v.set_folder_path("AtlasReborn/Generators")
    v.set_actor_scale3d(unreal.Vector(span / 190, span / 190, 3000))
    comp = v.get_component_by_class(unreal.PCGComponent)
    comp.set_graph(g)
    comp.set_editor_property("generation_trigger", unreal.PCGComponentGenerationTrigger.GENERATE_ON_DEMAND)
    return comp


def buildings():
    # buildings from an earlier run outlive their deleted PCG volume
    for a in actors.get_all_level_actors():
        if "BPP_" in a.get_class().get_name():
            actors.destroy_actor(a)
    g = new_graph("PCG_Reborn_Buildings")
    by = {b["name"]: b for b in plan["buildings"]}
    merge, _ = node(g, unreal.PCGMergeSettings, 2600, 0)
    y = 0
    for k, b in enumerate(plan["buckets"]):
        if not b["candidates"]:
            continue
        ga, gs = node(g, unreal.PCGDataFromActorSettings, 0, y, mode=unreal.PCGGetDataFromActorMode.GET_SINGLE_POINT,
                      merge_single_point_data=True)
        by_tag(gs, "RebornBucket_" + b["id"])
        entries = []
        for nm in b["candidates"]:
            cls = by[nm]["path"] + "." + nm + "_C"
            # long side along the lot; either way round
            for turn in (by[nm]["yaw"], by[nm]["yaw"] + 180):
                entries.append({"Building": ("class", cls), "Turn": ("rotator", turn)})
        m = pick(g, ga, "Out", 300, y, entries, 100 + k)
        edge(g, m, "Out", merge, "In")
        y += 200 + 140 * len(entries)
    rot, rs = node(g, unreal.PCGMetadataRotatorSettings, 2900, 0, operation=unreal.PCGMetadataRotatorOperation.COMBINE)
    selector_text(rs, "input_source1", "$Rotation")
    selector_text(rs, "input_source2", "Turn")
    selector_text(rs, "output_target", "$Rotation")
    edge(g, merge, "Out", rot, "InA")
    edge(g, merge, "Out", rot, "InB")
    if os.environ.get("REBORN_PCG_DEBUG"):
        edge(g, rot, "Out", g.get_output_node(), "Out")
        comp = volume("PCG_Reborn_Buildings", g)
        comp.generate(True)
        return comp
    sp, ss = node(g, unreal.PCGSpawnActorSettings, 3200, 0, spawn_by_attribute=True,
                  option=unreal.PCGSpawnActorOption.NO_MERGING)
    ss.set_editor_property("spawn_attribute", "Building")
    cb = cast(g, rot, "Out", 3050, 200, "Building", "class")
    edge(g, cb, "Out", sp, "In")
    edge(g, sp, "Out", g.get_output_node(), "Out")
    comp = volume("PCG_Reborn_Buildings", g)
    comp.generate(True)
    return comp


TREES = {
    "woods": ["Tree_Black_Alder", "Tree_Hornbeam", "Tree_Silver_Birch", "Tree_Norway_Spruce", "Tree_Baltic_Pine",
              "Tree_Black_Poplar"],
    "park_woods": ["Tree_Hornbeam", "Tree_Black_Alder", "Tree_Silver_Birch", "Tree_Ginkgo", "Tree_Black_Poplar"],
    "park": ["Tree_Ginkgo", "Tree_Hornbeam", "Tree_Silver_Birch", "Tree_Common_Hazel"],
}
SHRUBS = ["/Game/GV_FreeShrubsPack/Meshes/Shrubs/Wind/Shrub_%s/GV_Vol7_Shrub_%s_full_type1%s" % (k, k, sfx)
          for k, sfx in [("A", ""), ("B", ""), ("C", ""), ("D", ""), ("E", "_A"), ("F", "_B")]]
DENS = {"woods": 1 / 150.0, "park_woods": 1 / 160.0, "park": 1 / 380.0}


def planting():
    g = new_graph("PCG_Reborn_Planting")
    ld, ls = node(g, unreal.PCGGetLandscapeSettings, 0, -400)
    y = 0
    for kind, species in TREES.items():
        gs_n, gs = node(g, unreal.PCGGetSplineSettings, 0, y)
        by_tag(gs, "RebornZone_" + kind)
        cs, _ = node(g, unreal.PCGCreateSurfaceFromSplineSettings, 250, y)
        edge(g, gs_n, "Out", cs, "In")
        ss_n, ss = node(g, unreal.PCGSurfaceSamplerSettings, 500, y, points_per_squared_meter=DENS[kind],
                        point_extents=unreal.Vector(350, 350, 100), looseness=1.0)
        edge(g, cs, "Out", ss_n, "Surface")
        pr, _ = node(g, unreal.PCGProjectionSettings, 750, y)
        edge(g, ss_n, "Out", pr, "In")
        edge(g, ld, "Out", pr, "Projection Target")
        tp, _ = node(g, unreal.PCGTransformPointsSettings, 1000, y, rotation_min=unreal.Rotator(),
                     rotation_max=unreal.Rotator(yaw=360), scale_min=unreal.Vector(0.8, 0.8, 0.8),
                     scale_max=unreal.Vector(1.25, 1.25, 1.25), uniform_scale=True)
        edge(g, pr, "Out", tp, "In")
        meshes = []
        for sp in species:
            for v in "ABCD":
                meshes.append({"Mesh": ("object", "/Game/Megaplant_Library/%s/%s_01/%s_01_%s.%s_01_%s" % (sp, sp, sp, v, sp, v))})
        picked = pick(g, tp, "Out", 1250, y, meshes, 7 + len(species))
        merge = cast(g, picked, "Out", 2200, y, "Mesh", "object")
        sk, sks = node(g, unreal.PCGSkinnedMeshSpawnerSettings, 2400, y)
        # the selector is read-only from Python; its default (@Last) reads
        # the Mesh attribute the cast node has just written
        edge(g, merge, "Out", sk, "In")
        edge(g, sk, "Out", g.get_output_node(), "Out")
        # shrubs under and between the trees
        if kind != "park":
            s2_n, s2 = node(g, unreal.PCGSurfaceSamplerSettings, 500, y + 300, points_per_squared_meter=1 / 45.0,
                            point_extents=unreal.Vector(120, 120, 60), looseness=1.0, seed=99)
            edge(g, cs, "Out", s2_n, "Surface")
            p2, _ = node(g, unreal.PCGProjectionSettings, 750, y + 300)
            edge(g, s2_n, "Out", p2, "In")
            edge(g, ld, "Out", p2, "Projection Target")
            t2, _ = node(g, unreal.PCGTransformPointsSettings, 1000, y + 300, rotation_max=unreal.Rotator(yaw=360),
                         scale_min=unreal.Vector(0.7, 0.7, 0.7), scale_max=unreal.Vector(1.3, 1.3, 1.3),
                         uniform_scale=True)
            edge(g, p2, "Out", t2, "In")
            st, sts = node(g, unreal.PCGStaticMeshSpawnerSettings, 1250, y + 300)
            ms = unreal.PCGMeshSelectorWeighted()
            entries = []
            for path in SHRUBS:
                mesh = el.load_asset(path)
                if not mesh:
                    print("missing shrub", path)
                    continue
                e = unreal.PCGMeshSelectorWeightedEntry()
                d = e.get_editor_property("descriptor")
                d.set_editor_property("static_mesh", mesh)
                d.set_editor_property("instance_end_cull_distance", 25000)
                e.set_editor_property("descriptor", d)
                e.set_editor_property("weight", 1)
                entries.append(e)
            sts.set_editor_property("mesh_selector_type", unreal.PCGMeshSelectorWeighted)
            msp = sts.get_editor_property("mesh_selector_parameters")
            msp.set_editor_property("mesh_entries", entries)
            edge(g, t2, "Out", st, "In")
            edge(g, st, "Out", g.get_output_node(), "Out")
        y += 300 + 140 * len(meshes)
    comp = volume("PCG_Reborn_Planting", g)
    comp.generate(True)
    return comp


if ONLY in ("", "buildings"):
    buildings()
    print("buildings graph generated")
if ONLY in ("", "planting"):
    planting()
    print("planting graph generated")

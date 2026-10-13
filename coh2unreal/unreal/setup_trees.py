"""Replaces the zone's CoH trees with Megaplant trees.

Run in the Unreal editor (Megaplant Library added from Fab, Nanite Foliage
on in Project Settings), after `python -m coh2unreal.trees`:
    py "<repo>/coh2unreal/unreal/setup_trees.py" "<out folder>"

1. Hides the old trees: tile material slots whose material is used only by
   trees (<name>_trees.json "materials") get the invisible material.
2. Plants one Megaplant tree per CoH tree: species by the old tree's kind,
   a random A-D variant, random turn, scaled to the old tree's height.
   Each mesh variant is one instanced component on a single CoHTrees actor,
   so a thousand trees cost a few dozen draw groups.
Safe to run again (replaces CoHTrees, re-hides).
"""
import json
import os
import random
import sys

import unreal

LIB = "/Game/Megaplant_Library"
SPECIES = {
    "oak": ["Hornbeam", "Black_Alder"],
    "oak_small": ["Common_Hazel"],
    "poplar": ["Black_Poplar", "Silver_Birch"],
    "poplar_tall": ["Black_Poplar"],
    "park": ["Ginkgo", "Hornbeam"],
    "pine": ["Baltic_Pine", "Norway_Spruce", "Aleppo_Pine"],
    "palm": ["Ginkgo"],
    "tree": ["Black_Alder", "Silver_Birch", "Hornbeam"],
}
VARIANTS = "ABCD"
SCALE_RANGE = (0.45, 1.6)
INVISIBLE = "/Game/CoH/Materials/M_Invisible"
LABEL = "CoHTrees"

asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def log(msg):
    unreal.log("[CoH trees] " + msg)


def out_dir():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        return args[0]
    here = os.path.dirname(os.path.abspath(__file__)) \
        if "__file__" in globals() else os.getcwd()
    return here


def load_trees(folder):
    for f in os.listdir(folder):
        if f.endswith("_trees.json"):
            return json.load(open(os.path.join(folder, f)))
    raise RuntimeError("no *_trees.json in " + folder)


def mesh(species, variant):
    return unreal.load_asset("%s/Tree_%s/Tree_%s_01/Tree_%s_01_%s" % (
        LIB, species, species, species, variant))


def hide_old(materials):
    hide = {m.lower() for m in materials}
    inv = unreal.load_asset(INVISIBLE)
    n = 0
    for a in asub.get_all_level_actors():
        if not (isinstance(a, unreal.StaticMeshActor)
                and a.get_actor_label().startswith("tile_")):
            continue
        c = a.static_mesh_component
        for i in range(c.get_num_materials()):
            m = c.get_material(i)
            if m and m.get_name().lower() in hide:
                c.set_material(i, inv)
                n += 1
    log("old tree material slots hidden: %d" % n)


def add_component(actor, name):
    """Adds an InstancedSkinnedMeshComponent to `actor` as a real
    (saved) component via the subobject system."""
    sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sub.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(
        parent_handle=handles[0],
        new_class=unreal.InstancedSkinnedMeshComponent)
    handle, fail = sub.add_new_subobject(params)
    if not fail.is_empty():
        raise RuntimeError("add component: %s" % fail)
    sub.rename_subobject(handle, unreal.Text(name))
    data = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(handle)
    return unreal.SubobjectDataBlueprintFunctionLibrary.get_object(data)


def main():
    folder = out_dir()
    cfg = load_trees(folder)
    rng = random.Random(42)
    hide_old(cfg["materials"])
    for a in asub.get_all_level_actors():
        if a.get_actor_label() == LABEL:
            asub.destroy_actor(a)
    tops = {}
    groups = {}
    missing = set()
    for t in cfg["trees"]:
        species = rng.choice(SPECIES.get(t["kind"], SPECIES["tree"]))
        variant = rng.choice(VARIANTS)
        key = (species, variant)
        if key not in tops:
            m = mesh(species, variant)
            if m is None:
                missing.add(key)
                tops[key] = None
                continue
            b = m.get_bounds()
            tops[key] = (m, b.origin.z + b.box_extent.z)
        if tops[key] is None:
            continue
        m, top = tops[key]
        s = t["h"] / top if t.get("h", 0) > 100 and top > 0 else 1.0
        s = max(SCALE_RANGE[0], min(SCALE_RANGE[1], s)) * rng.uniform(0.9, 1.1)
        xf = unreal.Transform(unreal.Vector(*t["p"]),
                              unreal.Rotator(0, 0, rng.uniform(0, 360)),
                              unreal.Vector(s, s, s))
        groups.setdefault(key, []).append(xf)
    actor = asub.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
    actor.set_actor_label(LABEL)
    actor.set_folder_path("CoH")
    total = 0
    with unreal.ScopedSlowTask(len(groups), "Planting trees") as task:
        task.make_dialog(False)
        for (species, variant), xfs in sorted(groups.items()):
            task.enter_progress_frame(1, "%s %s" % (species, variant))
            comp = add_component(actor, "%s_%s" % (species, variant))
            comp.set_editor_property("skinned_asset", tops[(species,
                                                            variant)][0])
            comp.add_instances(xfs, [0] * len(xfs), False, True)
            total += len(xfs)
    log("planted %d trees in %d groups%s" % (
        total, len(groups),
        "; missing meshes: %s" % sorted(missing) if missing else ""))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


main()

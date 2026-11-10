"""Undo an UNSAVED cs_hide_coh_cars.py pass (run in the editor).

Reads hide_report.json. Render tiles: only the car slots the pass changed go
back to what they had before (no override when that was the mesh's own
material, otherwise the earlier override). Collision tiles: back to the
mesh they used before. Then the unsaved car-free copies and the hidden
material are dropped, and the restored actor packages get their dirty flag
cleared when they now match disk. Writes hide_revert.json (every actor,
before and after) so the pass can be redone quickly.
"""
import json
import os
import unreal

here = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(here, "hide_report.json")))
eas = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
HIDDEN = "/Game/AtlasPark4/CitySampleCars/M_CSCar_HiddenCoHCar"
out = dict(render=[], collision=[], dropped=[], still_dirty=[], problems=[])
touched = set()

for e in R["render"]:
    a = unreal.find_object(None, e["actor"])
    if not a:
        out["problems"].append(dict(actor=e["actor"], why="not found"))
        continue
    c = a.static_mesh_component
    mesh = c.static_mesh
    row = dict(label=e["label"], actor=e["actor"], slots=[])
    for i, was in zip(e["slots"], e["was"]):
        now = c.get_material(i)
        if not now or now.get_path_name().split(".")[0] != HIDDEN:
            row["slots"].append(dict(slot=i, left=now.get_path_name() if now else None, why="not ours any more"))
            continue
        default = mesh.get_material(i) if mesh else None
        if default and default.get_path_name() == was:
            c.set_material(i, None)       # back to the mesh's own material, no override
            how = "override cleared"
        else:
            c.set_material(i, eas.load_asset(was.split(".")[0]))
            how = "override restored"
        row["slots"].append(dict(slot=i, before_pass=was, hidden=HIDDEN, now=c.get_material(i).get_path_name(), how=how))
    out["render"].append(row)
    touched.add(a)

for e in R["collision"]:
    a = unreal.find_object(None, e["actor"])
    if not a:
        out["problems"].append(dict(actor=e["actor"], why="not found"))
        continue
    c = a.static_mesh_component
    cur = c.static_mesh.get_path_name().split(".")[0] if c.static_mesh else None
    if cur != e["copy"]:
        out["problems"].append(dict(label=e["label"], why="mesh changed since the pass", now=cur))
        continue
    src = eas.load_asset(e["src"])
    c.set_static_mesh(src)
    out["collision"].append(dict(label=e["label"], actor=e["actor"], before_pass=e["src"], pass_copy=e["copy"],
                                 now=c.static_mesh.get_path_name(), sections_off=e["sections_off"]))
    touched.add(a)

# drop the unsaved copies and the hidden material (never saved: nothing on disk)
for e in R["collision"]:
    if eas.does_asset_exist(e["copy"]):
        out["dropped"].append(dict(asset=e["copy"], deleted=eas.delete_asset(e["copy"])))
if eas.does_asset_exist(HIDDEN):
    out["dropped"].append(dict(asset=HIDDEN, deleted=eas.delete_asset(HIDDEN)))

# the restored actors now match disk: clear their dirty flag (no save)
for a in touched:
    p = a.get_package()
    try:
        p.set_dirty_flag(False)
    except Exception as ex:
        out["problems"].append(dict(label=a.get_actor_label(), why="dirty flag: %s" % ex))
dirty = set(p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
out["still_dirty"] = [a.get_actor_label() for a in touched if a.get_package().get_name() in dirty]
out["dirty_map_packages"] = sorted(dirty)
json.dump(out, open(os.path.join(here, "hide_revert.json"), "w"), indent=1)
print("render", len(out["render"]), "collision", len(out["collision"]), "dropped", len(out["dropped"]),
      "still dirty", len(out["still_dirty"]), "problems", len(out["problems"]), "dirty map pkgs", len(dirty))

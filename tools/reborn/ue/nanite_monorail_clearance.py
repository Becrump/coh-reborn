"""Clear the ported monorail's path in the Nanite dressing map.

The original map still has its parked monorail car ("monocab", with seats)
standing on the track in the station, and here and there tree branches or
signs reach into the train's space. Riders standing in a moving car were
scraped off by that collision. This removes, along Monorail_Track:

  collision  every triangle of the original tiles' collision (the hidden
             *_DryCollision proxies, the tile_*_glass panes) inside the car's volume
             (|lateral| < HALF_W, beam top + 0.1 m .. + CAR_H);
  render     the parked car itself (monocab_* / monorail_intr_* materials)
             from the render pieces attached to the station tile.

Nothing is edited in place: the mesh each component uses now (which may
already be another pass's copy, e.g. the car-free tiles) is copied to
/Game/AtlasNanite/Monorail/<name>_Mono[n] and the component in this map is
pointed at the copy, so other maps and the original assets are untouched.
REBORN_DRY=1 only reports. Run with the Nanite map open; saves the map."""
import math
import os

import unreal

MAP = "/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite"
DST = "/Game/AtlasNanite/Monorail"
HALF_W = 170.0          # car half width 150 cm + margin
FLOOR, CAR_H = 10.0, 480.0
PARKED = ("monocab", "monorail_intr")
DRY = os.environ.get("REBORN_DRY") == "1"

el = unreal.EditorAssetLibrary
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
w = editor.get_editor_world()
assert w.get_path_name().startswith(MAP), "open %s first" % MAP
assert editor.get_game_world() is None, "stop Play-In-Editor first"
acts = asub.get_all_level_actors()
track = next(a for a in acts if a.get_actor_label() == "Monorail_Track")
spline = track.get_component_by_class(unreal.SplineComponent)
L = spline.get_spline_length()
# track samples every 50 cm: position and unit tangent (xy)
S = []
d = 0.0
while d <= L:
    p = spline.get_location_at_distance_along_spline(d, unreal.SplineCoordinateSpace.WORLD)
    t = spline.get_tangent_at_distance_along_spline(d, unreal.SplineCoordinateSpace.WORLD)
    n = math.hypot(t.x, t.y) or 1.0
    S.append((p.x, p.y, p.z, t.x / n, t.y / n))
    d += 50.0
CELL = 2000.0
grid = {}
for i, s in enumerate(S):
    grid.setdefault((int(s[0] // CELL), int(s[1] // CELL)), []).append(i)
xs, ys = [s[0] for s in S], [s[1] for s in S]
BOX = (min(xs) - 500, max(xs) + 500, min(ys) - 500, max(ys) + 500)


def inside(x, y, z):
    """point inside the car volume along the track?"""
    gx, gy = int(x // CELL), int(y // CELL)
    for cx in (gx - 1, gx, gx + 1):
        for cy in (gy - 1, gy, gy + 1):
            for i in grid.get((cx, cy), ()):
                sx, sy, sz, fx, fy = S[i]
                dx, dy = x - sx, y - sy
                if abs(dx * fx + dy * fy) <= 26 and abs(-dx * fy + dy * fx) < HALF_W and sz + FLOOR < z < sz + CAR_H:
                    return True
    return False


def tri_points(dsc, tid):
    p = [dsc.get_vertex_position(v) for v in list(dsc.get_triangle_vertices(tid))[-3:]]
    pts = list(p)
    for a, b in ((0, 1), (1, 2), (2, 0)):
        for k in (0.25, 0.5, 0.75):
            pts.append(p[a] + (p[b] - p[a]) * k)
    cx = (p[0] + p[1] + p[2]) / 3.0
    pts.append(cx)
    return pts


def copy_without(mesh, comp, pick):
    """copy mesh minus the triangles pick(desc, tid, world_points) chooses; returns count"""
    xf = comp.get_world_transform()
    dsc = mesh.get_static_mesh_description(0)
    kill = []
    ti, seen, total = 0, 0, dsc.get_triangle_count()
    while seen < total:      # ids can be sparse in meshes other passes edited
        tid = unreal.TriangleID(ti)
        ti += 1
        if not dsc.is_triangle_valid(tid):
            continue
        seen += 1
        pts = [xf.transform_location(q) for q in tri_points(dsc, tid)]
        if pick(dsc, tid, pts):
            kill.append(tid)
    if not kill or DRY:
        return len(kill), None
    # always a fresh copy of the mesh the tile uses now (other passes keep
    # their own copies, e.g. the car-free tiles): never delete or reuse one
    base = DST + "/" + mesh.get_name() + "_Mono"
    path, k = base, 2
    while el.does_asset_exist(path):
        path, k = "%s%d" % (base, k), k + 1
    new = el.duplicate_asset(mesh.get_path_name().split(".")[0], path)
    nd = new.get_static_mesh_description(0)
    polys = set()
    for tid in kill:
        polys.add(nd.get_triangle_polygon(tid).id_value)
    for pid in sorted(polys, reverse=True):
        nd.delete_polygon(unreal.PolygonID(pid))
    # keep a CPU copy: complex collision is cooked from it (without it the
    # rebuilt mesh has no collision at all)
    new.set_editor_property("allow_cpu_access", True)
    new.build_from_static_mesh_descriptions([nd])
    el.save_loaded_asset(new)
    comp.modify()
    comp.set_static_mesh(new)
    return len(kill), new


def overlaps_track(a):
    o, e = a.get_actor_bounds(False)
    return not (o.x + e.x < BOX[0] or o.x - e.x > BOX[1] or o.y + e.y < BOX[2] or o.y - e.y > BOX[3])


report = []
# collision: the tile actors (hidden collision proxies, *_glass panes...)
for a in acts:
    if not isinstance(a, unreal.StaticMeshActor) or not overlaps_track(a):
        continue
    c = a.static_mesh_component
    m = c.static_mesh
    if not m or not a.get_actor_label().startswith("tile_") or c.get_collision_enabled() == unreal.CollisionEnabled.NO_COLLISION:
        continue
    n, new = copy_without(m, c, lambda dsc, tid, pts: any(inside(p.x, p.y, p.z) for p in pts))
    if n:
        report.append(("collision", a.get_actor_label(), m.get_name(), n))
# render: the parked car in the station tile's render pieces
station = next(a for a in acts if a.get_actor_label() == "tile_1_3")
for k in acts:
    if k.get_attach_parent_actor() != station:
        continue
    for c in k.get_components_by_class(unreal.StaticMeshComponent):
        m = c.static_mesh
        bad = {i for i, sm in enumerate(m.static_materials)
               if sm.material_interface and any(s in sm.material_interface.get_name().lower() for s in PARKED)}
        if not bad:
            continue
        sect = {}
        dsc = m.get_static_mesh_description(0)

        def pick(dsc, tid, pts, bad=bad):
            g = dsc.get_triangle_polygon_group(tid).id_value
            return g in bad and any(inside(p.x, p.y, p.z) for p in pts)
        n, new = copy_without(m, c, pick)
        if n:
            report.append(("render", k.get_actor_label(), m.get_name(), n))
for r in report:
    print(*r)
if not DRY and report:
    unreal.EditorLoadingAndSavingUtils.save_map(w, MAP)
print("dry run" if DRY else "saved", len(report), "meshes")

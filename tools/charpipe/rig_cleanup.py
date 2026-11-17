"""Meshy rig cleanup (Blender, reusable).

    blender -b --factory-startup -P meshy_cleanup.py -- <rigged_character.glb|fbx> <out.glb> [--report out.json] [--raw]

Fixes, in order (each one logged in the report):
 1. scale    Meshy rig files carry the armature at 0.01 with bones in cm (glb
             and FBX; the FBX also rotates the mesh 90 deg). All object
             transforms are baked into the data -> metres, identity objects.
 2. facing   rest pose turned so the face (Head -> headfront) looks down -Y.
 3. ground   whole rig moved so the lowest vertex sits on z = 0 and the
             hips are centred on x/y = 0 (no floating / sunk feet).
 4. weights  stray hand weights: any LeftHand/RightHand weight on a vertex
             more than 0.22 m from that hand bone's segment is removed
             (Meshy auto-skin leaks hand weights into hips/thighs, which
             then follow the fists). Then every vertex is limited to 4
             influences and normalised; a vertex left with no weight goes
             fully to its nearest bone.
 4b. limb isolation: each vertex is classed by its nearest bone segment
             body region it reaches first along the mesh surface (Dijkstra from
             confident arm/leg/core seeds: left arm, right arm, legs/hips,
             torso/head); weights from a
             conflicting class are removed (arm<->leg, left<->right arm).
             Fixes arms-down rigs (lieutenant) whose hands touch the thighs
             at rest and inherit thigh weights -> skin strands when arms lift.
 5. stray objects (glTF importer bone-shape Icosphere) and baked actions removed.
--raw only does the import + export (to compare against the cleaned file).
"""
import json
import math
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_point_line

args = sys.argv[sys.argv.index("--") + 1:]
src, dst = args[0], args[1]
report_path = args[args.index("--report") + 1] if "--report" in args else None
RAW = "--raw" in args
HAND_RADIUS = 0.22
rep = {"source": src}

bpy.ops.wm.read_factory_settings(use_empty=True)
if src.lower().endswith(".fbx"):
    bpy.ops.import_scene.fbx(filepath=src, automatic_bone_orientation=False)
else:
    bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
arm.animation_data_clear()
for m in meshes:
    m.animation_data_clear()
rep["armature_scale_in"] = [round(v, 4) for v in arm.scale]
rep["mesh_rotation_in"] = [[round(v, 3) for v in m.rotation_euler] for m in meshes]


def sel(objs, active):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def bbox(objs):
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in objs:
        for v in o.data.vertices:
            p = o.matrix_world @ v.co
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
    return lo, hi


if not RAW:
    # 1. scale: bake every transform
    for m in meshes:
        sel([m], m)
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    sel([arm], arm)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bones = arm.data.bones
    lo, hi = bbox(meshes)
    rep["mesh_height_m"] = round(hi.z - lo.z, 3)
    rep["head_bone_z_m"] = round(bones["Head"].head_local.z, 3)

    # 2. facing
    face = bones["headfront"].head_local - bones["Head"].head_local
    yaw = math.atan2(face.x, -face.y)  # 0 when facing -Y
    rep["facing_correction_deg"] = round(math.degrees(yaw), 2)
    if abs(yaw) > math.radians(2):
        R = Matrix.Rotation(yaw, 4, "Z")
        for o in [arm] + meshes:
            o.matrix_world = R @ o.matrix_world
        for o in [arm] + meshes:
            sel([o], o)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # 3. ground + centre
    lo, hi = bbox(meshes)
    hips = arm.data.bones["Hips"].head_local
    off = Vector((-hips.x, -hips.y, -lo.z))
    rep["ground_offset_m"] = [round(v, 4) for v in off]
    for o in [arm] + meshes:
        o.location += off
        sel([o], o)
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

    # re-parent meshes to the armature, keep their armature modifier
    for m in meshes:
        m.parent = arm
        m.matrix_parent_inverse.identity()
        mod = next((md for md in m.modifiers if md.type == "ARMATURE"), None) or m.modifiers.new("Armature", "ARMATURE")
        mod.object = arm

    # 4. weights
    bones = arm.data.bones
    deform = [b.name for b in bones if b.use_deform]
    stray_total = {}
    for m in meshes:
        vg = {g.index: g.name for g in m.vertex_groups}
        idx = {g.name: g.index for g in m.vertex_groups}
        seg = {n: (bones[n].head_local, bones[n].tail_local) for n in deform if n in bones}
        removed = {"LeftHand": 0, "RightHand": 0}
        orphan = limited = isolated = 0
        GROUP = {}
        for n in deform:
            if n.startswith("Left") and any(k in n for k in ("Shoulder", "Arm", "Hand")):
                GROUP[n] = "armL"
            elif n.startswith("Right") and any(k in n for k in ("Shoulder", "Arm", "Hand")):
                GROUP[n] = "armR"
            elif n in ("Hips",) or any(k in n for k in ("UpLeg", "Leg", "Foot", "Toe")):
                GROUP[n] = "legs"
            else:
                GROUP[n] = "core"
        CONFLICT = {"armL": {"legs", "armR"}, "armR": {"legs", "armL"}, "legs": {"armL", "armR"}, "core": set()}
        def segd(co, n):
            a, b = seg[n]
            p, t = intersect_point_line(co, a, b)
            t = min(max(t, 0.0), 1.0)
            return (co - (a + (b - a) * t)).length
        # surface labels: multi-source Dijkstra over mesh edges from confident seeds
        import heapq
        SEEDB = {"LeftArm": ("armL", 0.08), "LeftForeArm": ("armL", 0.07), "RightArm": ("armR", 0.08),
                 "RightForeArm": ("armR", 0.07), "LeftHand": ("armL", 0.06), "RightHand": ("armR", 0.06), "LeftUpLeg": ("legs", 0.10), "RightUpLeg": ("legs", 0.10),
                 "LeftLeg": ("legs", 0.08), "RightLeg": ("legs", 0.08), "Spine": ("core", 0.14),
                 "Spine01": ("core", 0.14), "neck": ("core", 0.08), "Head": ("core", 0.12)}
        adj = [[] for _ in m.data.vertices]
        for e in m.data.edges:
            a_, b_ = e.vertices
            L = (m.data.vertices[a_].co - m.data.vertices[b_].co).length
            adj[a_].append((b_, L))
            adj[b_].append((a_, L))
        label = [None] * len(m.data.vertices)
        dist_ = [1e9] * len(m.data.vertices)
        heap = []
        for v in m.data.vertices:
            nb = min(seg, key=lambda n: segd(v.co, n))
            if nb in SEEDB and segd(v.co, nb) < SEEDB[nb][1]:
                dist_[v.index] = 0.0
                label[v.index] = SEEDB[nb][0]
                heap.append((0.0, v.index))
        heapq.heapify(heap)
        while heap:
            d0, i0 = heapq.heappop(heap)
            if d0 > dist_[i0]:
                continue
            for j0, L in adj[i0]:
                if d0 + L < dist_[j0]:
                    dist_[j0] = d0 + L
                    label[j0] = label[i0]
                    heapq.heappush(heap, (d0 + L, j0))

        for v in m.data.vertices:
            co = v.co
            ws = {vg[g.group]: g.weight for g in v.groups if g.weight > 0}
            for hn in ("LeftHand", "RightHand"):
                if hn in ws and hn in seg:
                    a, b = seg[hn]
                    p, t = intersect_point_line(co, a, b)
                    t = min(max(t, 0.0), 1.0)
                    d = (co - (a + (b - a) * t)).length
                    if d > HAND_RADIUS:
                        removed[hn] += 1
                        ws.pop(hn)
            if ws:
                lead = label[v.index]
                if lead is None:  # loose island with no seed: fall back to weight majority
                    gw = {}
                    for n, w in ws.items():
                        gw[GROUP.get(n, "core")] = gw.get(GROUP.get(n, "core"), 0) + w
                    lead = max(gw, key=gw.get)
                bad = CONFLICT[lead]
                drop = [n for n in ws if GROUP.get(n) in bad]
                if drop and len(drop) < len(ws):
                    isolated += 1
                    for n in drop:
                        ws.pop(n)
            if len(ws) > 4:
                limited += 1
                ws = dict(sorted(ws.items(), key=lambda kv: -kv[1])[:4])
            tot = sum(ws.values())
            if tot <= 1e-6:
                orphan += 1
                best = min(seg, key=lambda n: (co - (seg[n][0] + seg[n][1]) / 2).length)
                ws = {best: 1.0}
                tot = 1.0
            for g in list(v.groups):
                m.vertex_groups[g.group].remove([v.index])
            for n, w in ws.items():
                if n not in idx:
                    idx[n] = m.vertex_groups.new(name=n).index
                    vg[idx[n]] = n
                m.vertex_groups[idx[n]].add([v.index], w / tot, "REPLACE")
        stray_total[m.name] = {"stray_hand_weights_removed": removed, "orphans_reassigned": orphan, "limb_isolation_fixed": isolated, "limited_to_4": limited,
                               "vertices": len(m.data.vertices)}
    rep["weights"] = stray_total
    lo, hi = bbox(meshes)
    rep["final_height_m"] = round(hi.z - lo.z, 3)
    rep["final_min_z"] = round(lo.z, 4)

sel([arm] + meshes, arm)
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_skins=True,
                          export_animations=False, export_yup=True)
rep["out"] = dst
print("CLEANUP", json.dumps(rep))
if report_path:
    json.dump(rep, open(report_path, "w"), indent=1)

"""Export a rigged character to FBX for Unreal, and optionally cut it into part slots (Blender).

    blender -b --factory-startup -P bl_export.py -- <rigged.glb> <out_dir> <name> [--parts]

Writes <name>.fbx (metres -> Unreal cm via FBX unit scale, no leaf bones, no animation) and,
with --parts, parts/<name>_<slot>.glb for slots head / torso / hands / legs / feet (faces go
to the slot of their dominant bones, as in sample G), each with the shared skeleton, ready for
random mixing (Blender g_parts or Unreal Mutable).
"""
import json
import os
import sys

import bmesh
import bpy

args = sys.argv[sys.argv.index("--") + 1:]
src, out, name = args[0], args[1], args[2]
os.makedirs(out, exist_ok=True)
SLOTS = {
    "head": ["neck", "Head", "head_end", "headfront"],
    "torso": ["Spine02", "Spine01", "Spine", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm", "LeftForeArm", "RightForeArm"],
    "hands": ["LeftHand", "RightHand"],
    "legs": ["Hips", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"],
    "feet": ["LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase"],
}
BONE_SLOT = {b: s for s, bs in SLOTS.items() for b in bs}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
meshes = [o for o in bpy.data.objects if o.type == "MESH"]


def select(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm


select([arm] + meshes)
bpy.ops.export_scene.fbx(filepath=os.path.join(out, name + ".fbx"), use_selection=True, add_leaf_bones=False,
                         bake_anim=False, apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
                         armature_nodetype="NULL", primary_bone_axis="Y", secondary_bone_axis="X",
                         path_mode="COPY", embed_textures=True)
report = {"fbx": name + ".fbx"}

if "--parts" in args:
    pdir = os.path.join(out, "parts")
    os.makedirs(pdir, exist_ok=True)
    body = meshes[0]
    gname = {g.index: g.name for g in body.vertex_groups}
    vslot = []
    for v in body.data.vertices:
        acc = {}
        for g in v.groups:
            s = BONE_SLOT.get(gname[g.group])
            if s:
                acc[s] = acc.get(s, 0) + g.weight
        vslot.append(max(acc, key=acc.get) if acc else "torso")
    counts = {}
    for s in SLOTS:
        ob = body.copy()
        ob.data = body.data.copy()
        ob.name = "%s_%s" % (name, s)
        bpy.context.scene.collection.objects.link(ob)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        kill = []
        for f in bm.faces:
            votes = {}
            for v in f.verts:
                votes[vslot[v.index]] = votes.get(vslot[v.index], 0) + 1
            if max(votes, key=votes.get) != s:
                kill.append(f)
        bmesh.ops.delete(bm, geom=kill, context="FACES")
        bm.to_mesh(ob.data)
        bm.free()
        counts[s] = len(ob.data.polygons)
        select([arm, ob])
        bpy.ops.export_scene.gltf(filepath=os.path.join(pdir, ob.name + ".glb"), export_format="GLB", use_selection=True,
                                  export_skins=True, export_animations=False)
        bpy.data.objects.remove(ob, do_unlink=True)
    report["parts_faces"] = counts
print("EXPORT_OK", json.dumps(report))

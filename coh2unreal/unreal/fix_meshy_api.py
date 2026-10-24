"""Normalises a Meshy API rig/animation FBX to one unit (run with Blender).

    blender -b --factory-startup -P fix_meshy_api.py -- <in.fbx> <out.glb> [--clips <dir>]

Meshy's API FBX puts the armature at 0.01 scale with bones in centimetres,
while the skinned mesh is in metres under a compensating parent matrix.
Importers that drop either scale end up with a mesh and skeleton of
different sizes, and the skinning stretches. This bakes everything into
metres with identity transforms:
  1. each mesh: world transform baked into its vertices, unparented
  2. armature: scale applied (bones -> metres; Blender rescales the
     actions' location keys itself)
  3. meshes re-parented to the armature (armature modifier kept)
Without --clips: writes <out.glb> (mesh + skeleton, no animation).
With --clips: writes one <dir>/<action>.glb per action (for import onto the
character's skeleton).
"""
import os
import re
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
src, dst = args[0], args[1]
clips = args[args.index("--clips") + 1] if "--clips" in args else None

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=src, automatic_bone_orientation=False)
arm = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
actions = list(bpy.data.actions)
factor = arm.scale[0]


def select(objs, active):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


# 1. meshes: bake world transform, unparent
for m in meshes:
    select([m], m)
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# 2. armature: apply scale; scale hips motion to match
arm.animation_data_clear() if not clips else None
select([arm], arm)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def fcurves(act):
    if hasattr(act, "fcurves") and act.fcurves:
        return list(act.fcurves)
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


# (Blender's apply-scale also rescales the actions' location keys)

# 2b. auto-rig clean-up: Meshy's rigger sometimes binds belt gear and loose
# clothing to the hands/forearms, which then stretch with arm moves. Remove
# hand/forearm influence from vertices far from those bones (rest pose).
HAND_BONES = ("LeftHand", "RightHand", "LeftForeArm", "RightForeArm",
              "LeftHand_End", "RightHand_End")
if not clips:
    from mathutils import Vector
    seg = {}
    for b in arm.data.bones:
        if b.name in HAND_BONES:
            seg[b.name] = (arm.matrix_world @ b.head_local,
                           arm.matrix_world @ b.tail_local)

    def dist_to_bone(p, name):
        a, b = seg[name]
        ab = b - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
        return (p - (a + ab * t)).length

    fixed = 0
    for m in meshes:
        groups = {g.index: g.name for g in m.vertex_groups}
        hips = m.vertex_groups.get("Hips") or m.vertex_groups.new(name="Hips")
        for v in m.data.vertices:
            p = m.matrix_world @ v.co
            moved = 0.0
            for g in list(v.groups):
                name = groups.get(g.group)
                if name in seg and g.weight > 0 and dist_to_bone(p, name) > 0.22:
                    moved += g.weight
                    m.vertex_groups[name].remove([v.index])
            if moved:
                hips.add([v.index], moved, "ADD")
                fixed += 1
    print("hand-weight clean-up: %d vertices" % fixed)

# 3. re-parent meshes, keep their armature modifier
for m in meshes:
    select([m, arm], arm)
    bpy.ops.object.parent_set(type="OBJECT", keep_transform=True)
    if not any(md.type == "ARMATURE" for md in m.modifiers):
        md = m.modifiers.new("Armature", "ARMATURE")
        md.object = arm
print("armature scale was", round(factor, 4), "-> dims (m)",
      [round(v, 3) for v in arm.dimensions])


def export(path, with_anim):
    select([arm] + meshes, arm)
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", use_selection=True,
        export_yup=True, export_skins=True, export_animations=with_anim,
        export_animation_mode="ACTIVE_ACTIONS", export_force_sampling=True,
        export_def_bones=True, export_frame_range=True)
    print("wrote", path)


if not clips:
    export(dst, False)
else:
    os.makedirs(clips, exist_ok=True)
    for act in actions:
        name = re.sub(r"[^A-Za-z0-9_]", "_", act.name.split("|")[-1])
        arm.animation_data_create()
        arm.animation_data.action = act
        s, e = (int(v) for v in act.frame_range)
        bpy.context.scene.frame_start, bpy.context.scene.frame_end = s, e
        export(os.path.join(clips, name + ".glb"), True)

"""Bakes Meshy animation clips onto a normalised rig (run with Blender).

    blender -b --factory-startup -P bake_clips.py -- <rig.glb> <animations.fbx> <out dir>

<rig.glb> is the character from fix_meshy_api.py (metres, identity
transforms). Each action in the Meshy animation FBX is played on its own
armature and copied, bone by bone in world space, onto the rig (whose rest
pose is the same, just in other units), then baked and written as
<out dir>/<action>.glb. The clips then match the rig's skeleton exactly.
"""
import os
import re
import sys

import bpy

rig_path, anim_path, out = sys.argv[sys.argv.index("--") + 1:][:3]
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=rig_path)
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
rig_meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent == rig]
before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=anim_path, automatic_bone_orientation=False)
src = [o for o in set(bpy.data.objects) - before if o.type == "ARMATURE"][0]
for o in set(bpy.data.objects) - before:
    if o.type == "MESH":
        o.hide_render = True
actions = [a for a in bpy.data.actions if a.name.startswith(src.name) or "|" in a.name]

# world-space copy constraints on every rig bone
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="POSE")
for pb in rig.pose.bones:
    if pb.name not in src.pose.bones:
        continue
    c = pb.constraints.new("COPY_ROTATION")
    c.target, c.subtarget = src, pb.name
    if pb.name == "Hips":
        c2 = pb.constraints.new("COPY_LOCATION")
        c2.target, c2.subtarget = src, pb.name
bpy.ops.object.mode_set(mode="OBJECT")

for act in actions:
    name = re.sub(r"[^A-Za-z0-9_]", "_", act.name.split("|")[-1])
    src.animation_data_create()
    src.animation_data.action = act
    s, e = (int(v) for v in act.frame_range)
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = s, e
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.nla.bake(frame_start=s, frame_end=e, only_selected=True,
                     visual_keying=True, clear_constraints=False,
                     use_current_action=False, bake_types={"POSE"})
    bpy.ops.object.mode_set(mode="OBJECT")
    baked = rig.animation_data.action
    baked.name = name
    # export with constraints muted so only the baked keys drive the bones
    for pb in rig.pose.bones:
        for c in pb.constraints:
            c.mute = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in [rig] + rig_meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(
        filepath=os.path.join(out, name + ".glb"), export_format="GLB",
        use_selection=True, export_yup=True, export_skins=True,
        export_animations=True, export_animation_mode="ACTIVE_ACTIONS",
        export_force_sampling=True, export_def_bones=True,
        export_frame_range=True)
    for pb in rig.pose.bones:
        for c in pb.constraints:
            c.mute = False
    rig.animation_data.action = None
    print("clip", name, s, e)

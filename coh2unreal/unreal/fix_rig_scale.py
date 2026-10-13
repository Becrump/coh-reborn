"""Bakes a Meshy/Mixamo-style rig to Unreal units (run with Blender).

    blender -b --factory-startup -P fix_rig_scale.py -- <in.fbx> <out.fbx>

Meshy exports the skeleton in metres with a x100 scale on the root bone;
Unreal's retargeter drops that scale and the animated bones collapse into
the hips. This re-imports the FBX, scales the armature and mesh to
centimetres with the scale applied (every bone scale 1), and writes a clean
FBX for Unreal (no leaf bones, no baked animation).
"""
import sys

import bpy

src, dst = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=src, automatic_bone_orientation=False)
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
arm = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
for o in meshes:
    o.animation_data_clear()
arm.animation_data_clear()
# work in centimetres: 1 Blender unit = 1 cm, applied into the data
bpy.context.scene.unit_settings.system = "METRIC"
bpy.context.scene.unit_settings.scale_length = 0.01
bpy.ops.object.select_all(action="DESELECT")
for o in [arm] + meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = arm
arm.scale = [s * 100 for s in arm.scale]
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
for o in meshes:
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
print("armature dims (cm):", [round(v, 1) for v in arm.dimensions])
bpy.ops.object.select_all(action="DESELECT")
for o in [arm] + meshes:
    o.select_set(True)
if dst.lower().endswith((".glb", ".gltf")):
    # glTF is metres: undo the cm scale, apply, export with the skin
    bpy.context.scene.unit_settings.scale_length = 1.0
    arm.scale = [s * 0.01 for s in arm.scale]
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    for o in meshes:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.transform_apply(location=False, rotation=True,
                                       scale=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in [arm] + meshes:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB",
                              use_selection=True, export_yup=True,
                              export_skins=True, export_animations=False,
                              export_def_bones=True)
    print("wrote", dst)
    raise SystemExit
bpy.ops.export_scene.fbx(
    filepath=dst, use_selection=True, object_types={"ARMATURE", "MESH"},
    apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
    add_leaf_bones=False, bake_anim=False, mesh_smooth_type="FACE",
    use_armature_deform_only=True, primary_bone_axis="Y",
    secondary_bone_axis="X")
print("wrote", dst)

"""Prepare a charpipe/Tripo character as MetaHuman Creator conform input (Blender).

    blender -b --factory-startup -P bl_mh_conform_prep.py -- <rigged.glb> <out_dir> <name>

* Poses the arms into the MetaHuman bind A-pose (upper arm 52 deg below horizontal), keeps legs.
* Applies the pose to the mesh, removes the skeleton: one combined static mesh with its texture.
* Scale: centimetres (scene unit cm, mesh x100), feet at the origin, centred on X/Y,
  front facing Blender -Y (imports into Unreal facing +Y like MetaHuman meshes).
* Writes <name>.fbx (embedded texture), <name>.obj/.mtl, <name>_basecolor.png,
  <name>_headless.fbx/.obj (vertices mostly weighted to Head removed), and a preview PNG.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
src, out, name = args[0], args[1], args[2]
TARGET = 52.0
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = next(o for o in bpy.data.objects if o.type == "MESH")
W = arm.matrix_world
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()


def drop(bname):
    b = arm.data.bones[bname]
    d = (W @ b.tail_local) - (W @ b.head_local)
    return math.degrees(math.atan2(-d.z, abs(d.x)))


report = {}
for bname, side in (("LeftArm", 1), ("RightArm", -1)):
    cur = drop(bname)
    delta = cur - TARGET  # raise the arm by this much
    pb = arm.pose.bones[bname]
    head = W @ pb.head
    R = Matrix.Translation(head) @ Matrix.Rotation(math.radians(-side * delta), 4, "Y") @ Matrix.Translation(-head)
    pb.matrix = W.inverted() @ (R @ (W @ pb.matrix))
    bpy.context.view_layer.update()
    report[bname] = (round(cur, 1), TARGET)
print("ARM_DROP before/after", report)

# bake pose into the mesh
bpy.context.view_layer.objects.active = body
for m in body.modifiers:
    if m.type == "ARMATURE":
        bpy.ops.object.modifier_apply(modifier=m.name)
head_vg = body.vertex_groups.get("Head")
head_idx = head_vg.index if head_vg else None
body.parent = None
body.matrix_world = Matrix.Identity(4) @ body.matrix_world
bpy.data.objects.remove(arm, do_unlink=True)
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# centre, feet to origin, metres -> cm
me = body.data
xs = [v.co.x for v in me.vertices]
ys = [v.co.y for v in me.vertices]
zmin = min(v.co.z for v in me.vertices)
off = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, zmin))
me.transform(Matrix.Scale(100, 4) @ Matrix.Translation(-off))
me.update()
height = max(v.co.z for v in me.vertices)
sc = bpy.context.scene
sc.unit_settings.system = "METRIC"
sc.unit_settings.scale_length = 0.01
sc.unit_settings.length_unit = "CENTIMETERS"
body.name = name

# texture out as PNG
img = None
for n in body.data.materials[0].node_tree.nodes:
    if n.type == "TEX_IMAGE" and n.image and img is None:
        img = n.image
if img:
    img.filepath_raw = os.path.join(out, name + "_basecolor.png")
    img.file_format = "PNG"
    img.save()


def export(tag):
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    fbx = os.path.join(out, name + tag + ".fbx")
    bpy.ops.export_scene.fbx(filepath=fbx, use_selection=True, object_types={"MESH"}, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_UNITS", path_mode="COPY", embed_textures=True,
                             mesh_smooth_type="FACE", add_leaf_bones=False)
    bpy.ops.wm.obj_export(filepath=os.path.join(out, name + tag + ".obj"), export_selected_objects=True,
                          export_materials=True, path_mode="COPY", global_scale=1.0, forward_axis="NEGATIVE_Z", up_axis="Y")
    return fbx


export("")
nverts_full = len(me.vertices)

# preview (full)
cam_d = bpy.data.cameras.new("C")
cam_d.type = "ORTHO"
cam_d.ortho_scale = height * 1.1
cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
cam.location = (0, -600, height / 2)
cam.rotation_euler = (math.pi / 2, 0, 0)
cam_d.clip_end = 5000
ld = bpy.data.lights.new("S", "SUN")
ld.energy = 3
lo = bpy.data.objects.new("S", ld)
sc.collection.objects.link(lo)
lo.rotation_euler = (math.radians(50), 0, math.radians(-30))
w = bpy.data.worlds.new("W")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.2158, 0.2158, 0.2158, 1)
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 768, 1152
sc.view_settings.view_transform = "Standard"
sc.render.filepath = os.path.join(out, name + "_preview.png")
bpy.ops.render.render(write_still=True)

# headless: drop vertices mostly weighted to Head
removed = 0
if head_idx is not None:
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    dl = bm.verts.layers.deform.active
    kill = [v for v in bm.verts if v[dl].get(head_idx, 0.0) >= 0.5]
    removed = len(kill)
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()
    export("_headless")
    sc.render.filepath = os.path.join(out, name + "_headless_preview.png")
    bpy.ops.render.render(write_still=True)
print("MH_PREP_OK height_cm", round(height, 1), "verts", nverts_full, "headless_removed", removed)

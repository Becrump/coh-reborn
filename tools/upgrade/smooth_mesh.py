"""Smooth an exported character and switch it to the upscaled textures.

    blender -b --factory-startup --python tools/upgrade/smooth_mesh.py -- \\
        <in.gltf> <upscaled textures dir> <out.gltf> [crease_degrees=55]

Each costume piece gets one Catmull-Clark subdivision applied *before* the
armature, so Blender interpolates the skin weights for the new vertices.
Edges sharper than crease_degrees are creased first, which keeps spikes,
horns and boot soles pointed. Materials gain the _n (normal) and _orm
(roughness) maps written by upscale_textures.py.
"""
import bmesh
import bpy
import math
import os
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
src, texdir, out = argv[0], argv[1], argv[2]
crease_deg = float(argv[3]) if len(argv) > 3 else 55.0

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src, merge_vertices=True)
for o in [o for o in bpy.context.scene.objects
          if o.type == "MESH" and o.name.startswith("Icosphere")]:
    bpy.data.objects.remove(o)          # glTF importer's bone-shape helper

for ob in [o for o in bpy.context.scene.objects if o.type == "MESH"]:
    bpy.context.view_layer.objects.active = ob
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    cl = bm.edges.layers.float.get("crease_edge") or \
        bm.edges.layers.float.new("crease_edge")
    for e in bm.edges:
        if len(e.link_faces) == 2 and \
                e.calc_face_angle(0) > math.radians(crease_deg):
            e[cl] = 1.0
    bm.to_mesh(me)
    bm.free()
    sub = ob.modifiers.new("Subd", "SUBSURF")
    sub.levels = sub.render_levels = 1
    sub.boundary_smooth = "PRESERVE_CORNERS"
    sub.use_limit_surface = True
    while ob.modifiers.find("Subd") > 0:
        bpy.ops.object.modifier_move_up(modifier="Subd")
    bpy.ops.object.modifier_apply(modifier="Subd")
    bpy.ops.object.shade_smooth()

for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None)
    if not bsdf or not tex or not tex.image:
        continue
    base = os.path.splitext(os.path.basename(tex.image.filepath))[0]
    path = os.path.join(texdir, base + ".png")
    if not os.path.exists(path):
        continue
    tex.image = bpy.data.images.load(path, check_existing=True)
    if os.path.exists(os.path.join(texdir, base + "_n.png")):
        n = bpy.data.images.load(os.path.join(texdir, base + "_n.png"))
        n.colorspace_settings.name = "Non-Color"
        nt_ = nt.nodes.new("ShaderNodeTexImage")
        nt_.image = n
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(nt_.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if os.path.exists(os.path.join(texdir, base + "_orm.png")):
        r = bpy.data.images.load(os.path.join(texdir, base + "_orm.png"))
        r.colorspace_settings.name = "Non-Color"
        rt = nt.nodes.new("ShaderNodeTexImage")
        rt.image = r
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(rt.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])

bpy.ops.export_scene.gltf(filepath=out, export_format="GLTF_SEPARATE",
                          export_texture_dir="textures", export_skins=True,
                          export_animations=True,
                          export_animation_mode="ACTIONS", export_yup=True)
print("SMOOTH_DONE")

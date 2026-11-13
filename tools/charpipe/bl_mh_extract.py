"""Extract a MetaHuman base body + head from a .blend into one skinned GLB on the body skeleton (Blender).

    blender -b <hero.blend> -P bl_mh_extract.py -- <out.glb> [--body MHC_Base_Male_Body_LOD0] [--head MHC_Base_Male_Head_LOD0]
            [--skin 0.62,0.45,0.36]

The head's facial bones don't exist on the body skeleton; their weights are folded into 'head'
(no facial animation, which CoH doesn't use). Output: one armature (UE5 / MetaHuman bone names,
A-pose, metres) with body + head meshes and a plain skin material.
"""
import sys
import bpy

args = sys.argv[sys.argv.index("--") + 1:]
out = args[0]
body_n = args[args.index("--body") + 1] if "--body" in args else "MHC_Base_Male_Body_LOD0"
head_n = args[args.index("--head") + 1] if "--head" in args else "MHC_Base_Male_Head_LOD0"
skin = tuple(float(v) for v in (args[args.index("--skin") + 1] if "--skin" in args else "0.62,0.45,0.36").split(",")) + (1,)
body, head = bpy.data.objects[body_n], bpy.data.objects[head_n]
arm = body.parent
keep = {arm, body, head}
for o in list(bpy.data.objects):
    if o not in keep:
        bpy.data.objects.remove(o, do_unlink=True)
bones = {b.name for b in arm.data.bones}
merged = 0
for g in list(head.vertex_groups):
    if g.name in bones:
        continue
    tgt = head.vertex_groups.get("head") or head.vertex_groups.new(name="head")
    for v in head.data.vertices:
        for x in v.groups:
            if x.group == g.index and x.weight > 0:
                tgt.add([v.index], x.weight, "ADD")
    head.vertex_groups.remove(g)
    merged += 1
for m in head.modifiers:
    if m.type == "ARMATURE":
        m.object = arm
# bake each mesh's own transform (MetaHuman meshes sit at 0.01 under the armature) into metres
sc0 = bpy.context.scene
for o in (body, head):
    if o.name not in sc0.collection.objects:
        sc0.collection.objects.link(o)
    o.hide_set(False)
    o.hide_viewport = False
    if o.data.users > 1:
        o.data = o.data.copy()
    if o.data.shape_keys:  # facial blendshapes keep a cm basis; CoH needs no facial animation
        bpy.context.view_layer.objects.active = o
        o.shape_key_clear()
    mw = o.matrix_world.copy()
    o.parent = None
    o.matrix_world = mw
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    zs = [v.co.z for v in o.data.vertices]
    if max(zs) - min(zs) > 10:  # mesh authored in centimetres (head on the cm face skeleton)
        from mathutils import Matrix
        o.data.transform(Matrix.Scale(0.01, 4))
    o.parent = arm
    o.matrix_parent_inverse = arm.matrix_world.inverted()
mat = bpy.data.materials.new("MH_Skin")
mat.use_nodes = True
p = mat.node_tree.nodes["Principled BSDF"]
p.inputs["Base Color"].default_value = skin
p.inputs["Roughness"].default_value = 0.5
try:
    p.inputs["Subsurface Weight"].default_value = 0.15
except KeyError:
    pass
for o in (body, head):
    o.data.materials.clear()
    o.data.materials.append(mat)
sc = bpy.context.scene
for coll in list(bpy.data.collections):
    bpy.data.collections.remove(coll)
for o in keep:
    if o.name not in sc.collection.objects:
        sc.collection.objects.link(o)
    o.hide_viewport = False
    o.hide_render = False
    o.hide_set(False)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=False, use_visible=False, export_skins=True,
                          export_animations=False)
print("MH_OK", out, "bones", len(bones), "head groups folded", merged)

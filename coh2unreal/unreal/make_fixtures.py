"""Builds ground spotlight fixture meshes (run with Blender).

    blender -b --factory-startup -P make_fixtures.py -- <out folder>

fixture_head.glb  the lamp can: 30 cm long, 18 cm across, aimed along +X,
                  origin at the lens (where the light is). Two material
                  slots: Body (dark metal) and Lens (glowing glass).
fixture_post.glb  ground plate plus a 1 m post (origin on the ground), scaled
                  in Z to reach the head.
"""
import os
import sys

import bpy

OUT = os.path.abspath(sys.argv[sys.argv.index("--") + 1:][0])
os.makedirs(OUT, exist_ok=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name):
    return bpy.data.materials.get(name) or bpy.data.materials.new(name)


def export(name):
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in bpy.data.objects:
        o.select_set(o in meshes)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for p in o.data.polygons:
        p.use_smooth = True
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, name + ".glb"),
                              export_format="GLB", export_yup=True)


def add(prim, material, **kw):
    getattr(bpy.ops.mesh, "primitive_%s_add" % prim)(**kw)
    o = bpy.context.object
    o.data.materials.append(mat(material))
    return o


# lamp can along +X, lens at x = 0
reset()
can = add("cylinder", "Body", vertices=24, radius=0.09, depth=0.28,
          location=(-0.14, 0, 0), rotation=(0, 1.5708, 0))
rim = add("cylinder", "Body", vertices=24, radius=0.1, depth=0.03,
          location=(-0.01, 0, 0), rotation=(0, 1.5708, 0))
lens = add("cylinder", "Lens", vertices=24, radius=0.075, depth=0.01,
           location=(0.002, 0, 0), rotation=(0, 1.5708, 0))
yoke = add("cube", "Body", size=1, location=(-0.14, 0, -0.1))
yoke.scale = (0.05, 0.22, 0.02)
export("fixture_head")

# ground plate + post, origin on the ground
reset()
add("cylinder", "Body", vertices=20, radius=0.12, depth=0.02,
    location=(0, 0, 0.01))
add("cylinder", "Body", vertices=12, radius=0.022, depth=1.0,
    location=(0, 0, 0.5))
export("fixture_post")
print("fixtures written to", OUT)

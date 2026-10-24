# Blender: top-down guide renders of the original Atlas Park glTF.
import bpy, sys, json, math, os
args = sys.argv[sys.argv.index("--") + 1:]
src, out = args[0], args[1]
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.type != 'MESH':
        bpy.data.objects.remove(o)
sc = bpy.context.scene
X0, X1, Y0, Y1 = -870.0, 1182.0, -1064.0, 636.0   # blender XY (Y = -gltf z)
MPP = 0.5
W, H = int((X1 - X0) / MPP), int((Y1 - Y0) / MPP)
cam_d = bpy.data.cameras.new("cam"); cam_d.type = 'ORTHO'
cam_d.ortho_scale = max(X1 - X0, Y1 - Y0); cam_d.clip_start = 1; cam_d.clip_end = 5000
cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.resolution_percentage = 100
cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
sc.render.film_transparent = True
sc.render.filter_size = 0.0
sc.view_settings.view_transform = 'Standard'
mats = [m for m in bpy.data.materials]
names = [m.name for m in mats]
json.dump({"names": names, "bounds_blender": [X0, X1, Y0, Y1], "mpp": MPP, "W": W, "H": H,
           "note": "UE X = bx*100, UE Y = -by*100, UE Z = bz*100"}, open(os.path.join(out, "meta.json"), "w"))

def place(top):
    if top:
        cam.location = (cx, cy, 2000); cam.rotation_euler = (0, 0, 0)
    else:
        cam.location = (cx, cy, -2000); cam.rotation_euler = (math.pi, 0, 0)

def emission_mat(name, build):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial"); e = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(e.outputs[0], o.inputs[0]); build(nt, e); return m

def set_all(fn):
    for ob in bpy.data.objects:
        if ob.type != 'MESH': continue
        for s in ob.material_slots:
            s.link = 'DATA'
        me = ob.data
        for i in range(len(me.materials)):
            me.materials[i] = fn(me.materials[i])

def render(path, exr):
    sc.render.image_settings.file_format = 'OPEN_EXR' if exr else 'PNG'
    if exr:
        sc.render.image_settings.color_depth = '32'
        sc.render.image_settings.color_mode = 'RGBA'
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)

# 1. colour (workbench, textures, flat)
sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading; sh.light = 'FLAT'; sh.color_type = 'TEXTURE'
place(True); render(os.path.join(out, "color_top.png"), False)
# eevee passes
sc.render.engine = 'BLENDER_EEVEE'
try: sc.eevee.taa_render_samples = 1
except Exception: pass
# 2. material id
orig = {}
idmats = {}
for i, m in enumerate(mats):
    v = float(i + 1)
    idmats[m.name] = emission_mat("id_%d" % i, lambda nt, e, v=v: e.inputs[0].default_value.__setitem__(slice(0, 3), (v, v, v)))
set_all(lambda m: idmats.get(m.name, m) if m else m)
place(True); render(os.path.join(out, "matid_top.exr"), True)
# 3. height top / bottom
def zb(nt, e):
    g = nt.nodes.new("ShaderNodeNewGeometry"); s = nt.nodes.new("ShaderNodeSeparateXYZ"); c = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(g.outputs["Position"], s.inputs[0])
    a = nt.nodes.new("ShaderNodeMath"); a.operation = 'ADD'; a.inputs[1].default_value = 1000.0
    nt.links.new(s.outputs[2], a.inputs[0])
    for k in range(3): nt.links.new(a.outputs[0], c.inputs[k])
    nt.links.new(c.outputs[0], e.inputs[0])
zm = emission_mat("zpass", zb)
set_all(lambda m: zm)
for m in [zm]:
    m.use_backface_culling = False
place(True); render(os.path.join(out, "z_top.exr"), True)
place(False); render(os.path.join(out, "z_bottom.exr"), True)
print("GUIDE_DONE", W, H)

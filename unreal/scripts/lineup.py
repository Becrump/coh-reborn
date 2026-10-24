import bpy, sys, math
out = sys.argv[sys.argv.index("--")+1]
names = ["hellion_biker", "hellion_hood", "hellion_punk", "hellion_lieutenant"]
bpy.ops.wm.read_factory_settings(use_empty=True)
for i, n in enumerate(names):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath="C:/Users/rtcru/CoHReborn/meshy/%s/rig/rigged_character_glb.glb" % n)
    for o in set(bpy.data.objects) - before:
        if o.parent is None:
            o.location.x += i * 1.4
sc = bpy.context.scene
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam)
cam.location = (2.1, -6.5, 1.1); cam.rotation_euler = (math.radians(88), 0, 0); cam.data.lens = 40
sc.camera = cam
for loc, e in (((2, -4, 5), 3.0), ((-3, -2, 3), 1.5)):
    l = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); l.data.energy = e; l.location = loc; l.rotation_euler = (math.radians(45), 0, math.radians(20)); sc.collection.objects.link(l)
sc.world = bpy.data.worlds.new("w"); sc.world.color = (0.25, 0.27, 0.3)
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 1600, 900
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("rendered", out)

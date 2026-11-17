"""Manual outfit tint for ONE finished character, with a preview before you use it (Blender).

    blender -b --factory-startup -P bl_tint_preview.py -- <rigged.glb> <out_dir> <name> --hue 20 [--sat 1.0] [--val 1.0]
            [--protect-skin]

Changes the hue / saturation / brightness of the character's base-colour texture(s) and writes:
  <out_dir>/<name>.glb                  the tinted character (same rig, nothing else changes)
  <out_dir>/<name>_preview.png          before | after, full body front + face close-up, to check by eye
--protect-skin keeps skin-coloured texels (YCbCr skin range) unchanged, so faces and arms keep their tone.
Nothing is placed or deformed: only colours change, so it cannot misplace or warp anything.
"""
import math
import os
import sys

import bpy
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT, NAME = a[0], a[1], a[2]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
HUE, SAT, VAL = float(opt("--hue", 0)), float(opt("--sat", 1)), float(opt("--val", 1))
os.makedirs(OUT, exist_ok=True)


def load():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=SRC)
    for o in list(bpy.data.objects):
        if o.name.startswith("Icosphere"):
            bpy.data.objects.remove(o, do_unlink=True)


def shoot(tag):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 400, 600
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.3, 0.3, 0.3, 1)
    for r_ in ((0.8, 0, -0.5), (0.9, 0, 2.5)):
        l_ = bpy.data.objects.new("L", bpy.data.lights.new("L", "SUN"))
        l_.data.energy = 2.5
        sc.collection.objects.link(l_)
        l_.rotation_euler = r_
    ms = [o for o in bpy.data.objects if o.type == "MESH"]
    zs = [(o.matrix_world @ v.co).z for o in ms for v in o.data.vertices]
    h = max(zs)
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
    cam.data.type = "ORTHO"
    sc.collection.objects.link(cam)
    sc.camera = cam
    paths = []
    for shot, sc_, z in (("full", h * 1.08, h / 2), ("face", 0.35, h - 0.14)):
        cam.data.ortho_scale = sc_
        cam.location = (0, -6, z)
        cam.rotation_euler = (math.pi / 2, 0, 0)
        p = os.path.join(OUT, "_%s_%s_%s.png" % (NAME, tag, shot))
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        paths.append(p)
    return paths


def tint_images():
    done = set()
    for m in bpy.data.materials:
        if not (m and m.use_nodes):
            continue
        for n in m.node_tree.nodes:
            if n.type != "TEX_IMAGE" or not n.image or n.image.name in done:
                continue
            nm = n.image.name.lower()
            if any(k in nm for k in ("normal", "rough", "metal", "occlusion", "_ao")):
                continue
            im = n.image
            done.add(im.name)
            px = np.empty(im.size[0] * im.size[1] * im.channels, np.float32)
            im.pixels.foreach_get(px)
            P = px.reshape(-1, im.channels)
            c = np.clip(P[:, :3], 0, 1) ** (1 / 2.2)
            keep = np.zeros(len(c), bool)
            if "--protect-skin" in a:
                r, g, b = c[:, 0] * 255, c[:, 1] * 255, c[:, 2] * 255
                Y = 0.299 * r + 0.587 * g + 0.114 * b
                Cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
                Cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
                keep = (Cr > 133) & (Cr < 178) & (Cb > 75) & (Cb < 130) & (Y > 35)
            mx, mn = c.max(1), c.min(1)
            v_ = mx
            s_ = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)
            rc, gc, bc = [(mx - c[:, i]) / np.maximum(mx - mn, 1e-9) for i in range(3)]
            h_ = (np.select([mx == c[:, 0], mx == c[:, 1]], [bc - gc, 2 + rc - bc], 4 + gc - rc) / 6.0 + HUE / 360.0) % 1.0
            s_ = np.clip(s_ * SAT, 0, 1)
            v_ = np.clip(v_ * VAL, 0, 1)
            i_ = (h_ * 6).astype(int) % 6
            f_ = h_ * 6 - np.floor(h_ * 6)
            p_, q_, t_ = v_ * (1 - s_), v_ * (1 - f_ * s_), v_ * (1 - (1 - f_) * s_)
            cand = [np.stack(x, 1) for x in ((v_, t_, p_), (q_, v_, p_), (p_, v_, t_), (p_, q_, v_), (t_, p_, v_), (v_, p_, q_))]
            out = np.zeros_like(c)
            for k in range(6):
                out = np.where((i_ == k)[:, None], cand[k], out)
            out = np.where(keep[:, None], c, out)
            P[:, :3] = out ** 2.2
            im.pixels.foreach_set(P.ravel())
            im.pack()
    return sorted(done)


load()
before = shoot("before")
load()
imgs = tint_images()
for x in bpy.data.objects:
    x.select_set(x.type in ("MESH", "ARMATURE"))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), export_format="GLB", use_selection=True,
                          export_skins=True, export_animations=False)
after = shoot("after")
# side-by-side preview: before full | after full | before face | after face (Blender images, no PIL needed)
tiles = [before[0], after[0], before[1], after[1]]
W_, H_ = 400, 600
sheet = np.ones((H_, W_ * 4, 4), np.float32)
for i, t in enumerate(tiles):
    im = bpy.data.images.load(t)
    px = np.empty(W_ * H_ * 4, np.float32)
    im.pixels.foreach_get(px)
    sheet[:, i * W_:(i + 1) * W_] = px.reshape(H_, W_, 4)
    os.remove(t)
out = bpy.data.images.new(NAME + "_preview", W_ * 4, H_)
out.pixels.foreach_set(sheet.ravel())
out.filepath_raw = os.path.join(OUT, NAME + "_preview.png")
out.file_format = "PNG"
out.save()
print("TINT_OK", NAME, "textures", imgs, "preview", out.filepath_raw)

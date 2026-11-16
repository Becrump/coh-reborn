"""Skin-tone system: find the skin in a character's textures and re-tint it with one SkinTone colour (Blender).

    blender -b --factory-startup -P bl_skin_tone.py -- <rigged.glb> <out_dir> <name> [--tones name=r,g,b;name=r,g,b] [--res 2048] [--outfit-tint h:s:v] [--outfit-meshes Body]

Per mesh (body and head):
 * region mask: UV areas of faces whose dominant bone is skin-likely (arms, forearms, hands, fingers,
   shoulders, neck, head; a separate head mesh counts fully)
 * skin mask = region mask AND skin colour in YCbCr (Cr 133-178, Cb 75-130, Y > 35), cleaned with a
   blur + threshold and feathered, so clothing, gloves, hair and the bandana stay untouched
 * detail = skin luminance / median skin luminance (keeps pores, shading, tattoos' darkness)
 * tinted albedo = lerp(original, SkinTone * detail, mask)
Writes <out_dir>/<name>_<mesh>_skinmask.png (R = mask, G = detail * 0.5, the Unreal material inputs),
and for each tone <out_dir>/<name>_<tone>.glb with tinted textures, plus skin_tone.json.
Unreal: MI parameter SkinTone (Vector), shared by body and head materials:
    BaseColor = lerp(Tex.rgb, SkinTone.rgb * (Mask.G * 2), Mask.R)
"""
import json
import os
import sys

import bpy
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
src, out, name = a[0], a[1], a[2]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
TONES = {}
for kv in (opt("--tones") or "light=0.86,0.67,0.56;medium=0.64,0.45,0.32;dark=0.36,0.23,0.16").split(";"):
    k, v = kv.split("=")
    TONES[k] = np.array([float(x) for x in v.split(",")])
RES = int(opt("--res", 2048))
OUTFIT_TINT = [float(x) for x in opt("--outfit-tint").split(":")] if opt("--outfit-tint") else None  # hue_deg:sat_mul:val_mul
OUTFIT_MESHES = set((opt("--outfit-meshes") or "Body").split(","))
os.makedirs(out, exist_ok=True)
SKIN_BONES = ("Arm", "ForeArm", "Hand", "Thumb", "Index", "Middle", "Ring", "Pinky", "Shoulder", "neck", "Head", "head",
              "UpLeg", "Leg", "Foot", "Spine", "Hips")  # colour gating keeps clothing out; bare legs / chests are skin


def load():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=src)
    for o in list(bpy.data.objects):
        if o.name.startswith("Icosphere"):
            bpy.data.objects.remove(o, do_unlink=True)


def tex_of(o):
    for m in o.data.materials:
        if m and m.use_nodes:
            p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if p and p.inputs["Base Color"].is_linked:
                n = p.inputs["Base Color"].links[0].from_node
                while n.type != "TEX_IMAGE" and n.inputs and any(i.is_linked for i in n.inputs):
                    n = next(i for i in n.inputs if i.is_linked).links[0].from_node
                if n.type == "TEX_IMAGE" and n.image:
                    return n.image
    return None


def raster_tri(img, pts):
    (x0, y0), (x1, y1), (x2, y2) = pts
    xmin, xmax = int(max(min(x0, x1, x2), 0)), int(min(max(x0, x1, x2) + 1, img.shape[1]))
    ymin, ymax = int(max(min(y0, y1, y2), 0)), int(min(max(y0, y1, y2) + 1, img.shape[0]))
    if xmax <= xmin or ymax <= ymin:
        return
    X, Y = np.meshgrid(np.arange(xmin, xmax) + 0.5, np.arange(ymin, ymax) + 0.5)
    d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(d) < 1e-9:
        return
    l1 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / d
    l2 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / d
    inside = (l1 >= -0.02) & (l2 >= -0.02) & (1 - l1 - l2 >= -0.02)
    img[ymin:ymax, xmin:xmax][inside] = 1.0


def region_mask(o, size, bones=None):
    img = np.zeros((size, size), np.float32)
    whole = (o.name.lower().startswith("head") or not o.vertex_groups) and bones is None
    gname = {g.index: g.name for g in o.vertex_groups}
    uv = o.data.uv_layers.active.data
    from collections import Counter
    for p in o.data.polygons:
        if not whole:
            c = Counter()
            for vi in p.vertices:
                for g in o.data.vertices[vi].groups:
                    c[gname[g.group]] += g.weight
            if not c or not any(k in c.most_common(1)[0][0] for k in (bones or SKIN_BONES)):
                continue
        pts = [(uv[li].uv.x * size, (1 - uv[li].uv.y) * size) for li in p.loop_indices]
        for i in range(1, len(pts) - 1):
            raster_tri(img, (pts[0], pts[i], pts[i + 1]))
    return img


def blur(m, r):
    r = max(1, int(r))
    k = np.ones(2 * r + 1) / (2 * r + 1)
    for _ in range(2):
        m = np.apply_along_axis(lambda x: np.convolve(x, k, mode="same"), 0, m)
        m = np.apply_along_axis(lambda x: np.convolve(x, k, mode="same"), 1, m)
    return m


def save_png(arr, path):
    h, w = arr.shape[:2]
    im = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    P = np.ones((h, w, 4), np.float32)
    P[..., :3] = arr[::-1] / 255.0
    im.pixels.foreach_set(P.ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()


DE_MAX = float(opt("--de", 16))
REF = {}


def to_lab(rgb):
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def reference_skin():
    """median colour of the bare forearms of the body mesh (the surest skin on a Hellion)"""
    body = max((o for o in bpy.data.objects if o.type == "MESH" and o.vertex_groups), key=lambda o: len(o.data.vertices), default=None)
    if body is None:
        return
    im = tex_of(body)
    if im is None:
        return
    work = im.copy()
    work.scale(RES, RES)
    px = np.empty(RES * RES * work.channels, np.float32)
    work.pixels.foreach_get(px)
    bpy.data.images.remove(work)
    rgb = (np.clip(px.reshape(RES, RES, -1)[:, :, :3], 0, 1) ** (1 / 2.2) * 255)[::-1]
    reg = region_mask(body, RES, bones=("ForeArm",)) > 0.5
    Y = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    Cb = 128 - 0.168736 * rgb[..., 0] - 0.331264 * rgb[..., 1] + 0.5 * rgb[..., 2]
    Cr = 128 + 0.5 * rgb[..., 0] - 0.418688 * rgb[..., 1] - 0.081312 * rgb[..., 2]
    sel = reg & (Cr > 133) & (Cr < 178) & (Cb > 75) & (Cb < 130) & (Y > 35)
    if sel.sum() > 200:
        REF["lab"] = np.median(to_lab(rgb[sel]), 0)


def build_mask(o):
    im = tex_of(o)
    if im is None:
        return None
    work = im.copy()
    work.scale(RES, RES)
    src_px = np.empty(RES * RES * work.channels, np.float32)
    work.pixels.foreach_get(src_px)
    px = src_px.reshape(RES, RES, work.channels)[:, :, :3]
    bpy.data.images.remove(work)
    rgb = (np.clip(px, 0, 1) ** (1 / 2.2) * 255)[::-1]  # sRGB, top row first
    Y = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    Cb = 128 - 0.168736 * rgb[..., 0] - 0.331264 * rgb[..., 1] + 0.5 * rgb[..., 2]
    Cr = 128 + 0.5 * rgb[..., 0] - 0.418688 * rgb[..., 1] - 0.081312 * rgb[..., 2]
    col = ((Cr > 133) & (Cr < 178) & (Cb > 75) & (Cb < 130) & (Y > 35)).astype(np.float32)
    reg = region_mask(o, RES)
    lab = to_lab(rgb)
    ref = REF.get("lab")
    if ref is None:  # this mesh has no bare forearms: use its own most common skin-coloured colour
        sel = (col * reg) > 0.5
        ref = np.median(lab[sel], 0) if sel.any() else np.array([65.0, 15.0, 20.0])
    dE = np.sqrt(((lab - ref) ** 2 * np.array([0.35, 1.0, 1.0])).sum(-1))  # lightness matters less (shading)
    col = col * (dE < DE_MAX)
    m = (blur(col * reg, RES / 512) > 0.5).astype(np.float32)
    m = blur(m, RES / 1024)
    med = np.median(Y[m > 0.5]) if (m > 0.5).any() else 128.0
    detail = np.clip(Y / max(med, 1), 0, 2)
    return im, rgb, m, detail


load()
reference_skin()
rep = {"name": name, "reference_lab": REF.get("lab", np.zeros(3)).round(1).tolist(), "tones": {k: v.tolist() for k, v in TONES.items()}, "meshes": {}}
data = {}
for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    r = build_mask(o)
    if r is None:
        continue
    im, rgb, m, detail = r
    mk = np.zeros((RES, RES, 3), np.float32)
    mk[..., 0] = m * 255
    mk[..., 1] = np.clip(detail * 0.5, 0, 1) * 255
    save_png(mk, os.path.join(out, "%s_%s_skinmask.png" % (name, o.name)))
    data[o.name] = (rgb, m, detail)
    rep["meshes"][o.name] = {"texture": im.name, "skin_fraction": round(float(m.mean()), 4)}
for tone, col in TONES.items():
    load()
    for o in [o for o in bpy.data.objects if o.type == "MESH"]:
        if o.name not in data:
            continue
        rgb, m, detail = data[o.name]
        tint = (col * 255)[None, None, :] * detail[..., None]
        base = rgb
        if OUTFIT_TINT and not o.name.lower().startswith("head"):  # outfit palette swap on the non-skin texels (HSV)
            hd, sm, vm = OUTFIT_TINT
            c = base / 255.0
            mx, mn = c.max(-1), c.min(-1)
            v_ = mx
            s_ = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)
            rc, gc, bc_ = [(mx - c[..., i]) / np.maximum(mx - mn, 1e-9) for i in range(3)]
            h_ = (np.select([mx == c[..., 0], mx == c[..., 1]], [bc_ - gc, 2 + rc - bc_], 4 + gc - rc) / 6.0 + hd / 360.0) % 1.0
            s_ = np.clip(s_ * sm, 0, 1)
            v_ = np.clip(v_ * vm, 0, 1)
            i_ = (h_ * 6).astype(int) % 6
            f_ = h_ * 6 - np.floor(h_ * 6)
            p_, q_, t_ = v_ * (1 - s_), v_ * (1 - f_ * s_), v_ * (1 - (1 - f_) * s_)
            cand = [np.stack(x, -1) for x in ((v_, t_, p_), (q_, v_, p_), (p_, v_, t_), (p_, q_, v_), (t_, p_, v_), (v_, p_, q_))]
            out_ = np.zeros_like(c)
            for k_ in range(6):
                out_ = np.where((i_ == k_)[..., None], cand[k_], out_)
            base = out_ * 255
        outc = base * (1 - m[..., None]) + tint * m[..., None]
        lin = (np.clip(outc / 255.0, 0, 1) ** 2.2)[::-1]
        im = tex_of(o)
        im.scale(RES, RES)
        P = np.ones((RES, RES, im.channels), np.float32)
        P[..., :3] = lin
        im.pixels.foreach_set(P.ravel())
        im.pack()
    for x in bpy.data.objects:
        x.select_set(x.type in ("MESH", "ARMATURE"))
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, "%s_%s.glb" % (name, tone)), export_format="GLB", use_selection=True,
                              export_skins=True, export_animations=False)
json.dump(rep, open(os.path.join(out, "skin_tone.json"), "w"), indent=1)
print("SKINTONE_OK", json.dumps(rep))

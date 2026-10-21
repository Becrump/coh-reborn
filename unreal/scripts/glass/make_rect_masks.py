"""Offline: hand-placed pane masks for window textures whose glass can't be colour-keyed
(storefronts with posters, stone/brick facades). Glass = inside the listed rectangles (UV 0..1),
minus dark mullions (luma below 'dark') and saturated decals/signs (saturation above 'sat').
Writes masks/T_GlassMask_<texture>.png (greyscale, texture-sized, max 256) for import as a mask texture."""
import os
import numpy as np
from PIL import Image, ImageFilter

SRC = os.path.expandvars(r"%USERPROFILE%\CoHReborn\out\atlas_park\textures")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "masks")
SPEC = {  # texture: (rects [(x0, y0, x1, y1)], dark luma cut, saturation cut or None)
    "Store_Front_Stucco_1d_Window_1": ([(0.215, 0.505, 0.785, 0.795)], 0.22, None),
    "Store_Front_Window_2": ([(0.0, 0.02, 1.0, 0.365), (0.0, 0.40, 1.0, 0.965)], 0.0, 0.62),
    "Store_Front_Window_3": ([(0.0, 0.40, 1.0, 0.965)], 0.0, 0.62),
    "Store_Front_Window_4": ([(0.0, 0.02, 1.0, 0.365), (0.0, 0.40, 1.0, 0.965)], 0.0, 0.62),
    "Bld_SkyB_Base01_d": ([(0.03, 0.03, 0.485, 0.19), (0.52, 0.03, 0.97, 0.19), (0.03, 0.22, 0.485, 0.81),
                           (0.52, 0.22, 0.97, 0.81), (0.03, 0.85, 0.485, 0.97), (0.52, 0.85, 0.97, 0.97)], 0.0, None),
    "P_BrickA_StoneWindow_d": ([(0.32, 0.20, 0.435, 0.425), (0.32, 0.45, 0.435, 0.665),
                                (0.565, 0.20, 0.685, 0.425), (0.565, 0.45, 0.685, 0.665)], 0.0, None),
    "P_BrickC_Window_d": ([(0.445, 0.44, 0.595, 0.74), (0.68, 0.44, 0.83, 0.74)], 0.18, None),
    "p_warehouse_shipwindow01_b": ([(0.03, 0.12, 0.97, 0.70)], 0.2, None),
}
os.makedirs(OUT, exist_ok=True)
for name, (rects, dark, sat) in SPEC.items():
    im = Image.open(os.path.join(SRC, name + ".png")).convert("RGB")
    a = np.asarray(im, dtype=np.float32) / 255
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    u, v = (xx + 0.5) / w, (yy + 0.5) / h
    m = np.zeros((h, w), np.float32)
    for x0, y0, x1, y1 in rects:
        m[(u >= x0) & (u <= x1) & (v >= y0) & (v <= y1)] = 1
    luma = a @ np.array([0.3, 0.59, 0.11])
    if dark:
        m[luma < dark] = 0
    if sat:
        mx, mn = a.max(2), a.min(2)
        m[(mx - mn) / np.maximum(mx, 1e-3) > sat] = 0  # posters, neon, signs stay as painted
    img = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))
    if max(w, h) > 256:
        img = img.resize((256, 256), Image.BILINEAR)
    img.save(os.path.join(OUT, "T_GlassMask_%s.png" % name))
    print(name, "glass %.2f" % (np.asarray(img).mean() / 255), img.size)

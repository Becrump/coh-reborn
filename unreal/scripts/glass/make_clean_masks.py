"""Offline: turn a speckled colour-key pane mask into a clean painted mask texture.

For window textures where the glass is bluer than the wall but has white reflection streaks:
blue key (b - r, Otsu) -> keep components bigger than MIN_AREA of the image -> close gaps -> fill holes
-> cut dark mullions back out (luma below the 'dark' cut). Writes masks/T_GlassMask_<name>.png and adds
{"key": "texture"} entries to window_masks.json, like make_rect_masks.py.

  GLASS_TEX_SRC=<folder of source pngs> python make_clean_masks.py name1 name2 ...
"""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

SRC = os.environ.get("GLASS_TEX_SRC") or os.path.expandvars(r"%USERPROFILE%\CoHReborn\out\atlas_park\textures")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "masks")
MIN_AREA = 0.004
DARK = {"default": 0.06}  # linear luma below this inside the window = mullion / frame


def otsu(v):
    h, b = np.histogram(v, 256, (v.min(), v.max() + 1e-6))
    p = h / h.sum(); w = np.cumsum(p); mu = np.cumsum(p * b[:-1])
    s = (mu[-1] * w - mu) ** 2 / (w * (1 - w) + 1e-9)
    return float(b[np.argmax(s)])


os.makedirs(OUT, exist_ok=True)
table_path = os.path.join(HERE, "window_masks.json")
table = json.load(open(table_path))
for name in sys.argv[1:]:
    a = np.asarray(Image.open(os.path.join(SRC, name + ".png")).convert("RGB"), dtype=np.float32) / 255
    a = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    key = a[..., 2] - a[..., 0]
    m = key > otsu(key.ravel())
    lab, n = ndimage.label(m)
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s > MIN_AREA * m.size]
    m = np.isin(lab, keep)
    k = max(3, int(round(min(m.shape) / 40)))
    m = ndimage.binary_closing(m, structure=np.ones((k, k)), iterations=2)
    m = ndimage.binary_fill_holes(m)
    luma = a @ np.array([0.3, 0.59, 0.11])
    m &= luma > DARK.get(name, DARK["default"])
    m = ndimage.binary_opening(m, structure=np.ones((2, 2)))
    img = Image.fromarray((m * 255).astype(np.uint8))
    if max(img.size) > 256:
        img = img.resize((256, 256), Image.BILINEAR)
    out = "T_GlassMask_%s" % name
    img.save(os.path.join(OUT, out + ".png"))
    table[name] = {"key": "texture", "mask_texture": "/Game/GlassUpgrade/Masks/" + out}
    print(name, "glass %.2f" % m.mean(), "components kept", len(keep))
json.dump(table, open(table_path, "w"), indent=1)

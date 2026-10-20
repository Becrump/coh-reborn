"""Offline: pick a pane-mask key per original window texture (run with plain Python + numpy/Pillow).
Tries luma and blue-minus-red keys in linear space, Otsu threshold, keeps the cleaner one
(less speckle = fewer mask edges per pixel). Writes window_masks.json used by apply_test_overrides.py."""
import json, os, sys
import numpy as np
from PIL import Image

SRC = os.path.expandvars(r"%USERPROFILE%\CoHReborn\out\atlas_park\textures")
NAMES = sys.argv[1:] or ["deco_skyscraper_02_window_01_b", "deco_building_03_window_01_b",
                         "deco_building_03_window_03_b", "deco_building_08_window_01_b"]
# hand-checked against mask previews where Otsu splits inside the pane gradient
OVERRIDES = {
    "deco_skyscraper_02_window_01_b": dict(key="luma", MaskWeights=[0.3, 0.59, 0.11, 0], MaskThreshold=0.04,
                                           MaskSoftness=0.02, MaskInvert=0.0),  # near-black mullions
    "deco_building_03_window_01_b": dict(key="luma", MaskWeights=[0.3, 0.59, 0.11, 0], MaskThreshold=0.21,
                                         MaskSoftness=0.02, MaskInvert=1.0),  # light grey frames
}
KEYS = {"luma": (0.3, 0.59, 0.11), "blue": (-1.0, 0.0, 1.0)}


def otsu(v):
    h, b = np.histogram(v, 256, (v.min(), v.max() + 1e-6))
    p = h / h.sum(); w = np.cumsum(p); mu = np.cumsum(p * b[:-1])
    s = (mu[-1] * w - mu) ** 2 / (w * (1 - w) + 1e-9)
    return float(b[np.argmax(s)])


out = {}
for n in NAMES:
    a = np.asarray(Image.open(os.path.join(SRC, n + ".png")).convert("RGB"), dtype=np.float32) / 255
    a = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)  # the shader sees linear values
    best = None
    for key, wts in KEYS.items():
        v = a @ np.array(wts)
        t = otsu(v.ravel()); s = max(0.3 * abs(t), 0.003)
        m = np.clip((v - t) / s, 0, 1)
        inv = 0.0
        if key == "luma" and m.mean() < 0.5:  # panes are the larger class
            inv, m = 1.0, 1 - m
        speck = (np.abs(np.diff(m > 0.5, axis=0)).mean() + np.abs(np.diff(m > 0.5, axis=1)).mean())
        c = dict(key=key, MaskWeights=list(wts) + [0], MaskThreshold=round(t, 4), MaskSoftness=round(s, 4),
                 MaskInvert=inv, pane_frac=round(float(m.mean()), 2), speckle=round(float(speck), 4), mask=m)
        if best is None or c["speckle"] < best["speckle"]:
            best = c
    if n in OVERRIDES:
        o = OVERRIDES[n]
        v = a @ np.array(o["MaskWeights"][:3])
        m = np.clip((v - o["MaskThreshold"]) / o["MaskSoftness"], 0, 1)
        m = 1 - m if o["MaskInvert"] else m
        best = dict(o, pane_frac=round(float(m.mean()), 2), mask=m, manual=True)
    m = best.pop("mask")
    out[n] = best
    print(n, best)
    if os.environ.get("MASK_PREVIEW"):
        Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(os.environ["MASK_PREVIEW"], n + "_mask.png"))
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_masks.json"), "w"), indent=1)

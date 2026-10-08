"""Upscale a character's baked textures 4x and derive normal/roughness maps.

Run with a Python that has torch + spandrel (ComfyUI's embedded Python):

    python_embeded/python.exe tools/upgrade/upscale_textures.py <model.pth> <textures dir>

Every <name>.png in the folder is replaced by its 4x upscale (alpha is
resized separately so emblem cut-outs survive). Next to it are written
<name>_n.png (tangent-space normal map from fine luminance detail) and
<name>_orm.png (glTF metallicRoughness layout: G = roughness, B = metal 0).
Files already ending in _n/_orm are skipped, so reruns don't double up.
"""
import glob
import os
import sys

import numpy as np
import torch
from PIL import Image, ImageFilter
from spandrel import ModelLoader


def main(model_path, tex_dir):
    model = ModelLoader().load_from_file(model_path)
    model = model.cuda().eval() if torch.cuda.is_available() else model.eval()
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    def up(img):
        rgb = np.asarray(img.convert("RGB"), np.float32) / 255.0
        t = torch.from_numpy(rgb).permute(2, 0, 1)[None].to(dev)
        with torch.no_grad():
            o = model(t).clamp(0, 1)
        return Image.fromarray(
            (o[0].permute(1, 2, 0).cpu().numpy() * 255 + 0.5).astype(np.uint8))

    for f in sorted(glob.glob(os.path.join(tex_dir, "*.png"))):
        if f.endswith(("_n.png", "_orm.png")):
            continue
        src = Image.open(f)
        if max(src.size) >= 1024:
            print("skip (already large)", os.path.basename(f))
            continue
        big = up(src)
        if src.mode == "RGBA":
            big.putalpha(src.getchannel("A").resize(big.size, Image.LANCZOS))
        big.save(f)
        lum = big.convert("L")
        fine = np.asarray(lum.filter(ImageFilter.GaussianBlur(1.2)), np.float32)
        broad = np.asarray(lum.filter(ImageFilter.GaussianBlur(24)), np.float32)
        g = (fine - broad) / 255.0
        dx = (np.roll(g, -1, 1) - np.roll(g, 1, 1)) * 6.0
        dy = (np.roll(g, -1, 0) - np.roll(g, 1, 0)) * 6.0
        n = np.dstack([-dx, dy, np.ones_like(g)])
        n /= np.linalg.norm(n, axis=2, keepdims=True)
        Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(
            f[:-4] + "_n.png")
        L = np.asarray(lum, np.float32) / 255.0
        rough = np.clip(0.85 - 0.35 * L, 0.35, 0.95)
        orm = np.dstack([np.ones_like(rough), rough, np.zeros_like(rough)])
        Image.fromarray((orm * 255).astype(np.uint8)).save(f[:-4] + "_orm.png")
        print(os.path.basename(f), src.size, "->", big.size)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

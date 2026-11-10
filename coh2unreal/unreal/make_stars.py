"""Generates a starfield sky texture (equirectangular, tiles left-right).

    python make_stars.py <out folder> [--size 4096]

Writes stars.png: a few thousand visible stars with a realistic brightness
spread and colour (blue-white to orange), plus a faint Milky Way band.
The Unreal setup maps it onto a sky dome that fades in at night.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageFilter


def make(size, rng):
    w, h = size, size // 2
    img = np.zeros((h, w, 3), np.float32)
    # Milky Way: a tilted band of soft glow
    ys, xs = np.mgrid[0:h, 0:w]
    lon = xs / w * 2 * math.pi
    lat = (0.5 - ys / h) * math.pi
    tilt = 0.45 * np.sin(lon + 0.8)                  # band wanders in latitude
    band = np.exp(-((lat - tilt) / 0.18) ** 2)
    noise = Image.fromarray((rng.random((h // 8, w // 8)) * 255).astype(np.uint8))
    noise = noise.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6))
    band *= 0.4 + 0.6 * np.asarray(noise, np.float32) / 255
    img += band[..., None] * np.array([0.05, 0.055, 0.07])
    # stars: more near the band, power-law brightness
    n = int(w * h * 0.0016)
    sx = rng.random(n) * w
    lat_s = np.arcsin(rng.uniform(-1, 1, n))         # uniform on the sphere
    near = rng.random(n) < 0.35                       # extra stars in band
    lat_s[near] = (0.45 * np.sin(sx[near] / w * 2 * math.pi + 0.8)
                   + rng.normal(0, 0.12, near.sum()))
    sy = np.clip((0.5 - lat_s / math.pi) * h, 0, h - 1)
    mag = rng.pareto(2.2, n) * 0.08 + 0.02
    temp = rng.uniform(0, 1, n)                       # 0 blue .. 1 orange
    col = np.stack([0.75 + 0.35 * temp, 0.85 + 0.05 * temp,
                    1.1 - 0.45 * temp], 1)
    for x, y, m, c in zip(sx.astype(int), sy.astype(int), mag, col):
        v = min(m, 6.0)
        img[y, x] += c * v
        if v > 0.6:                                   # bright: small halo
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                img[(y + dy) % h, (x + dx) % w] += c * v * 0.25
    img = np.clip(img, 0, 1) ** (1 / 1.6)             # lift faint stars
    return Image.fromarray((img * 255).astype(np.uint8))


if __name__ == "__main__":
    out = sys.argv[1]
    size = int(sys.argv[sys.argv.index("--size") + 1]) \
        if "--size" in sys.argv else 4096
    make(size, np.random.default_rng(42)).save(os.path.join(out, "stars.png"))
    print("wrote", os.path.join(out, "stars.png"))

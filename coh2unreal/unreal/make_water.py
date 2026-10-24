"""Generates a seamless water-ripple normal map.

    python make_water.py <out folder> [--size 1024]

Writes water_normal.png: band-limited noise heights (FFT, so it tiles)
turned into a tangent-space normal map. Two copies panning in different
directions make the moving water surface in Unreal.
"""
import os
import sys

import numpy as np
from PIL import Image


def make(size, rng):
    f = np.fft.fft2(rng.standard_normal((size, size)))
    fy = np.fft.fftfreq(size)[:, None] * size
    fx = np.fft.fftfreq(size)[None, :] * size
    k = np.sqrt(fx * fx + fy * fy)
    # ripples: a band of wavelengths, slightly stretched along one axis
    shape = np.exp(-((k - 18) / 10) ** 2) + 0.35 * np.exp(-((k - 45) / 18) ** 2)
    h = np.real(np.fft.ifft2(f * shape * np.exp(-(fy / (k + 1e-6)) ** 2 * 0.3)))
    h = (h - h.min()) / np.ptp(h)
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 4.0
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 4.0
    n = np.stack([-dx, dy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8))


if __name__ == "__main__":
    out = sys.argv[1]
    size = int(sys.argv[sys.argv.index("--size") + 1]) \
        if "--size" in sys.argv else 1024
    make(size, np.random.default_rng(7)).save(
        os.path.join(out, "water_normal.png"))
    print("wrote", os.path.join(out, "water_normal.png"))

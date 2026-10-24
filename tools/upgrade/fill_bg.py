"""Prepare a concept image for planar projection onto a generated mesh.

    python tools/upgrade/fill_bg.py <concept.png> <out_filled.png> <out_bbox.json> [mask.png]

Finds the object (pixels that are saturated or dark against the plain studio
background), writes its bounding box, and replaces every background pixel
with the colour of the nearest object pixel. Mesh areas the projection maps
just outside the silhouette (finger sides, the back of a head) then pick up
the neighbouring colour instead of the pale studio grey.
"""
import json
import sys

import numpy as np
from PIL import Image
from scipy import ndimage


def main(src, out_png, out_json, mask_png=None):
    im = Image.open(src).convert("RGB")
    rgb = np.asarray(im, np.uint8)
    hsv = np.asarray(im.convert("HSV"), np.float32) / 255.0
    # background colour from the image border (plain studio grey); white or
    # pale objects (skull faces, surgical caps) differ from it in brightness
    # rather than saturation, so test the colour distance as well
    f = rgb.astype(np.float32)
    h, w = f.shape[:2]
    # the studio backdrop is a soft gradient: fit a smooth (quadratic)
    # background to the border pixels and measure distance from that
    yy, xx = np.mgrid[0:h, 0:w]
    edge = np.zeros((h, w), bool)
    edge[:8], edge[-8:], edge[:, :8], edge[:, -8:] = True, True, True, True
    X, Y = xx / w, yy / h

    def basis(x, y):
        return np.stack([np.ones_like(x), x, y, x * x, y * y, x * y], -1)
    A = basis(X[edge], Y[edge])
    coef, *_ = np.linalg.lstsq(A, f[edge], rcond=None)
    bg = basis(X, Y) @ coef
    dist = np.sqrt(((f - bg) ** 2).sum(2))
    # pale objects are brighter than the backdrop; the soft floor shadow is
    # darker and unsaturated, so only count brighter-than-background pixels
    brighter = f.mean(2) - bg.mean(2) > 12
    obj = ((hsv[..., 1] > 0.15) | (hsv[..., 2] < 0.3)
           | ((dist > 28) & brighter) | (dist > 55))
    if mask_png:
        # a proper matte (tools/upgrade/matte.py, BRIA RMBG) beats colour
        # thresholds for pale objects and floor shadows
        obj = np.asarray(Image.open(mask_png).convert("L")) > 127
    # drop specks and the soft floor shadow: keep the largest blob
    obj = ndimage.binary_opening(obj, iterations=2)
    lab, n = ndimage.label(obj)
    if n:
        sizes = ndimage.sum(obj, lab, range(1, n + 1))
        obj = lab == (int(np.argmax(sizes)) + 1)
    obj = ndimage.binary_fill_holes(obj)
    # bounding box from rows/columns with real coverage, so a faint floor
    # shadow or a thin wisp touching the edge doesn't stretch it
    cols = np.where(obj.sum(0) > 0.04 * obj.sum(0).max())[0]
    rows = np.where(obj.sum(1) > 0.04 * obj.sum(1).max())[0]
    box = {"x0": int(cols.min()), "x1": int(cols.max()), "y0": int(rows.min()),
           "y1": int(rows.max()), "w": im.width, "h": im.height}
    # nearest object pixel for every background pixel
    _, (iy, ix) = ndimage.distance_transform_edt(~obj, return_indices=True)
    filled = rgb[iy, ix]
    Image.fromarray(filled).save(out_png)
    with open(out_json, "w") as f:
        json.dump(box, f)
    print("bbox", box, "object px", int(obj.sum()))


if __name__ == "__main__":
    main(*sys.argv[1:5])

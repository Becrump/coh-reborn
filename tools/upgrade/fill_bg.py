"""Prepare a concept image for planar projection onto a generated mesh.

    python tools/upgrade/fill_bg.py <concept.png> <out_filled.png> <out_bbox.json>

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


def main(src, out_png, out_json):
    im = Image.open(src).convert("RGB")
    rgb = np.asarray(im, np.uint8)
    hsv = np.asarray(im.convert("HSV"), np.float32) / 255.0
    obj = (hsv[..., 1] > 0.15) | (hsv[..., 2] < 0.3)
    # drop specks and the soft floor shadow: keep the largest blob
    obj = ndimage.binary_opening(obj, iterations=2)
    lab, n = ndimage.label(obj)
    if n:
        sizes = ndimage.sum(obj, lab, range(1, n + 1))
        obj = lab == (int(np.argmax(sizes)) + 1)
    obj = ndimage.binary_fill_holes(obj)
    ys, xs = np.where(obj)
    box = {"x0": int(xs.min()), "x1": int(xs.max()), "y0": int(ys.min()),
           "y1": int(ys.max()), "w": im.width, "h": im.height}
    # nearest object pixel for every background pixel
    _, (iy, ix) = ndimage.distance_transform_edt(~obj, return_indices=True)
    filled = rgb[iy, ix]
    Image.fromarray(filled).save(out_png)
    with open(out_json, "w") as f:
        json.dump(box, f)
    print("bbox", box, "object px", int(obj.sum()))


if __name__ == "__main__":
    main(*sys.argv[1:4])

import bpy, numpy as np, sys, os
d = sys.argv[sys.argv.index("--") + 1]
for n in ["matid_top", "z_top", "z_bottom"]:
    im = bpy.data.images.load(os.path.join(d, n + ".exr"))
    w, h = im.size
    a = np.empty(w * h * 4, np.float32); im.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)[::-1]  # top row first
    np.save(os.path.join(d, n + ".npy"), a[..., [0, 3]])
    print(n, w, h, a[..., 0].min(), a[..., 0].max())

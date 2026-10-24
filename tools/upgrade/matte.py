"""Cut a concept image out of its studio background with BRIA RMBG.

Run with ComfyUI's embedded Python (it has rembg + onnxruntime):

    python_embeded/python.exe tools/upgrade/matte.py <rmbg model dir> <concept.png> <out_mask.png>

<rmbg model dir> holds bria-rmbg.onnx (ComfyUI/models/rembg/models/bria-rmbg).
Writes an 8-bit mask (255 = object). fill_bg.py uses it when present, which
handles pale objects and floor shadows far better than colour thresholds.
"""
import os
import sys

from PIL import Image


def main(model_dir, src, out):
    os.environ["U2NET_HOME"] = model_dir
    from rembg import new_session, remove
    session = new_session("bria-rmbg")
    mask = remove(Image.open(src).convert("RGB"), session=session,
                  only_mask=True)
    mask.convert("L").save(out)
    print("mask", out)


if __name__ == "__main__":
    main(*sys.argv[1:4])

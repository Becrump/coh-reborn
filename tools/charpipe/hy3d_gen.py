"""Hunyuan3D-2 shape / texture step for charpipe (runs inside the hy3d venv).

    <hy3d>/venv/Scripts/python.exe hy3d_gen.py shape   --out shape.glb --front f.png [--left l --back b --right r]
    <hy3d>/venv/Scripts/python.exe hy3d_gen.py texture --mesh shape.glb --front f.png --out textured.glb

shape: 1 image -> Hunyuan3D-2mini, 2+ views -> Hunyuan3D-2mv (fp16, FlashVDM decoding when available),
       floaters/degenerate faces removed, reduced to --faces.
texture: Hunyuan3D-Paint v2.0 turbo with CPU offload (fits 8 GB), front image as reference.
Writes <out>.json (timings, peak VRAM). Exit code 0 = ok.
"""
import argparse
import json
import time

import torch
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=["shape", "texture"])
ap.add_argument("--out", required=True)
ap.add_argument("--mesh")
for v in ("front", "left", "back", "right"):
    ap.add_argument("--" + v)
ap.add_argument("--steps", type=int, default=30)
ap.add_argument("--octree", type=int, default=380)
ap.add_argument("--faces", type=int, default=40000)
ap.add_argument("--seed", type=int, default=12345)
a = ap.parse_args()
t0 = time.time()
log = {"mode": a.mode}
torch.cuda.reset_peak_memory_stats()

from hy3dgen.rembg import BackgroundRemover  # noqa: E402

rem = BackgroundRemover()
views = {v: rem(Image.open(getattr(a, v)).convert("RGB")) for v in ("front", "left", "back", "right") if getattr(a, v)}

if a.mode == "shape":
    from hy3dgen.shapegen import (DegenerateFaceRemover, FaceReducer, FloaterRemover,  # noqa: E402
                                  Hunyuan3DDiTFlowMatchingPipeline)
    multi = len(views) > 1
    repo, sub = ("tencent/Hunyuan3D-2mv", "hunyuan3d-dit-v2-mv") if multi else ("tencent/Hunyuan3D-2mini", "hunyuan3d-dit-v2-mini")
    log["model"] = repo + "/" + sub
    pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(repo, subfolder=sub, variant="fp16")
    try:
        pipe.enable_flashvdm()
        log["flashvdm"] = True
    except Exception as e:  # noqa: BLE001
        log["flashvdm"] = str(e)[:120]
    mesh = pipe(image=views if multi else views["front"], num_inference_steps=a.steps, octree_resolution=a.octree,
                num_chunks=20000, generator=torch.manual_seed(a.seed), output_type="trimesh")[0]
    mesh = FloaterRemover()(mesh)
    mesh = DegenerateFaceRemover()(mesh)
    mesh = FaceReducer()(mesh, max_facenum=a.faces)
    log["faces"] = int(len(mesh.faces))
else:
    import trimesh  # noqa: E402
    from hy3dgen.texgen import Hunyuan3DPaintPipeline  # noqa: E402
    mesh = trimesh.load(a.mesh, force="mesh")
    paint = Hunyuan3DPaintPipeline.from_pretrained("tencent/Hunyuan3D-2", subfolder="hunyuan3d-paint-v2-0-turbo")
    paint.enable_model_cpu_offload()
    mesh = paint(mesh, image=views["front"])
mesh.export(a.out)
log["seconds"] = round(time.time() - t0, 1)
log["peak_vram_gb"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
json.dump(log, open(a.out + ".json", "w"), indent=1)
print("HY3D_OK", json.dumps(log))

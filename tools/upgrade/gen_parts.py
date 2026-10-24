"""Generate a replacement costume piece (head, hand, ...) from a text prompt.

    python tools/upgrade/gen_parts.py <name> "<prompt>" <out_dir> [--seed N]

Uses the local ComfyUI (started on 127.0.0.1:8188 if it isn't running, and
stopped again afterwards so the GPU is free for Unreal):
1. Z-Image Turbo draws a concept image (workflows/zimage_concept.json).
2. Trellis2 (GGUF, low VRAM) turns it into a mesh
   (workflows/trellis2_image_to_3d.json).
3. matte.py cuts the concept out of its backdrop (BRIA RMBG) and
   fill_bg.py prepares it for projection.

Writes <out_dir>/<name>_concept.png, <name>.glb, <name>_filled.png,
<name>_bbox.json and <name>_gen.json (timings and checks). Trellis2's own
texture is ignored (it is often noise on 8 GB GPUs); fit_parts.py projects
the concept image instead.

Paths come from tools/upgrade/config.json (see config.example.json).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "http://127.0.0.1:8188"


def cfg():
    p = os.path.join(HERE, "config.json")
    if not os.path.exists(p):
        p = os.path.join(HERE, "config.example.json")
    with open(p) as f:
        return json.load(f)


def up():
    try:
        urllib.request.urlopen(URL + "/system_stats", timeout=2)
        return True
    except Exception:
        return False


def start_comfy(c):
    root = c["comfyui_root"]
    log = open(os.path.join(root, "gen_parts_comfy.log"), "w")
    p = subprocess.Popen([c["comfyui_python"], "-I", "-W",
                          "ignore::FutureWarning", "ComfyUI/main.py",
                          "--windows-standalone-build", "--listen",
                          "127.0.0.1", "--port", "8188",
                          "--disable-auto-launch"],
                         cwd=root, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(180):
        if up():
            return p
        time.sleep(2)
    p.kill()
    raise RuntimeError("ComfyUI did not start (see gen_parts_comfy.log)")


def submit(prompt):
    data = json.dumps({"prompt": prompt, "client_id": str(uuid.uuid4())})
    req = urllib.request.Request(URL + "/prompt", data.encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))["prompt_id"]


def wait(pid, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = json.load(urllib.request.urlopen(URL + "/history/" + pid))
        if pid in h:
            st = h[pid]["status"]
            if st.get("status_str") != "success":
                raise RuntimeError("ComfyUI job failed: %s" % st)
            return h[pid]["outputs"]
        time.sleep(3)
    raise RuntimeError("ComfyUI job timed out")


def newest(folder, prefix, ext):
    hits = [f for f in os.listdir(folder)
            if f.startswith(prefix) and f.endswith(ext)]
    if not hits:
        raise RuntimeError("no %s*%s in %s" % (prefix, ext, folder))
    return os.path.join(folder, max(
        hits, key=lambda f: os.path.getmtime(os.path.join(folder, f))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("prompt")
    ap.add_argument("out_dir")
    ap.add_argument("--seed", type=int, default=20261007)
    a = ap.parse_args()
    c = cfg()
    os.makedirs(a.out_dir, exist_ok=True)
    comfy_out = os.path.join(c["comfyui_root"], "ComfyUI", "output")
    comfy_in = os.path.join(c["comfyui_root"], "ComfyUI", "input")
    prefix = "cohup_%s_%d" % (a.name, int(time.time()))
    report = {"name": a.name, "prompt": a.prompt, "seed": a.seed,
              "checks": []}
    proc = None if up() else start_comfy(c)
    try:
        t0 = time.time()
        z = json.load(open(os.path.join(HERE, "workflows",
                                        "zimage_concept.json")))
        z["57:27"]["inputs"]["text"] = a.prompt
        z["57:3"]["inputs"]["seed"] = a.seed
        z["9"]["inputs"]["filename_prefix"] = prefix
        wait(submit(z), 900)
        concept = newest(comfy_out, prefix, ".png")
        shutil.copy(concept, os.path.join(a.out_dir, a.name + "_concept.png"))
        shutil.copy(concept, os.path.join(comfy_in, prefix + ".png"))
        report["concept_seconds"] = round(time.time() - t0)

        t0 = time.time()
        t = json.load(open(os.path.join(HERE, "workflows",
                                        "trellis2_image_to_3d.json")))
        t["13"]["inputs"]["image"] = prefix + ".png"
        t["35"]["inputs"]["value"] = prefix
        wait(submit(t), 3600)
        glb = newest(comfy_out, prefix + "_Textured", ".glb")
        shutil.copy(glb, os.path.join(a.out_dir, a.name + ".glb"))
        report["mesh_seconds"] = round(time.time() - t0)
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(30)
            except Exception:
                proc.kill()
    size = os.path.getsize(os.path.join(a.out_dir, a.name + ".glb"))
    report["checks"].append({"name": "mesh_written", "ok": size > 100000,
                             "bytes": size})
    concept = os.path.join(a.out_dir, a.name + "_concept.png")
    mask = os.path.join(a.out_dir, a.name + "_mask.png")
    # cut the concept out of its backdrop (BRIA RMBG via ComfyUI's Python)
    if c.get("rmbg_model_dir"):
        subprocess.call([c["comfyui_python"], os.path.join(HERE, "matte.py"),
                         c["rmbg_model_dir"], concept, mask])
    subprocess.check_call([sys.executable, os.path.join(HERE, "fill_bg.py"),
                           concept,
                           os.path.join(a.out_dir, a.name + "_filled.png"),
                           os.path.join(a.out_dir, a.name + "_bbox.json")]
                          + ([mask] if os.path.exists(mask) else []))
    box = json.load(open(os.path.join(a.out_dir, a.name + "_bbox.json")))
    fill = (box["x1"] - box["x0"]) * (box["y1"] - box["y0"]) / \
        float(box["w"] * box["h"])
    report["checks"].append({"name": "object_found_in_concept",
                             "ok": 0.05 < fill < 0.95,
                             "bbox_fraction": round(fill, 3)})
    report["ok"] = all(x["ok"] for x in report["checks"])
    with open(os.path.join(a.out_dir, a.name + "_gen.json"), "w") as f:
        json.dump(report, f, indent=1)
    print("GEN_DONE", a.name, "ok=%s" % report["ok"])


if __name__ == "__main__":
    main()

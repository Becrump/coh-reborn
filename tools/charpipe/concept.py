"""Local concept art for charpipe: Z-Image Turbo (Q4 GGUF, Apache-2.0) in a headless ComfyUI.

    python tools/charpipe/concept.py <in_dir>/<name> "<prompt>" [--seed N] [--wait]

Writes <in_dir>/<name>/front.png (1024x1024, full body, front, plain background) for charpipe.
Starts the ComfyUI from 3D Gen Studio headless on 127.0.0.1:8189 with --lowvram and its
GGUF nodes, runs the graph, and stops it again so the GPU is free for Hunyuan3D. The same GPU
guard as charpipe applies (Unreal running / GPU_HOLD.txt / low VRAM -> wait or exit).
Models (download once: C:/Users/rtcru/hy3d/dl_zimage.py): z_image_turbo-Q4_K_M.gguf,
Qwen3-4B-Q4_K_M.gguf, ae.safetensors in 3DGenStudio/comfy-data/models.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charpipe as CP  # noqa: E402

STUDIO = "C:/Users/rtcru/AppData/Roaming/3DGenStudio"
PY = STUDIO + "/comfy-venv/Scripts/python.exe"
MAIN = STUDIO + "/comfyui/main.py"
MODELS = STUDIO + "/comfy-data/models"
URL = "http://127.0.0.1:8189"
STYLE = (", full body character, standing in a relaxed A-pose, arms slightly away from the body, front view facing the camera, "
         "whole figure from head to boots visible, symmetrical, plain light grey background, studio lighting, "
         "realistic modern video game character, highly detailed")


PORTRAIT = (", head and neck portrait, front view facing the camera, neutral expression, symmetrical, whole head and neck visible, "
            "plain light grey background, studio lighting, realistic modern video game character, highly detailed face")


VIEWS = {
    "body": STYLE,
    "portrait": PORTRAIT,
    "arm": (", a single right arm only, isolated, hanging straight down: shoulder at the top of the image, clenched fist at "
            "the bottom, seen from the front, no torso, no head, plain light grey background, studio lighting, realistic modern "
            "video game asset, highly detailed"),
    "prop": (", a single isolated object only, product shot, centred, whole object visible, plain light grey background, "
             "studio lighting, realistic modern video game prop, highly detailed"),
    "legs": (", lower body only from the waist down, both legs slightly apart, standing straight, seen from the front, "
             "no torso, no arms, plain light grey background, studio lighting, realistic modern video game asset, highly detailed"),
}


def graph(prompt, seed, prefix, style=STYLE):
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "z_image_turbo-Q4_K_M.gguf"}},
        "2": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": "Qwen3-4B-Q4_K_M.gguf", "type": "lumina2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt + style}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
                                                   "latent_image": ["7", 0], "seed": seed, "steps": 8, "cfg": 1.0,
                                                   "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


YAML = ("charpipe:\n  base_path: %s\n  diffusion_models: diffusion_models\n  unet: diffusion_models\n"
        "  text_encoders: text_encoders\n  clip: text_encoders\n  vae: vae\n")


def call(path, body=None):
    r = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as x:
        return json.loads(x.read() or b"{}")


def main():
    if "--jobs" in sys.argv:
        return batch(sys.argv[sys.argv.index("--jobs") + 1])
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cdir, prompt = args[0], args[1]
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 20261114
    out = os.path.dirname(os.path.abspath(cdir))
    name = os.path.basename(os.path.abspath(cdir))
    os.makedirs(cdir, exist_ok=True)
    cfg = CP.load_cfg(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    CP.gpu_guard(cfg, 5000, "--wait" in sys.argv, out, name, "concept")
    yml = os.path.join(os.path.dirname(MAIN), "extra_model_paths_charpipe.yaml")
    open(yml, "w").write("charpipe:\n  base_path: %s\n  diffusion_models: diffusion_models\n  unet: diffusion_models\n"
                         "  text_encoders: text_encoders\n  clip: text_encoders\n  vae: vae\n" % MODELS)
    outdir = os.path.join(out, "_comfy_out")
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")  # ComfyUI prints emoji; cp1252 crashes it
    proc = subprocess.Popen([PY, MAIN, "--listen", "127.0.0.1", "--port", "8189", "--lowvram", "--disable-auto-launch",
                             "--extra-model-paths-config", yml, "--output-directory", outdir],
                            stdout=open(os.path.join(out, "comfy_concept.log"), "w"), stderr=subprocess.STDOUT,
                            cwd=os.path.dirname(MAIN), env=env)
    try:
        for _ in range(180):
            try:
                call("/system_stats")
                break
            except Exception:  # noqa: BLE001
                time.sleep(2)
        else:
            raise SystemExit("ComfyUI did not start (see comfy_concept.log)")
        style = PORTRAIT if "--portrait" in sys.argv else STYLE
        pid = call("/prompt", {"prompt": graph(prompt, seed, "charpipe_" + name, style)})["prompt_id"]
        while True:
            h = call("/history/" + pid)
            if pid in h:
                st = h[pid].get("status", {})
                if st.get("status_str") == "error":
                    raise SystemExit("ComfyUI error: %s" % json.dumps(st)[:400])
                imgs = [i for o in h[pid]["outputs"].values() for i in o.get("images", [])]
                if imgs:
                    src = os.path.join(outdir, imgs[0].get("subfolder", ""), imgs[0]["filename"])
                    os.replace(src, os.path.join(cdir, "front.png"))
                    break
            time.sleep(2)
        CP.log(out, name, "concept", "OK", "%.0fs Z-Image Turbo Q4, seed %d" % (time.time() - t0, seed))
        open(os.path.join(cdir, "prompt.txt"), "w").write(prompt + (PORTRAIT if "--portrait" in sys.argv else STYLE) + "\nseed %d\n" % seed)
    finally:
        proc.terminate()
        try:
            proc.wait(30)
        except Exception:  # noqa: BLE001
            proc.kill()


def batch(jobs_path):
    """--jobs jobs.json: [{"dir": ..., "prompt": ..., "view": body|portrait|arm|legs, "seed": N, "name": "front"}], one ComfyUI session."""
    jobs = json.load(open(jobs_path))
    out = os.path.dirname(os.path.abspath(jobs_path))
    cfg = CP.load_cfg(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    CP.gpu_guard(cfg, 5000, "--wait" in sys.argv, out, "concepts", "concept")
    yml = os.path.join(os.path.dirname(MAIN), "extra_model_paths_charpipe.yaml")
    open(yml, "w").write(YAML % MODELS)
    outdir = os.path.join(out, "_comfy_out")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    proc = subprocess.Popen([PY, MAIN, "--listen", "127.0.0.1", "--port", "8189", "--lowvram", "--disable-auto-launch",
                             "--extra-model-paths-config", yml, "--output-directory", outdir],
                            stdout=open(os.path.join(out, "comfy_concept.log"), "w"), stderr=subprocess.STDOUT,
                            cwd=os.path.dirname(MAIN), env=env)
    try:
        for _ in range(180):
            try:
                call("/system_stats")
                break
            except Exception:  # noqa: BLE001
                time.sleep(2)
        for j in jobs:
            t0 = time.time()
            os.makedirs(j["dir"], exist_ok=True)
            style = VIEWS[j.get("view", "body")]
            pid = call("/prompt", {"prompt": graph(j["prompt"], j.get("seed", 20261114), "cp", style)})["prompt_id"]
            while True:
                h = call("/history/" + pid)
                if pid in h:
                    if h[pid].get("status", {}).get("status_str") == "error":
                        raise SystemExit("ComfyUI error on %s" % j["dir"])
                    imgs = [i for o in h[pid]["outputs"].values() for i in o.get("images", [])]
                    if imgs:
                        os.replace(os.path.join(outdir, imgs[0].get("subfolder", ""), imgs[0]["filename"]),
                                   os.path.join(j["dir"], j.get("name", "front") + ".png"))
                        break
                time.sleep(2)
            open(os.path.join(j["dir"], j.get("name", "front") + "_prompt.txt"), "w").write(j["prompt"] + style + "\nseed %d\n" % j.get("seed", 20261114))
            CP.log(out, os.path.basename(j["dir"]), "concept", "OK", "%.0fs %s view, seed %d" % (time.time() - t0, j.get("view", "body"), j.get("seed", 20261114)))
    finally:
        proc.terminate()
        try:
            proc.wait(30)
        except Exception:  # noqa: BLE001
            proc.kill()


if __name__ == "__main__":
    main()

"""charpipe: reference images -> textured, rigged, CoH-animatable character (local, unattended).

    python tools/charpipe/charpipe.py <in_dir> <out_dir> [--only NAME] [--parts] [--wait] [--redo STEP]
                                      [--height 1.8] [--config tools/charpipe/config.json]

<in_dir>/<character>/ holds the reference images: front.png (required) and optionally left.png,
back.png, right.png (orthographic, character facing the camera in front.png; T-pose works best).
Any single image in the folder is used as the front view. Optional <character>/height.txt (metres).

Steps per character (each skipped when its output exists, so reruns resume):
  shape    Hunyuan3D-2mini (1 view) / 2mv (2+ views)          GPU  (hy3d venv)
  texture  Hunyuan3D-Paint v2.0 turbo, CPU offload             GPU  (hy3d venv)
  rig      fit the shared 24-bone skeleton + heat weights      CPU  (Blender)
  clean    rig_cleanup: scale, facing, ground, weight fixes    CPU  (Blender)
  export   FBX for Unreal (+ part slots with --parts)          CPU  (Blender)
  preview  CoH idle / run / Brawl retargeted, 4 PNGs          GPU-light (Blender EEVEE)
GPU guard: before a GPU step, if UnrealEditor*.exe is running or nvidia-smi reports less free
VRAM than the step needs, the run exits with a message, or with --wait polls every few minutes.
It never closes the editor. Log: <out_dir>/charpipe_log.txt (one line per step: OK / FAIL / SKIP).
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CFG = {
    "blender": "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe",
    "hy3d_python": "C:/Users/rtcru/hy3d/venv/Scripts/python.exe",
    "coh_clip_character": "C:/Users/rtcru/CoHReborn/out/characters/hellions/Thug_Hellion_01/Thug_Hellion_01.gltf",
    "coh_brawl_chunk": "C:/Users/rtcru/CoHReborn/out/player/anims/male/male_anims_01.gltf",
    "gpu_free_mb_shape": 6000,
    "gpu_free_mb_texture": 6000,
    "gpu_free_mb_preview": 1500,
    "wait_poll_s": 180,
    "faces": 40000,
}
VIEWS = ("front", "left", "back", "right")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


class Fail(Exception):
    pass


def load_cfg(path):
    cfg = dict(DEFAULT_CFG)
    if path and os.path.exists(path):
        cfg.update(json.load(open(path)))
    return cfg


def log(out, char, step, status, msg=""):
    line = "%s  %-14s %-8s %-4s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), char, step, status, msg)
    print(line, flush=True)
    with open(os.path.join(out, "charpipe_log.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ------------------------------------------------------------------ GPU guard
def unreal_running():
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001
        return []
    names = []
    for row in csv.reader(io.StringIO(r.stdout)):
        if row and row[0].lower().startswith("unrealeditor"):
            names.append(row[0])
    return sorted(set(names))


def gpu_free_mb():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=30)
        return int(r.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return -1


def gpu_guard(cfg, need_mb, wait, out, char, step):
    while True:
        ue = unreal_running()
        free = gpu_free_mb()
        if not ue and (free < 0 or free >= need_mb):
            return
        why = ("Unreal is running (%s)" % ", ".join(ue)) if ue else "only %d MB VRAM free, need %d" % (free, need_mb)
        if not wait:
            log(out, char, step, "WAIT", why + " - not starting GPU work. Rerun later or add --wait. The editor is never closed.")
            raise SystemExit(3)
        log(out, char, step, "WAIT", why + "; checking again in %ds" % cfg["wait_poll_s"])
        time.sleep(cfg["wait_poll_s"])


# ------------------------------------------------------------------ steps
def run(cmd, logfile, ok_token):
    with open(logfile, "w", encoding="utf-8", errors="replace") as f:
        p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    text = open(logfile, encoding="utf-8", errors="replace").read()
    if p.returncode != 0 or ok_token not in text:
        tail = [ln for ln in text.splitlines() if ln.strip()][-3:]
        raise Fail("exit %s: %s" % (p.returncode, " | ".join(t[:160] for t in tail)))
    for ln in text.splitlines():
        if ok_token in ln:
            return ln.split(ok_token, 1)[1].strip()[:300]
    return ""


def find_views(cdir):
    imgs = [f for f in sorted(os.listdir(cdir)) if f.lower().endswith(IMG_EXT)]
    views = {}
    for v in VIEWS:
        m = [f for f in imgs if os.path.splitext(f)[0].lower() == v]
        if m:
            views[v] = os.path.join(cdir, m[0])
    if "front" not in views and imgs:
        views["front"] = os.path.join(cdir, imgs[0])
    return views


def process(char, cdir, odir, cfg, a):
    os.makedirs(odir, exist_ok=True)
    os.makedirs(os.path.join(odir, "logs"), exist_ok=True)
    L = lambda s: os.path.join(odir, "logs", s + ".log")  # noqa: E731
    views = find_views(cdir)
    if "front" not in views:
        log(a.out, char, "input", "FAIL", "no image in " + cdir)
        return False
    hfile = os.path.join(cdir, "height.txt")
    height = float(open(hfile).read().strip()) if os.path.exists(hfile) else a.height
    vargs = sum((["--" + v, p] for v, p in views.items()), [])
    B = [cfg["blender"], "-b", "--factory-startup", "--python"]
    shape, tex = os.path.join(odir, "shape.glb"), os.path.join(odir, "textured.glb")
    raw, rig = os.path.join(odir, "rigged_raw.glb"), os.path.join(odir, char + ".glb")
    steps = [
        ("shape", shape, cfg["gpu_free_mb_shape"],
         lambda: run([cfg["hy3d_python"], os.path.join(HERE, "hy3d_gen.py"), "shape", "--out", shape,
                      "--faces", str(cfg["faces"])] + vargs, L("shape"), "HY3D_OK")),
        ("texture", tex, cfg["gpu_free_mb_texture"],
         lambda: run([cfg["hy3d_python"], os.path.join(HERE, "hy3d_gen.py"), "texture", "--mesh", shape, "--out", tex,
                      "--front", views["front"]], L("texture"), "HY3D_OK")),
        ("rig", raw, 0,
         lambda: run(B + [os.path.join(HERE, "bl_autorig.py"), "--", tex, raw, "--height", str(height),
                          "--report", os.path.join(odir, "autorig.json")], L("rig"), "AUTORIG")),
        ("clean", rig, 0,
         lambda: run(B + [os.path.join(HERE, "rig_cleanup.py"), "--", raw, rig, "--report",
                          os.path.join(odir, "cleanup.json")], L("clean"), "CLEANUP")),
        ("export", os.path.join(odir, char + ".fbx"), 0,
         lambda: run(B + [os.path.join(HERE, "bl_export.py"), "--", rig, odir, char] + (["--parts"] if a.parts else []),
                     L("export"), "EXPORT_OK")),
        ("preview", os.path.join(odir, "preview", "preview_brawl.png"), cfg["gpu_free_mb_preview"],
         lambda: run(B + [os.path.join(HERE, "bl_preview.py"), "--", rig, os.path.join(odir, "preview"), "--coh",
                          cfg["coh_clip_character"], "--brawl", cfg["coh_brawl_chunk"]], L("preview"), "PREVIEW_OK")),
    ]
    names = [s[0] for s in steps]
    if a.redo:
        for s in steps[names.index(a.redo):]:
            if os.path.exists(s[1]):
                os.remove(s[1])
    if a.parts and not os.path.isdir(os.path.join(odir, "parts")):
        p = os.path.join(odir, char + ".fbx")
        if os.path.exists(p):
            os.remove(p)
    for step, target, need, fn in steps:
        if os.path.exists(target):
            log(a.out, char, step, "SKIP", "done earlier")
            continue
        if need:
            gpu_guard(cfg, need, a.wait, a.out, char, step)
        t0 = time.time()
        try:
            info = fn()
        except Fail as e:
            log(a.out, char, step, "FAIL", "%.0fs %s (see %s)" % (time.time() - t0, e, L(step)))
            return False
        log(a.out, char, step, "OK", "%.0fs %s" % (time.time() - t0, info[:200]))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--only")
    ap.add_argument("--parts", action="store_true")
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--redo", choices=["shape", "texture", "rig", "clean", "export", "preview"])
    ap.add_argument("--height", type=float, default=1.8)
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    a = ap.parse_args()
    cfg = load_cfg(a.config)
    os.makedirs(a.out, exist_ok=True)
    for k in ("blender", "hy3d_python"):
        if not os.path.exists(cfg[k]):
            sys.exit("missing %s: %s (see docs/character-pipeline.md)" % (k, cfg[k]))
    chars = sorted(d for d in os.listdir(a.inp) if os.path.isdir(os.path.join(a.inp, d)))
    if a.only:
        chars = [c for c in chars if c == a.only]
    ok = 0
    for c in chars:
        if process(c, os.path.join(a.inp, c), os.path.join(a.out, c), cfg, a):
            ok += 1
            log(a.out, c, "ALL", "OK")
        else:
            log(a.out, c, "ALL", "FAIL")
    log(a.out, "-", "summary", "OK" if ok == len(chars) else "FAIL", "%d/%d characters done" % (ok, len(chars)))
    sys.exit(0 if ok == len(chars) else 1)


if __name__ == "__main__":
    main()

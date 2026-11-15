"""Watch the Tripo drop folder and turn every new download into a rigged, tested, Unreal-ready character.

    python tools/charpipe/tripo_watch.py            (process what is new, then keep watching; Ctrl+C to stop)
    python tools/charpipe/tripo_watch.py --once     (process what is new and exit)

Folder: C:/Users/rtcru/charpipe_test/tripo/in/  (drop .glb / .gltf / .fbx / .obj from the Tripo website or bridge)
Per new file (name = character name; height and headless come from the name, see bl_tripo_clean.py:
kid/lean 172, veteran 178, average 180, heavy/brawler 183, big/biker 193, default 182; "headless"):
  clean (weld, floaters, normals, 50k tris, 2K textures, size) -> proxy head if headless -> autorig
  -> rig_cleanup -> fingers (smooth knuckles) -> weight polish -> FBX -> CoH clip test renders
Output: tripo/work/<name>/ (all steps + reports), tripo/ue_ready/<name>.fbx, tripo/ue_ready/previews/<name>.jpg
(idle front/side/back, run, Brawl, hit, death, extreme pose, fist). Log: tripo/watch_log.txt.
Skips files already processed (same size + mtime, in tripo/watch_state.json) and files still being
written (changed in the last 20 s). Waits while CPU_HOLD.txt or GPU_HOLD.txt exists in the project folder.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "C:/Users/rtcru/charpipe_test/tripo"
IN, WORK, UE = ROOT + "/in", ROOT + "/work", ROOT + "/ue_ready"
HOLDS = ["C:/Users/rtcru/ClaudeProjects/COHReborn/CPU_HOLD.txt", "C:/Users/rtcru/ClaudeProjects/COHReborn/GPU_HOLD.txt"]
BLENDER = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
RENDER = "C:/Users/rtcru/ClaudeProjects/COHReborn/model-upgrade-samples/scripts/rig_test_render.py"
RENDERS = "C:/Users/rtcru/ClaudeProjects/COHReborn/model-upgrade-samples/renders"
EXTS = (".glb", ".gltf", ".fbx", ".obj")
BUILDS = [("kid", 172), ("lean", 172), ("veteran", 178), ("average", 180), ("heavy", 183), ("brawler", 183), ("big", 193), ("biker", 193)]


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)
    with open(ROOT + "/watch_log.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def editor_running():
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq UnrealEditor.exe", "/NH"], capture_output=True, text=True)
        return "UnrealEditor.exe" in r.stdout
    except Exception:  # noqa: BLE001
        return False


def hold_wait():
    # yield to hold files and to the shared Unreal editor (its GPU/RAM use comes first)
    while any(os.path.exists(h) for h in HOLDS) or editor_running():
        log("hold file present or Unreal editor running, waiting")
        time.sleep(60)


def bl(script, *args):
    hold_wait()
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = [l for l in r.stdout.splitlines() if any(k in l for k in ("_OK", "AUTORIG", "FINGERS", "CLEANUP", "RT_OK"))]
    err = [l for l in (r.stdout + r.stderr).splitlines() if "Error" in l or "Traceback" in l]
    if err and not ok:
        raise RuntimeError("%s: %s" % (os.path.basename(script), err[-1][:200]))
    return ok


def process(src):
    base = os.path.splitext(os.path.basename(src))[0]
    low = base.lower()
    hcm = next((h for k, h in BUILDS if k in low), 182)
    headless = "headless" in low
    w = os.path.join(WORK, base).replace("\\", "/")
    os.makedirs(w, exist_ok=True)
    t0 = time.time()
    s = lambda n: os.path.join(HERE, n)  # noqa: E731
    bl(s("bl_tripo_clean.py"), src, w + "/clean.glb", "--height-cm", str(hcm), *(["--headless"] if headless else []), "--report", w + "/clean.json")
    rig_in, cut = w + "/clean.glb", None
    if headless:
        bl(s("bl_proxy_head.py"), rig_in, w + "/proxy.glb", "--height-cm", str(hcm), "--report", w + "/proxy.json")
        rig_in, cut = w + "/proxy.glb", json.load(open(w + "/proxy.json"))["cut_above"]
    bl(s("bl_autorig.py"), rig_in, w + "/rig_raw.glb", "--height", str(hcm / 100.0), "--report", w + "/autorig.json")
    bl(s("rig_cleanup.py"), w + "/rig_raw.glb", w + "/rig_clean.glb", "--report", w + "/cleanup.json")
    bl(s("bl_fingers.py"), w + "/rig_clean.glb", w + "/fingers.glb", "--report", w + "/fingers.json")
    bl(s("bl_weight_polish.py"), w + "/fingers.glb", w + "/" + base + ".glb", *(["--cut-above", str(cut)] if cut else []), "--report", w + "/polish.json")
    bl(s("bl_export.py"), w + "/" + base + ".glb", UE, base)
    prev = ""
    if os.path.exists(RENDER):
        try:
            bl(RENDER, w + "/" + base + ".glb", base)
            from PIL import Image
            views = ["idle_front", "idle_side", "idle_back", "run", "brawl", "hit", "death", "extreme", "fist"]
            sheet = Image.new("RGB", (9 * 240, 360))
            for i, v in enumerate(views):
                p = "%s/RT_%s_%s.png" % (RENDERS, base, v)
                if os.path.exists(p):
                    sheet.paste(Image.open(p).convert("RGB").resize((240, 360)), (i * 240, 0))
            os.makedirs(UE + "/previews", exist_ok=True)
            prev = UE + "/previews/" + base + ".jpg"
            sheet.save(prev, quality=86)
        except Exception as e:  # noqa: BLE001  previews are optional
            log("  preview failed for %s: %s" % (base, e))
    c = json.load(open(w + "/clean.json"))
    log("OK %s: %d -> %d tris, %d cm%s, %.0f s -> %s/%s.fbx %s" % (base, c["in_tris"], c["out_tris"], hcm,
        " headless" if headless else "", time.time() - t0, UE, base, ("preview " + prev) if prev else ""))


def scan(state):
    done = 0
    for f in sorted(os.listdir(IN)):
        if not f.lower().endswith(EXTS):
            continue
        p = os.path.join(IN, f).replace("\\", "/")
        st = os.stat(p)
        sig = "%d:%d" % (st.st_size, int(st.st_mtime))
        if state.get(f) == sig or time.time() - st.st_mtime < 20:
            continue
        log("NEW %s" % f)
        try:
            process(p)
            state[f] = sig
        except Exception as e:  # noqa: BLE001
            log("FAIL %s: %s" % (f, e))
            state[f] = sig + ":failed"
        json.dump(state, open(ROOT + "/watch_state.json", "w"), indent=1)
        done += 1
    return done


def main():
    for d in (IN, WORK, UE):
        os.makedirs(d, exist_ok=True)
    sp = ROOT + "/watch_state.json"
    state = json.load(open(sp)) if os.path.exists(sp) else {}
    n = scan(state)
    if "--once" in sys.argv:
        log("once: %d file(s) processed" % n)
        return
    log("watching %s (Ctrl+C to stop)" % IN)
    while True:
        time.sleep(30)
        scan(state)


if __name__ == "__main__":
    main()

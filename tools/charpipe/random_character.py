"""Random character assembler: outfit body + library head + skin tone + outfit tint + socket gear (main route).

    python tools/charpipe/random_character.py <library.json> <out_dir> --count 8 [--seed 7] [--render]

library.json:
  {"bodies":  {"name": {"file": "rigged.glb", "headless": true}},      # one Tripo export per outfit, clothes baked in
   "heads":   {"name": "head.glb"},                                    # head library (head + neck, any scale)
   "tones":   {"light": [0.86,0.67,0.56], "medium": [...], "dark": [...]},
   "tints":   [[0,1,1], [20,1.1,1.0], [180,0.6,0.9]],                  # outfit palette swaps: hue_deg, sat_mul, val_mul
   "gear":    {"name": {"file": "gear.glb|fbx", "slot": "head|face|neck|hand_r|belt"}},
   "gear_chance": 0.6}
Per character (all steps are the existing charpipe tools, run headless in Blender):
  headless body -> bl_head_swap.py (random head) -> bl_skin_tone.py (one tone + one outfit tint)
  -> bl_gear_item.py per chosen gear item, fitted to THIS body (max one per slot)
  -> optional preview render (CoH idle front, face, Brawl) via rig_test_render.py
Writes <out_dir>/<id>/character.glb + gear_*.glb + recipe.json, and <out_dir>/recipes.json.
Waits while CPU_HOLD.txt / GPU_HOLD.txt exist.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
RENDER = "C:/Users/rtcru/ClaudeProjects/COHReborn/model-upgrade-samples/scripts/rig_test_render.py"
HOLDS = ["C:/Users/rtcru/ClaudeProjects/COHReborn/CPU_HOLD.txt", "C:/Users/rtcru/ClaudeProjects/COHReborn/GPU_HOLD.txt"]


def bl(script, *args, env=None):
    while any(os.path.exists(h) for h in HOLDS):
        print("hold file present, waiting", flush=True)
        time.sleep(60)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    tail = [l for l in (r.stdout + chr(10) + r.stderr).splitlines() if "_OK" in l or "Error" in l or "Traceback" in l]
    if not any("_OK" in l for l in tail) and any("Error" in l or "Traceback" in l for l in tail):
        raise RuntimeError("%s: %s" % (os.path.basename(script), tail[-1][:200]))
    return tail


def main():
    lib = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d  # noqa: E731
    n = int(arg("--count", 8))
    rng = random.Random(int(arg("--seed", 7)))
    os.makedirs(out, exist_ok=True)
    recipes = []
    for i in range(n):
        cid = "hellion_%02d" % (i + 1)
        d = os.path.join(out, cid)
        os.makedirs(d, exist_ok=True)
        bname = rng.choice(sorted(lib["bodies"]))
        body = lib["bodies"][bname]
        head = rng.choice(sorted(lib["heads"])) if body.get("headless") else None
        tone = rng.choice(sorted(lib["tones"]))
        tint = rng.choice(lib.get("tints", [[0, 1, 1]]))
        gear, used = [], set()
        for g in rng.sample(sorted(lib.get("gear", {})), len(lib.get("gear", {}))):
            slot = lib["gear"][g]["slot"]
            if slot in used or rng.random() > lib.get("gear_chance", 0.6):
                continue
            if head is None and slot in ("head", "face") and not body.get("allow_headgear", True):
                continue
            used.add(slot)
            gear.append(g)
        rec = {"id": cid, "body": bname, "head": head, "tone": tone, "outfit_tint": tint, "gear": gear}
        step = os.path.join(d, "with_head.glb")
        if head:
            bl(os.path.join(HERE, "bl_head_swap.py"), body["file"], lib["heads"][head], step)
        else:
            shutil.copy(body["file"], step)
        col = ",".join(str(x) for x in lib["tones"][tone])
        bl(os.path.join(HERE, "bl_skin_tone.py"), step, d, "char", "--tones", "%s=%s" % (tone, col), "--res", "1024",
           "--outfit-tint", "%g:%g:%g" % tuple(tint))
        final = os.path.join(d, "character.glb")
        os.replace(os.path.join(d, "char_%s.glb" % tone), final)
        gear_files = []
        for g in gear:
            gi = lib["gear"][g]
            bl(os.path.join(HERE, "bl_gear_item.py"), final, gi["file"], d, "--name", "gear_" + g, "--slot", gi["slot"])
            gear_files.append(os.path.join(d, gi["slot"], "gear_%s.glb" % g))
        rec["files"] = {"character": final, "gear": gear_files}
        json.dump(rec, open(os.path.join(d, "recipe.json"), "w"), indent=1)
        if "--render" in sys.argv and os.path.exists(RENDER):
            env = dict(os.environ, RT_QUICK="1")
            bl(RENDER, final, "rnd_" + cid, *gear_files, env=env)
        print("CHARACTER_OK", json.dumps(rec), flush=True)
        recipes.append(rec)
        json.dump(recipes, open(os.path.join(out, "recipes.json"), "w"), indent=1)


if __name__ == "__main__":
    main()

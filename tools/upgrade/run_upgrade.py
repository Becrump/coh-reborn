"""Upgrade exported CoH characters: one command per batch, with checks.

    python tools/upgrade/run_upgrade.py tools/upgrade/jobs/<batch>.json [--only NAME] [--stages ...]

A batch file:
{
  "characters_dir": "C:/Users/rtcru/CoHReborn/out/characters",
  "work_dir": "C:/Users/rtcru/CoHReborn/out/upgrade",
  "parts": {                                   # generated once, shared
    "hellion_boss_head": {"prompt": "...", "seed": 20261007},
    "hellion_glove":     {"prompt": "...", "is_right_hand": true}
  },
  "characters": [
    {"costume": "Thug_Hellion_Boss_01",
     "head": "hellion_boss_head", "hand": "hellion_glove",
     "unreal": {"dest": "/Game/Upgraded/Hellions/Thug_Hellion_Boss_01",
                "label": "Hellion_Boss_01_Upgraded",
                "place": [1500, 11000, 925, 180], "folder": "Upgraded/Hellions"}}
  ]
}

Stages (all by default, in order): upscale, smooth, parts, fit, unreal.
"head"/"hand" are optional; without them a character only gets the
upscale + smooth pass. New hands are only fitted when the batch sets
"fit_hands": true (off by default: the original hands are kept). Each stage skips work whose output already exists
(delete the folder to redo it).

Writes <work_dir>/summary.json: per character, each stage's status and
every automatic check. A reviewer only needs to look at characters with
"needs_review": true and their check renders in <work>/<costume>/checks/.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def cfg():
    p = os.path.join(HERE, "config.json")
    if not os.path.exists(p):
        p = os.path.join(HERE, "config.example.json")
    with open(p) as f:
        return json.load(f)


def run(cmd, log):
    t0 = time.time()
    with open(log, "a") as f:
        f.write("\n$ %s\n" % " ".join(cmd))
        f.flush()
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    return r.returncode, round(time.time() - t0, 1)


def find_gltf(chars_dir, costume):
    hits = glob.glob(os.path.join(chars_dir, "*", costume, costume + ".gltf"))
    if not hits:
        raise FileNotFoundError("no exported glTF for %s" % costume)
    return hits[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--stages", nargs="*",
                    default=["upscale", "smooth", "parts", "fit", "unreal"])
    a = ap.parse_args()
    c = cfg()
    B = json.load(open(a.batch))
    work = B["work_dir"]
    os.makedirs(work, exist_ok=True)
    parts_dir = os.path.join(work, "_parts")
    log = os.path.join(work, "run.log")
    summary_path = os.path.join(work, "summary.json")
    summary = json.load(open(summary_path)) if os.path.exists(
        summary_path) else {}

    # ---- shared generated parts
    if "parts" in a.stages:
        for name, p in B.get("parts", {}).items():
            if not B.get("fit_hands") and "is_right_hand" in p:
                continue                    # hand part not needed
            if os.path.exists(os.path.join(parts_dir, name + ".glb")):
                continue
            code, secs = run([sys.executable, os.path.join(HERE, "gen_parts.py"),
                              name, p["prompt"], parts_dir,
                              "--seed", str(p.get("seed", 20261007))], log)
            print("part", name, "exit", code, "%ss" % secs)

    ue_items = []
    for ch in B["characters"]:
        name = ch["costume"]
        if a.only and name not in a.only:
            continue
        cw = os.path.join(work, name)
        st = summary.setdefault(name, {"stages": {}, "checks": []})
        src = find_gltf(B["characters_dir"], name)
        up = os.path.join(cw, "upscaled")
        if "upscale" in a.stages and not os.path.exists(up):
            shutil.copytree(os.path.dirname(src), up)
            code, secs = run([c["comfyui_python"],
                              os.path.join(HERE, "upscale_textures.py"),
                              c["upscale_model"], os.path.join(up, "textures")],
                             log)
            st["stages"]["upscale"] = {"exit": code, "seconds": secs}
        smooth = os.path.join(cw, "smooth", name + ".gltf")
        if "smooth" in a.stages and not os.path.exists(smooth):
            os.makedirs(os.path.dirname(smooth), exist_ok=True)
            code, secs = run([c["blender"], "-b", "--factory-startup",
                              "--python", os.path.join(HERE, "smooth_mesh.py"),
                              "--", os.path.join(up, name + ".gltf"),
                              os.path.join(up, "textures"), smooth], log)
            st["stages"]["smooth"] = {"exit": code, "seconds": secs,
                                      "ok": os.path.exists(smooth)}
        final = smooth
        if ch.get("head") or ch.get("hand"):
            fitted = os.path.join(cw, "fitted", name + ".gltf")
            if "fit" in a.stages and not os.path.exists(fitted):
                job = {"base_gltf": smooth, "out_gltf": fitted,
                       "check_dir": os.path.join(cw, "checks")}
                for kind in ("head", "hand"):
                    pn = ch.get(kind)
                    # new hands are off for now (Robert: heads only); the
                    # original hands stay, upscaled and smoothed
                    if not pn or (kind == "hand" and not B.get("fit_hands")):
                        continue
                    pdef = B["parts"][pn]
                    job[kind] = {
                        "glb": os.path.join(parts_dir, pn + ".glb"),
                        "image": os.path.join(parts_dir, pn + "_filled.png"),
                        "bbox": os.path.join(parts_dir, pn + "_bbox.json")}
                    job[kind].update({k: v for k, v in pdef.items()
                                      if k not in ("prompt", "seed")})
                os.makedirs(os.path.dirname(fitted), exist_ok=True)
                jp = os.path.join(cw, "fit_job.json")
                json.dump(job, open(jp, "w"), indent=1)
                code, secs = run([c["blender"], "-b", "--factory-startup",
                                  "--python", os.path.join(HERE, "fit_parts.py"),
                                  "--", jp], log)
                rep = os.path.join(cw, "checks", "report.json")
                checks = json.load(open(rep))["checks"] if os.path.exists(
                    rep) else [{"name": "fit_ran", "ok": False}]
                st["stages"]["fit"] = {"exit": code, "seconds": secs}
                st["checks"] = checks
            final = fitted
        st["final_gltf"] = final
        st["needs_review"] = (not os.path.exists(final)) or any(
            not x["ok"] for x in st["checks"]) or any(
            s.get("exit", 0) != 0 for s in st["stages"].values())
        if "unreal" in a.stages and ch.get("unreal") and os.path.exists(final):
            it = dict(ch["unreal"])
            it["gltf"] = final.replace("\\", "/")
            ue_items.append(it)
        json.dump(summary, open(summary_path, "w"), indent=1)

    if ue_items:
        wrapper = os.path.join(work, "ue_job.py")
        with open(wrapper, "w") as f:
            f.write("JOB = %r\n" % {"items": ue_items, "save_level": True})
            f.write("exec(open(%r).read())\n" %
                    os.path.join(HERE, "ue_import.py").replace("\\", "/"))
        ue_exec = c["ue_exec"] if os.path.isabs(c["ue_exec"]) else \
            os.path.join(REPO, c["ue_exec"])
        out = subprocess.run([sys.executable, ue_exec, wrapper, "--file",
                              "--timeout", "1800"], capture_output=True,
                             text=True)
        line = next((l for l in out.stdout.splitlines()
                     if l.startswith("UE_RESULT ")), None)
        res = json.loads(line[10:]) if line else []
        for r in res:
            for name, st in summary.items():
                if st.get("final_gltf", "").replace("\\", "/") in \
                        [i["gltf"] for i in ue_items if i["label"] == r["label"]]:
                    st["stages"]["unreal"] = r
                    st["needs_review"] = st["needs_review"] or not r["ok"]
        if not line:
            print(out.stdout[-2000:], out.stderr[-2000:])
        json.dump(summary, open(summary_path, "w"), indent=1)

    bad = [n for n, s in summary.items() if s.get("needs_review")]
    print("SUMMARY %d characters, %d need review: %s" %
          (len(summary), len(bad), ", ".join(bad) or "none"))
    print("details:", summary_path)


if __name__ == "__main__":
    main()

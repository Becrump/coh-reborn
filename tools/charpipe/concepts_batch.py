"""Batch concept art for charpipe: Gemini (paid, hard-capped) or local Z-Image (free).

    python tools/charpipe/concepts_batch.py <jobs.json> <out_dir> --provider gemini --cap-images N [--cap-usd X] [--dry-run]
    python tools/charpipe/concepts_batch.py <jobs.json> <out_dir> --provider local [--wait]

jobs.json: [{"name": "hellions_b2_o1", "line": "<character line>", "views": ["headless", "left", "back", "right"]}, ...]
Each job writes <out_dir>/<name>/front.png (+ headless.png, left.png, back.png, right.png).

Gemini (model gemini-2.5-flash-image via the Generative Language REST API):
  * key read from C:/Users/rtcru/.gemini_key (never printed or logged)
  * one chat per character: style block + character line with the style reference
    (full hellion1.jpg) and the A-pose reference attached, then each follow-up view in the same chat
  * --cap-images N is REQUIRED: the run stops before the image that would exceed N (all jobs
    together, persisted in <out_dir>/gemini_state.json, so reruns resume without paying twice);
    --cap-usd adds a money cap at the listed ~$0.039 per image
  * --dry-run prints the plan without calling the API
Local: the same jobs through concept.py (Z-Image Turbo in the headless ComfyUI, GPU guard applies);
only the front view is generated (Z-Image has no multi-turn consistency), as a draft to compare.
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = "C:/Users/rtcru/.gemini_key"
MODEL = "gemini-2.5-flash-image"
API = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % MODEL
USD_PER_IMAGE = 0.039
STYLE_REF = "C:/Users/rtcru/Downloads/full hellion1.jpg"
POSE_REF = "C:/Users/rtcru/ClaudeProjects/COHReborn/model-upgrade-samples/gemini_refs/hellions/nogear/hellions_minion_01_front.png"
STYLE = ("Use the attached images as references: the first for the rendering style, the second for the exact pose. "
         "Create a NEW character in exactly this style: photoreal modern video game character render (Unreal Engine 5 quality), "
         "full body from the top of the head to the soles of the boots, front view facing the camera, straight-on camera at chest "
         "height. Pose: the standard MetaHuman bind A-pose, both upper arms lowered about 52 degrees below horizontal, elbows almost "
         "straight, palms facing down and slightly inward toward the thighs, fingers relaxed and not touching the body, legs straight "
         "and slightly apart. Bare face, no headwear, masks, bandanas, goggles, helmets or face coverings; hair visible. No weapons or "
         "held items, empty hands. Keep all clothing, gloves and boots. Plain flat mid-grey background, soft even studio lighting, "
         "no text, no watermark, realistic adult proportions. The character: ")
FOLLOW = {
    "headless": "Now the exact same character, same pose, clothing and lighting, but without the head: a clean neck stump at the collar, nothing above the neck.",
    "left": "Now the exact same character seen from its left side (camera rotated 90 degrees), same A-pose, clothing and lighting, same framing and height.",
    "back": "Now the exact same character from behind (back view), same A-pose, clothing and lighting, same framing and height.",
    "right": "Now the exact same character seen from its right side (camera rotated 90 degrees the other way), same A-pose, clothing and lighting, same framing and height.",
}


def arg(k, d=None):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d


def img_part(path):
    mt = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    return {"inline_data": {"mime_type": mt, "data": base64.b64encode(open(path, "rb").read()).decode()}}


def gemini_call(contents):
    key = open(KEY_FILE, encoding="utf-8-sig").read().strip()
    body = json.dumps({"contents": contents, "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Content-Type": "application/json", "x-goog-api-key": key, "User-Agent": "charpipe/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit("Gemini HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:300]))
    parts = out["candidates"][0]["content"]["parts"]
    imgs = [p for p in parts if "inline_data" in p or "inlineData" in p]
    if not imgs:
        raise SystemExit("Gemini returned no image: %s" % json.dumps(parts)[:300])
    d = imgs[0].get("inline_data") or imgs[0].get("inlineData")
    return parts, base64.b64decode(d["data"])


def run_gemini(jobs, out):
    cap = arg("--cap-images")
    if cap is None:
        raise SystemExit("--cap-images N is required for the paid Gemini path.")
    cap = int(cap)
    cap_usd = float(arg("--cap-usd", 1e9))
    sp = os.path.join(out, "gemini_state.json")
    st = json.load(open(sp)) if os.path.exists(sp) else {"images": 0, "done": []}
    plan = [(j["name"], v) for j in jobs for v in ["front"] + j.get("views", [])]
    todo = [p for p in plan if "%s/%s" % p not in st["done"]]
    print("plan: %d images (%d already done), cap %d images / $%.2f, spent so far %d images ~$%.2f"
          % (len(plan), len(plan) - len(todo), cap, cap_usd, st["images"], st["images"] * USD_PER_IMAGE))
    if "--dry-run" in sys.argv:
        for n, v in todo:
            print("  would generate", n, v)
        return
    if not os.path.exists(KEY_FILE):
        raise SystemExit("No key file at %s." % KEY_FILE)
    for j in jobs:
        d = os.path.join(out, j["name"])
        os.makedirs(d, exist_ok=True)
        contents = [{"role": "user", "parts": [img_part(STYLE_REF), img_part(POSE_REF), {"text": STYLE + j["line"]}]}]
        for v in ["front"] + j.get("views", []):
            if v != "front":
                contents.append({"role": "user", "parts": [{"text": FOLLOW[v]}]})
            key_ = "%s/%s" % (j["name"], v)
            path = os.path.join(d, v + ".png")
            if key_ in st["done"] and os.path.exists(path):
                contents.append({"role": "model", "parts": [img_part(path)]})
                continue
            if st["images"] + 1 > cap or (st["images"] + 1) * USD_PER_IMAGE > cap_usd:
                json.dump(st, open(sp, "w"), indent=1)
                raise SystemExit("Cap reached at %d images (~$%.2f). Stopping before %s." % (st["images"], st["images"] * USD_PER_IMAGE, key_))
            parts, png = gemini_call(contents)
            open(path, "wb").write(png)
            st["images"] += 1
            st["done"].append(key_)
            json.dump(st, open(sp, "w"), indent=1)
            print("  %s ok (%d images, ~$%.2f)" % (key_, st["images"], st["images"] * USD_PER_IMAGE), flush=True)
            contents.append({"role": "model", "parts": [img_part(path)]})
    print("GEMINI_DONE %d images ~$%.2f" % (st["images"], st["images"] * USD_PER_IMAGE))


def run_local(jobs, out):
    lj = [{"dir": os.path.join(out, j["name"]), "prompt": j["line"], "view": "apose_headless" if "headless" in j.get("views", []) else "body",
           "seed": 20261115 + i, "name": "front"} for i, j in enumerate(jobs)]
    os.makedirs(out, exist_ok=True)
    jp = os.path.join(out, "local_jobs.json")
    json.dump(lj, open(jp, "w"), indent=1)
    cmd = [sys.executable, os.path.join(HERE, "concept.py"), "--jobs", jp] + (["--wait"] if "--wait" in sys.argv else [])
    raise SystemExit(subprocess.call(cmd))


def main():
    jobs = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    prov = arg("--provider", "local")
    (run_gemini if prov == "gemini" else run_local)(jobs, out)


if __name__ == "__main__":
    main()

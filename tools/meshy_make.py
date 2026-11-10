"""Generates rigged, animated characters with the Meshy API.

    python meshy_make.py <batch.json> [--dry-run]

batch.json:
{
  "out": "C:/Users/me/CoHReborn/meshy",
  "defaults": {"height_m": 1.78, "polycount": 40000},
  "animations": {"from": "hellion_biker", "action_ids": [243, 89, ...]},
  "characters": [{"name": "hellion_biker", "prompt": "...", "height_m": 1.8}, ...]
}

For each character: text-to-3D preview -> PBR texture -> auto rig; then the
animation set on the "from" character's rig (one merged FBX). Downloads go to
<out>/<name>/. Progress is kept in <out>/<batch>_state.json, so a re-run
resumes and never pays twice for a finished step. The API key is read from
~/.meshy_key and never printed.
"""
import json
import os
import sys
import time
import urllib.request

API = "https://api.meshy.ai/openapi"


def key():
    return open(os.path.expanduser("~/.meshy_key"),
                encoding="utf-8-sig").read().strip()


def call(method, path, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + key(),
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def wait(path, label):
    last = None
    while True:
        t = call("GET", path)
        st, pr = t.get("status"), t.get("progress")
        if (st, pr) != last:
            print("  %s: %s %s%%" % (label, st, pr), flush=True)
            last = (st, pr)
        if st == "SUCCEEDED":
            return t
        if st in ("FAILED", "CANCELED", "EXPIRED"):
            raise RuntimeError("%s %s: %s" % (label, st, t.get("task_error")))
        time.sleep(10)


def urls(obj, prefix=""):
    """Every *_url string in a task response, flattened with its key path."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v.startswith("http"):
                out[prefix + k] = v
            elif isinstance(v, (dict, list)):
                out.update(urls(v, prefix + k + "."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(urls(v, prefix + str(i) + "."))
    return out


def download(url, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with urllib.request.urlopen(url, timeout=600) as r, open(path, "wb") as f:
        f.write(r.read())
    print("  saved", path, flush=True)


def ext_of(url):
    base = url.split("?")[0].rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[-1] if "." in base else "bin"


def main():
    batch_path = sys.argv[1]
    dry = "--dry-run" in sys.argv
    cfg = json.load(open(batch_path))
    out = cfg["out"]
    os.makedirs(out, exist_ok=True)
    state_path = os.path.join(out, os.path.splitext(
        os.path.basename(batch_path))[0] + "_state.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}

    def save():
        json.dump(state, open(state_path, "w"), indent=1)

    d = cfg.get("defaults", {})
    for ch in cfg["characters"]:
        name = ch["name"]
        s = state.setdefault(name, {})
        print("==", name, flush=True)
        if dry:
            print("  would generate:", ch["prompt"][:80])
            continue
        if "preview" not in s:
            s["preview"] = call("POST", "/v2/text-to-3d", {
                "mode": "preview", "prompt": ch["prompt"],
                "ai_model": "latest", "pose_mode": "t-pose",
                "should_remesh": True, "topology": "triangle",
                "target_polycount": ch.get("polycount", d.get("polycount",
                                                               40000)),
            })["result"]
            save()
        wait("/v2/text-to-3d/" + s["preview"], "shape")
        if "refine" not in s:
            s["refine"] = call("POST", "/v2/text-to-3d", {
                "mode": "refine", "preview_task_id": s["preview"],
                "enable_pbr": True, "texture_resolution": "2k",
            })["result"]
            save()
        t = wait("/v2/text-to-3d/" + s["refine"], "texture")
        if not s.get("textured_saved"):
            for k, u in urls(t).items():
                if k.startswith(("model_urls.", "texture_urls.")) and \
                        not k.endswith("thumbnail_url"):
                    download(u, os.path.join(out, name, "textured",
                                             k.replace(".", "_") + "." +
                                             ext_of(u)))
            s["textured_saved"] = True
            save()
        if "rig" not in s:
            s["rig"] = call("POST", "/v1/rigging", {
                "input_task_id": s["refine"],
                "height_meters": ch.get("height_m", d.get("height_m", 1.78)),
            })["result"]
            save()
        t = wait("/v1/rigging/" + s["rig"], "rig")
        if not s.get("rig_saved"):
            for k, u in urls(t).items():
                if "rigged_character" in k or "basic_animations" in k:
                    download(u, os.path.join(out, name, "rig",
                                             k.split(".")[-1].replace(
                                                 "_url", "") + "." +
                                             ext_of(u)))
            s["rig_saved"] = True
            save()
    anim = cfg.get("animations")
    if anim and not dry:
        src = anim["from"]
        a = state.setdefault("_animations", {})
        print("== animations on", src, flush=True)
        if "task" not in a:
            a["task"] = call("POST", "/v1/animations", {
                "rig_task_id": state[src]["rig"],
                "action_ids": anim["action_ids"],
            })["result"]
            save()
        t = wait("/v1/animations/" + a["task"], "animations")
        if not a.get("saved"):
            for k, u in urls(t).items():
                if "animation" in k and k.endswith(("fbx_url", "glb_url")):
                    download(u, os.path.join(out, src, "anims",
                                             k.split(".")[-1].replace(
                                                 "_url", "") + "." +
                                             ext_of(u)))
            a["saved"] = True
            save()
    print("done", flush=True)


if __name__ == "__main__":
    main()

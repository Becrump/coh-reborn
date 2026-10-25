"""Downloads Meshy animations (one GLB per action) for a rigged Meshy character.

    python tools/meshy_anims.py <state.json> <character> <out dir> <action_id> [<action_id> ...] [--dry-run]

state.json is a meshy_make.py state file: <character>["rig"] is the rig task. Each action is
one /v1/animations task (paid); the task ids go to <out dir>/anims_state.json so a re-run
never pays twice. The API key is read from ~/.meshy_key and never printed.
The Climbing set of the library (animation_library.json): 434-440, 444-449, hanging 482 / 486.
"""
import json
import os
import sys
import time
import urllib.request

API = "https://api.meshy.ai/openapi"


def key():
    return open(os.path.expanduser("~/.meshy_key"), encoding="utf-8-sig").read().strip()


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + key(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def balance():
    return call("GET", "/v1/balance")["balance"]


def walk(o, prefix=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, prefix + k + ".")
    elif isinstance(o, str) and o.startswith("http"):
        yield prefix.rstrip("."), o


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    state_file, char, out = args[0], args[1], args[2]
    ids = [int(a) for a in args[3:]]
    rig = json.load(open(state_file))[char]["rig"]
    os.makedirs(out, exist_ok=True)
    sp = os.path.join(out, "anims_state.json")
    st = json.load(open(sp)) if os.path.exists(sp) else {}
    lib = {a["action_id"]: a for a in json.load(open(os.path.join(os.path.dirname(os.path.abspath(state_file)), "animation_library.json")))}
    print("credits:", balance())
    for i in ids:
        name = lib[i]["key"]
        print("==", i, name)
        if dry:
            continue
        if os.path.exists(os.path.join(out, name + ".glb")) and os.path.exists(os.path.join(out, name + ".fbx")):
            print("  have it")
            continue
        if str(i) not in st:
            st[str(i)] = call("POST", "/v1/animations", {"rig_task_id": rig, "action_id": i})["result"]
            json.dump(st, open(sp, "w"), indent=1)
        task = st[str(i)]
        last = None
        while True:
            t = call("GET", "/v1/animations/" + task)
            if t.get("status") == "SUCCEEDED":
                break
            if t.get("status") in ("FAILED", "CANCELED"):
                print("  failed:", t.get("task_error"))
                break
            if t.get("status") != last:
                print("  ", t.get("status"), t.get("progress"), flush=True)
                last = t.get("status")
            time.sleep(4)
        if t.get("status") == "SUCCEEDED":
            for suffix, ext in (("animation_glb_url", ".glb"), ("animation_fbx_url", ".fbx")):
                url = next((u for k, u in walk(t) if k.endswith(suffix)), None)
                if url:
                    with urllib.request.urlopen(url, timeout=300) as r, open(os.path.join(out, name + ext), "wb") as f:
                        f.write(r.read())
                    print("  saved", name + ext)
    print("credits left:", balance())


main()

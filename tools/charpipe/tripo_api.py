"""Tripo3D API client for charpipe (developer platform credits, separate from the website plan).

    python tools/charpipe/tripo_api.py balance
    python tools/charpipe/tripo_api.py gen <image> <out_dir> --cap N [--dry-run]
    python tools/charpipe/tripo_api.py batch <concepts_dir> --cap N [--out C:/Users/rtcru/charpipe_test/tripo/in] [--dry-run]

API v2 (https://api.tripo3d.ai/v2/openapi; the key does not work on v3). A User-Agent header is
required (Cloudflare rejects bare urllib with 403 / error 1010).
Key: C:/Users/rtcru/.tripo_key (read only, never printed or logged).
gen/batch: image_to_model with texture + PBR, no auto-rig (charpipe rigs onto the shared skeleton);
the textured GLB is downloaded as <name>.glb.
batch: every <concepts_dir>/<name>/headless.png (preferred: faces come from MetaHuman) or front.png,
or loose <concepts_dir>/*.png -> <out>/<name>.glb, ready for tripo_rig.sh.
Spending rules:
  * --cap N (credits) is REQUIRED for paid commands. Before each task the run checks
    spent + estimate <= cap and that the live balance covers the estimate; it stops otherwise.
  * Real cost = balance before - balance after each task (logged), persisted in
    <out>/tripo_state.json with the task ids, so a rerun resumes and never pays twice.
  * --dry-run lists what would be sent and spends nothing. Log: <out>/tripo_batch_log.txt
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "https://api.tripo3d.ai/v2/openapi"
KEY_FILE = os.path.expanduser("~/.tripo_key")
UA = "charpipe/1.0 (+local pipeline)"
EST = 40  # conservative credits per textured image_to_model task (checked against the real balance delta)


def key():
    if not os.path.exists(KEY_FILE):
        raise SystemExit("No API key file at %s." % KEY_FILE)
    return open(KEY_FILE, encoding="utf-8-sig").read().strip()


def call(method, path, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(API + path, method=method, data=data, headers={
        "Authorization": "Bearer " + key(), "Content-Type": ctype, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit("%s %s -> HTTP %s: %s" % (method, path, e.code, e.read().decode(errors="replace")[:300]))
    if out.get("code") not in (0, None):
        raise SystemExit("%s %s -> code %s: %s" % (method, path, out.get("code"), json.dumps(out)[:300]))
    return out.get("data", out)


def balance():
    d = call("GET", "/user/balance")
    return float(d.get("balance", 0)), float(d.get("frozen", 0))


def upload(path):
    b = "----charpipe" + uuid.uuid4().hex
    name = os.path.basename(path)
    ctype = "image/png" if name.lower().endswith(".png") else "image/jpeg"
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
             % (b, name, ctype)).encode() + open(path, "rb").read() + ("\r\n--%s--\r\n" % b).encode())
    return call("POST", "/upload", raw=body, ctype="multipart/form-data; boundary=" + b)["image_token"]


def wait(task_id, label):
    last = None
    while True:
        t = call("GET", "/task/" + task_id)
        st, pr = t.get("status"), t.get("progress")
        if (st, pr) != last:
            print("  %s: %s %s%%" % (label, st, pr), flush=True)
            last = (st, pr)
        if st == "success":
            return t
        if st in ("failed", "cancelled", "banned", "expired", "unknown"):
            raise RuntimeError("%s %s" % (label, st))
        time.sleep(8)


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as r, open(path, "wb") as f:
        f.write(r.read())


class State:
    def __init__(self, out):
        os.makedirs(out, exist_ok=True)
        self.out = out
        self.path = os.path.join(out, "tripo_state.json")
        self.d = json.load(open(self.path)) if os.path.exists(self.path) else {"tasks": {}, "spent": 0.0}

    def save(self):
        json.dump(self.d, open(self.path, "w"), indent=1)

    def log(self, msg):
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
        print(line, flush=True)
        open(os.path.join(self.out, "tripo_batch_log.txt"), "a", encoding="utf-8").write(line + "\n")


def gen_one(st, name, img, cap):
    t = st.d["tasks"].get(name)
    dst = os.path.join(st.out, name + ".glb")
    if t and t.get("status") == "success" and os.path.exists(dst):
        st.log("SKIP %s (already done)" % name)
        return
    if not t or t.get("status") == "failed":
        if st.d["spent"] + EST > cap:
            raise SystemExit("Credit cap: spent %.0f + ~%d > cap %d. Stopping before %s." % (st.d["spent"], EST, cap, name))
        bal, _ = balance()
        if bal < EST:
            raise SystemExit("Balance %.0f is below the ~%d credits a task needs. Top up first." % (bal, EST))
        body = {"type": "image_to_model", "file": {"type": "png" if img.lower().endswith(".png") else "jpg", "file_token": upload(img)},
                "texture": True, "pbr": True}
        tid = call("POST", "/task", body)["task_id"]
        st.d["tasks"][name] = t = {"task_id": tid, "image": img, "balance_before": bal}
        st.save()
        st.log("SENT %s task %s (balance %.0f)" % (name, tid, bal))
    try:
        res = wait(t["task_id"], name)
    except RuntimeError as e:
        t["status"] = "failed"
        st.save()
        st.log("FAIL %s: %s (failed tasks are not charged)" % (name, e))
        return
    o = res.get("output", {})
    url = o.get("pbr_model") or o.get("model") or o.get("base_model")
    download(url, dst)
    bal, _ = balance()
    cost = max(0.0, t.get("balance_before", bal) - bal)
    t.update(status="success", credits=cost)
    st.d["spent"] = round(st.d["spent"] + cost, 2)
    st.save()
    st.log("OK %s -> %s, cost %.0f credits (total %.0f, balance %.0f)" % (name, dst, cost, st.d["spent"], bal))


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "balance"
    if cmd == "balance":
        b, f = balance()
        print("Tripo API balance: %.2f credits (frozen %.2f)" % (b, f))
        return
    cap = arg("--cap")
    if cap is None:
        raise SystemExit("--cap <credits> is required for paid commands.")
    cap = int(cap)
    if cmd == "gen":
        img, out = sys.argv[2], sys.argv[3]
        jobs = [(os.path.splitext(os.path.basename(img))[0], img)]
    elif cmd == "batch":
        src = sys.argv[2]
        out = arg("--out", "C:/Users/rtcru/charpipe_test/tripo/in")
        jobs = []
        for e in sorted(os.listdir(src)):
            p = os.path.join(src, e)
            if os.path.isdir(p):
                for cand in ("headless.png", "front.png", "front.jpg"):
                    if os.path.exists(os.path.join(p, cand)):
                        jobs.append((e + ("_headless" if cand.startswith("headless") else ""), os.path.join(p, cand)))
                        break
            elif e.lower().endswith((".png", ".jpg", ".jpeg")):
                jobs.append((os.path.splitext(e)[0], p))
    else:
        raise SystemExit("unknown command " + cmd)
    if "--dry-run" in sys.argv:
        print("DRY RUN: %d task(s), ~%d credits each (cap %d):" % (len(jobs), EST, cap))
        for n, i in jobs:
            print("  %s <- %s" % (n, i))
        return
    st = State(out)
    for n, i in jobs:
        gen_one(st, n, i, cap)
    st.log("BATCH_DONE spent %.0f credits" % st.d["spent"])


if __name__ == "__main__":
    main()

"""Tripo3D API client for charpipe (developer platform, separate from the website plan).

    python tools/charpipe/tripo_api.py balance
    python tools/charpipe/tripo_api.py gen <image> <out_dir> --cap N [--parts] [--quality standard|detailed] [--dry-run]
    python tools/charpipe/tripo_api.py segment <out_dir> --cap N            (splits the model made by 'gen')

Key: C:/Users/rtcru/.tripo_key (read only, never printed or logged). Base URL https://openapi.tripo3d.com/v3.
Spending rules:
  * --cap N is required for every paid command: the run refuses to start, or stops before the
    next paid call, once credits spent in <out_dir>/tripo_state.json (+ the next task's estimate)
    would exceed N, or when the live balance is lower than the estimate.
  * state.json records every task id and its credits_consumed, so a rerun resumes a finished or
    running task instead of paying again; failed/cancelled tasks are not charged by Tripo.
  * --dry-run prints what would be sent (without the key) and spends nothing.
gen: image -> POST /files -> POST /generation/image-to-model (v3.1, texture+PBR, detailed texture),
     or with --parts: generate_parts=true (Tripo requires texture/pbr off for parts).
segment: POST /mesh/segment (v2 semantic, balanced) on the gen task -> parts as separate meshes.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "https://openapi.tripo3d.com/v3"
KEY_FILE = os.path.expanduser("~/.tripo_key")
EST = {"gen": 60, "gen_parts": 60, "segment": 50}  # conservative pre-checks; real cost read from credits_consumed


def key():
    if not os.path.exists(KEY_FILE):
        raise SystemExit("No API key file at %s (save the key alone in that file)." % KEY_FILE)
    k = open(KEY_FILE, encoding="utf-8-sig").read().strip()
    if not k:
        raise SystemExit("API key file is empty.")
    return k


def call(method, path, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(API + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + key(), "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:400]
        raise SystemExit("%s %s -> HTTP %s: %s" % (method, path, e.code, msg))
    if out.get("code") not in (0, None):
        raise SystemExit("%s %s -> code %s: %s" % (method, path, out.get("code"), json.dumps(out)[:400]))
    return out.get("data", out)


def balance():
    d = call("GET", "/account/balance")
    return float(d.get("balance", 0)), float(d.get("frozen", 0))


def upload(path):
    b = "----charpipe" + uuid.uuid4().hex
    name = os.path.basename(path)
    ctype = "image/png" if name.lower().endswith(".png") else "image/jpeg"
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
             % (b, name, ctype)).encode() + open(path, "rb").read() + ("\r\n--%s--\r\n" % b).encode())
    return call("POST", "/files", raw=body, ctype="multipart/form-data; boundary=" + b)["file_token"]


def wait(task_id, label):
    last = None
    while True:
        t = call("GET", "/tasks/" + task_id)
        st, pr = t.get("status"), t.get("progress")
        if (st, pr) != last:
            print("  %s: %s %s%%" % (label, st, pr), flush=True)
            last = (st, pr)
        if st == "success":
            return t
        if st in ("failed", "cancelled", "banned", "expired"):
            raise SystemExit("%s %s: %s" % (label, st, json.dumps(t)[:300]))
        time.sleep(8)


def download(url, path):
    with urllib.request.urlopen(url, timeout=600) as r, open(path, "wb") as f:
        f.write(r.read())
    print("  saved", path, flush=True)


class State:
    def __init__(self, out):
        os.makedirs(out, exist_ok=True)
        self.path = os.path.join(out, "tripo_state.json")
        self.d = json.load(open(self.path)) if os.path.exists(self.path) else {"tasks": {}, "spent": 0.0}

    def save(self):
        json.dump(self.d, open(self.path, "w"), indent=1)

    def guard(self, cap, step):
        est = EST[step]
        if self.d["spent"] + est > cap:
            raise SystemExit("Credit cap: spent %.0f + next step ~%d > cap %d. Stopping before '%s'."
                             % (self.d["spent"], est, cap, step))
        bal, frozen = balance()
        if bal < est:
            raise SystemExit("Balance %.0f is below the ~%d credits '%s' needs. Top up first." % (bal, est, step))
        print("  balance %.0f (frozen %.0f), spent so far %.0f, cap %d" % (bal, frozen, self.d["spent"], cap), flush=True)

    def done(self, step, task):
        c = float(task.get("credits_consumed") or 0)
        self.d["tasks"][step]["credits"] = c
        self.d["tasks"][step]["status"] = "success"
        self.d["spent"] = round(self.d["spent"] + c, 2)
        self.save()
        print("  %s cost %.0f credits (total %.0f)" % (step, c, self.d["spent"]), flush=True)


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "balance"
    if cmd == "balance":
        bal, frozen = balance()
        print("Tripo API balance: %.2f credits (frozen %.2f)" % (bal, frozen))
        return
    cap = arg("--cap")
    if cap is None:
        raise SystemExit("--cap <credits> is required for paid commands.")
    cap = int(cap)
    if cmd == "gen":
        img, out = sys.argv[2], sys.argv[3]
        parts = "--parts" in sys.argv
        step = "gen_parts" if parts else "gen"
        body = {"model": "v3.1-20260211", "geometry_quality": "detailed"}
        if parts:
            body.update(texture=False, pbr=False, generate_parts=True)
        else:
            body.update(texture=True, pbr=True, texture_quality=arg("--quality", "detailed"))
        if "--dry-run" in sys.argv:
            print("DRY RUN: would upload %s and POST /generation/image-to-model %s (cap %d)" % (img, json.dumps(body), cap))
            return
        st = State(out)
        t = st.d["tasks"].get(step)
        if not t or t.get("status") != "success":
            if not t:
                st.guard(cap, step)
                body["input"] = upload(img)
                tid = call("POST", "/generation/image-to-model", body)["task_id"]
                st.d["tasks"][step] = {"task_id": tid, "request": {k: v for k, v in body.items() if k != "input"}}
                st.save()
            res = wait(st.d["tasks"][step]["task_id"], step)
            st.done(step, res)
            o = res.get("output", {})
            for k_, v in o.items():
                if isinstance(v, str) and v.startswith("http"):
                    ext = v.split("?")[0].rsplit(".", 1)[-1][:5]
                    download(v, os.path.join(out, "%s_%s.%s" % (step, k_.replace("_url", ""), ext)))
        print("TRIPO_OK", json.dumps({"step": step, "spent": st.d["spent"]}))
    elif cmd == "segment":
        out = sys.argv[2]
        st = State(out)
        src = (st.d["tasks"].get("gen") or st.d["tasks"].get("gen_parts") or {}).get("task_id")
        if not src:
            raise SystemExit("Run 'gen' first.")
        body = {"input": src, "model": "v2.0-20260430", "segmentation_granularity": "balanced"}
        if "--dry-run" in sys.argv:
            print("DRY RUN: would POST /mesh/segment %s (cap %d)" % (json.dumps(body), cap))
            return
        t = st.d["tasks"].get("segment")
        if not t:
            st.guard(cap, "segment")
            tid = call("POST", "/mesh/segment", body)["task_id"]
            st.d["tasks"]["segment"] = {"task_id": tid, "request": body}
            st.save()
        if st.d["tasks"]["segment"].get("status") != "success":
            res = wait(st.d["tasks"]["segment"]["task_id"], "segment")
            st.done("segment", res)
            for k_, v in res.get("output", {}).items():
                if isinstance(v, str) and v.startswith("http"):
                    ext = v.split("?")[0].rsplit(".", 1)[-1][:5]
                    download(v, os.path.join(out, "segment_%s.%s" % (k_.replace("_url", ""), ext)))
        print("TRIPO_OK", json.dumps({"step": "segment", "spent": st.d["spent"]}))
    else:
        raise SystemExit("unknown command " + cmd)


if __name__ == "__main__":
    main()

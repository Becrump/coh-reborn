"""Bulk-download Mixamo animations (Y Bot, FBX Binary, Without Skin, 30 fps, no keyframe reduction).

    python tools/charpipe/mixamo_bulk.py [--out DIR] [--limit N] [--dry-run] [--packs] [--character-id ID]

Uses the same (unofficial) web API the mixamo.com site calls, with the signed-in user's bearer token:
  GET  /api/v1/products?page=P&limit=96&type=Motion            list animations
  GET  /api/v1/products/<id>?similar=0&character_id=<char>     details (gms_hash, supports in-place)
  POST /api/v1/animations/export                               start an export job
  GET  /api/v1/characters/<char>/monitor                       poll until status == completed -> job_result URL

Token: read from C:\\Users\\<you>\\.mixamo_token (never printed, logged or written anywhere). To create it:
  sign in at mixamo.com, press F12 -> Console, run   copy(localStorage.access_token)   and paste into that file.
Tokens expire after a while; a 401 stops the run cleanly and a re-run resumes where it stopped.

Per animation it writes <name>__<id8>.fbx (root motion as authored) and, where Mixamo offers it,
<name>__<id8>_inplace.fbx. Resumable: finished ids are kept in mixamo_state.json; everything is appended to
mixamo_log.txt; manifest.json lists id, name, description, duration, frames, in_place, files.
Throttle: >= 1 s between API calls (--delay), exponential back-off on 429 / 5xx, stop on 401.
Note: bulk automated downloading is not an officially supported use of Mixamo; run it at your own discretion.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API = "https://www.mixamo.com/api/v1"
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".mixamo_token")
DEFAULT_OUT = r"C:\Users\rtcru\charpipe_test\tripo\Tripo Exports\Animations\Mixamo"
UA = "charpipe-mixamo-bulk/1.0"


class Stop(Exception):
    pass


class Client:
    def __init__(self, token, delay, log):
        self.token, self.delay, self.log, self.last = token, delay, log, 0.0

    def _wait(self):
        dt = time.time() - self.last
        if dt < self.delay:
            time.sleep(self.delay - dt)
        self.last = time.time()

    def call(self, method, url, body=None, auth=True, raw=False):
        backoff = 5.0
        for attempt in range(8):
            self._wait()
            hdr = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": UA}
            if auth:
                hdr.update({"Authorization": "Bearer " + self.token, "X-Api-Key": "mixamo2",
                            "X-Requested-With": "XMLHttpRequest"})
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(url, data=data, headers=hdr, method=method)
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    payload = r.read()
                    return (r.status, payload) if raw else (r.status, json.loads(payload or b"{}"))
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise Stop("401 Unauthorized - token missing/expired; refresh %s and re-run" % TOKEN_FILE)
                if e.code == 429 or e.code >= 500:
                    ra = e.headers.get("Retry-After")
                    w = float(ra) if ra and ra.isdigit() else backoff
                    self.log("HTTP %d on %s -> waiting %.0f s" % (e.code, url.split("?")[0], w))
                    time.sleep(w)
                    backoff = min(backoff * 2, 600)
                    continue
                if e.code == 404:
                    return 404, {}
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                self.log("network error %s -> retry in %.0f s" % (type(e).__name__, backoff))
                time.sleep(backoff)
                backoff = min(backoff * 2, 600)
        raise Stop("too many retries on " + url.split("?")[0])


def slug(s):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_")[:60] or "anim"


def find_ybot(c):
    for q in ("Y Bot", "Y-Bot", "ybot"):
        st, j = c.call("GET", API + "/products?page=1&limit=48&type=Character&query=" + urllib.request.quote(q))
        for p in j.get("results", []):
            if re.sub(r"[^a-z]", "", p.get("name", "").lower()) == "ybot":
                return p["id"]
    raise Stop("could not find the Y Bot character id; pass --character-id")


def list_motions(c, packs):
    typ = "Motion%2CMotionPack" if packs else "Motion"
    out, page, pages = [], 1, 1
    while page <= pages:
        st, j = c.call("GET", API + "/products?page=%d&limit=96&order=&type=%s&query=" % (page, typ))
        out += j.get("results", [])
        pages = int(j.get("pagination", {}).get("num_pages", 1))
        page += 1
    return out


def export(c, char, prod, details, inplace):
    g = dict(details["gms_hash"])
    params = g.get("params", [])
    g["params"] = ",".join(str(p[1]) for p in params) if isinstance(params, list) else params
    if "inplace" in g or inplace:
        g["inplace"] = bool(inplace)
    body = {"character_id": char, "gms_hash": [g], "product_name": prod.get("description") or prod.get("name"),
            "type": prod.get("type", "Motion"),
            "preferences": {"format": "fbx7", "skin": "false", "fps": "30", "reducekf": "0"}}
    st, j = c.call("POST", API + "/animations/export", body)
    t0 = time.time()
    while time.time() - t0 < 300:
        st, m = c.call("GET", API + "/characters/%s/monitor" % char)
        s = m.get("status")
        if s == "completed":
            return m["job_result"]
        if s == "failed":
            raise RuntimeError("export failed: %s" % str(m.get("message", ""))[:200])
        time.sleep(1.0)
    raise RuntimeError("export timed out")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0, help="stop after N new animations (0 = all)")
    ap.add_argument("--delay", type=float, default=1.2, help="seconds between API calls (min 1.0)")
    ap.add_argument("--packs", action="store_true", help="also export MotionPacks (zips)")
    ap.add_argument("--no-inplace", action="store_true")
    ap.add_argument("--character-id")
    ap.add_argument("--dry-run", action="store_true", help="list only, download nothing")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    logf = open(os.path.join(a.out, "mixamo_log.txt"), "a", encoding="utf-8")

    def log(msg):
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    if not os.path.isfile(TOKEN_FILE):
        log("NO TOKEN: %s not found. Sign in at mixamo.com, F12 -> Console, run copy(localStorage.access_token), "
            "paste into that file, then re-run." % TOKEN_FILE)
        return 2
    token = open(TOKEN_FILE, encoding="utf-8").read().strip().strip('"')
    c = Client(token, max(1.0, a.delay), log)
    stp = os.path.join(a.out, "mixamo_state.json")
    mfp = os.path.join(a.out, "manifest.json")
    state = json.load(open(stp)) if os.path.isfile(stp) else {"done": [], "failed": {}}
    manifest = json.load(open(mfp)) if os.path.isfile(mfp) else {}

    def save():
        json.dump(state, open(stp + ".tmp", "w"), indent=1)
        os.replace(stp + ".tmp", stp)
        json.dump(manifest, open(mfp + ".tmp", "w"), indent=1)
        os.replace(mfp + ".tmp", mfp)

    try:
        char = a.character_id or find_ybot(c)
        log("character id %s" % char)
        prods = list_motions(c, a.packs)
        todo = [p for p in prods if p["id"] not in state["done"]]
        log("listed %d animations, %d already done, %d to go" % (len(prods), len(prods) - len(todo), len(todo)))
        if a.dry_run:
            for p in todo[:50]:
                log("  would get %s | %s" % (p.get("name"), p.get("description", "")))
            return 0
        n = 0
        for p in todo:
            if a.limit and n >= a.limit:
                break
            pid = p["id"]
            try:
                st, d = c.call("GET", API + "/products/%s?similar=0&character_id=%s" % (pid, char))
                det = d.get("details", {})
                if not det.get("gms_hash"):
                    raise RuntimeError("no gms_hash in details")
                base = "%s__%s" % (slug(p.get("name") or p.get("description", "")), pid[:8])
                ext = ".zip" if p.get("type") == "MotionPack" else ".fbx"
                variants = [(False, base + ext)]
                if not a.no_inplace and det.get("supports_inplace"):
                    variants.append((True, base + "_inplace" + ext))
                files = []
                for inp, fn in variants:
                    dst = os.path.join(a.out, fn)
                    if not os.path.isfile(dst):
                        url = export(c, char, p, det, inp)
                        st, blob = c.call("GET", url, auth=False, raw=True)  # presigned link: no token sent
                        open(dst + ".part", "wb").write(blob)
                        os.replace(dst + ".part", dst)
                    files.append(fn)
                dur = det.get("duration") or p.get("duration") or p.get("motion", {}).get("duration")
                manifest[pid] = {"id": pid, "name": p.get("name"), "description": p.get("description"),
                                 "type": p.get("type"), "duration": dur,
                                 "frames": round(float(dur) * 30) if dur else None,
                                 "in_place": [fn for (inp, fn) in variants if inp], "files": files}
                state["done"].append(pid)
                state["failed"].pop(pid, None)
                n += 1
                log("OK %4d  %s  (%s)" % (len(state["done"]), p.get("name"), ", ".join(files)))
            except Stop:
                raise
            except Exception as e:  # noqa: BLE001  one bad animation must not stop the run
                state["failed"][pid] = "%s: %s" % (p.get("name"), str(e)[:200])
                log("FAIL %s: %s" % (p.get("name"), str(e)[:200]))
            save()
    except Stop as e:
        log("STOPPED: %s" % e)
        save()
        return 3
    save()
    log("finished: %d done, %d failed" % (len(state["done"]), len(state["failed"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

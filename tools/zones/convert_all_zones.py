"""Convert every remaining Paragon City zone, unattended.

Runs the repo converter (coh2unreal --instanced) over each zone in ZONES,
then lists its trees for modern replacement and exports its original enemy
spawn points. Follows the faithful-conversion rule (docs/zones/one-world-plan.md):
buildings and props as in the original, original parked cars left out (cars
come later), trees listed for replacement, no civilians.

    python convert_all_zones.py --work <folder> [--only city_02_01,...] [--redo]

<work> gets:
  i24/       sparse clone of Thunderspies/i24 (made if missing)
  piggs/     game archives (downloaded if missing, about 3 GB)
  zones/<id>_<name>/   one export per zone
  convert_log.txt      one line per zone: OK / FAIL / SKIP, newest at the end
  status.json          last result per zone, for the next session

A zone that already has zones/<id>_<name>/DONE.txt is skipped unless --redo,
so re-running only retries failures and new zones. No Claude is needed.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
CONVERTER = os.path.join(REPO, "coh2unreal")

# Paragon City order from the one-world plan: inner ring, green line, outer.
# Atlas Park (city_01_01) keeps its own map; Galaxy City (city_01_03) was
# converted on 2026-11-10 but is listed so a fresh PC can rebuild it too.
ZONES = [
    ("city_01_03", "galaxy_city"),
    ("hazard_01_01", "perez_park"),
    ("city_01_02", "kings_row"),
    ("city_02_01", "steel_canyon"),
    ("city_02_02", "skyway_city"),
    ("city_03_02", "independence_port"),
    ("city_03_01", "talos_island"),
    ("city_04_02", "brickstown"),
    ("city_04_01", "founders_falls"),
    ("city_05_01", "peregrine_island"),
    ("city_02_05", "faultline"),
    ("city_03_03", "croatoa"),
    ("city_03_04", "firebase_zulu"),
    ("city_02_04", "pocket_d"),
    ("hazard_01_02", "the_hollows"),
    ("hazard_02_01", "boomtown"),
    ("hazard_03_01", "dark_astoria"),
    ("hazard_03_02", "creys_folly"),
    ("hazard_04_01", "eden"),
    ("hazard_06_01", "shadow_shard_1"),
    ("hazard_06_02", "shadow_shard_2"),
    ("hazard_06_03", "shadow_shard_3"),
    ("war_05_01", "rikti_war_zone"),
    ("trial_01_01", "trial_01_01"),
    ("trial_01_02", "trial_01_02"),
    ("trial_02_01", "trial_02_01"),
    ("trial_03_01", "trial_03_01"),
    ("trial_04_01", "terra_volta"),
    ("trial_04_02", "trial_04_02"),
    ("trial_05_01", "trial_05_01"),
    ("trial_06_01", "trial_06_01"),
]

SPARSE = ["data/maps/city_zones", "data/object_library", "data/tricks",
          "data/scenes", "data/defs", "data/scripts.loc/spawndefs", "tools"]
PIGG_URL = "https://dists.thunderspy.org/piggs/"
DROP_PARKED_CARS = "_prkd_*@-999999,-999999,999999,999999"


def log(work, line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(line, flush=True)
    with open(os.path.join(work, "convert_log.txt"), "a", encoding="utf-8") as f:
        f.write("%s  %s\n" % (stamp, line))


def run(cmd, cwd=None, logfile=None):
    with open(logfile, "a", encoding="utf-8") if logfile else open(os.devnull, "w") as out:
        p = subprocess.run(cmd, cwd=cwd, stdout=out, stderr=subprocess.STDOUT)
    return p.returncode


def ensure_i24(work):
    i24 = os.path.join(work, "i24")
    if not os.path.isdir(os.path.join(i24, ".git")):
        print("Cloning i24 data (sparse, a few minutes)...", flush=True)
        if run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
                "https://github.com/Thunderspies/i24", i24]):
            sys.exit("git clone of i24 failed: is git installed and online?")
    if run(["git", "sparse-checkout", "set"] + SPARSE, cwd=i24):
        sys.exit("git sparse-checkout in %s failed" % i24)
    return os.path.join(i24, "data")


def ensure_piggs(work, data):
    piggs = os.path.join(work, "piggs")
    os.makedirs(piggs, exist_ok=True)
    ps1 = os.path.join(os.path.dirname(data), "tools", "fetch_data.ps1")
    names = sorted(set(re.findall(r"[A-Za-z0-9_]+\.pigg", open(ps1, errors="replace").read())))
    missing = [n for n in names if not os.path.isfile(os.path.join(piggs, n))]
    for i, n in enumerate(missing, 1):
        print("Downloading %s (%d/%d)..." % (n, i, len(missing)), flush=True)
        tmp = os.path.join(piggs, n + ".part")
        # curl (built into Windows 10+) works with this server; plain urllib
        # gets 403, so it is only the fallback.
        curl = shutil.which("curl")
        if curl:
            if run([curl, "-fsSL", "--retry", "3", "-o", tmp, PIGG_URL + n]):
                sys.exit("download of %s failed (curl)" % n)
        else:
            req = urllib.request.Request(PIGG_URL + n, headers={"User-Agent": "curl/8.0"})
            with urllib.request.urlopen(req) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
        os.replace(tmp, os.path.join(piggs, n))
    return piggs


def geometry_map(data, zone):
    d = os.path.join(data, "maps", "city_zones", zone)
    if not os.path.isdir(d):
        return None
    files = {f.lower(): f for f in os.listdir(d)}
    for want in (zone + "_layer_geometry.txt", zone + ".txt"):
        if want in files:
            return "maps/city_zones/%s/%s" % (zone, files[want])
    return None


def convert(work, data, piggs, zone, name, redo):
    out = os.path.join(work, "zones", "%s_%s" % (zone, name))
    if os.path.isfile(os.path.join(out, "DONE.txt")) and not redo:
        return "SKIP", "already done", 0
    mp = geometry_map(data, zone)
    if not mp:
        return "FAIL", "no map file for %s in i24 data" % zone, 0
    os.makedirs(out, exist_ok=True)
    zlog = os.path.join(out, "convert.log")
    if os.path.exists(zlog):
        os.remove(zlog)
    t0 = time.time()
    env_py = [sys.executable, "-m"]
    rc = run(env_py + ["coh2unreal", "--data", data, "--piggs", piggs, "--map", mp,
                       "--out", out, "--name", name, "--instanced",
                       "--drop", DROP_PARKED_CARS], cwd=CONVERTER, logfile=zlog)
    if rc:
        return "FAIL", "converter exit %d, see %s" % (rc, zlog), time.time() - t0
    rc = run(env_py + ["coh2unreal.trees", "--data", data, "--piggs", piggs,
                       "--out", out, "--name", name], cwd=CONVERTER, logfile=zlog)
    if rc:
        return "FAIL", "tree list exit %d, see %s" % (rc, zlog), time.time() - t0
    rc = run([sys.executable, os.path.join(HERE, "spawns.py"), data, zone,
              os.path.join(out, name + "_spawns_gamefeet.json")], logfile=zlog)
    if rc:
        return "FAIL", "spawn export exit %d, see %s" % (rc, zlog), time.time() - t0
    report = open(zlog, encoding="utf-8", errors="replace").read()
    missing = re.findall(r"^(missing_geo|missing_model|bad_geo): (\d+)", report, re.M)
    note = ", ".join("%s %s" % m for m in missing if m[1] != "0") or "nothing missing"
    with open(os.path.join(out, "DONE.txt"), "w") as f:
        f.write(note + "\n")
    return "OK", note, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--only", default="", help="comma list of zone ids")
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    free_gb = shutil.disk_usage(work).free / 1e9
    if free_gb < 25:
        log(work, "WARN only %.0f GB free; all zones need roughly 15-20 GB" % free_gb)
    data = ensure_i24(work)
    piggs = ensure_piggs(work, data)
    only = {z.strip() for z in a.only.split(",") if z.strip()}
    status_path = os.path.join(work, "status.json")
    status = json.load(open(status_path)) if os.path.exists(status_path) else {}
    counts = {"OK": 0, "FAIL": 0, "SKIP": 0}
    for zone, name in ZONES:
        if only and zone not in only:
            continue
        print("== %s (%s)" % (name, zone), flush=True)
        try:
            res, note, secs = convert(work, data, piggs, zone, name, a.redo)
        except Exception as e:  # keep going; the next session fixes it
            res, note, secs = "FAIL", "%s: %s" % (type(e).__name__, e), 0
        counts[res] += 1
        log(work, "%-4s %-13s %-18s %4.0fs  %s" % (res, zone, name, secs, note))
        if res != "SKIP":
            status[zone] = {"name": name, "result": res, "note": note,
                            "when": time.strftime("%Y-%m-%d %H:%M:%S")}
            json.dump(status, open(status_path, "w"), indent=1)
    log(work, "DONE  ok %(OK)d, failed %(FAIL)d, skipped %(SKIP)d" % counts)


if __name__ == "__main__":
    main()

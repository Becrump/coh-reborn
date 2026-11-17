"""Import the converted indoor mission maps into Unreal, one small level each: /Game/Missions/L_<id>.

    python tools/missions/import_missions.py [--out <out>] [--only id,id] [--one]

Reads <out>/missions/missions.json and <out>/missions/<id>/ (tools/missions/mission_maps.py).
Same model/material library as the zones (/Game/Zones/Library); models the library lacks are
imported once, so later maps of a set mostly just place. Stages per map, run in the open editor:
  index filter level meshes mats link place interior save
Levels are plain (not World Partition): the game streams one in as a level instance per mission.
Resumes from <out>/missions/import_state.json; one line per map in <out>/missions/import_log.txt.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools", "zones"))
import import_zones as iz  # noqa: E402

OUT = os.environ.get("COH_OUT", r"C:\Users\rtcru\CoHReborn\out")
STAGES = ["index", "filter", "level", "meshes", "mats", "link", "place", "interior", "save"]


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def run_map(mdir, mid, info, st, logf):
    ms = st.setdefault(mid, {"done": []})
    if "save" in ms["done"]:
        return "done"
    cfg = {"zone": "Missions_" + mid, "name": mid, "level": "/Game/Missions/L_" + mid,
           "partitioned": False,
           "placements": os.path.join(mdir, mid + "_placements.json"),
           "masked_json": os.path.join(mdir, "masked_materials.json"),
           "lights": os.path.join(mdir, mid + "_lights.json"),
           "bounds": info.get("bounds"),
           "index_out": os.path.join(iz.WORK, "library_index.json"),
           "save_prefixes": ["/Game/Missions/L_" + mid, "/Game/Zones/Library"]}
    cfg.update(ms.get("filter", {}))
    t0 = time.time()
    for stage in STAGES:
        if stage in ms["done"] and stage != "level":
            continue
        print("[%s] %s ..." % (mid, stage), flush=True)
        if stage == "filter":
            index = json.load(open(cfg["index_out"]))
            # editor markers were left out of the placements; keep their meshes out of the library too
            skip = os.path.join(mdir, "skip_meshes.json")
            if os.path.isfile(skip):
                index["meshes"] = list(index["meshes"]) + [re.sub(r"[^A-Za-z0-9_\-]", "_", n)
                                                           for n in json.load(open(skip))]
            f = iz.filter_gltf(mdir, mid, index)
            ms["filter"] = f
            cfg.update(f)
            ok, out = True, "new models %d, new materials %d" % (len(f["new_mesh_names"]), len(f["new_mat_names"]))
        else:
            ok, out = iz.ue(iz.stage_code(cfg, stage), 7200)
        with open(os.path.join(mdir, "import_report.txt"), "a", encoding="utf-8") as f:
            lines = [l for l in out.splitlines() if l.startswith(("[zone]", "[Error]"))]
            f.write("%s %s %s\n%s\n" % (now(), stage, "OK" if ok else "FAIL", "\n".join(lines) or out[-1500:]))
        if not ok:
            json.dump(st, open(st["_path"], "w"), indent=1)
            logf("FAIL %-34s stage %s: %s" % (mid, stage, (out.strip().splitlines() or ["?"])[-1][:200]))
            return "fail"
        ms["done"].append(stage)
        json.dump(st, open(st["_path"], "w"), indent=1)
    logf("OK   %-34s %s, %.1f min" % (mid, info.get("set", ""), (time.time() - t0) / 60))
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--only", default="")
    ap.add_argument("--one", action="store_true")
    a = ap.parse_args()
    root = os.path.join(a.out, "missions")
    index = json.load(open(os.path.join(root, "missions.json")))
    sp = os.path.join(root, "import_state.json")
    st = json.load(open(sp)) if os.path.isfile(sp) else {}
    st["_path"] = sp

    def logf(line):
        print(line, flush=True)
        with open(os.path.join(root, "import_log.txt"), "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (now(), line))
    want = set(a.only.split(",")) if a.only else None
    counts = {"ok": 0, "fail": 0, "done": 0, "skip": 0}
    for mid, info in sorted(index["maps"].items()):
        if want and mid not in want:
            continue
        mdir = os.path.join(root, mid)
        if not os.path.isfile(os.path.join(mdir, "DONE.txt")):
            counts["skip"] += 1
            continue
        if "save" not in st.get(mid, {}).get("done", []) and not iz.wait_free():
            return 2
        r = run_map(mdir, mid, info, st, logf)
        counts[r] += 1
        if a.one and r in ("ok", "fail"):
            break
    logf("MISSIONS %d imported, %d already, %d failed, %d not converted" % (
        counts["ok"], counts["done"], counts["fail"], counts["skip"]))
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())

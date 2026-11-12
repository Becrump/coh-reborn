"""Import converted zones into Unreal, one World Partition level per zone, sharing one model library.

    python tools/zones/import_zones.py [--zones a,b] [--one] [--dry]

Reads the batch converter output (exports/zones/zones/<id>_<name>/), filters each zone's glTF down to
models and materials the shared library does not have yet, and runs coh2unreal/unreal/zone_batch_ue.py
stage by stage in the open editor (Python remote execution). Progress lives in
docs/zones/import/state.json (per-stage), docs/zones/import/import_log.txt (one line per zone) and
docs/zones/import/<Zone>/ (report + screenshots). Re-running resumes: finished zones are skipped and an
unfinished zone continues after its last finished stage. Glazing is never sent twice for a zone.

Before each zone: exactly one UnrealEditor process, no Play-In-Editor, no other remote script
running (ue_exec/uex/mcp_call processes); otherwise it waits.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXPORTS = r"C:\Users\rtcru\ClaudeProjects\COHReborn\exports\zones\zones"
UE_EXEC = os.path.join(REPO, "unreal", "scripts", "ue_exec.py")
UE_MOD = os.path.join(REPO, "coh2unreal", "unreal", "zone_batch_ue.py")
GLAZE = os.path.join(REPO, "unreal", "scripts", "glass", "glaze_zone.py")
SETUP_LEVEL = os.path.join(REPO, "coh2unreal", "unreal", "setup_level.py")
SETUP_TREES = os.path.join(REPO, "coh2unreal", "unreal", "setup_trees.py")
TREE_TABLE = os.path.join(REPO, "docs", "zones", "tree_replacement.json")
GLAZE_PATHS = {"GalaxyCity": "/Game/Zones/GalaxyCity"}   # Galaxy's materials predate the library
OPTIONAL = {"props", "trees", "shot_overview", "shot_street"}   # a failure here is logged, the zone carries on
OUT = os.path.join(REPO, "docs", "zones", "import")
WORK = os.path.join(os.environ.get("TEMP", "."), "coh_zone_batch")
SHOT_DIR = r"C:\Users\rtcru\OneDrive\Documents\Unreal Projects\COHREBORN\Saved\Screenshots\WindowsEditor"

# order from docs/zones/one-world-plan.md (Galaxy City was imported first and seeds the library)
ORDER = [
    ("city_01_03", "galaxy_city", "GalaxyCity"),
    ("hazard_01_01", "perez_park", "PerezPark"), ("city_01_02", "kings_row", "KingsRow"),
    ("city_02_01", "steel_canyon", "SteelCanyon"), ("city_02_02", "skyway_city", "SkywayCity"),
    ("hazard_01_02", "the_hollows", "TheHollows"),
    ("city_03_02", "independence_port", "IndependencePort"), ("city_03_01", "talos_island", "TalosIsland"),
    ("city_04_02", "brickstown", "Brickstown"), ("city_04_01", "founders_falls", "FoundersFalls"),
    ("hazard_02_01", "boomtown", "Boomtown"), ("city_02_05", "faultline", "Faultline"),
    ("hazard_04_01", "eden", "Eden"), ("hazard_03_02", "creys_folly", "CreysFolly"),
    ("hazard_03_01", "dark_astoria", "DarkAstoria"), ("city_03_03", "croatoa", "Croatoa"),
    ("city_05_01", "peregrine_island", "PeregrineIsland"), ("trial_05_01", "trial_05_01", "RiktiCrashSite"),
    ("hazard_06_01", "shadow_shard_1", "ShadowShard1"), ("hazard_06_02", "shadow_shard_2", "ShadowShard2"),
    ("hazard_06_03", "shadow_shard_3", "ShadowShard3"), ("city_02_04", "pocket_d", "PocketD"),
    ("war_05_01", "rikti_war_zone", "RiktiWarZone"), ("city_03_04", "firebase_zulu", "FirebaseZulu"),
    ("trial_01_01", "trial_01_01", "Trial_01_01"), ("trial_01_02", "trial_01_02", "Trial_01_02"),
    ("trial_02_01", "trial_02_01", "Trial_02_01"), ("trial_03_01", "trial_03_01", "Trial_03_01"),
    ("trial_04_01", "terra_volta", "TerraVolta"), ("trial_04_02", "trial_04_02", "Trial_04_02"),
    ("trial_06_01", "trial_06_01", "Trial_06_01"),
]
STAGES = ["index", "filter", "level", "meshes", "mats", "link", "place", "props", "trees", "sky", "save", "glaze", "save2",
          "shot_overview", "shot_street", "stats"]


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_state():
    p = os.path.join(OUT, "state.json")
    return json.load(open(p)) if os.path.isfile(p) else {}


def save_state(st):
    os.makedirs(OUT, exist_ok=True)
    json.dump(st, open(os.path.join(OUT, "state.json"), "w"), indent=1)


def logline(line):
    print(line, flush=True)
    for d in (OUT, os.path.dirname(EXPORTS)):
        with open(os.path.join(d, "import_log.txt"), "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (now(), line))


def ue(code, timeout=7200):
    """run python in the editor; returns (ok, output). Never retried by the caller for glaze."""
    os.makedirs(WORK, exist_ok=True)
    f = os.path.join(WORK, "_stage.py")
    open(f, "w", encoding="utf-8").write(code)
    for attempt in range(40):
        p = subprocess.run([sys.executable, UE_EXEC, f, "--file", "--timeout", str(timeout)],
                           capture_output=True, text=True, timeout=timeout + 120)
        out = p.stdout + p.stderr
        # "no Unreal editor found" = the command was never sent (editor busy saving): safe to wait and retry
        if "no Unreal editor found" not in out:
            break
        print("editor busy, waiting (%d)" % attempt, flush=True)
        time.sleep(60)
    ok = p.returncode == 0 and out.rstrip().endswith("success")
    return ok, out


def stage_code(cfg, stage):
    return "ZONE_CFG = %s\nSTAGE = %r\nexec(compile(open(r%r).read(), %r, 'exec'))\n" % (
        repr(cfg), stage, UE_MOD, "zone_batch_ue.py")


def editor_free():
    ps = ("Get-CimInstance Win32_Process | ? { $_.Name -eq 'UnrealEditor.exe' -or ($_.CommandLine -match "
          "'ue_exec|uex\\.sh|mcp_call' -and $_.CommandLine -notmatch 'import_zones|_stage\\.py|_probe') } | "
          "% { $_.Name + '|' + $_.ProcessId }")
    out = subprocess.run(["powershell", "-NoProfile", "-c", ps], capture_output=True, text=True).stdout
    procs = [l for l in out.splitlines() if l.strip()]
    eds = [l for l in procs if l.startswith("UnrealEditor")]
    others = [l for l in procs if not l.startswith("UnrealEditor")]
    if len(eds) != 1 or others:
        return False, "editors=%d others=%s" % (len(eds), others)
    ok, o = ue("import unreal\nprint('PIE', unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)"
               ".get_game_world() is not None)\n", 60)
    if not ok or "PIE False" not in o:
        return False, "PIE or no response: " + o[-200:]
    return True, ""


def wait_free(max_wait=6 * 3600):
    t0 = time.time()
    while True:
        ok, why = editor_free()
        if ok:
            return True
        if time.time() - t0 > max_wait:
            logline("WAIT timeout: " + why)
            return False
        print("waiting for editor:", why, flush=True)
        time.sleep(60)


def filter_gltf(zdir, name, index):
    """write <work>/<name>_new_meshes.gltf and _new_mats.gltf with only what the library lacks"""
    san = lambda s: re.sub(r"[^A-Za-z0-9_\-]", "_", s)
    g = json.load(open(os.path.join(zdir, name + ".gltf")))
    have_m = set(index["meshes"])
    have_t = set(index["materials"])
    new_meshes = [i for i, m in enumerate(g["meshes"]) if san(m["name"]) not in have_m]
    used = {p["material"] for i in new_meshes for p in g["meshes"][i]["primitives"] if "material" in p}
    all_used = {p["material"] for m in g["meshes"] for p in m["primitives"] if "material" in p}
    new_mats = sorted(i for i in all_used if san(g["materials"][i]["name"]).lower() not in have_t)
    abs_bin = os.path.join(zdir, g["buffers"][0]["uri"]).replace("\\", "/")
    os.makedirs(WORK, exist_ok=True)
    res = {"new_mesh_names": [san(g["meshes"][i]["name"]) for i in new_meshes],
           "new_mat_names": [g["materials"][i]["name"] for i in new_mats],
           "new_meshes_gltf": None, "new_mats_gltf": None}
    base = dict(g)
    # written next to the original so the relative .bin/texture uris resolve (Unreal treats absolute uris as relative)
    if new_meshes:
        m = dict(base)
        m["meshes"] = [g["meshes"][i] for i in new_meshes]
        m["nodes"] = [{"name": g["meshes"][i]["name"], "mesh": k} for k, i in enumerate(new_meshes)]
        m["scenes"] = [{"name": name, "nodes": list(range(len(new_meshes)))}]
        # materials kept for slot names only; their textures dropped so nothing texture-related loads
        m["materials"] = [{"name": mt["name"]} for mt in g["materials"]]
        for k in ("textures", "images", "samplers"):
            m.pop(k, None)
        res["new_meshes_gltf"] = os.path.join(zdir, name + "_new_meshes.gltf").replace("\\", "/")
        json.dump(m, open(res["new_meshes_gltf"], "w"))
    if new_mats:
        # one tiny carrier mesh per new material (the material pass imports no meshes)
        prim0 = g["meshes"][0]["primitives"][0]
        t = dict(base)
        t["meshes"] = [{"name": "carrier_%d" % k, "primitives": [dict(prim0, material=i)]}
                       for k, i in enumerate(new_mats)]
        t["nodes"] = [{"name": "carrier_%d" % k, "mesh": k} for k in range(len(new_mats))]
        t["scenes"] = [{"name": name + "_mats", "nodes": list(range(len(new_mats)))}]
        res["new_mats_gltf"] = os.path.join(zdir, name + "_new_mats.gltf").replace("\\", "/")
        json.dump(t, open(res["new_mats_gltf"], "w"))
    return res


def shot_to_repo(zone, which, dst_dir):
    src = os.path.join(SHOT_DIR, "%s_%s.png" % (zone, which))
    # the editor only renders in the background when poked: nudge it until the shot lands
    for i in range(60):
        if os.path.isfile(src):
            break
        ue("import unreal\nunreal.EditorLevelLibrary.editor_invalidate_viewports()\n", 60)
        time.sleep(5)
    if not os.path.isfile(src):
        return None
    time.sleep(2)
    from PIL import Image
    im = Image.open(src).convert("RGB")
    dst = os.path.join(dst_dir, "%s_%s.jpg" % (zone, which))
    q = 88
    while True:
        im.save(dst, quality=q)
        if os.path.getsize(dst) < 900_000 or q < 60:
            break
        q -= 6
    return dst


def run_zone(zid, name, zone, st, dry=False):
    zdir = os.path.join(EXPORTS, "%s_%s" % (zid, name))
    if not os.path.isfile(os.path.join(zdir, "DONE.txt")):
        logline("SKIP %-16s no converter output" % zone)
        return "skip"
    zs = st.setdefault(zone, {"done": [], "started": now()})
    if "stats" in zs["done"]:
        return "done"
    rdir = os.path.join(OUT, zone)
    os.makedirs(rdir, exist_ok=True)
    cfg = {"zone": zone, "name": name, "placements": os.path.join(zdir, name + "_placements.json"),
           "masked_json": os.path.join(zdir, "masked_materials.json"),
           "index_out": os.path.join(WORK, "library_index.json"),
           "stats_out": os.path.join(rdir, "stats.json"), "shot_dir": SHOT_DIR.replace("\\", "/")}
    cfg.update(zs.get("filter", {}))
    t0 = time.time()
    notes = []
    for stage in STAGES:
        if stage in zs["done"] and stage != "level":   # always re-open the zone level on resume
            continue
        if stage == "glaze" and zs.get("glaze_sent"):
            notes.append("glaze already sent earlier; not re-sent")
            zs["done"].append(stage)
            save_state(st)
            continue
        if dry and stage not in ("index", "filter"):
            break
        print("[%s] %s ..." % (zone, stage), flush=True)
        if stage == "filter":
            index = json.load(open(cfg["index_out"]))
            f = filter_gltf(zdir, name, index)
            zs["filter"] = f
            cfg.update(f)
            notes.append("new models %d, new materials %d" % (len(f["new_mesh_names"]), len(f["new_mat_names"])))
            ok, out = True, "filtered"
        elif stage == "glaze":
            zs["glaze_sent"] = now()
            save_state(st)
            code = ("import os\nos.environ['GLASS_ZONE_PATH']=%r\nos.environ['GLASS_DRY']='0'\n"
                    "os.environ['GLASS_SAVE']='1'\n__file__=r%r\n"
                    % (GLAZE_PATHS.get(zone, "/Game/Zones/Library/Materials"), GLAZE)) + open(GLAZE).read()
            ok, out = ue(code, 3600)
            glazed = re.search(r"^glass\s+(\d+)\s+(.*)$", out, re.M)
            notes.append("glazed %s" % (glazed.group(1) + ": " + glazed.group(2)[:300] if glazed else "0"))
        elif stage == "props":
            code = ("import sys\nsys.argv=['setup_level.py','--only','props']\n__file__=r%r\n"
                    % os.path.join(zdir, "setup_level.py")) + open(SETUP_LEVEL).read()
            ok, out = ue(code, 1800)
            notes.append("lamps step %s" % ("ok" if ok else "FAILED"))
        elif stage == "trees":
            code = ("import sys\nsys.argv=['setup_trees.py',r%r,r%r]\n__file__=r%r\n"
                    % (zdir, TREE_TABLE, SETUP_TREES)) + open(SETUP_TREES).read()
            ok, out = ue(code, 1800)
            m = re.findall(r"\[CoH trees\] (.*)", out)
            notes.append("trees %s" % ("; ".join(m[-2:]) if ok else "FAILED (continuing without trees)"))
        elif stage.startswith("shot_"):
            which = stage[5:]
            stale = os.path.join(SHOT_DIR, "%s_%s.png" % (zone, which))
            if os.path.isfile(stale):
                os.replace(stale, stale + ".old")   # our own earlier shot; keep it aside
            c = dict(cfg, shot=which)
            ok, out = ue(stage_code(c, "shots"), 300)
            if ok:
                dst = shot_to_repo(zone, which, rdir)
                ok = dst is not None
                out += "\nshot file %s" % dst
        else:
            ok, out = ue(stage_code(cfg, "save" if stage == "save2" else stage),
                         14400 if stage in ("meshes", "place") else 3600)
        lines = [l for l in out.splitlines() if l.startswith(("[zone]", "[Error]", "glass", "saved"))]
        with open(os.path.join(rdir, "report.txt"), "a", encoding="utf-8") as f:
            f.write("%s %s %s\n%s\n" % (now(), stage, "OK" if ok else "FAIL", "\n".join(lines) or out[-1500:]))
        if not ok and stage in OPTIONAL:
            logline("WARN %-16s optional stage %s failed; continuing: %s" % (
                zone, stage, (out.strip().splitlines() or ["?"])[-1][:200]))
            ok = True
        if not ok:
            zs["failed"] = "%s at %s" % (stage, now())
            save_state(st)
            logline("FAIL %-16s stage %s after %.0f min: %s" % (zone, stage, (time.time() - t0) / 60,
                                                               (out.strip().splitlines() or ["?"])[-1][:200]))
            return "fail"
        zs["done"].append(stage)
        save_state(st)
    if dry:
        logline("DRY  %-16s %s" % (zone, "; ".join(notes)))
        return "dry"
    s = json.load(open(cfg["stats_out"]))
    zs["minutes"] = round((time.time() - t0) / 60, 1)
    zs.pop("failed", None)
    save_state(st)
    # counts from the placement step (the stats stage only sees World Partition cells loaded in the editor)
    rep = open(os.path.join(rdir, "report.txt"), encoding="utf-8").read()
    m = re.findall(r"place: (\d+) single, (\d+) instances in (\d+) instance actors; (\d+) models missing", rep)
    if m:
        single, inst, iact, miss = (int(x) for x in m[-1])
        counts = "actors %d + instance actors %d (%d instances), %d models missing" % (single, iact, inst, miss)
    else:
        counts = "loaded actors %d, instances %d" % (s["actors"], s["instances"])
    logline("OK   %-16s %s, %.0f min; %s" % (zone, counts, zs["minutes"], "; ".join(notes)))
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zones", default="")
    ap.add_argument("--one", action="store_true", help="stop after one zone (finished or failed)")
    ap.add_argument("--dry", action="store_true", help="only index + filter, no editor changes")
    a = ap.parse_args()
    want = set(a.zones.split(",")) if a.zones else None
    st = load_state()
    for zid, name, zone in ORDER:
        if want and zone not in want and zid not in want:
            continue
        if "stats" in st.get(zone, {}).get("done", []):
            continue
        if not a.dry and not wait_free():
            return 2
        r = run_zone(zid, name, zone, st, a.dry)
        if a.one and r in ("ok", "fail"):
            return 0 if r == "ok" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

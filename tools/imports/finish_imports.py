"""Finish importing the original game's content, unattended: convert on this
PC from the original data, then import into the open Unreal editor.

    python tools/imports/finish_imports.py [--convert-only] [--unreal-only] [--redo STAGE ...]

Convert stages (no editor needed; each takes seconds to a few minutes):
  encounters   every zone's original encounters (tools/zones/encounters.py)
               -> out/zone_encounters/<zone>/encounters.json, sites.json
  enemies      enemy kit for every villain the 18 city-map zones can spawn
               (tools/zones/enemy_kit_all.py) -> out/enemies: kit.json (a
               superset of Atlas Park's, same format), roster.json, models/.
               The old kit.json and roster.json are backed up first;
               Atlas Park's encounters.json is left as it is.
  enemy_fx     effects, textures and sounds of all those villains' powers
               -> out/enemies/fx
  player_fx    effects of every player power -> out/fx (only if missing)
  story        contacts, story arcs, missions, task forces, clues, encounter
               dialog and the English text (tools/story/coh_story.py) -> out/story
  items        badges, enhancements, inventions, stores, rewards
               (tools/story/coh_items.py) -> out/items
  story_game   what the game reads for contacts and missions: where contacts,
               mission doors and visit spots are in the 19 zones
               (tools/story/world_points.py) and the compiled contacts, tasks,
               arcs and reward tables (tools/story/story_game.py)
               -> out/story/story_game.json
  missions     indoor mission maps the tasks use, 2 layouts per map set and
               length (tools/missions/mission_maps.py) -> out/missions
  characters   the 120 hero presets and every contact/mission NPC model
               (coh2unreal.player models) -> out/player/models, models.json

Unreal stages (exactly one editor open, Python Remote Execution on, nobody
else using it; each call imports a small batch and saves, so it can stop
and resume at any time):
  ue_fx        effect textures and sounds of all powers -> /Game/CoH/FX
  ue_enemies   villain models -> /Game/CoH/Enemies/<costume>
  ue_presets   hero presets and contacts on player bodies
               -> /Game/CoH/Player/Presets/<body>/<name>
  ue_npcs      the other NPC models, each on its own skeleton -> /Game/CoH/NPCs
  ue_missions  indoor mission maps, one level each -> /Game/Missions/L_<id>
               (tools/missions/import_missions.py)

Progress: finish_imports_state.json and one line per stage in
finish_imports_log.txt, both in <out>. Re-running skips finished stages.

Paths (override with environment variables):
  COH_OUT    C:\\Users\\rtcru\\CoHReborn\\out (the game reads its data here)
  COH_I24    i24 checkout (made full if it is a sparse checkout)
  COH_PIGGS  folder of .pigg files
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PY = sys.executable
OUT = os.environ.get("COH_OUT", r"C:\Users\rtcru\CoHReborn\out")
I24_CANDIDATES = [os.environ.get("COH_I24", ""), r"C:\Users\rtcru\CoHReborn\i24",
                  r"C:\Users\rtcru\ClaudeProjects\COHReborn\exports\zones\i24"]
PIGG_CANDIDATES = [os.environ.get("COH_PIGGS", ""),
                   r"C:\Users\rtcru\ClaudeProjects\COHReborn\exports\zones\piggs",
                   r"C:\Users\rtcru\CoHReborn\piggs", r"D:\Users\Robert\Documents\CoH\piggs"]
UE_EXEC = os.path.join(REPO, "unreal", "scripts", "ue_exec.py")
GS = os.path.join(REPO, "unreal", "scripts", "game_systems")
NEEDED = ("texts/english", "scripts.loc/contacts", "scripts.loc/spawndefs",
          "maps/city_zones", "maps/missions", "object_library", "defs/powers", "sequencers",
          "aiscript", "menu")
CONVERT = ["encounters", "enemies", "enemy_fx", "player_fx", "story", "items", "story_game",
           "missions", "characters"]
UNREAL = ["ue_fx", "ue_enemies", "ue_missions", "ue_presets", "ue_npcs"]


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(line):
    print(line, flush=True)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "finish_imports_log.txt"), "a", encoding="utf-8") as f:
        f.write("%s  %s\n" % (now(), line))


def state():
    p = os.path.join(OUT, "finish_imports_state.json")
    return json.load(open(p)) if os.path.isfile(p) else {}


def mark(stage, info):
    st = state()
    st[stage] = {"done": now(), "info": info}
    json.dump(st, open(os.path.join(OUT, "finish_imports_state.json"), "w"), indent=1)


def run(args, timeout=None):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [os.path.join(REPO, "coh2unreal"), os.environ.get("PYTHONPATH", "")]))
    p = subprocess.run(args, cwd=REPO, env=env, capture_output=True, text=True,
                       timeout=timeout, encoding="utf-8", errors="replace")
    with open(os.path.join(OUT, "finish_imports_console.txt"), "a", encoding="utf-8") as f:
        f.write("\n==== %s %s\n%s\n%s" % (now(), " ".join(args), p.stdout, p.stderr))
    return p


def find_i24():
    for c in I24_CANDIDATES:
        if c and os.path.isdir(os.path.join(c, "data", "defs")):
            if not all(os.path.isdir(os.path.join(c, "data", n)) for n in NEEDED):
                log("i24 at %s is sparse: checking out all of data/ (a few minutes)" % c)
                subprocess.run(["git", "sparse-checkout", "set", "--no-cone", "/data/",
                                "/tools/"], cwd=c)
            return os.path.join(c, "data")
    sys.exit("no i24 checkout found; set COH_I24")


def find_piggs():
    for c in PIGG_CANDIDATES:
        if c and os.path.isdir(c) and any(f.endswith(".pigg") for f in os.listdir(c)):
            return c
    sys.exit("no .pigg folder found; set COH_PIGGS")


def last_line(p, word):
    lines = [l for l in (p.stdout + p.stderr).splitlines() if word in l]
    return lines[-1].strip() if lines else (p.stdout + p.stderr).strip().splitlines()[-1:]


def convert(stage, data, piggs):
    o = lambda *a: os.path.join(OUT, *a)  # noqa: E731
    if stage == "encounters":
        p = run([PY, "tools/zones/encounters.py", data, o("zone_encounters")])
        return p.returncode == 0, "%d zones" % len(os.listdir(o("zone_encounters")))
    if stage == "enemies":
        bk = o("enemies", "backup_" + time.strftime("%Y%m%d_%H%M%S"))
        for f in ("kit.json", "roster.json", "enemy_power_anims.json"):
            if os.path.isfile(o("enemies", f)):
                os.makedirs(bk, exist_ok=True)
                shutil.copy2(o("enemies", f), bk)
        p = run([PY, "tools/zones/enemy_kit_all.py", data, piggs, o("zone_encounters"),
                 o("enemies")])
        return p.returncode == 0, last_line(p, "villains,")
    if stage == "enemy_fx":
        p = run([PY, "-m", "coh2unreal.fx", "--data", data, "--piggs", piggs, "--out",
                 o("enemies", "fx"), "export", "--powers-json",
                 o("enemies", "enemy_power_anims.json"), "--all"])
        return p.returncode == 0, "fx library %s" % os.path.isfile(o("enemies", "fx", "fx_library.json"))
    if stage == "player_fx":
        if os.path.isfile(o("fx", "fx_library.json")):
            return True, "already there"
        p = run([PY, "-m", "coh2unreal.fx", "--data", data, "--piggs", piggs, "--out",
                 o("fx"), "export", "--powers-json", o("powers", "power_anims.json"), "--all"])
        return p.returncode == 0, "fx library %s" % os.path.isfile(o("fx", "fx_library.json"))
    if stage == "story":
        p = run([PY, "tools/story/coh_story.py", data, o("story")])
        return p.returncode == 0, last_line(p, "unresolved")
    if stage == "items":
        p = run([PY, "tools/story/coh_items.py", data, o("items"), "--strings",
                 o("story", "strings.json")])
        return p.returncode == 0, last_line(p, "unresolved")
    if stage == "story_game":
        p = run([PY, "tools/story/world_points.py", data, o("story")])
        if p.returncode != 0:
            return False, last_line(p, "Error")
        p = run([PY, "tools/story/story_game.py", o("story")])
        return p.returncode == 0, last_line(p, "contacts placed")
    if stage == "missions":
        p = run([PY, "tools/missions/mission_maps.py", data, piggs, o("missions")])
        return p.returncode == 0, last_line(p, "missions.json")
    if stage == "characters":
        npcs = json.load(open(o("story", "npcs.json"), encoding="utf-8"))
        models = sorted({c["a"][0] for rel, t in npcs.items() for d in t
                         if d["k"].lower() == "npcdef" for c in d.get("c", [])
                         if c["k"].lower() == "model" and c.get("a")})
        args = [PY, "-m", "coh2unreal.player", "--data", data, "--piggs", piggs,
                "--out", o("player"), "models", "--all-presets"]
        for m in models:
            args += ["--npc", m]
        p = run(args)
        return p.returncode == 0, last_line(p, "models")
    raise ValueError(stage)


def ue(code, timeout):
    """Run code in the editor. After a big save the editor can take minutes
    to answer remote execution again (ue_exec gives up after 10 s), so retry
    "no Unreal editor found" for up to 15 minutes while the editor runs."""
    t0 = time.time()
    while True:
        p = run([PY, UE_EXEC, code, "--timeout", str(timeout)], timeout=timeout + 120)
        if "no Unreal editor found" not in (p.stdout + p.stderr):
            return p
        tl = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
        if "unrealeditor.exe" not in tl or time.time() - t0 > 900:
            return p
        time.sleep(30)


def editor_free():
    tl = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
    # a second UnrealEditor.exe is a game copy (play_two) or another editor
    return tl.count("unrealeditor.exe") == 1


def exec_file(path, globals_):
    pre = "; ".join("%s=%r" % kv for kv in globals_.items())
    return "%s; exec(open(r'%s').read())" % (pre, path) if pre else \
        "exec(open(r'%s').read())" % path


def unreal_stage(stage):
    if stage == "ue_fx":
        p = ue(exec_file(os.path.join(GS, "import_fx.py"), {"GS_STEP": "materials"}), 600)
        p = ue(exec_file(os.path.join(GS, "import_fx.py"), {"GS_STEP": "assets", "GS_POWERS": None}), 4 * 3600)
        return "FX ASSETS imported" in p.stdout, last_line(p, "FX ASSETS")
    if stage == "ue_enemies":
        last = None
        for _ in range(200):
            p = ue(exec_file(os.path.join(GS, "import_enemies.py"),
                             {"GS_LIMIT": 15, "GS_OUT": os.path.join(OUT, "enemies")}), 3600)
            line = last_line(p, "ENEMIES")
            log("  %s" % line)
            parts = str(line).split()
            if len(parts) >= 4 and parts[0] == "ENEMIES" and parts[1] == parts[3]:
                return True, line
            # the rest are props/vehicles with no skeletal mesh (static
            # meshes, PPD_SquadCar, Longbow_Skiff ...): a batch that adds
            # nothing ends the stage instead of retrying them forever
            if len(parts) >= 4 and parts[0] == "ENEMIES" and parts[1] == last:
                return True, "%s (the rest have no skeletal mesh)" % line
            if len(parts) >= 4 and parts[0] == "ENEMIES":
                last = parts[1]
            if "ENEMIES" not in str(line):
                return False, line
        return False, "gave up after 200 batches"
    if stage in ("ue_presets", "ue_npcs"):
        step, word = ("presets", "PRESETS LEFT") if stage == "ue_presets" else ("npcs", "NPCS LEFT")
        g = {"GS_STEP": step, "GS_LIMIT": 15}
        if step == "presets":
            g["GS_PRESETS"] = "all"
        for _ in range(200):
            p = ue(exec_file(os.path.join(GS, "import_player.py"), g), 3600)
            line = str(last_line(p, word))
            log("  %s" % line)
            if line.endswith(" 0"):
                return True, line
            if word not in line:
                return False, line
        return False, "gave up after 200 batches"
    if stage == "ue_missions":
        p = run([PY, "tools/missions/import_missions.py", "--out", OUT], timeout=48 * 3600)
        return p.returncode == 0, last_line(p, "MISSIONS")
    raise ValueError(stage)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--convert-only", action="store_true")
    ap.add_argument("--unreal-only", action="store_true")
    ap.add_argument("--redo", nargs="*", default=[])
    a = ap.parse_args()
    st = state()
    if not a.unreal_only:
        data, piggs = find_i24(), find_piggs()
        log("convert: data %s, piggs %s, out %s" % (data, piggs, OUT))
        for s in CONVERT:
            if s in st and s not in a.redo:
                continue
            t0 = time.time()
            try:
                ok, info = convert(s, data, piggs)
            except Exception as e:  # keep going with the next stage
                ok, info = False, repr(e)
            log("%-11s %s  %s (%.0f s)" % (s, "OK" if ok else "FAIL", info, time.time() - t0))
            if ok:
                mark(s, info)
    if a.convert_only:
        return 0
    for s in UNREAL:
        if s in state() and s not in a.redo:
            continue
        for _ in range(60):
            if editor_free():
                break
            log("waiting: need exactly one Unreal editor open and no game running")
            time.sleep(60)
        else:
            log("%s SKIPPED: editor not available" % s)
            return 2
        t0 = time.time()
        try:
            ok, info = unreal_stage(s)
        except Exception as e:
            ok, info = False, repr(e)
        log("%-11s %s  %s (%.0f s)" % (s, "OK" if ok else "FAIL", info, time.time() - t0))
        if ok:
            mark(s, info)
    log("finished; see finish_imports_state.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

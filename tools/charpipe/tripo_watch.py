"""Watch the Tripo drop folder and turn every new download into a rigged, tested, Unreal-ready character.

    python tools/charpipe/tripo_watch.py            (process what is new, then keep watching; Ctrl+C to stop)
    python tools/charpipe/tripo_watch.py --once     (process what is new and exit)
    python tools/charpipe/tripo_watch.py --dry-run  (only list + classify everything, see tripo_catalog.py)

Folders (drop .glb / .gltf / .fbx / .obj from the Tripo website or bridge):
  C:/Users/rtcru/charpipe_test/tripo/in/                                  bodies and heads
  C:/Users/rtcru/ClaudeProjects/COHReborn/model-upgrade-samples/parts/hellions/   pieces / accessories (primary)
  C:/Users/rtcru/charpipe_test/tripo/incoming/                            treated like parts/hellions
Pieces: gear (cap, mask, goggles, bandana, chain, bat, pipe, gun, wallet, ...) -> bl_gear_item.py: sized by name,
socket/slot from the name, saved into the Hellion wardrobe (charpipe_test/wardrobe/hellions/<slot>/gear_<item>.glb +
wardrobe.json); after a batch a gear sheet is rendered on the test Hellion (tripo/ue_ready/previews/gear_sheet.jpg).
Clothing pieces (vest, shirt, jeans, boots, gloves, jacket...) need the base body they were exported with (Tripo
part export): they are logged and left for the kitbash flow (bl_kitbash_tuck/export + bl_wardrobe_make).
Per new file (name = character name; height and headless come from the name, see bl_tripo_clean.py:
kid/lean 172, veteran 178, average 180, heavy/brawler 183, big/biker 193, default 182; "headless"):
  clean (weld, floaters, normals, 50k tris, 2K textures, size) -> proxy head if headless -> autorig
  -> rig_cleanup -> fingers (smooth knuckles) -> weight polish -> FBX -> CoH clip test renders
Output: tripo/work/<name>/ (all steps + reports), tripo/ue_ready/<name>.fbx, tripo/ue_ready/previews/<name>.jpg
(idle front/side/back, run, Brawl, hit, death, extreme pose, fist). Log: tripo/watch_log.txt.
Skips files already processed (same size + mtime, in tripo/watch_state.json) and files still being
written (changed in the last 20 s). Waits while CPU_HOLD.txt or GPU_HOLD.txt exists in the project folder.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "C:/Users/rtcru/charpipe_test/tripo"
IN, WORK, UE = ROOT + "/in", ROOT + "/work", ROOT + "/ue_ready"
PARTS = "C:/Users/rtcru/ClaudeProjects/COHReborn/model-upgrade-samples/parts/hellions"
INCOMING = ROOT + "/incoming"
EXPORTS = ROOT + "/Tripo Exports"  # Robert's single drop folder (searched recursively; originals are never moved or deleted)
WARDROBE = "C:/Users/rtcru/charpipe_test/wardrobe/hellions"
GEAR_WORDS = ("cap", "hat", "beanie", "helmet", "hood", "mask", "goggle", "glasses", "visor", "respirator", "bandana", "scarf",
              "chain", "necklace", "bat", "pipe", "axe", "knife", "gun", "pistol", "shotgun", "smg", "sledge", "crowbar",
              "wrench", "machete", "weapon", "club", "hammer", "wallet", "pouch", "holster", "belt", "gear")
CLOTH_WORDS = ("vest", "shirt", "tee", "jeans", "pants", "trousers", "boots", "shoes", "gloves", "jacket", "hoodie", "coat")
HOLDS = ["C:/Users/rtcru/ClaudeProjects/COHReborn/CPU_HOLD.txt", "C:/Users/rtcru/ClaudeProjects/COHReborn/GPU_HOLD.txt"]
BLENDER = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
RENDER = "C:/Users/rtcru/ClaudeProjects/COHReborn/model-upgrade-samples/scripts/rig_test_render.py"
RENDERS = "C:/Users/rtcru/ClaudeProjects/COHReborn/model-upgrade-samples/renders"
EXTS = (".glb", ".gltf", ".fbx", ".obj")
BUILDS = [("kid", 172), ("lean", 172), ("veteran", 178), ("average", 180), ("heavy", 183), ("brawler", 183), ("big", 193), ("biker", 193)]


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)
    with open(ROOT + "/watch_log.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def editor_running():
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq UnrealEditor.exe", "/NH"], capture_output=True, text=True)
        return "UnrealEditor.exe" in r.stdout
    except Exception:  # noqa: BLE001
        return False


def hold_wait():
    # yield to hold files and to the shared Unreal editor (its GPU/RAM use comes first)
    while any(os.path.exists(h) for h in HOLDS) or editor_running():
        log("hold file present or Unreal editor running, waiting")
        time.sleep(60)


def bl(script, *args):
    hold_wait()
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = [l for l in r.stdout.splitlines() if any(k in l for k in ("_OK", "AUTORIG", "FINGERS", "CLEANUP", "RT_OK"))]
    err = [l for l in (r.stdout + r.stderr).splitlines() if "Error" in l or "Traceback" in l]
    if err and not ok:
        raise RuntimeError("%s: %s" % (os.path.basename(script), err[-1][:200]))
    return ok


def process(src):
    base = os.path.splitext(os.path.basename(src))[0]
    low = base.lower()
    hcm = next((h for k, h in BUILDS if k in low), 182)
    headless = "headless" in low
    w = os.path.join(WORK, base).replace("\\", "/")
    os.makedirs(w, exist_ok=True)
    t0 = time.time()
    s = lambda n: os.path.join(HERE, n)  # noqa: E731
    bl(s("bl_tripo_clean.py"), src, w + "/clean.glb", "--height-cm", str(hcm), *(["--headless"] if headless else []), "--report", w + "/clean.json")
    rig_in, cut = w + "/clean.glb", None
    if headless:
        bl(s("bl_proxy_head.py"), rig_in, w + "/proxy.glb", "--height-cm", str(hcm), "--report", w + "/proxy.json")
        rig_in, cut = w + "/proxy.glb", json.load(open(w + "/proxy.json"))["cut_above"]
    bl(s("bl_autorig.py"), rig_in, w + "/rig_raw.glb", "--height", str(hcm / 100.0), "--report", w + "/autorig.json")
    bl(s("rig_cleanup.py"), w + "/rig_raw.glb", w + "/rig_clean.glb", "--report", w + "/cleanup.json")
    bl(s("bl_fingers.py"), w + "/rig_clean.glb", w + "/fingers.glb", "--report", w + "/fingers.json")
    bl(s("bl_weight_polish.py"), w + "/fingers.glb", w + "/" + base + ".glb", *(["--cut-above", str(cut)] if cut else []), "--report", w + "/polish.json")
    bl(s("bl_export.py"), w + "/" + base + ".glb", UE, base)
    prev = ""
    if os.path.exists(RENDER):
        try:
            bl(RENDER, w + "/" + base + ".glb", base)
            from PIL import Image
            views = ["idle_front", "idle_side", "idle_back", "run", "brawl", "hit", "death", "extreme", "fist"]
            sheet = Image.new("RGB", (9 * 240, 360))
            for i, v in enumerate(views):
                p = "%s/RT_%s_%s.png" % (RENDERS, base, v)
                if os.path.exists(p):
                    sheet.paste(Image.open(p).convert("RGB").resize((240, 360)), (i * 240, 0))
            os.makedirs(UE + "/previews", exist_ok=True)
            prev = UE + "/previews/" + base + ".jpg"
            sheet.save(prev, quality=86)
        except Exception as e:  # noqa: BLE001  previews are optional
            log("  preview failed for %s: %s" % (base, e))
    c = json.load(open(w + "/clean.json"))
    log("OK %s: %d -> %d tris, %d cm%s, %.0f s -> %s/%s.fbx %s" % (base, c["in_tris"], c["out_tris"], hcm,
        " headless" if headless else "", time.time() - t0, UE, base, ("preview " + prev) if prev else ""))


def process_gear(src, name=None):
    base = name or os.path.splitext(os.path.basename(src))[0].lower().replace(" ", "_")
    body = WARDROBE + "/body/base.glb"
    r = bl(os.path.join(HERE, "bl_gear_item.py"), body, src, WARDROBE, "--name", base)
    log("OK gear %s %s" % (base, " ".join(x for x in r if "GEAR_ITEM_OK" in x)[:200]))


def gear_sheet():
    """render every gear item on the test Hellion (base body + tee + jeans + boots): idle front + Brawl"""
    try:
        wd = json.load(open(WARDROBE + "/wardrobe.json"))
    except Exception:  # noqa: BLE001
        return
    gear = [k for k in wd.get("items", {}) if k.startswith("gear_")]
    if not gear or not os.path.exists(RENDER):
        return
    from PIL import Image, ImageDraw
    base = [WARDROBE + "/" + wd["items"][k]["file"] for k in ("tee", "jeans", "boots") if k in wd.get("items", {})]
    sheet = Image.new("RGB", (len(gear) * 2 * 200, 330), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    env = dict(os.environ, RT_QUICK="1")
    for i, g in enumerate(gear):
        hold_wait()
        subprocess.run([BLENDER, "-b", "--factory-startup", "-P", RENDER, "--", WARDROBE + "/body/base.glb", g, *base,
                        WARDROBE + "/" + wd["items"][g]["file"]], capture_output=True, env=env)
        for j, v in enumerate(("idle_front", "brawl")):
            p = "%s/RT_%s_%s.png" % (RENDERS, g, v)
            if os.path.exists(p):
                sheet.paste(Image.open(p).convert("RGB").resize((200, 300)), ((2 * i + j) * 200, 0))
        d.text((i * 400 + 6, 306), "%s (%s)" % (g, wd["items"][g]["slot"]), fill=(230, 230, 230))
    os.makedirs(UE + "/previews", exist_ok=True)
    sheet.save(UE + "/previews/gear_sheet.jpg", quality=86)
    log("gear sheet: %s (%d items)" % (UE + "/previews/gear_sheet.jpg", len(gear)))


def kind(folder, f):
    low = f.lower()
    if folder == IN:
        return "gear" if low.startswith("gear_") else "body"
    if "hair" in low:
        return "gear"
    if any(w in low for w in ("headless", "hellion_", "body", "full")) and not low.startswith("gear_"):
        return "body"
    if any(w in low for w in CLOTH_WORDS) and not any(w in low for w in GEAR_WORDS):
        return "cloth"
    return "gear"


def scan(state):
    done, gear_done = 0, 0
    if "--dry-run" in sys.argv:
        import tripo_catalog as TC
        TC.main()
        return 0
    files = []
    # Robert's export tree: classified by folder path (tripo_catalog), zips extracted to the _unzipped cache
    import tripo_catalog as TC
    groups = {}
    for r in TC.catalogue(EXPORTS, do_extract=True):
        if r.get("duplicate_of_loose"):
            continue
        key = "exports:" + r["rel"]
        st_ = os.stat(TC.lp(r["path"]))
        sig = "%d:%d" % (st_.st_size, int(st_.st_mtime))
        if state.get(key) == sig or time.time() - st_.st_mtime < 20:
            continue
        name = (r["character"] + "_" + r["piece"]).lower().replace(" ", "_").replace("/", "_").replace("#", "")
        try:
            if r["type"] == "body":
                log("NEW body %s -> rig" % r["rel"])
                process(r["path"])
            elif r["type"] == "gear":
                log("NEW gear %s" % r["rel"])
                process_gear(r["path"], name)
                gear_done += 1
            else:  # cloth / setpart / head / ?: grouped per character for the kitbash / set-assembly flow
                groups.setdefault((r["character"], r["type"]), []).append(r["rel"])
            state[key] = sig
        except Exception as e:  # noqa: BLE001
            log("FAIL %s: %s" % (r["rel"], e))
            state[key] = sig + ":failed"
        json.dump(state, open(ROOT + "/watch_state.json", "w"), indent=1)
    for (ch, t), rels in sorted(groups.items()):
        log("  %s %s x%d waiting for the %s flow: %s" % (ch, t, len(rels), "kitbash" if t == "cloth" else "set assembly" if t == "setpart" else "manual", "; ".join(rels[:6])))
    for folder in (IN, PARTS, INCOMING):
        if not os.path.isdir(folder):
            continue
        for dp, _, fs in os.walk(folder):
            for f in sorted(fs):
                if f.lower().endswith(EXTS) and ".fbm" not in dp:
                    files.append((folder, dp, f))
    for folder, dp, f in files:
        if True:
            p = os.path.join(dp, f).replace("\\", "/")
            f = os.path.basename(dp) + "_" + f if folder == EXPORTS and dp != folder else f
            st = os.stat(p)
            sig = "%d:%d" % (st.st_size, int(st.st_mtime))
            key = p if folder != IN else f
            if state.get(key) == sig or time.time() - st.st_mtime < 20:
                continue
            k = kind(folder, f)
            log("NEW %s (%s)" % (p, k))
            try:
                if k == "body":
                    process(p)
                elif k == "gear":
                    process_gear(p)
                    gear_done += 1
                else:
                    log("  clothing piece: needs the base body it was exported with (kitbash flow), not processed")
                state[key] = sig
            except Exception as e:  # noqa: BLE001
                log("FAIL %s: %s" % (f, e))
                state[key] = sig + ":failed"
            json.dump(state, open(ROOT + "/watch_state.json", "w"), indent=1)
            done += 1
    if gear_done:
        gear_sheet()
    return done


def main():
    for d in (IN, WORK, UE, PARTS, INCOMING, EXPORTS):
        os.makedirs(d, exist_ok=True)
    sp = ROOT + "/watch_state.json"
    state = json.load(open(sp)) if os.path.exists(sp) else {}
    n = scan(state)
    if "--once" in sys.argv or "--dry-run" in sys.argv:
        log("once: %d file(s) processed" % n)
        return
    log("watching %s, %s, %s (Ctrl+C to stop)" % (IN, PARTS, INCOMING))
    while True:
        time.sleep(30)
        scan(state)


if __name__ == "__main__":
    main()

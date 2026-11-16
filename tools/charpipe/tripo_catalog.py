"""Catalogue Robert's Tripo export tree: every model (loose or inside zips), classified by its folder path.

    python tools/charpipe/tripo_catalog.py                (dry run: table + summary, nothing extracted or processed)
    python tools/charpipe/tripo_catalog.py --extract      (also extract new zips into the cache)

Tree: <root>/<Character>/<piece folder>/.../<file>  (e.g. Tripo Exports/Hellions/h_hoody/Untitled_#130.fbx)
  * character = first folder under the root ("Hellions", "Clockwork"); loose files at the root -> "_loose"
  * piece name = the nearest folder that is not a generic export folder (or the zip name), else the file name;
    generic file names (Untitled_#81, model, tripo_*, base, mesh) never decide anything on their own
  * type, from the piece name words (CamelCase / _ / - / spaces split; "h_" prefix dropped):
      body   base, body, naked, nude, headless, mannequin (one base body per character for the kitbash)
      head   head, face, bust (a library head)
      cloth  vest, shirt, tshirt, tee, undershirt, tank, jeans, pants, cargo, trousers, shorts, boots, shoes,
             sneakers, gloves, jacket, longjacket, hoody, hoodie, coat, trench, sweater (exact words first)
      gear   hair, cap, hat, beanie, helmet, mask, goggles, bandana, chain, bat, pipe, axe, knife, gun, wallet,
             tool, belt... (also found inside compound words, e.g. "hipchainandtool")
      reference  a file named full* / whole* (the unsplit model of a part set): used only as the placement guide
      setpart  unnamed parts (generic names only) inside a set folder (e.g. Clockwork/Clockwork1/Untitled #212.zip):
             Tripo part exports share one coordinate space, so a set is assembled as one character
      ?      anything else (reported, not processed)
  * zips: members are listed first; only model / texture / material files with safe relative paths are accepted
    (no absolute paths, no "..", no drive letters); extraction goes to
    C:/Users/rtcru/charpipe_test/tripo/_unzipped/<zip path relative to root, without .zip>/, never next to or over
    the originals; a zip already extracted with the same size + mtime is skipped
  * long paths (> 240 chars) are opened with the \\\\?\\ prefix
Originals are only read, never moved, renamed or deleted.
"""
import json
import os
import re
import sys
import time
import zipfile

ROOT = "C:/Users/rtcru/charpipe_test/tripo/Tripo Exports"
CACHE = "C:/Users/rtcru/charpipe_test/tripo/_unzipped"
MODEL = (".glb", ".gltf", ".fbx", ".obj")
OK_IN_ZIP = MODEL + (".mtl", ".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tif", ".tiff", ".bin", ".webp", ".exr")
GENERIC = re.compile(r"^(untitled.*|model|mesh|base_?mesh|tripo.*|export.*|output.*|textured.*|[0-9a-f\-]{8,}|\d+|fbm)$", re.I)
BODY = {"base", "body", "naked", "nude", "headless", "mannequin", "basebody"}
HEAD = {"head", "face", "bust"}
CLOTH = {"vest", "shirt", "tshirt", "tee", "undershirt", "tank", "tanktop", "jeans", "pants", "cargo", "cargos", "trousers",
         "shorts", "boots", "boot", "shoes", "sneakers", "gloves", "glove", "jacket", "longjacket", "hoody", "hoodie", "coat",
         "trench", "sweater", "overalls", "coverall", "skirt", "leggings"}
GEAR = ("hair", "cap", "hat", "beanie", "helmet", "hood", "mask", "goggle", "glasses", "visor", "bandana", "scarf", "chain",
        "necklace", "bat", "pipe", "axe", "knife", "gun", "pistol", "shotgun", "smg", "sledge", "crowbar", "wrench", "machete",
        "weapon", "club", "hammer", "wallet", "pouch", "holster", "belt", "tool", "badge", "patch", "earring", "piercing")


def lp(p):
    """long-path-safe absolute path on Windows"""
    p = os.path.abspath(p)
    if os.name == "nt" and len(p) > 240 and not p.startswith("\\\\?\\"):
        return "\\\\?\\" + p.replace("/", "\\")
    return p


def words(s):
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = re.sub(r"^h[_ ]", "", s.strip(), flags=re.I)
    return [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]


def piece_name(parts, fname):
    for d in reversed(parts):
        if not GENERIC.match(d) and not d.lower().endswith(".fbm"):
            return d
    stem = os.path.splitext(fname)[0]
    return stem if not GENERIC.match(stem) else (parts[-1] if parts else stem)


def classify(character, piece, fname):
    if re.match(r"^(full|whole)", os.path.splitext(fname)[0].lower()):
        return "reference"
    ws = words(piece)
    joined = "".join(ws)
    cw = [w for w in ws if w.lower() != character.lower().rstrip("s")]
    if set(cw) & BODY or (joined.startswith("base") and not set(cw) & CLOTH):
        return "body"
    if "hair" in joined:
        return "gear"
    if set(cw) & HEAD and not set(cw) & CLOTH:
        return "head"
    if set(cw) & CLOTH:
        return "cloth"
    if any(g in joined for g in GEAR):
        return "gear"
    if any(c in joined for c in CLOTH if len(c) > 3):
        return "cloth"
    return "?"


def zip_members(zp):
    good, bad = [], []
    try:
        with zipfile.ZipFile(lp(zp)) as z:
            for i in z.infolist():
                n = i.filename.replace("\\", "/")
                if i.is_dir():
                    continue
                unsafe = n.startswith("/") or ":" in n.split("/")[0] or any(x == ".." for x in n.split("/"))
                if unsafe or not n.lower().endswith(OK_IN_ZIP):
                    bad.append(n)
                else:
                    good.append(n)
    except zipfile.BadZipFile:
        bad.append("<not a valid zip>")
    return good, bad


def extract(zp, rel, state):
    st = os.stat(lp(zp))
    sig = "%d:%d" % (st.st_size, int(st.st_mtime))
    dst = os.path.join(CACHE, os.path.splitext(rel)[0])
    if state.get(rel) == sig and os.path.isdir(lp(dst)):
        return dst, False
    good, _ = zip_members(zp)
    with zipfile.ZipFile(lp(zp)) as z:
        for n in good:
            out = os.path.normpath(os.path.join(dst, n))
            if not out.startswith(os.path.normpath(dst)):
                continue
            os.makedirs(lp(os.path.dirname(out)), exist_ok=True)
            with z.open(n) as src, open(lp(out), "wb") as f:
                f.write(src.read())
    state[rel] = sig
    return dst, True


def catalogue(root=ROOT, do_extract=False):
    rows = []
    zstate_p = os.path.join(CACHE, "_zip_state.json")
    zstate = json.load(open(zstate_p)) if os.path.exists(zstate_p) else {}
    for dp, dns, fns in os.walk(lp(root)):
        dns[:] = [d for d in dns if not d.lower().endswith(".fbm")]
        rel_dir = os.path.relpath(dp, lp(root))
        parts = [] if rel_dir == "." else rel_dir.replace("\\", "/").split("/")
        character = parts[0] if parts else "_loose"
        for f in sorted(fns):
            full = os.path.join(dp, f)
            rel = "/".join(parts + [f])
            plen = len(os.path.abspath(full).replace("\\\\?\\", ""))
            if f.lower().endswith(MODEL):
                pn = piece_name(parts[1:], f)
                t = classify(character, pn, f)
                if t == "?" and GENERIC.match(os.path.splitext(f)[0].replace(" ", "_")) and len(parts) >= 2:
                    t, pn = "setpart", parts[-1] + "/" + f
                rows.append(dict(path=full, rel=rel, len=plen, character=character, piece=pn, type=t, source="file"))
            elif f.lower().endswith(".zip"):
                good, bad = zip_members(full)
                zname = os.path.splitext(f)[0]
                models = [n for n in good if n.lower().endswith(MODEL)]
                dst = None
                if do_extract and models:
                    dst, _ = extract(full, rel, zstate)
                if not models:
                    rows.append(dict(path=full, rel=rel, len=plen, character=character, piece=zname, type="?",
                                     source="zip (no model inside)", rejected=bad))
                for n in models:
                    inner = n.split("/")
                    pn = piece_name(parts[1:] + [zname] + inner[:-1], inner[-1])
                    t = classify(character, pn, inner[-1])
                    if t == "?" and GENERIC.match(zname.replace(" ", "_")) and len(parts) >= 2:
                        t, pn = "setpart", parts[-1] + "/" + zname
                    rows.append(dict(path=os.path.join(dst, n) if dst else full + "::" + n, rel=rel + "::" + n, len=plen,
                                     character=character, piece=pn, type=t,
                                     source="zip" + (" (extracted)" if dst else ""), rejected=bad))
    if do_extract:
        os.makedirs(CACHE, exist_ok=True)
        json.dump(zstate, open(zstate_p, "w"), indent=1)
    # a loose copy and a zip with the same piece: keep both rows but flag the zip copy as duplicate
    seen = {(r["character"], r["piece"].lower()) for r in rows if r["source"] == "file"}
    for r in rows:
        if r["source"].startswith("zip") and (r["character"], r["piece"].lower()) in seen:
            r["duplicate_of_loose"] = True
    return rows


def main():
    rows = catalogue(do_extract="--extract" in sys.argv)
    print("%-6s %-10s %-28s %-4s %-14s %s" % ("type", "character", "piece", "len", "source", "relative path"))
    for r in rows:
        print("%-6s %-10s %-28s %-4d %-14s %s%s" % (r["type"], r["character"][:10], r["piece"][:28], r["len"], r["source"][:14],
                                                  r["rel"], "  [dup of loose file]" if r.get("duplicate_of_loose") else ""))
    from collections import Counter, defaultdict
    by = defaultdict(Counter)
    for r in rows:
        if not r.get("duplicate_of_loose"):
            by[r["character"]][r["type"]] += 1
    print("\nSUMMARY")
    for c, cnt in sorted(by.items()):
        print("  %-12s %s" % (c, ", ".join("%s %d" % kv for kv in sorted(cnt.items()))))
    unk = [r for r in rows if r["type"] == "?"]
    longp = [r for r in rows if r["len"] > 240]
    rej = sorted({b for r in rows for b in r.get("rejected", [])})
    print("  unclassified: %d%s" % (len(unk), "".join("\n    " + r["rel"] for r in unk)))
    print("  paths over 240 chars: %d (handled with the \\\\?\\ prefix)" % len(longp))
    print("  zip members rejected (unsafe path or not a model/texture): %d%s" % (len(rej), "".join("\n    " + b for b in rej[:20])))


if __name__ == "__main__":
    main()

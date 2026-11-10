"""Extract the original power and powerset icons as PNG.

    python tools/powers/export_icons.py <piggs dir> <powers out dir>

Reads the IconName of every power and powerset in powers.json /
powersets.json (export_powers.py), finds the matching .texture in the game's
.pigg archives and writes <out>/icons/<name>.png. Lists the ones it could
not find in icons_missing.txt.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "coh2unreal"))
from coh2unreal.pigg import AssetStore  # noqa: E402
from coh2unreal.texture import to_png  # noqa: E402

PIGGS, OUT = sys.argv[1], sys.argv[2]
ICONS = os.path.join(OUT, "icons")
os.makedirs(ICONS, exist_ok=True)
store = AssetStore(pigg_paths=glob.glob(os.path.join(PIGGS, "*.pigg")))

wanted = set()
for p in json.load(open(os.path.join(OUT, "powers.json"), encoding="utf-8")):
    if p.get("IconName"):
        wanted.add(p["IconName"])
for s in json.load(open(os.path.join(OUT, "powersets.json"), encoding="utf-8")):
    if s.get("icon"):
        wanted.add(s["icon"])

found, missing = 0, []
for icon in sorted(wanted):
    stem = os.path.splitext(icon)[0]
    hits = store.find_basename(stem + ".texture")
    # prefer the GUI icon folders over same-named world textures
    hits.sort(key=lambda r: (0 if "/gui/" in r or "/icons/" in r else 1, r))
    png = None
    for rel in hits:
        png, _ = to_png(store.read(rel))
        if png:
            break
    if not png:
        missing.append(icon)
        continue
    open(os.path.join(ICONS, stem.lower() + ".png"), "wb").write(png)
    found += 1
open(os.path.join(OUT, "icons_missing.txt"), "w").write("\n".join(missing))
print("icons wanted", len(wanted), "written", found, "missing", len(missing))

"""Extract the original City of Heroes UI art and fonts.

    python tools/ui/export_gui.py <piggs dir> <out dir>

Writes every texture under texture_library/gui/ as <out>/gui/.../<name>.png
(original folder layout, lower case), every font from fonts.pigg to
<out>/fonts/, and the English menu texts to <out>/texts/. Needs stage*.pigg,
texGui1.pigg, fonts.pigg and texts.pigg (dists.thunderspy.org/piggs/).
Also writes <out>/ui_art.json: texture name (lower case, no extension) ->
[width, height, png path]. The archive stores GUI art padded out to a power of
two (edge pixels repeated); the .texture header keeps the original size, so
each PNG is cropped back to it. The UI code positions everything by that size.
Failures are listed in <out>/_failed.txt. Output is game data: keep it out of git.

Unreal: copy <out> to <Project>/Content/UI/ (CoHUIArt.cpp reads it at runtime).
"""
import glob
import io
import json
import struct
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "coh2unreal"))
from coh2unreal.pigg import AssetStore  # noqa: E402
from coh2unreal.texture import to_png  # noqa: E402

PIGGS, OUT = sys.argv[1], sys.argv[2]
store = AssetStore(pigg_paths=sorted(glob.glob(os.path.join(PIGGS, "*.pigg"))))

def crop(png, w, h):
    """Cuts the power-of-two padding off (the original art is the top-left w x h)."""
    from PIL import Image
    img = Image.open(io.BytesIO(png))
    if w <= 0 or h <= 0 or (w >= img.width and h >= img.height):
        return png
    out = io.BytesIO()
    img.crop((0, 0, min(w, img.width), min(h, img.height))).save(out, "PNG")
    return out.getvalue()


ok, failed, manifest = 0, [], {}
for name in store.names():
    low = name.lower()
    if "/gui/" in low and low.endswith(".texture"):
        dest = os.path.join(OUT, low.split("texture_library/", 1)[1][:-len(".texture")] + ".png")
        try:
            png, _ = to_png(store.read(name))
            if png is None:
                raise ValueError("unsupported format")
            data = store.read(name)
            w, h = struct.unpack_from("<ii", data, 8)
            png = crop(png, w, h)
            key = os.path.basename(low)[:-len(".texture")]
            rel = os.path.relpath(dest, OUT).replace(os.sep, "/")
            # the same name in several folders: prefer the HUD art
            if key not in manifest or ("/hud/" in rel and "/hud/" not in manifest[key][2]):
                manifest[key] = [w, h, rel]
        except Exception as e:  # keep going, list it
            failed.append(f"{name}: {e}")
            continue
    elif low.startswith("fonts/") or low.startswith("texts/english/menus/"):
        dest, png = os.path.join(OUT, low), store.read(name)
    else:
        continue
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(png)
    ok += 1

with open(os.path.join(OUT, "ui_art.json"), "w") as f:
    json.dump(manifest, f, indent=0, sort_keys=True)
with open(os.path.join(OUT, "_failed.txt"), "w") as f:
    f.write("\n".join(failed))
print(f"{ok} files written, {len(failed)} failed")

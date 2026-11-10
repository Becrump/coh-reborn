"""Extract the original City of Heroes UI art and fonts.

    python tools/ui/export_gui.py <piggs dir> <out dir>

Writes every texture under texture_library/gui/ as <out>/gui/.../<name>.png
(original folder layout, lower case), every font from fonts.pigg to
<out>/fonts/, and the English menu texts to <out>/texts/. Needs stage*.pigg,
texGui1.pigg, fonts.pigg and texts.pigg (dists.thunderspy.org/piggs/).
Failures are listed in <out>/_failed.txt. Output is game data: keep it out of git.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "coh2unreal"))
from coh2unreal.pigg import AssetStore  # noqa: E402
from coh2unreal.texture import to_png  # noqa: E402

PIGGS, OUT = sys.argv[1], sys.argv[2]
store = AssetStore(pigg_paths=sorted(glob.glob(os.path.join(PIGGS, "*.pigg"))))

ok, failed = 0, []
for name in store.names():
    low = name.lower()
    if "/gui/" in low and low.endswith(".texture"):
        dest = os.path.join(OUT, low.split("texture_library/", 1)[1][:-len(".texture")] + ".png")
        try:
            png, _ = to_png(store.read(name))
            if png is None:
                raise ValueError("unsupported format")
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

with open(os.path.join(OUT, "_failed.txt"), "w") as f:
    f.write("\n".join(failed))
print(f"{ok} files written, {len(failed)} failed")

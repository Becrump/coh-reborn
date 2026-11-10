"""Writes the Climb power's icon (32 px, like the original inherent icons): the grey
disc of Inherent_Sprint with a ladder and an up arrow.

    python tools/make_climb_icon.py "<Unreal project>/Content/CoH/Data/Icons/inherent_climb.cohicon"
"""
import sys

from PIL import Image, ImageDraw, ImageFilter

S = 256                                       # drawn large, shrunk to 32
im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
# the disc: a light rim, a darker body, a soft highlight at the top left
d.ellipse((6, 6, S - 6, S - 6), fill=(150, 150, 154, 255))
d.ellipse((22, 22, S - 22, S - 22), fill=(118, 118, 124, 255))
hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(hl).ellipse((40, 30, 170, 130), fill=(255, 255, 255, 70))
im = Image.alpha_composite(im, hl.filter(ImageFilter.GaussianBlur(18)))
d = ImageDraw.Draw(im)
dark, light = (28, 28, 32, 255), (240, 240, 244, 255)
# the ladder: two rails and rungs, outlined dark
for off, col, w in ((5, dark, 20), (0, light, 11)):
    for x in (92, 164):
        d.line((x + off * 0.3, 52 + off, x - off * 0.3, 214 - off), fill=col, width=w)
    for y in range(78, 214, 34):
        d.line((92, y + off * 0.3, 164, y + off * 0.3), fill=col, width=w - 3)
# the arrow over it
d.polygon([(128, 18), (176, 70), (146, 70), (146, 96), (110, 96), (110, 70), (80, 70)], fill=(255, 196, 64, 255), outline=dark)
im = im.resize((32, 32), Image.LANCZOS)
im.save(sys.argv[1], format="PNG")
print("wrote", sys.argv[1])

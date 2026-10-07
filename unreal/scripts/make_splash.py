import sys
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw
src, outdir = sys.argv[1], sys.argv[2]
art = Image.open(src).convert("RGB")

def compose(W, H):
    # blurred, darkened fill behind the portrait art so it reads at 16:9
    s = max(W / art.width, H / art.height)
    bg = art.resize((round(art.width * s), round(art.height * s)), Image.LANCZOS)
    x, y = (bg.width - W) // 2, (bg.height - H) // 4
    bg = bg.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(W / 40))
    bg = ImageEnhance.Brightness(bg).enhance(0.45)
    fh = H
    fw = round(art.width * fh / art.height)
    fg = art.resize((fw, fh), Image.LANCZOS)
    # feather the art's left/right edges into the fill
    mask = Image.new("L", (fw, fh), 255)
    d = ImageDraw.Draw(mask)
    feather = fw // 12
    for i in range(feather):
        a = round(255 * i / feather)
        d.line([(i, 0), (i, fh)], fill=a)
        d.line([(fw - 1 - i, 0), (fw - 1 - i, fh)], fill=a)
    bg.paste(fg, ((W - fw) // 2, 0), mask)
    return bg

compose(1920, 1080).save(f"{outdir}/LoadingScreen.png", optimize=True)
compose(960, 540).save(f"{outdir}/Splash.bmp")
compose(960, 540).save(f"{outdir}/EdSplash.bmp")

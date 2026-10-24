"""Reader for City of Heroes .texture files.

Format follows TextureFileHeader in Game/src/render/tex.h: a small header,
the original file name, optional preload mips, then an embedded .dds or
.tga file.
"""
import io
import struct


def unwrap(data):
    """Returns (original_name, payload_bytes) from a .texture file."""
    header_size, file_size = struct.unpack_from("<ii", data, 0)
    end = data.index(b"\0", 32)
    name = data[32:end].decode("latin-1")
    payload = data[header_size:header_size + file_size]
    return name, payload


def to_png(data):
    """Converts a .texture file to PNG bytes. Needs Pillow.

    Returns (png_bytes, has_alpha) or (None, False) if it can't decode.
    """
    from PIL import Image
    name, payload = unwrap(data)
    try:
        img = Image.open(io.BytesIO(payload))
        img.load()
    except Exception:
        return None, False
    has_alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
    if has_alpha:
        img = img.convert("RGBA")
        if img.getextrema()[3][0] == 255:
            has_alpha = False
            img = img.convert("RGB")
    else:
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, "PNG", optimize=False)
    return out.getvalue(), has_alpha


def combine_alpha(color_data, mask_data):
    """Colour from one .texture and opacity from another's alpha channel.

    Foliage materials keep the leaf silhouette in a companion "_a" texture
    (their DualColor1 layer). Returns PNG bytes or None.
    """
    from PIL import Image
    try:
        color = Image.open(io.BytesIO(unwrap(color_data)[1]))
        mask = Image.open(io.BytesIO(unwrap(mask_data)[1]))
        color.load()
        mask.load()
    except Exception:
        return None
    color = color.convert("RGB")
    if "A" in mask.getbands():
        alpha = mask.getchannel("A")
    else:
        alpha = mask.convert("L")
    if alpha.size != color.size:
        alpha = alpha.resize(color.size)
    color.putalpha(alpha)
    out = io.BytesIO()
    color.save(out, "PNG", optimize=False)
    return out.getvalue()

"""Reads a zone's time-of-day sky (scene file -> sky file) for Unreal.

A zone's main map file names its scene ("Scenefile scenes/....txt"); the
scene lists skies ("Sky sun_....txt", the first is the normal one), and the
sky file holds "suntime" keyframes: hour, sun (diffuse) and ambient colour,
fog colour and distance, and which sky dome to show. Colours are 0-255 but
the game allows overbright values above 255.
"""
import posixpath

from .maplayout import _lines


def find_scene(store, map_path):
    """Returns the scene file path for a map layer, or None."""
    folder = posixpath.dirname(map_path.replace("\\", "/").lower())
    main = posixpath.join(folder, posixpath.basename(folder) + ".txt")
    if main not in store:
        return None
    for tok in _lines(store.read(main).decode("latin-1")):
        if tok[0].lower() == "scenefile" and len(tok) > 1:
            return tok[1].replace("\\", "/").lower()
    return None


def first_sky(store, scene_path):
    """Returns the path of the scene's first (default) sky file, or None."""
    if not scene_path or scene_path not in store:
        return None
    for tok in _lines(store.read(scene_path).decode("latin-1")):
        if tok[0].lower() == "sky" and len(tok) > 1:
            return "scenes/skies/" + tok[1].lower()
    return None


_COLOR_KEYS = {"diffuse": "sun", "ambient": "ambient", "fogcolor": "fog",
               "backgroundcolor": "background"}


def parse_sky(text):
    """Returns {"lamp_light_time": [on, off] or None, "keys": [...]}, keys
    sorted by hour."""
    out = {"lamp_light_time": None, "keys": []}
    block, cur = None, None
    for tok in _lines(text):
        key = tok[0].lower()
        if key in ("sun", "suntime", "cloud") and block is None:
            block = key
            if key == "suntime":
                cur = {}
            continue
        if key == "end":
            if block == "suntime" and "time" in cur:
                out["keys"].append(cur)
            block, cur = None, None
            continue
        try:
            if block == "sun" and key == "lamplighttime" and len(tok) >= 3:
                out["lamp_light_time"] = [float(tok[1]), float(tok[2])]
            elif block == "suntime":
                if key == "time":
                    cur["time"] = float(tok[1])
                elif key in _COLOR_KEYS and len(tok) >= 4:
                    cur[_COLOR_KEYS[key]] = [float(v) for v in tok[1:4]]
                elif key == "fogdist" and len(tok) >= 3:
                    cur["fog_dist_ft"] = [float(tok[1]), float(tok[2])]
                elif key == "skyname" and len(tok) > 1:
                    cur["sky"] = tok[1]
        except ValueError:
            pass
    out["keys"].sort(key=lambda k: k["time"])
    return out


def load(store, map_path):
    """Returns the parsed default sky for a map, with its source paths, or
    None if the map has no scene/sky."""
    scene = find_scene(store, map_path)
    sky = first_sky(store, scene)
    if not sky or sky not in store:
        return None
    data = parse_sky(store.read(sky).decode("latin-1"))
    data["scene"], data["sky_file"] = scene, sky
    return data

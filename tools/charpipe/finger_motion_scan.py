"""Read-only scan: which animation clips really move the fingers (glTF / GLB / FBX).

    python tools/charpipe/finger_motion_scan.py <file_or_dir> [...] [--json out.json] [--min-deg 5]

glTF / GLB are read directly (no Blender): for every animation, the rotation channels of finger nodes
(Index/Middle/Ring/Pinky/Thumb, CoH RING*/F1*/F2*/T1-3*, mixamorig:*Hand*, *_01_l ...) are decoded and a clip counts
as "finger motion" when any finger bone rotates more than --min-deg (default 5 deg) away from its first key during
the clip. Static or bind-pose keys do not count. FBX files are handed to Blender headless (bl_finger_scan helper
inside this script) with the same rule.
Prints one line per file and a summary; --json writes the per-clip results.
"""
import base64
import json
import os
import re
import struct
import subprocess
import sys

import numpy as np

FINGER_RX = re.compile(r"(index|middle|ring|pinky|thumb|^RING|^F[12]_|^T[123]_|finger)", re.I)
CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
BLENDER = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"


def load_gltf(path):
    if path.lower().endswith(".glb"):
        data = open(path, "rb").read()
        jl = struct.unpack("<I", data[12:16])[0]
        g = json.loads(data[20:20 + jl])
        bins = [data[20 + jl + 8:]]
    else:
        g = json.load(open(path, encoding="utf-8"))
        bins = []
        for b in g.get("buffers", []):
            uri = b.get("uri", "")
            if uri.startswith("data:"):
                bins.append(base64.b64decode(uri.split(",", 1)[1]))
            else:
                bins.append(open(os.path.join(os.path.dirname(path), uri), "rb").read())
    return g, bins


def accessor(g, bins, i):
    a = g["accessors"][i]
    bv = g["bufferViews"][a["bufferView"]]
    buf = bins[bv.get("buffer", 0)]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    n, nc, dt = a["count"], NC[a["type"]], CT[a["componentType"]]
    stride = bv.get("byteStride", 0)
    item = nc * np.dtype(dt).itemsize
    if stride and stride != item:
        raw = np.frombuffer(buf, np.uint8, count=stride * (n - 1) + item, offset=off).reshape(-1)
        arr = np.stack([np.frombuffer(raw[k * stride:k * stride + item].tobytes(), dt) for k in range(n)])
    else:
        arr = np.frombuffer(buf, dt, count=n * nc, offset=off).reshape(n, nc)
    if a.get("normalized") and dt != np.float32:
        arr = arr.astype(np.float32) / np.iinfo(dt).max
    return arr.astype(np.float64)


def scan_gltf(path, min_deg):
    g, bins = load_gltf(path)
    names = [n.get("name", "") for n in g.get("nodes", [])]
    out = []
    for an in g.get("animations", []):
        best, bone = 0.0, None
        for ch in an["channels"]:
            t = ch["target"]
            if t.get("path") != "rotation" or "node" not in t:
                continue
            nm = names[t["node"]]
            if not FINGER_RX.search(nm.split(":")[-1]):
                continue
            q = accessor(g, bins, an["samplers"][ch["sampler"]]["output"])
            if len(q) < 2:
                continue
            q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-9)
            dots = np.clip(np.abs(q @ q[0]), 0, 1)
            ang = float(np.degrees(2 * np.arccos(dots)).max())
            if ang > best:
                best, bone = ang, nm
        out.append({"clip": an.get("name", "?"), "finger_max_deg": round(best, 1), "bone": bone, "fingers": best > min_deg})
    return out


BL_HELPER = r'''
import bpy, sys, json, re, math
p = sys.argv[sys.argv.index("--") + 1]; mind = float(sys.argv[-1])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=p, automatic_bone_orientation=False)
rx = re.compile(r"(index|middle|ring|pinky|thumb|finger)", re.I)
arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
res = []
for act in bpy.data.actions:
    if arm is None: break
    arm.animation_data_create(); arm.animation_data.action = act
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    fb = [pb for pb in arm.pose.bones if rx.search(pb.name.split(":")[-1])]
    base = {}; best = 0.0; bone = None
    for f in range(f0, f1 + 1, max(1, (f1 - f0) // 60)):
        bpy.context.scene.frame_set(f)
        for pb in fb:
            q = pb.matrix_basis.to_quaternion()
            if pb.name not in base: base[pb.name] = q; continue
            a = math.degrees(base[pb.name].rotation_difference(q).angle)
            if a > best: best, bone = a, pb.name
    res.append({"clip": act.name, "finger_max_deg": round(best, 1), "bone": bone, "fingers": best > mind})
print("FSCAN" + json.dumps(res))
'''


def scan_fbx(path, min_deg):
    hp = os.path.join(os.environ.get("TEMP", "."), "bl_finger_scan.py")
    open(hp, "w").write(BL_HELPER)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", hp, "--", path, str(min_deg)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    line = next((l for l in r.stdout.splitlines() if l.startswith("FSCAN")), None)
    return json.loads(line[5:]) if line else [{"clip": "?", "error": (r.stderr or r.stdout)[-200:]}]


def main():
    args, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False
        elif a in ("--json", "--min-deg"):
            skip = True  # the next argument is this option's value, not an input path
        elif not a.startswith("--"):
            args.append(a)
    mind = float(sys.argv[sys.argv.index("--min-deg") + 1]) if "--min-deg" in sys.argv else 5.0
    files = []
    for a in args:
        if os.path.isdir(a):
            for dp, _, fs in os.walk(a):
                files += [os.path.join(dp, f) for f in fs if f.lower().endswith((".gltf", ".glb", ".fbx")) and not f.lower().endswith(".ue.gltf")]
        else:
            files.append(a)
    allr = {}
    for f in sorted(files):
        try:
            r = scan_fbx(f, mind) if f.lower().endswith(".fbx") else scan_gltf(f, mind)
        except Exception as e:  # noqa: BLE001
            r = [{"clip": "?", "error": str(e)[:200]}]
        allr[f] = r
        n = len([x for x in r if "error" not in x])
        k = sum(1 for x in r if x.get("fingers"))
        print("%-90s clips %3d  with finger motion %3d" % (f[-90:], n, k), flush=True)
    tot = sum(len(v) for v in allr.values())
    fing = sum(1 for v in allr.values() for x in v if x.get("fingers"))
    print("TOTAL clips %d, with finger motion %d" % (tot, fing))
    if "--json" in sys.argv:
        json.dump(allr, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)


if __name__ == "__main__":
    main()

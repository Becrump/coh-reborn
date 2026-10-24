"""Turn the built ZoneGraph lanes into a life file for ACoHLifeManager.

    python tools/reborn/make_life.py <zonegraph dump.txt> <out dir> [original life.json]

The dump is the 'ZoneStorage=' line that `obj dump ZoneGraphData_0` writes to
the editor log (ue/dump_zonegraph.py saves it). Car lanes (tag bit 1) become
'traffic' points every 4 m with their travel direction, sidewalk lanes (tag
bit 2) become civilian 'npc' nodes every 10 m. The monorail, blimp and drone
routes are taken from the original zone's life file (route data only).
Writes reborn_life.json (positions in cm, as the life manager expects).
"""
import json
import math
import os
import re
import sys

dump, out = sys.argv[1], sys.argv[2]
orig = sys.argv[3] if len(sys.argv) > 3 else None
s = open(dump, encoding="utf-8", errors="replace").read()


def vec_list(key):
    i = s.index(key + "=((") + len(key) + 2
    j = s.index("))", i) + 1
    return [tuple(float(v) for v in re.findall(r"=(-?[\d.]+)", t)) for t in re.findall(r"\(([^()]*)\)", s[i - 1:j + 1])]


pts = vec_list("LanePoints")
tan = vec_list("LaneTangentVectors")
lanes = []
for t in re.findall(r"\(Width=[\d.]+,Tags=\(Mask=\d+\)[^()]*\)", s[s.index("Lanes=(("):]):
    d = dict(re.findall(r"(\w+)=(-?[\d.]+)", t))
    lanes.append((int(d.get("Mask", 0)), int(d.get("PointsBegin", 0)), int(d.get("PointsEnd", 0))))


def resample(seq, step):
    """[(x,y,z)] -> points every `step` cm with direction"""
    outp = []
    acc = 0.0
    for (a, b) in zip(seq[:-1], seq[1:]):
        seg = math.dist(a, b)
        if seg < 1e-3:
            continue
        dx, dy = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
        while acc <= seg:
            t = acc / seg
            outp.append(([a[k] + (b[k] - a[k]) * t for k in range(3)], [dx, dy]))
            acc += step
        acc -= seg
    return outp


traffic, npc = [], []
for mask, b, e in lanes:
    seq = pts[b:e]
    if len(seq) < 2:
        continue
    if mask & 2:
        for p, d in resample(seq, 400.0):
            traffic.append({"p": [round(p[0], 1), round(p[1], 1), round(p[2] + 15, 1)], "d": [round(d[0], 4), round(d[1], 4)]})
    elif mask & 4:
        for p, _ in resample(seq, 1000.0):
            npc.append([round(p[0], 1), round(p[1], 1), round(p[2] + 15, 1)])
# traffic signals: at every junction of 3+ roads, one per approach. Stop
# point = middle of the approach's incoming lanes at the road end; the two
# crossing directions alternate (group 0/1); each junction has its own phase
import random
rng = random.Random(11)
roads_json = json.load(open(os.path.join(out, "roads.json")))
R = roads_json["roads"]
signals, heads = [], []
for j in roads_json["junctions"]:
    if len(j["roads"]) < 3:
        continue
    cx, cy = j["center"]
    offset = round(rng.uniform(0, 40), 1)
    ref = None
    for rid in j["roads"]:
        pts = R[rid]["dense"]
        start = math.dist(pts[0][:2], (cx, cy)) < math.dist(pts[-1][:2], (cx, cy))
        end, prev = (pts[0], pts[1]) if start else (pts[-1], pts[-2])
        dx, dy = end[0] - prev[0], end[1] - prev[1]
        n = math.hypot(dx, dy) or 1.0
        dx, dy = dx / n, dy / n                      # direction cars approach in
        ang = math.degrees(math.atan2(dy, dx)) % 180
        if ref is None:
            ref = ang
        diff = abs(ang - ref) % 180
        group = 0 if min(diff, 180 - diff) < 45 else 1
        rx, ry = -dy, dx                              # right of travel
        half = R[rid]["width"] / 2
        stop = (end[0] + rx * half / 2, end[1] + ry * half / 2, end[2])
        signals.append({"p": [round(stop[0] * 100, 1), round(stop[1] * 100, 1), round(stop[2] * 100, 1)],
                        "d": [round(dx, 4), round(dy, 4)], "offset": offset, "group": group})
        pole = (end[0] + rx * (half + 1.2), end[1] + ry * (half + 1.2), end[2])
        heads.append({"p": [round(v, 2) for v in pole], "yaw": round(math.degrees(math.atan2(-dy, -dx)), 2),
                      "offset": offset, "group": group})
with open(os.path.join(out, "signals.json"), "w") as f:
    json.dump(heads, f)
life = {"traffic": traffic, "signals": signals, "npc": npc, "monorail": [], "blimp": [], "drones": [], "cars": [], "fx": []}
if orig:
    o = json.load(open(orig))
    for k in ("monorail", "blimp", "drones"):
        life[k] = o.get(k, [])
with open(os.path.join(out, "reborn_life.json"), "w") as f:
    json.dump(life, f)
print("signals", len(signals), "lanes", len(lanes), "traffic points", len(traffic), "civilian nodes", len(npc),
      "monorail", len(life["monorail"]))

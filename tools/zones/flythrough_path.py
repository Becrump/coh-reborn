"""Writes the waypoint path for coh.flythrough from docs/zones/zone_offsets.json.

    python tools/zones/flythrough_path.py [out.txt] [--alt 60]

Route: Atlas Park side -> Galaxy City -> Perez Park -> Kings Row -> Steel Canyon ->
Skyway City -> Talos Island, through each zone's centre, so the flight crosses the
borders between them. One "X,Y,Z" line per point in Unreal world centimetres, using
place_world.py's mapping (Unreal X = game x, Unreal Y = -game z), at a fixed height.
"""
import json
import os
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ROUTE = ["city_01_01", "city_01_03", "hazard_01_01", "city_01_02", "city_02_01", "city_02_02", "city_03_01"]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.join(REPO, "tools", "build", "flythrough_city.txt")
    alt_m = float(sys.argv[sys.argv.index("--alt") + 1]) if "--alt" in sys.argv else 60.0
    zones = json.load(open(os.path.join(REPO, "docs", "zones", "zone_offsets.json")))["zones"]
    lines = ["# coh.flythrough path (X,Y,Z cm): " + " -> ".join(zones[z]["name"] for z in ROUTE if z in zones)]
    pts = []
    for z in ROUTE:
        if z not in zones:
            continue
        x0, z0, x1, z1 = zones[z]["world_rect_m"]
        gx, gz = (x0 + x1) / 2, (z0 + z1) / 2
        pts.append((gx * 100, -gz * 100, alt_m * 100))
        lines.append("%.0f,%.0f,%.0f  # %s" % (pts[-1] + (zones[z]["name"],)))
    km = sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** .5 for a, b in zip(pts, pts[1:])) / 100000
    open(out, "w").write("\n".join(lines) + "\n")
    print("wrote %s: %d points, %.1f km" % (out, len(pts), km))


main()

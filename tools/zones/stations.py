"""Original monorail arrival points (SpawnLocation monorail_zoneteleport_PC) per zone, zone-local."""
import glob, re, json, os, sys
base = sys.argv[1] if len(sys.argv) > 1 else "i24/data/maps/city_zones"
out = {}
for f in sorted(glob.glob(base + "/*/*_layer_[pP]aragon[cC]ity[tT]eleport.txt")):
    t = open(f, errors="replace").read()
    pos = [tuple(map(float, m)) for m in re.findall(r"Pos ([-\d.]+) ([-\d.]+) ([-\d.]+)", t.split("Def grp_ParagonCityTeleport")[1].split("\nEnd")[0])]
    yaw = re.findall(r"PYR [-\d.]+ ([-\d.]+) ", t.split("Def grp_ParagonCityTeleport")[1])
    ref = re.search(r"Ref grp_ParagonCityTeleport\s+(?:PYR ([-\d.]+) ([-\d.]+) ([-\d.]+)\s+)?Pos ([-\d.]+) ([-\d.]+) ([-\d.]+)", t)
    rx, ry, rz = float(ref.group(4)), float(ref.group(5)), float(ref.group(6))
    ryaw = float(ref.group(2) or 0)
    if ryaw: print("WARN ref rotation", f)
    c = [sum(p[i] for p in pos) / len(pos) for i in range(3)]
    zone = os.path.basename(os.path.dirname(f)).lower()
    out[zone] = {"local_ft": [round(c[0] + rx, 1), round(c[1] + ry, 1), round(c[2] + rz, 1)],
                 "local_m": [round((c[0] + rx) * .3048, 1), round((c[1] + ry) * .3048, 1), round((c[2] + rz) * .3048, 1)],
                 "game_yaw_deg": round(float(yaw[0]) + ryaw - 180 if yaw else 0, 1)}
print(json.dumps(out, indent=1))

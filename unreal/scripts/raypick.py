"""python raypick.py sx sy [fov]  -> material under normalized screen point for the editor camera"""
import json, math, sys, numpy as np
cam = json.load(open("cam.json"))["returnValue"]
loc = np.array([cam["location"][k] for k in "xyz"]) / 100.0          # UE metres
p, y = math.radians(cam["rotation"]["pitch"]), math.radians(cam["rotation"]["yaw"])
fwd = np.array([math.cos(p)*math.cos(y), math.cos(p)*math.sin(y), math.sin(p)])
right = np.array([-math.sin(y), math.cos(y), 0.0]); up = np.cross(fwd, right)
sx, sy = float(sys.argv[1]), float(sys.argv[2]); fov = math.radians(float(sys.argv[3]) if len(sys.argv) > 3 else 90)
aspect = 2038/1222; t = math.tan(fov/2)
d = fwd + (2*sx-1)*t*right + (1-2*sy)*t/aspect*up; d /= np.linalg.norm(d)
o = np.array([loc[0], loc[2], loc[1]]); dg = np.array([d[0], d[2], d[1]])   # to glTF (x, y-up, z)
G = r"C:\Users\rtcru\CoHReborn\out\atlas_park_v2\atlas_park"
g = json.load(open(G + ".gltf")); b = open(G + ".bin", "rb").read()
def acc(i, c, dt):
    a = g["accessors"][i]; v = g["bufferViews"][a["bufferView"]]
    arr = np.frombuffer(b, dtype=dt, count=a["count"]*c, offset=v["byteOffset"]); return arr.reshape(-1, c) if c > 1 else arr
hits = []
for m in g["meshes"]:
    for pr in m["primitives"]:
        a = g["accessors"][pr["attributes"]["POSITION"]]
        mn, mx = np.array(a["min"]), np.array(a["max"])
        # slab test vs primitive bounds
        inv = 1/np.where(dg == 0, 1e-9, dg); t1 = (mn-o)*inv; t2 = (mx-o)*inv
        if np.max(np.minimum(t1, t2)) > np.min(np.maximum(t1, t2)) or np.min(np.maximum(t1, t2)) < 0: continue
        P = acc(pr["attributes"]["POSITION"], 3, np.float32); I = acc(pr["indices"], 1, np.uint32).reshape(-1, 3)
        v0, v1, v2 = P[I[:,0]], P[I[:,1]], P[I[:,2]]; e1, e2 = v1-v0, v2-v0
        h = np.cross(dg, e2); det = (e1*h).sum(1); ok = np.abs(det) > 1e-9
        f = np.where(ok, 1/np.where(ok, det, 1), 0); s = o - v0
        u = f*(s*h).sum(1); q = np.cross(s, e1); v = f*(q*dg).sum(1); tt = f*(e2*q).sum(1)
        sel = ok & (u >= 0) & (v >= 0) & (u+v <= 1) & (tt > 0.1)
        for k in np.nonzero(sel)[0]:
            hits.append((tt[k], g["materials"][pr["material"]]["name"], m["name"]))
for h in sorted(hits)[:6]: print("%.1fm" % h[0], h[1], h[2])

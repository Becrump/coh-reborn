"""Measure seams between separate costume pieces of exported characters.

    python tools/check_seams.py <characters folder> [--frames 6] [--csv out]

For every glTF listed in <folder>/index.json, the meshes are skinned on the
CPU (numpy) at the rest pose and at evenly spaced frames of every clip.
For each hand and foot piece, the open rim that faces the body (the
boundary loop closest to the other pieces) is found, and the distance from
each rim vertex to the nearest triangle of the other pieces is measured.
Distances are signed with the neighbouring face's normal, so a rim that
tucks inside a sleeve or trouser leg counts as covered (0). The reported gap
is the largest distance of a rim point lying outside the neighbour.
"""
import argparse
import json
import os
import struct

import numpy as np

COMP = {5126: np.float32, 5123: np.uint16, 5121: np.uint8, 5125: np.uint32}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class Gltf:
    def __init__(self, path):
        with open(path) as f:
            self.g = json.load(f)
        base = os.path.dirname(path)
        with open(os.path.join(base, self.g["buffers"][0]["uri"]), "rb") as f:
            self.bin = f.read()
        self.parent = {}
        for i, n in enumerate(self.g["nodes"]):
            for c in n.get("children", []):
                self.parent[c] = i

    def acc(self, i):
        a = self.g["accessors"][i]
        v = self.g["bufferViews"][a["bufferView"]]
        n = NCOMP[a["type"]]
        arr = np.frombuffer(self.bin, COMP[a["componentType"]],
                            a["count"] * n,
                            v.get("byteOffset", 0) + a.get("byteOffset", 0))
        return arr.reshape(a["count"], n) if n > 1 else arr

    def local(self, i, over=None):
        n = self.g["nodes"][i]
        t = np.array(n.get("translation", [0, 0, 0]), float)
        r = np.array(n.get("rotation", [0, 0, 0, 1]), float)
        s = np.array(n.get("scale", [1, 1, 1]), float)
        if over and i in over:
            t = over[i].get("translation", t)
            r = over[i].get("rotation", r)
        x, y, z, w = r / np.linalg.norm(r)
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w),
                       2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z),
                       2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w),
                       1 - 2 * (x * x + y * y)]])
        M = np.eye(4)
        M[:3, :3] = R * s
        M[:3, 3] = t
        return M

    def world(self, over=None):
        cache = {}

        def w(i):
            if i not in cache:
                L = self.local(i, over)
                cache[i] = w(self.parent[i]) @ L if i in self.parent else L
            return cache[i]
        return {i: w(i) for i in range(len(self.g["nodes"]))}

    def pose(self, anim=None, t=0.0):
        """Per-node overrides from an animation at time t (linear keys)."""
        if anim is None:
            return None
        over = {}
        for ch in anim["channels"]:
            s = anim["samplers"][ch["sampler"]]
            times = self.acc(s["input"])
            vals = self.acc(s["output"])
            k = int(np.searchsorted(times, t, side="right")) - 1
            k = max(0, min(k, len(times) - 1))
            k2 = min(k + 1, len(times) - 1)
            f = 0.0 if k2 == k else (t - times[k]) / (times[k2] - times[k])
            v = vals[k] * (1 - f) + vals[k2] * f
            over.setdefault(ch["target"]["node"], {})[
                ch["target"]["path"]] = np.array(v, float)
        return over

    def skinned(self, over=None):
        """{mesh node name: (positions Nx3, triangles Mx3)} in metres."""
        W = self.world(over)
        skin = self.g["skins"][0]
        ibm = self.acc(skin["inverseBindMatrices"]).reshape(-1, 4, 4)
        J = np.stack([W[j] @ ibm[k].T for k, j in enumerate(skin["joints"])])
        out = {}
        for n in self.g["nodes"]:
            if "mesh" not in n:
                continue
            prims = self.g["meshes"][n["mesh"]]["primitives"]
            if not prims:
                continue
            # the exporter's primitives share one set of vertex attributes
            a = prims[0]["attributes"]
            P = self.acc(a["POSITION"]).astype(float)
            jn = self.acc(a["JOINTS_0"]).astype(int)
            wt = self.acc(a["WEIGHTS_0"]).astype(float)
            Ph = np.c_[P, np.ones(len(P))]
            M = np.einsum("vk,vkij->vij", wt, J[jn])
            Q = np.einsum("vij,vj->vi", M, Ph)[:, :3]
            tris = np.vstack([self.acc(p["indices"]).reshape(-1, 3)
                              for p in prims]).astype(int)
            out[n["name"]] = (Q, tris)
        return out


def boundary_loops(P, tris):
    """Open-edge vertex groups after welding coincident vertices."""
    key = np.round(P / 1e-5).astype(np.int64)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    weld = weld.ravel()
    T = weld[tris]
    edges = {}
    for a, b, c in T:
        for e in ((a, b), (b, c), (c, a)):
            k = (min(e), max(e))
            edges[k] = edges.get(k, 0) + 1
    bnd = [k for k, n in edges.items() if n == 1]
    adj = {}
    for a, b in bnd:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    seen, loops = set(), []
    rep = {w: i for i, w in enumerate(weld)}
    for v in adj:
        if v in seen:
            continue
        stack, comp = [v], []
        seen.add(v)
        while stack:
            u = stack.pop()
            comp.append(u)
            for x in adj[u]:
                if x not in seen:
                    seen.add(x)
                    stack.append(x)
        loops.append(np.array([rep[w] for w in comp]))
    return loops


def point_tri_dist(p, A, B, C):
    """Distance from point p to many triangles (Ericson's closest point)."""
    ab, ac, ap = B - A, C - A, p - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - B
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - C
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    denom = va + vb + vc
    denom[denom == 0] = 1e-12
    v = vb / denom
    w = vc / denom
    Q = A + ab * v[:, None] + ac * w[:, None]
    # regions
    m = (d1 <= 0) & (d2 <= 0)
    Q[m] = A[m]
    m = (d3 >= 0) & (d4 <= d3)
    Q[m] = B[m]
    m = (d6 >= 0) & (d5 <= d6)
    Q[m] = C[m]
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t = d1 / np.where(d1 - d3 == 0, 1e-12, d1 - d3)
    Q[m] = (A + ab * t[:, None])[m]
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t = d2 / np.where(d2 - d6 == 0, 1e-12, d2 - d6)
    Q[m] = (A + ac * t[:, None])[m]
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    t = (d4 - d3) / np.where((d4 - d3) + (d5 - d6) == 0, 1e-12,
                             (d4 - d3) + (d5 - d6))
    Q[m] = (B + (C - B) * t[:, None])[m]
    d = np.sqrt(((Q - p) ** 2).sum(1))
    k = int(d.argmin())
    # sign from the face normal (glTF CCW = outward): negative means the
    # point lies under that surface, i.e. tucked inside the neighbour
    n = np.cross(ab[k], ac[k])
    side = float(np.dot(p - Q[k], n))
    return d[k] if side >= 0 else -d[k]


def rim_gap(pieces, name, others):
    P, T = pieces[name]
    loops = boundary_loops(P, T)
    if not loops:
        return None
    OP = [pieces[o] for o in others if o in pieces]
    if not OP:
        return None
    A = np.vstack([p[t[:, 0]] for p, t in OP])
    B = np.vstack([p[t[:, 1]] for p, t in OP])
    C = np.vstack([p[t[:, 2]] for p, t in OP])
    best = None
    for lp in loops:
        d = np.array([point_tri_dist(P[i], A, B, C) for i in lp])
        if best is None or np.abs(d).mean() < np.abs(best).mean():
            best = d
    # visible gap: the furthest rim point outside the neighbour's surface
    return float(max(0.0, best.max()))


SEAMS = {"Hand_R": "wrist R", "Hand_L": "wrist L",
         "Foot_R": "ankle R", "Foot_L": "ankle L"}


def check(path, frames):
    gl = Gltf(path)
    poses = [("rest", None, 0.0)]
    for a in gl.g.get("animations", []):
        tmax = max(float(gl.acc(s["input"]).max()) for s in a["samplers"])
        for k in range(frames):
            poses.append((a["name"], a, tmax * k / max(1, frames - 1)))
    res = {}
    for label, a, t in poses:
        pieces = gl.skinned(gl.pose(a, t))
        for name in SEAMS:
            if name not in pieces:
                continue
            twin = {"Hand_R": "Hand_L", "Hand_L": "Hand_R",
                    "Foot_R": "Foot_L", "Foot_L": "Foot_R"}[name]
            others = [o for o in pieces if o not in (name, twin)]
            g = rim_gap(pieces, name, others)
            if g is None:
                continue
            r = res.setdefault(name, {"rest": None, "max": 0.0, "at": ""})
            if label == "rest":
                r["rest"] = g
            if g > r["max"]:
                r["max"], r["at"] = g, "%s@%.2fs" % (label, t)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--frames", type=int, default=6)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--json", help="write full results here")
    args = ap.parse_args()
    with open(os.path.join(args.folder, "index.json")) as f:
        index = json.load(f)
    allres = {}
    for e in index:
        if args.only and e["costume"] not in args.only:
            continue
        r = check(os.path.join(args.folder, e["gltf"]), args.frames)
        allres[e["costume"]] = {"group": e.get("group"), "seams": r}
        worst = max((v["max"] for v in r.values()), default=0.0)
        flag = "  <-- over 1 cm" if worst > 0.01 else ""
        print("%-40s %s%s" % (e["costume"], "  ".join(
            "%s rest %.1f / max %.1f cm (%s)" % (SEAMS[k], v["rest"] * 100,
                                                 v["max"] * 100, v["at"])
            for k, v in sorted(r.items())), flag))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(allres, f, indent=1)


if __name__ == "__main__":
    main()

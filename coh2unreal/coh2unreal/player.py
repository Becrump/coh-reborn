"""Export the original player bodies (male, female, huge) for Unreal.

    python -m coh2unreal.player --data i24/data --piggs piggs --out out/player presets
    python -m coh2unreal.player ... models [--npc Model_Positron ...] [--costume my_hero.json ...]
    python -m coh2unreal.player ... anims --list out/powers/anim_list.json

presets  lists the hero NPCs on player bodies (signature heroes, Freedom
         Corps, contacts...) that can stand in as player models
models   exports hero NPCs and/or costume files as rigged glTF on the
         player skeletons, with the core player clips (ready, run, hit,
         death, brawl)
anims    exports the player animation library: for each body type every
         .anim that a player power or core move uses (anim_list.json from
         coh2unreal.powanim), sampled onto that body's skeleton, in chunks
         of glTF files. Each clip is the whole .anim track, named after it
         (male/energy_rapid -> male__energy_rapid); power_anims.json gives
         the frame ranges a move plays.

A costume file is the NPC Costume block as JSON, so any part the costume
creator offers can be used:

    {"name": "My_Hero", "body": "male",            # male | fem | huge
     "scale": 0, "skin": [230, 190, 160],
     "parts": [{"part": "Chest", "geometry": "Tights", "texture1": "Tight_Stripes",
                "texture2": "None", "color1": [200, 0, 0], "color2": [255, 255, 255]},
               ...]}

Part names, geometry and texture names are those of the .nd costumes and the
costume creator menus (menu/costume); `presets --show NAME` prints any
preset in this format to start from.
"""
import argparse
import glob
import json
import os
import re
import sys

from . import anim as A
from .character import (FPS, Builder, GameData, Skeleton, add_clip,
                        export_npc, pos3)
from .defs import Node

BODIES = {"male": ("male", 0), "fem": ("fem", 1), "huge": ("huge", 4)}
# player sequencer moves for the clips every model carries
PLAYER_MOVES = [("idle", ["Ready"]),
                ("combat_idle", ["CombatReady"]),
                ("run", ["RunCycle"]),
                ("attack", ["Brawl_R", "Initial_Strike"]),
                ("hit", ["HitQuick", "C_HitQuick"]),
                ("death", ["Default_Death", "Death_Mid_Air"])]
PRESET_FILES = ("npcs_signature.nd", "freedom_corp.nd", "hero_corp.nd",
                "ogtheroes.nd", "contacts_atlas.nd", "gc_close_heroes.nd")


def _body_of(npc):
    cos = npc.get("Costume")
    if cos is None:
        return None
    ent = (cos.arg("EntTypeFile") or "").lower()
    if not ent:
        ent = {0: "male", 1: "fem", 4: "huge"}.get(
            int(cos.arg("BodyType", "0") or 0), "")
    return ent if ent in BODIES else None


def presets(gd):
    out = []
    for fn in PRESET_FILES:
        path = os.path.join(gd.data_dir, "defs", "npc", fn)
        if not os.path.exists(path):
            continue
        with open(path, encoding="latin-1") as f:
            text = f.read()
        for name in re.findall(r'^NPC\s+"?([^"\s]+)', text, re.M):
            npc = gd.npcs().get(name.lower())
            body = _body_of(npc) if npc is not None else None
            if body:
                out.append({"npc": name, "body": body, "file": fn})
    return out


def costume_json(npc):
    """An NPC's Costume block as a costume file."""
    cos = npc.get("Costume")

    def col(n, k):
        v = n.get(k)
        return [int(float(x)) for x in v.args[:3]] if v else None

    parts = []
    for cp in cos.all("CostumePart"):
        p = {"part": cp.args[0] if cp.args else ""}
        for key in ("Geometry", "Texture1", "Texture2", "Fx", "BodySetName"):
            if cp.arg(key):
                p[key.lower()] = cp.arg(key)
        for key in ("Color1", "Color2"):
            if col(cp, key):
                p[key.lower()] = col(cp, key)
        parts.append(p)
    return {"name": npc.args[0], "body": _body_of(npc),
            "scale": float(cos.arg("Scale", "0") or 0),
            "skin": col(cos, "SkinColor"), "parts": parts}


def costume_npc(spec):
    """Builds an NPC node from a costume file, for export_npc."""
    body = spec.get("body", "male").lower()
    ent, bt = BODIES[body]
    cos = Node("Costume", [])
    cos.children.append(Node("EntTypeFile", [ent]))
    cos.children.append(Node("BodyType", [str(bt)]))
    cos.children.append(Node("Scale", [str(spec.get("scale", 0))]))
    if spec.get("skin"):
        cos.children.append(Node("SkinColor", [str(v) for v in spec["skin"]]))
    for p in spec.get("parts", []):
        cp = Node("CostumePart", [p["part"]])
        for key in ("Geometry", "Texture1", "Texture2", "Fx", "BodySetName"):
            if p.get(key.lower()):
                cp.children.append(Node(key, [p[key.lower()]]))
        for key in ("Color1", "Color2"):
            if p.get(key.lower()):
                cp.children.append(Node(key, [str(v) for v in p[key.lower()]]))
        cos.children.append(cp)
    npc = Node("NPC", [spec["name"]])
    npc.children.append(cos)
    return npc


def export_anims(gd, body, anims, out_dir, chunk=40, log=print):
    """Writes <body>_anims_NN.gltf files: the body's skeleton, a one-triangle
    carrier mesh skinned to the hips (so the file imports as a skeletal
    asset), and one animation per .anim."""
    ent = gd.ent_type(BODIES[body][0])
    seq = gd.sequencer((ent.get("sequencer") or ["player.txt"])[0])
    seq_type = (ent.get("sequencertype") or [body])[0]
    base_name = seq.base_skeleton(seq_type)
    sk = Skeleton(gd.anim(base_name))
    os.makedirs(out_dir, exist_ok=True)
    index = []
    names = sorted(anims)
    for ci in range(0, len(names), chunk):
        part = names[ci:ci + chunk]
        fname = "%s_anims_%02d" % (body, ci // chunk)
        b = Builder()
        g = b.gltf
        joint_index = {}
        for bid in sk.order:
            joint_index[bid] = b.node({"name": A.BONE_NAMES[bid],
                                       "translation": list(pos3(sk.local[bid]))})
        for bid in sk.order:
            p = sk.parents[bid]
            if p >= 0:
                g["nodes"][joint_index[p]].setdefault("children", []).append(
                    joint_index[bid])
        roots = [joint_index[x] for x in sk.order if sk.parents[x] < 0]
        ibm = []
        for bid in sk.order:
            w = pos3(sk.world[bid])
            ibm.extend([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0,
                        -w[0], -w[1], -w[2], 1])
        g["skins"].append({"name": body + "_skin",
                           "joints": [joint_index[x] for x in sk.order],
                           "inverseBindMatrices": b.accessor(ibm, 16, 5126),
                           "skeleton": roots[0]})
        root = b.node({"name": body, "children": roots,
                       "rotation": [0.0, 1.0, 0.0, 0.0]})
        g["scenes"][0]["nodes"].append(root)
        hips = pos3(sk.world[sk.order[0]])
        tri = [hips[0], hips[1], hips[2], hips[0] + 0.01, hips[1], hips[2],
               hips[0], hips[1] + 0.01, hips[2]]
        attrs = {"POSITION": b.accessor(tri, 3, 5126, 34962, True),
                 "JOINTS_0": b.accessor([0] * 12, 4, 5123, 34962),
                 "WEIGHTS_0": b.accessor([1, 0, 0, 0] * 3, 4, 5126, 34962)}
        g["meshes"].append({"name": "AnimCarrier", "primitives": [{
            "attributes": attrs, "indices": b.accessor([0, 1, 2], 1, 5125,
                                                       34963)}]})
        g["nodes"][root]["children"].append(b.node(
            {"name": "AnimCarrier", "mesh": 0, "skin": 0}))
        done = []
        for an in part:
            tr = gd.anim(an)
            if tr is None:
                log("  %s: missing" % an)
                continue
            clip = an.replace("/", "__")
            add_clip(b, sk, joint_index, gd, clip, tr, 0, 0,
                     {"cohAnim": an, "body": body})
            done.append({"clip": clip, "anim": an, "frames": int(tr.length),
                         "seconds": round(tr.length / FPS, 3), "file": fname})
        for k in ("textures", "images", "materials"):
            if not g[k]:
                del g[k]
        g["buffers"] = [{"uri": fname + ".bin", "byteLength": len(b.buf)}]
        with open(os.path.join(out_dir, fname + ".bin"), "wb") as f:
            f.write(b.buf)
        with open(os.path.join(out_dir, fname + ".gltf"), "w") as f:
            json.dump(g, f)
        index.extend(done)
        log("  %s: %d clips, %.1f MB" % (fname, len(done), len(b.buf) / 1e6))
    return {"body": body, "skeleton": base_name, "clips": index}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", required=True, help="i24/data folder")
    ap.add_argument("--piggs", required=True, help="folder of .pigg files")
    ap.add_argument("--out", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("presets")
    sp.add_argument("--show", help="print this preset as a costume file")
    sm = sub.add_parser("models")
    sm.add_argument("--npc", action="append", default=[])
    sm.add_argument("--costume", action="append", default=[],
                    help="costume .json file")
    sm.add_argument("--all-presets", action="store_true")
    sa = sub.add_parser("anims")
    sa.add_argument("--list", required=True, help="anim_list.json")
    sa.add_argument("--body", action="append", choices=list(BODIES))
    sa.add_argument("--chunk", type=int, default=40)
    args = ap.parse_args(argv)

    gd = GameData(args.data, glob.glob(os.path.join(args.piggs, "*.pigg")))
    os.makedirs(args.out, exist_ok=True)
    if args.cmd == "presets":
        if args.show:
            print(json.dumps(costume_json(gd.npcs()[args.show.lower()]),
                             indent=1))
            return 0
        ps = presets(gd)
        with open(os.path.join(args.out, "presets.json"), "w") as f:
            json.dump(ps, f, indent=1)
        for p in ps:
            print("%-40s %-5s %s" % (p["npc"], p["body"], p["file"]))
        print("%d presets" % len(ps))
    elif args.cmd == "models":
        jobs = [(n, None) for n in args.npc]
        if args.all_presets:
            jobs += [(p["npc"], None) for p in presets(gd)]
        for path in args.costume:
            with open(path, encoding="utf-8") as f:
                jobs.append((None, json.load(f)))
        index = []
        for npc_name, spec in jobs:
            if spec is not None:
                npc = costume_npc(spec)
                gd.npcs()[npc.args[0].lower()] = npc
                npc_name = npc.args[0]
            body = _body_of(gd.npcs()[npc_name.lower()])
            out_dir = os.path.join(args.out, "models", body or "other",
                                   npc_name)
            os.makedirs(os.path.join(out_dir, "textures"), exist_ok=True)
            try:
                r = export_npc(gd, npc_name, out_dir, moves=PLAYER_MOVES)
            except (KeyError, ValueError) as e:
                print("  %s: %s" % (npc_name, e))
                continue
            r.update({"name": npc_name, "body": body,
                      "gltf": os.path.relpath(r["gltf"], args.out)})
            index.append(r)
        with open(os.path.join(args.out, "models.json"), "w") as f:
            json.dump(index, f, indent=1)
        print("%d models" % len(index))
    elif args.cmd == "anims":
        with open(args.list, encoding="utf-8") as f:
            lists = json.load(f)
        index = []
        for body in args.body or list(BODIES):
            print(body)
            index.append(export_anims(gd, body, lists[body],
                                      os.path.join(args.out, "anims", body),
                                      args.chunk))
        with open(os.path.join(args.out, "anims.json"), "w") as f:
            json.dump(index, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

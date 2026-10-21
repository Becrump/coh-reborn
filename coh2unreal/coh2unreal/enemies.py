"""Export the enemies of a zone as a kit for Unreal: each villain's model
(with every clip its powers and idle behaviors play), its powers mapped to
moves on its own sequencer, and its idle animations.

    python tools/ai/coh_encounters.py <i24>/data export out/enemies     # roster.json, encounters.json
    python -m coh2unreal.enemies --data i24/data --piggs piggs --out out/enemies \
        [--group Hellions ...] [--villain Hellions_Brawl_Thug ...] [--all-costumes] [--no-models]
    python -m coh2unreal.fx --data i24/data --piggs piggs --out out/enemies/fx export \
        --powers-json out/enemies/enemy_power_anims.json --all

A villain's powers (VillainDef `Power Category Set *`) carry the same .pfx
fields as player powers. They are resolved as coh2unreal.powanim does for
heroes, but on the villain's own sequencer and sequencer type (from its
costume's ent type: Hellions play the male player moves, Clockwork their
own robot sequencer). Idle behaviors from the encounters (AI_InActive
"<<Menace>>" -> DoNothing(AnimList(MenaceVariation))) name anim lists
(sequencers/animlists/*.al: a list of sequencer bits), resolved the same way.

Writes:
  kit.json                 villain -> group, rank, class, AI config, levels,
                           costumes and model files, sequencer, powers (timing,
                           effects, move segments), idle anim lists, core clips
  enemy_power_anims.json   the villains' powers in power_anims.json form,
                           for coh2unreal.fx
  models/<costume>.gltf    rigged models; each clip is named after its move
                           (power segments name their moves), plus idle, run,
                           attack, hit, death
"""
import argparse
import glob
import json
import os
import re
import sys

from . import powanim as P
from .character import DEFAULT_MOVES, GameData, export_npc, resolve_costume

# reactions every enemy needs whatever its powers (sequencer move names)
CORE_MOVES = ("Ready", "CombatReady", "RunCycle", "WalkCycle", "HitQuick",
              "HitBack", "Default_Death", "KnockBack", "KnockDown", "GetUp",
              "Held", "Sleep", "Stunned", "Afraid", "JumpUp", "Fall", "Land")


def load_anim_lists(data):
    out = {}
    for path in glob.glob(os.path.join(data, "sequencers", "animlists",
                                       "*.al")):
        with open(path, encoding="latin-1") as f:
            for line in f:
                line = line.split("//", 1)[0]
                m = re.match(r"\s*AnimList:\s*(\w+)\s*,\s*(.*)", line)
                if m:
                    out[m.group(1).lower()] = m.group(2).upper().split()
    return out


def load_aliases(data):
    out = {}
    with open(os.path.join(data, "aiscript", "behavioraliases.bal"),
              encoding="latin-1") as f:
        for line in f:
            line = line.split("//", 1)[0]
            m = re.match(r"\s*Alias:\s*(\w+)\s*,\s*(.*)", line)
            if m:
                out[m.group(1).lower()] = m.group(2).strip()
    return out


def anim_lists_of(behavior, aliases, depth=0, anim_lists=None):
    """AnimList names a behavior string uses, following <<Alias>>es and
    bare alias names."""
    if not behavior or depth > 6:
        return []
    out = re.findall(r"AnimList\((\w+)", behavior, re.I)
    for name in re.findall(r"<<\s*(\w+)\s*>>", behavior) + \
            re.findall(r"^\s*\"?(\w+)\"?\s*$", behavior):
        a = aliases.get(name.lower())
        if a:
            out += anim_lists_of(a, aliases, depth + 1, anim_lists)
        elif anim_lists is not None and name.lower() in anim_lists:
            # spawn sheets name some idles after their anim list
            # (<<BatMenace>>) with no alias of that name
            out.append(name)
    seen = []
    for n in out:
        if n.lower() not in [s.lower() for s in seen]:
            seen.append(n)
    return seen


def expand_powers(specs, powers):
    """`Category Set *` / `Category Set Power` -> full power names."""
    out = []
    keys = {k.lower(): k for k in powers}
    for spec in specs:
        parts = spec.split(".")
        if len(parts) < 3:
            continue
        if parts[2] == "*":
            pre = (parts[0] + "." + parts[1] + ".").lower()
            out += sorted(k for low, k in keys.items() if low.startswith(pre))
        elif spec.lower() in keys:
            out.append(keys[spec.lower()])
    return out


def readies_of(seq):
    out = [seq.moves[m] for m in ("combatready", "ready") if m in seq.moves]
    if not out:
        out = [m for m in seq.order if "cycle" in m.flags][:1]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", required=True, help="i24/data folder")
    ap.add_argument("--piggs", required=True, help="folder of .pigg files")
    ap.add_argument("--out", required=True,
                    help="folder with roster.json and encounters.json")
    ap.add_argument("--group", action="append", default=[])
    ap.add_argument("--villain", action="append", default=[])
    ap.add_argument("--all-costumes", action="store_true")
    ap.add_argument("--no-models", action="store_true")
    args = ap.parse_args(argv)

    with open(os.path.join(args.out, "roster.json")) as f:
        roster = json.load(f)
    enc_path = os.path.join(args.out, "encounters.json")
    encounters = {}
    if os.path.exists(enc_path):
        with open(enc_path) as f:
            encounters = json.load(f)["encounters"]
    groups = {g.lower() for g in args.group}
    names = [n for n, r in roster.items()
             if (not groups and not args.villain) or
             (r.get("group") or "").lower() in groups or n in args.villain]

    gd = GameData(args.data, glob.glob(os.path.join(args.piggs, "*.pigg")))
    paths = P.PathIndex(args.data)
    powers = P.load_powers(paths, args.data)
    anim_lists = load_anim_lists(args.data)
    aliases = load_aliases(args.data)
    seqs = {}

    # idle behaviors per villain, from the encounters it appears in
    behaviors = {}
    for ename, sd in encounters.items():
        for act in sd["actors"]:
            for lvl_names in act.get("rolls", {}).values():
                for n in lvl_names:
                    b = behaviors.setdefault(n, set())
                    for k in ("ai_inactive", "ai_active", "ai_completion"):
                        if act.get(k):
                            b.add(act[k])

    kit, power_out = {}, {}
    model_dir = os.path.join(args.out, "models")
    os.makedirs(os.path.join(model_dir, "textures"), exist_ok=True)
    npcs = gd.npcs()
    for name in sorted(names):
        r = roster[name]
        costumes = r.get("costumes") or []
        npc = npcs.get(costumes[0].lower()) if costumes else None
        if npc is None:
            print("%s: no costume" % name)
            continue
        ent_name, _prefix, _parts = resolve_costume(gd, npc, lambda *a: None)
        et = gd.ent_type(ent_name)
        seq_file = (et.get("sequencer") or ["player.txt"])[0]
        # no SequencerType: the sequencer's file name (seqtype.c)
        seq_type = (et.get("sequencertype") or [os.path.splitext(
            os.path.basename(seq_file))[0]])[0].lower()
        if seq_file.lower() not in seqs:
            seqs[seq_file.lower()] = P.load_sequencer(paths, seq_file)
        seq = seqs[seq_file.lower()]
        readies = readies_of(seq)
        entry = {k: r.get(k) for k in ("group", "rank", "class", "ai_config", "ally",
                                        "def_levels", "spawn_levels",
                                        "weight", "encounters")}
        entry.update({"costumes": costumes, "ent_type": ent_name,
                      "sequencer": seq_file, "sequencer_type": seq_type,
                      "powers": {}, "anim_lists": {}, "unresolved": []})
        moves_needed = []

        def need(segs):
            for m in segs:
                if m[0] not in moves_needed:
                    moves_needed.append(m[0])

        for pname in expand_powers(r.get("powers", []), powers):
            base, _themes = powers[pname]
            if not base.f:
                continue
            res = P.resolve(seq, base.f, seq_type, readies)
            p = dict(base.f)
            p["moves"] = res
            entry["powers"][pname] = p
            power_out[pname] = dict(base.f, moves={seq_type: res})
            for bf, rr in res.items():
                if rr is None:
                    entry["unresolved"].append("%s %s" % (pname, bf))
                else:
                    need(rr["segments"])
        for beh in sorted(behaviors.get(name, ())):
            for al in anim_lists_of(beh, aliases, anim_lists=anim_lists):
                bits = anim_lists.get(al.lower())
                if not bits or al in entry["anim_lists"]:
                    continue
                found = []
                for rd in readies:
                    found = seq.pick(set(bits), rd)
                    if found:
                        break
                segs = []
                for m in (seq.chain(found[0]) if found else []):
                    a = seq.anim_for(m, seq_type)
                    if a:
                        segs.append([m.name, a[0], a[1], a[2]])
                entry["anim_lists"][al] = {"bits": bits, "segments": segs}
                need(segs)
        entry["behaviors"] = sorted(behaviors.get(name, ()))
        core = []
        for mname in CORE_MOVES:
            m = seq.moves.get(mname.lower())
            if m is not None and seq.anim_for(m, seq_type):
                core.append(m.name)
        need([[m] for m in core])
        entry["clips"] = moves_needed
        entry["models"] = []
        if not args.no_models:
            for c in (costumes if args.all_costumes else costumes[:1]):
                if os.path.exists(os.path.join(model_dir, c + ".gltf")):
                    entry["models"].append("models/%s.gltf" % c)
                    continue
                try:
                    res = export_npc(gd, c, model_dir, name=c,
                                     moves=DEFAULT_MOVES +
                                     [(m, [m]) for m in moves_needed],
                                     log=lambda *a: None)
                    entry["models"].append("models/%s.gltf" % c)
                    entry.setdefault("model_clips", res["clips"])
                except Exception as e:  # keep going; report it
                    entry["unresolved"].append("model %s: %s" % (c, e))
        kit[name] = entry
        print("%-42s %-10s %-22s %2d powers %2d idles %3d clips%s" % (
            name, r.get("rank"), seq_type, len(entry["powers"]),
            len(entry["anim_lists"]), len(moves_needed),
            ("  unresolved %d" % len(entry["unresolved"]))
            if entry["unresolved"] else ""))
    with open(os.path.join(args.out, "kit.json"), "w") as f:
        json.dump(kit, f, indent=1)
    with open(os.path.join(args.out, "enemy_power_anims.json"), "w") as f:
        json.dump(power_out, f, indent=1)
    print("%d villains, %d powers" % (len(kit), len(power_out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

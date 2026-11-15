"""Export the original game's story content and its text: contacts, story
arcs, task sets (missions), task forces and strike teams, NPC defs, clues and
souvenirs, encounter dialog, and the English string table, as JSON.

    python tools/story/coh_story.py <i24>/data <out_dir> [--villains]

Writes into <out_dir> (game data, keep it out of git):

  strings.json     every English message id -> text ("P944566542" ->
                   "Aaron Thiery"), from data/texts/english/**/*.ms
  contacts.json    contact file (scripts.loc relative, lower case) -> def
  storyarcs.json   .storyarc files      tasksets.json  .taskset / .task files
  npcs.json        .npc files (contact and mission NPC models)
  souvenirs.json   souvenir/clue defs   dialogs.json   .dialog2 / .dialog /
                   dialogdefs (encounter and contact dialog trees)
  spawnincs.json   .spawninc / .taskinc / .varinc includes used by missions
  index.json       contacts by zone, arcs and task sets per contact,
                   counts, unresolved string ids, missing referenced files

Every def keeps the original file's order as a tree of nodes:
  {"k": key, "a": [args], "c": [children], "t": [texts]}
"t" is only present when an arg is a message id (P1234, "<<P1234>>"): the
English text in the same position, so dialog reads without a lookup. Var
lines (var X = a, b) stay nodes; the game picks one per use, as the original
does. Hero side only by default (contacts, storyarcs, striketeams, npcs,
souvenirclues, dialogdefs, spawndefs dialogs); --villains adds v_contacts,
v_npcs, v_souvenirclues and alignment missions.
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "coh2unreal"))
from coh2unreal.defs import parse_braces  # noqa: E402

MSG = re.compile(r'^\s*"(P\d+)"\s+"(.*)"\s*$')
ID = re.compile(r"^(?:<<)?(P\d{3,})(?:>>)?$")

HERO_DIRS = ("contacts", "storyarcs", "striketeams", "npcs", "souvenirclues",
             "dialogdefs", "skillcontacts", "notorietycontacts",
             "supergroupcontacts", "spawndefs")
VILLAIN_DIRS = ("v_contacts", "v_npcs", "v_souvenirclues", "alignment_missions")

KIND = {".contact": "contacts", ".storyarc": "storyarcs",
        ".taskset": "tasksets", ".task": "tasksets", ".npc": "npcs",
        ".sc": "souvenirs", ".dialog2": "dialogs", ".dialog": "dialogs",
        ".spawninc": "spawnincs", ".taskinc": "spawnincs",
        ".varinc": "spawnincs"}


def load_strings(texts):
    out = {}
    for d, _s, files in os.walk(texts):
        for fn in sorted(files):
            if not fn.lower().endswith(".ms"):
                continue
            with open(os.path.join(d, fn), encoding="utf-8-sig",
                      errors="replace") as f:
                for line in f:
                    m = MSG.match(line)
                    if m and m.group(1) not in out:
                        out[m.group(1)] = m.group(2).replace('\\"', '"')
    return out


def to_json(nodes, strings, unresolved):
    out = []
    for n in nodes:
        o = {"k": n.key}
        if n.args:
            o["a"] = n.args
            texts, hit = [], False
            for a in n.args:
                m = ID.match(a.strip(","))
                if m:
                    t = strings.get(m.group(1))
                    if t is None:
                        unresolved.add(m.group(1))
                    else:
                        hit = True
                    texts.append(t)
                else:
                    texts.append(None)
            if hit:
                o["t"] = texts
        if n.children:
            o["c"] = to_json(n.children, strings, unresolved)
        out.append(o)
    return out


def refs_in(nodes, acc):
    """scripts.loc paths named anywhere in a tree (StoryArc, TaskSet, include)."""
    for n in nodes:
        for a in n.args:
            if a.lower().startswith("scripts.loc"):
                acc.add(a.replace("\\", "/").lower()[len("scripts.loc/"):])
        refs_in(n.children, acc)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--villains", action="store_true")
    a = ap.parse_args()
    strings = load_strings(os.path.join(a.data, "texts", "english"))
    print("strings: %d" % len(strings), flush=True)
    root = os.path.join(a.data, "scripts.loc")
    dirs = HERO_DIRS + (VILLAIN_DIRS if a.villains else ())
    found = {}
    for top in dirs:
        for d, _s, files in os.walk(os.path.join(root, top)):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if top == "spawndefs" and ext not in (".dialog2", ".dialog",
                                                      ".spawninc", ".taskinc",
                                                      ".varinc"):
                    continue
                if ext in KIND:
                    full = os.path.join(d, fn)
                    found[os.path.relpath(full, root).replace("\\", "/").lower()] = full
    out = collections.defaultdict(dict)
    unresolved, refs = set(), set()
    for rel, full in sorted(found.items()):
        with open(full, encoding="latin-1") as f:
            text = f.read()
        nodes = parse_braces(text)
        refs_in(nodes, refs)
        out[KIND[os.path.splitext(rel)[1]]][rel] = to_json(nodes, strings,
                                                           unresolved)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "strings.json"), "w", encoding="utf-8") as f:
        json.dump(strings, f, ensure_ascii=False, indent=0)
    for kind, defs in sorted(out.items()):
        with open(os.path.join(a.out, kind + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump(defs, f, ensure_ascii=False)

    # index: contacts by zone folder, the arcs/task sets each one gives
    by_zone = collections.defaultdict(list)
    per_contact = {}
    for rel, tree in out["contacts"].items():
        parts = rel.split("/")
        by_zone["/".join(parts[:-1])].append(rel)
        acc = set()
        refs_in_json(tree, acc)
        name = next((n.get("t", [None])[0] or n["a"][0]
                     for d in tree if d["k"].lower() == "contactdef"
                     for n in d.get("c", []) if n["k"].lower() == "name"
                     and n.get("a")), None)
        flags = [x.strip(",").lower() for d in tree for n in d.get("c", [])
                 if n["k"].lower() == "flags" for x in n.get("a", [])]
        per_contact[rel] = {"name": name, "flags": flags,
                            "storyarcs": sorted(r for r in acc if r.endswith(".storyarc")),
                            "tasksets": sorted(r for r in acc if r.endswith((".taskset", ".task")))}
    known = set(found)
    missing = sorted(r for r in refs if os.path.splitext(r)[1] in KIND
                     and r not in known)
    index = {"counts": {k: len(v) for k, v in out.items()},
             "strings": len(strings),
             "unresolved_strings": sorted(unresolved),
             "missing_files": missing,
             "contacts_by_folder": {k: sorted(v) for k, v in sorted(by_zone.items())},
             "contacts": per_contact}
    with open(os.path.join(a.out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    for k, v in sorted(index["counts"].items()):
        print("%-10s %5d" % (k, v))
    print("unresolved string ids: %d, missing referenced files: %d" % (
        len(unresolved), len(missing)))
    return 0


def refs_in_json(tree, acc):
    for n in tree:
        for x in n.get("a", []):
            if x.lower().startswith("scripts.loc"):
                acc.add(x.replace("\\", "/").lower()[len("scripts.loc/"):])
        refs_in_json(n.get("c", []), acc)


if __name__ == "__main__":
    sys.exit(main())

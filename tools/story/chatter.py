"""Villain chatter from the original game: the lines street villains say.

    python tools/story/chatter.py <i24>/data <out>

The zone encounters (tools/zones/encounters.py, encounters.json) keep each actor's
Dialog_InActive / Dialog_Alerted / Dialog_Completion / Dialog_ThankHero as the
original wrote it: a var name (LOITER_ATTACK_TEXT) from the spawn definition's
Dialog file (SpawnDefs/dialog/Hellions.dialog2), or a message id ("K123") when the
spawn definition set the var itself. This reads every dialog file under
scripts.loc/spawndefs/dialog, looks the ids up in <out>/story/strings.json
(coh_story.py: K and P ids share their number) and writes <out>/story/chatter.json:

  "files": {"spawndefs/dialog/hellions.dialog2": {"LOITER_ATTACK_TEXT": ["line", ...]}}
  "ids":   {"K123": "line"}       ids that spawn definitions name directly

Lines keep the original's {HeroName}-style variables for the game to fill in.
"""
import glob
import json
import os
import re
import sys

VAR = re.compile(r"(?m)^\s*var\s+(\w+)(?:\s+volatile)?\s*=\s*(.+?)\s*(?://.*)?$")
ID = re.compile(r"[KP](\d+)")
TAG = re.compile(r"<[^>]{1,60}>")


def text(strings, raw):
    m = ID.fullmatch(raw.strip().strip('"').strip("<>").strip())
    if not m:
        return None
    t = strings.get("P" + m.group(1), "")
    t = TAG.sub("", t).replace("\r", " ").replace("\n", " ").strip()
    return t or None


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    data, out = sys.argv[1], sys.argv[2]
    strings = json.load(open(os.path.join(out, "story", "strings.json"), encoding="utf-8"))
    root = os.path.join(data, "scripts.loc", "spawndefs")
    files, ids = {}, {}
    for path in sorted(glob.glob(os.path.join(root, "dialog", "*.dialog*"))):
        key = "spawndefs/dialog/" + os.path.basename(path).lower()
        table = {}
        for m in VAR.finditer(open(path, encoding="latin-1").read()):
            lines = [t for t in (text(strings, v) for v in m.group(2).split(",")) if t]
            if lines:
                table[m.group(1).upper()] = lines
        if table:
            files[key] = table
    # ids named straight in spawn definitions (var X = "K123", or an actor's Dialog_* "K123")
    for path in glob.glob(os.path.join(root, "**", "*.spawndef"), recursive=True):
        for m in re.finditer(r"\b[KP](\d+)\b", open(path, encoding="latin-1").read()):
            t = text(strings, m.group(0))
            if t:
                ids["K" + m.group(1)] = t
    os.makedirs(os.path.join(out, "story"), exist_ok=True)
    with open(os.path.join(out, "story", "chatter.json"), "w", encoding="utf-8") as f:
        json.dump({"files": files, "ids": ids}, f, ensure_ascii=False)
    print("chatter: %d dialog files, %d lines, %d direct ids, chatter.json written" % (
        len(files), sum(len(x) for t in files.values() for x in t.values()), len(ids)))


if __name__ == "__main__":
    main()

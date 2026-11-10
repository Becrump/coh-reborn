"""Parsers for the City of Heroes text defs used by the character exporter.

- Brace defs (.villain, .nd, .bp): `Key args...` lines and `{ }` blocks.
- Sequencers: line-based `TypeDef/TypeDefEnd`, `Move/MEnd`, `Type/TEnd`
  blocks with `Include` lines (seqload.c).
- Ent types: `Key value` lines between `Type` and `End` (seqtype.c).
"""
import os
import re

_TOK = re.compile(r'"[^"]*"|[{}]|[^\s,{}"]+')


def _strip_comment(line):
    out = []
    q = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            q = not q
        elif not q and (c == "#" or line.startswith("//", i)):
            break
        out.append(c)
        i += 1
    return "".join(out)


def _tokens(line):
    return [t[1:-1] if t.startswith('"') else t
            for t in _TOK.findall(_strip_comment(line))]


class Node:
    __slots__ = ("key", "args", "children")

    def __init__(self, key, args):
        self.key = key
        self.args = args
        self.children = []

    def get(self, key, default=None):
        k = key.lower()
        for c in self.children:
            if c.key.lower() == k:
                return c
        return default

    def all(self, key):
        k = key.lower()
        return [c for c in self.children if c.key.lower() == k]

    def arg(self, key, default=None):
        n = self.get(key)
        return n.args[0] if n is not None and n.args else default


def parse_braces(text):
    """Parses a brace def file into a list of top-level Nodes."""
    root = Node("", [])
    stack = [root]
    last = None
    for line in text.splitlines():
        for tok_line in [_tokens(line)]:
            i = 0
            while i < len(tok_line):
                t = tok_line[i]
                if t == "{":
                    if last is None:
                        last = Node("", [])
                        stack[-1].children.append(last)
                    stack.append(last)
                    last = None
                    i += 1
                elif t == "}":
                    if len(stack) > 1:
                        stack.pop()
                    last = None
                    i += 1
                else:
                    j = i + 1
                    while j < len(tok_line) and tok_line[j] not in "{}":
                        j += 1
                    last = Node(t, tok_line[i + 1:j])
                    stack[-1].children.append(last)
                    i = j
    return root.children


def parse_kv(text):
    """Ent type files: {key_lower: [values]} (first occurrence wins)."""
    out = {}
    for line in text.splitlines():
        t = _tokens(line)
        if len(t) >= 1 and t[0].lower() not in out:
            out[t[0].lower()] = t[1:]
    return out


# ----------------------------------------------------------------- sequencer
class Move:
    def __init__(self, name):
        self.name = name
        self.types = {}    # type name lower -> (anim name, first, last)
        self.flags = []


class Sequencer:
    def __init__(self):
        self.typedefs = {}   # lower name -> {"baseskeleton":, "parenttype":}
        self.moves = {}      # lower name -> Move

    def type_chain(self, seqtype):
        chain = []
        t = (seqtype or "").lower()
        while t and t != "none" and t not in chain:
            chain.append(t)
            t = self.typedefs.get(t, {}).get("parenttype", "none").lower()
        return chain

    def base_skeleton(self, seqtype):
        for t in self.type_chain(seqtype):
            b = self.typedefs.get(t, {}).get("baseskeleton")
            if b:
                return b.replace("\\", "/")
        return None

    def anim_for(self, move_name, seqtype):
        """(anim, first, last) for a move, following ParentType like
        seqGetTypeGfx (seqload.c)."""
        mv = self.moves.get(move_name.lower())
        if not mv:
            return None
        for t in self.type_chain(seqtype):
            if t in mv.types:
                return mv.types[t]
        return None


def load_sequencer(data_dir, name):
    seq = Sequencer()
    seen = set()

    def read(rel):
        rel = rel.replace("\\", "/")
        if not rel.lower().startswith("sequencers/"):
            rel = "sequencers/" + rel
        path = os.path.join(data_dir, rel)
        if path.lower() in seen or not os.path.exists(path):
            return []
        seen.add(path.lower())
        with open(path, encoding="latin-1") as f:
            lines = f.read().splitlines()
        out = []
        for line in lines:
            t = _tokens(line)
            if t and t[0].lower() == "include" and len(t) > 1:
                out.extend(read(t[1]))
            else:
                out.append(t)
        return out

    lines = read(name)
    td = None
    mv = None
    ty = None
    for t in lines:
        if not t:
            continue
        k = t[0].lower()
        if k == "typedef" and len(t) > 1:
            td = seq.typedefs.setdefault(t[1].lower(), {})
        elif k == "typedefend":
            td = None
        elif td is not None and len(t) > 1:
            td[k] = t[1]
        elif k == "move" and len(t) > 1:
            mv = Move(t[1])
            seq.moves.setdefault(t[1].lower(), mv)
            ty = None
        elif k == "mend":
            mv = None
            ty = None
        elif mv is not None and k == "type" and len(t) > 1:
            ty = t[1].lower()
        elif mv is not None and k == "tend":
            ty = None
        elif mv is not None and ty and k == "anim" and len(t) > 1:
            first = int(float(t[2])) if len(t) > 2 else 0
            last = int(float(t[3])) if len(t) > 3 else 0
            mv.types.setdefault(ty, (t[1].replace("\\", "/"), first, last))
        elif mv is not None and k == "flags":
            mv.flags.extend(x.lower() for x in t[1:])
    return seq

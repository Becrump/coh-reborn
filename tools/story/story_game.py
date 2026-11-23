"""Compile the story export (coh_story.py) and the story places
(world_points.py) into the one file the game reads: the contacts placed in
the city's zones, their dialogue and stores, and every task they can give
(street tasks, deliveries, visits, door missions, story arc episodes).

    python tools/story/story_game.py <out>/story

Reads contacts.json, tasksets.json, storyarcs.json, npcs.json and
world_points.json from <out>/story; writes <out>/story/story_game.json:

  contacts  "<contact file>": name, profession, description, location, zone,
            npc, model, pos (world cm), yaw, level band, task_force (null, or
            {names, min_size, level_adjust, invite and refusal lines}), contact points to
            friend/confidant/complete, dialogue lines (hello is a list: one
            is picked per visit), store items, tasks (ids, offered in order)
  tasks     "<file>#<name>": type (mission, killx, deliver, visit), texts
            (intro, accept, sendoff, active, busy, begin, complete, return),
            level band, contact points, reward table, and per type:
            killx {group, count}; deliver {npc, contact}; visit {location};
            mission {mapset, group, zone, door, length, entry, complete_with,
            objectives [{name, display, number, begin, done}], spawns
            [{logical, placement, count, group, villain, display, lines,
            kind (fight, rescue, escort, ambush, destroy), actors, objective,
            create_on, activate_on, hostage}]} (docs/missions.md);
            clues {begin, complete, return}: clues and souvenirs given or taken
            secondary / return_secondary: reward tables for the whole team on
            completing / turning in (a name that is no table is a badge token)
            force_level: the level its villains are (ForceTaskLevel)
            next: the task that follows (compound tasks, arc episodes);
            auto_next: it follows at once (compound parts), else the
            contact offers it once this one is turned in (arc episodes)
  arcs      "<file>": name, level band, episodes (task ids)
  clues     "<file>#<clue>": name, text (ClueDefs of the tasks and arcs)
  souvenirs "<souvenir>": name, text (souvenirs.json)

Texts are plain: links, colours and markup are stripped, <br> is a line
break, and task variables ({ITEM_NAME}) take their first value. {HeroName}
and {Level} stay for the game to fill in.
"""
import json
import os
import re
import sys

LINK = re.compile(r"<\s*a\s[^>]*>|<\s*/\s*a\s*>", re.I)
BR = re.compile(r"<\s*br\s*/?\s*>", re.I)
TAG = re.compile(r"<[^>]{1,60}>")
VAR = re.compile(r"\{([A-Za-z0-9_]+)\}")
KEEP = {"heroname", "level", "herolevel", "contactname", "villaingroup", "taskforcename"}


def norm(path):
    p = path.replace("\\", "/").strip().lower()
    if p.startswith("scripts.loc/"):
        p = p[len("scripts.loc/"):]
    return p


def kids(n, key=None):
    return [c for c in n.get("c", []) if key is None or c["k"].lower() == key.lower()]


def kid(n, key):
    k = kids(n, key)
    return k[0] if k else None


def arg(n, key, i=0, default=""):
    c = kid(n, key)
    if c is None or len(c.get("a", [])) <= i:
        return default
    return c["a"][i]


def text_of(node, i=0):
    """The English text of an arg (or the arg itself when it is plain)."""
    if node is None:
        return ""
    t = node.get("t") or []
    if i < len(t) and t[i]:
        return t[i]
    a = node.get("a") or []
    return a[i] if i < len(a) else ""


class Vars:
    """var NAME = a, b, c lines of a def and its parents: first value wins."""

    def __init__(self, parent=None):
        self.v = dict(parent.v) if parent else {}

    def take(self, n):
        for c in kids(n, "var"):
            a = c.get("a", [])
            if len(a) >= 3 and a[1] == "=":
                vals = [text_of(c, i) for i in range(2, len(a))]
                vals = [v for v in vals if v]
                if vals:
                    self.v[a[0].upper()] = vals[0]
        return self

    def sub(self, s, depth=0):
        if not s:
            return ""
        if s.upper() in self.v and depth < 4:      # the whole text is a var name
            return self.sub(self.v[s.upper()], depth + 1)

        def rep(m):
            k = m.group(1)
            if k.lower() in KEEP:
                return m.group(0)
            v = self.v.get(k.upper())
            return self.sub(v, depth + 1) if v is not None and depth < 4 else m.group(0)
        return VAR.sub(rep, s)


def clean(s, vars_=None):
    if not s:
        return ""
    if vars_:
        s = vars_.sub(s)
    s = s.replace("<<", "").replace(">>", "") if s.startswith("<<") else s
    s = LINK.sub("", s)
    s = BR.sub("\n", s)
    s = TAG.sub("", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def line(n, key, vars_):
    return clean(text_of(kid(n, key)), vars_)


def dialog_of(n, vars_):
    """TaskComplete / ReturnSuccess blocks: Dialog text, contact points, reward."""
    if n is None:
        return "", 0, ""
    cp = arg(n, "ContactPoints", 0, "0")
    try:
        cp = int(cp)
    except ValueError:
        cp = 0
    return line(n, "Dialog", vars_), cp, arg(n, "PrimaryReward")


def secondary_of(*blocks):
    """SecondaryReward tables of reward blocks: the original gives them to the whole team
    ("TaskForceReward, SynapseTF": the task force's reward and its badge token)."""
    out = []
    for n in blocks:
        for c in kids(n or {}, "SecondaryReward"):
            out += [a.strip(", ") for a in c.get("a", []) if a.strip(", ")]
    return out


def add_secondary(t, names, key="return_secondary"):
    if names:
        t[key] = t.get(key, []) + [x for x in names if x not in t.get(key, [])]


INCS = {}          # spawnincs.json: the encounter files mission spawns include
CLUES = {}         # "<file>#<clue>" (lower case) -> {"name", "text"}


def take_clues(n, scope):
    for c in kids(n, "ClueDef"):
        cid = (c.get("a") or [""])[0].lower()
        if cid:
            CLUES.setdefault("%s#%s" % (scope, cid), {"name": clean(text_of(kid(c, "Name"))),
                                                      "text": clean(text_of(kid(c, "DetailString")))})
RANKS = {"minion": "Minion", "lieutenant": "Lieutenant", "boss": "Boss", "archvillain": "ArchVillain",
         "eliteboss": "Boss", "sniper": "Minion", "pet": "Minion"}


def names(n, key):
    return [a for c in kids(n, key) for a in c.get("a", [])]


def clues_of(n):
    """AddClues / RemoveClues / SouvenirClue lines of a reward block."""
    if n is None:
        return {}
    out = {"add": names(n, "AddClues"), "remove": names(n, "RemoveClues"),
           "souvenirs": names(n, "SouvenirClue")}
    return {k: v for k, v in out.items() if v}


def encounter_of(sd, v):
    """The spawn's included encounter (spawnincs.json): kind and actors.

    kind: rescue (a hostage freed once its captors are down, then follows),
    escort (a hostage led to the exit), ambush (a wave that runs at the heroes
    when it is created), destroy (an object to smash), or fight."""
    inc = next((norm(c["a"][0]) for c in kids(sd, "include") if c.get("a")), "")
    nodes = list(INCS.get(inc, []))
    nodes += [c for c in sd.get("c", []) if c["k"] in ("Actor", "Script", "EncounterSpawn")]
    scripts = {}
    for sc in [c for c in nodes if c["k"] == "Script"]:
        sv = Vars(v).take(sc)
        scripts[arg(sc, "ScriptName").lower()] = sv
    actors = []
    rescuee = None
    if "leadtoplace" in scripts or "multileadtoplace" in scripts:
        sv = scripts.get("leadtoplace") or scripts.get("multileadtoplace")
        rescuee = clean(sv.v.get("POSITIONOFRESCUEE", "40"))
    for a in [c for c in nodes if c["k"] == "Actor"]:
        def val(key, default=""):
            x = arg(a, key, 0, default)
            return clean(v.sub(x)) if x else default
        villain, group = val("Villain"), val("VillainGroup")
        if villain.upper() == villain and "_" in villain and villain.upper() in (k for k in v.v):
            villain = ""
        if group.upper() == "VILLAIN_GROUP":
            group = ""
        num = val("Number", "1")
        lo = val("ExactHeroesRequired") or val("MinimumHeroesRequired", "1")
        hi = val("ExactHeroesRequired") or val("MaximumHeroesRequired", "8")
        ai = (val("AI_InActive") + " " + val("AI_Active")).lower()
        loc = val("Location", "0")
        role = "foe"
        if rescuee and loc == rescuee:
            role = "hostage"
        elif "untargetable" in ai or "marker" in villain.lower() or \
                (villain.lower() in ("pets_target", "") and not group and not val("VillainType")):
            role = "helper"
        elif "OBJECT" in arg(a, "Villain").upper() or "donothing" in ai and villain.lower().startswith(("object", "obj_", "destructible")):
            role = "object"
        if role == "helper":
            continue
        def say(*keys):
            for k in keys:
                raw = arg(a, k)
                t = clean(v.sub(raw), v) if raw else ""
                if t and not re.fullmatch(r"[A-Z0-9_]+", t) and t != raw:
                    return t
            return ""
        actors.append({"say": [say("Dialog_InActive"), say("Dialog_Alerted", "Dialog_Active")],
                       "role": role, "villain": villain, "group": group,
                       "rank": RANKS.get(val("VillainType").lower(), "Minion" if role == "foe" else ""),
                       "name": clean(val("Name"), v), "number": int(num) if num.isdigit() else 1,
                       "heroes": [int(lo) if lo.isdigit() else 1, int(hi) if hi.isdigit() else 8],
                       "fail_on_death": val("FailOnDeath") == "1"})
    if rescuee and any(x["role"] == "hostage" for x in actors):
        sv = scripts.get("leadtoplace") or scripts.get("multileadtoplace")
        kind = "rescue" if clean(sv.v.get("SUCCEEDONRESCUEORDELIVERY", "Rescue")).lower() == "rescue" else "escort"
    elif "waveattackencounter" in scripts:
        kind = "ambush"
    elif any(x["role"] == "object" for x in actors):
        kind = "destroy"
    else:
        kind = "fight"
    return kind, actors, inc


def parse_spawn(sd, vars_):
    v = Vars(vars_).take(sd)
    lines = [clean(text_of(c, 3), v) for c in kids(sd, "var")
             if len(c.get("a", [])) >= 3 and "DIALOG" in c["a"][0].upper()]
    def var(name):
        return v.v.get(name, "")
    count = arg(sd, "MissionCount", 0, "1")
    kind, actors, inc = encounter_of(sd, v)
    ob = kid(sd, "Objective")
    out = {"logical": arg(sd, "LogicalName"),
           "placement": arg(sd, "MissionPlacement", 0, "Any"),
           "count": int(count) if count.isdigit() else 1,
           "group": clean(var("VILLAIN_GROUP")),
           "villain": clean(var("BOSS_VILLAIN") or var("VILLAIN")),
           "display": clean(var("BOSS_DISPLAYNAME"), v),
           "lines": [l for l in lines if l][:4],
           "kind": kind, "actors": actors, "include": os.path.basename(inc),
           "create_on": names(sd, "CreateOnObjectiveComplete"),
           "activate_on": names(sd, "ActivateOnObjectiveComplete"),
           "uncounted": kid(sd, "MissionUncounted") is not None}
    if kind in ("rescue", "escort"):
        h = next(x for x in actors if x["role"] == "hostage")
        out["hostage"] = {"villain": h["villain"], "name": h["name"] or clean(var("HOSTAGE_NAME"), v)}
    if ob is not None:
        out["objective"] = (ob.get("a") or [""])[0]
        out["objective_text"] = line(ob, "Description", v)
        rw = kid(ob, "Reward")
        out["reward"] = line(rw or {}, "Dialog", v)
        out["clues"] = clues_of(rw)
    return out


def parse_mission(md, vars_):
    v = Vars(vars_).take(md)
    objs = []
    for o in kids(md, "Objective"):
        num = arg(o, "Number", 0, "1")
        delay = arg(o, "InteractDelay", 0, "0")
        rw = kid(o, "Reward")
        objs.append({"name": (o.get("a") or [""])[0],
                     "display": line(o, "ModelDisplayName", v),
                     "model": arg(o, "Model"),
                     "number": int(num) if num.isdigit() else 1,
                     "location": arg(o, "Location", 0, "ItemFloor"),
                     "placement": arg(o, "MissionPlacement", 0, ""),
                     "delay": int(delay) if delay.isdigit() else 0,
                     "desc": line(o, "Description", v),
                     "activate_on": names(o, "ActivateOnObjectiveComplete"),
                     "begin": line(o, "InteractBeginString", v),
                     "done": line(o, "InteractCompleteString", v),
                     "reward": line(rw or {}, "Dialog", v),
                     "clues": clues_of(rw)})
    length = arg(md, "MapLength", 0, "15")
    return {"mapset": arg(md, "MapSet"), "group": arg(md, "VillainGroup"),
            "zone": arg(md, "CityZone").lower(), "door": arg(md, "DoorType").lower(),
            "map": arg(md, "MapName"),
            "length": int(length) if length.isdigit() else 15,
            "entry": line(md, "EntryString", v),
            "complete_with": [" ".join(c.get("a", [])) for c in kids(md, "CanCompleteWith")],
            "fail_with": [" ".join(c.get("a", [])) for c in kids(md, "CanFailWith")],
            "objectives": objs,
            "spawns": [parse_spawn(s, v) for s in kids(md, "SpawnDef")]}


def task_type(flags):
    for f in flags:
        f = f.lower()
        if f in ("taskmission", "taskkillx", "taskdeliveritem", "taskvisitlocation",
                 "taskcompound"):
            return f[4:]
    return None


TYPES = {"mission": "mission", "killx": "killx", "deliveritem": "deliver",
         "visitlocation": "visit"}


def compile_task(td, tid, vars_, npc_contact, out, parent=None):
    """Adds the task (and a compound task's parts) to out; returns its id."""
    flags = td.get("a", [])
    kind = task_type(flags)
    if kind is None or kid(td, "Deprecated") is not None:
        return None
    v = Vars(vars_).take(td)
    texts = {"intro": line(td, "IntroString", v), "accept": line(td, "AcceptString", v),
             "sendoff": line(td, "SendOffString", v), "active": line(td, "ActiveTaskString", v),
             "busy": line(td, "YoureStillBusyString", v), "title": line(td, "TaskTitle", v)}
    if parent:
        for k in ("intro", "accept", "sendoff", "busy", "title"):
            texts[k] = texts[k] or parent.get(k, "")
    if kind == "compound":
        parts = [c for c in kids(td, "TaskDef")]
        ids = []
        for i, p in enumerate(parts):
            pid = compile_task(p, "%s/%d" % (tid, i + 1), v, npc_contact, out, texts)
            if pid:
                ids.append(pid)
        if not ids:
            return None
        for a, b in zip(ids, ids[1:]):
            out[a]["next"] = b
            out[a]["auto_next"] = True      # parts of one task follow on at once
        # the whole compound: the first part carries the intro, the last the return
        first, last = out[ids[0]], out[ids[-1]]
        for k in ("intro", "accept", "sendoff"):
            first[k] = texts[k] or first[k]
        ret, cp, reward = dialog_of(kid(td, "ReturnSuccess"), v)
        if ret:
            last["return"] = ret
        last["contact_points"] = max(last.get("contact_points", 0), cp)
        last["reward"] = reward or last.get("reward", "")
        add_secondary(last, secondary_of(kid(td, "ReturnSuccess")))
        fl = arg(td, "ForceTaskLevel")
        if fl.isdigit():
            for i in ids:
                out[i].setdefault("force_level", int(fl))
        rc = clues_of(kid(td, "ReturnSuccess"))
        if rc:
            last.setdefault("clues", {})["return"] = rc
        take_clues(td, tid.split("#")[0])
        return ids[0]
    t = dict(texts)
    t["type"] = TYPES[kind]
    t["id"] = tid
    t["long"] = "taskLong" in flags
    t["required"] = "taskRequired" in flags
    t["no_return"] = any(f.lower() == "taskdontreturntocontact" for f in flags)
    lo, hi = arg(td, "MinPlayerLevel", 0, "1"), arg(td, "MaxPlayerLevel", 0, "54")
    t["min_level"] = int(lo) if lo.isdigit() else 1
    t["max_level"] = int(hi) if hi.isdigit() else 54
    t["begin"] = line(kid(td, "TaskBegin") or {}, "Dialog", v)
    done = kid(td, "TaskComplete") or kid(td, "TaskSuccess")
    t["complete"], cp1, t["complete_reward"] = dialog_of(done, v)
    t["return"], cp2, t["reward"] = dialog_of(kid(td, "ReturnSuccess"), v)
    t["contact_points"] = cp1 + cp2
    add_secondary(t, secondary_of(done), "secondary")
    add_secondary(t, secondary_of(kid(td, "ReturnSuccess")))
    fl = arg(td, "ForceTaskLevel")
    if fl.isdigit():
        t["force_level"] = int(fl)
    take_clues(td, tid.split("#")[0])
    cl = {k: clues_of(n) for k, n in (("begin", kid(td, "TaskBegin")), ("complete", done),
                                       ("return", kid(td, "ReturnSuccess")))}
    t["clues"] = {k: c for k, c in cl.items() if c}
    if t["type"] == "killx":
        cnt = arg(td, "VillainCount", 0, "5")
        t["killx"] = {"group": arg(td, "VillainType"), "count": int(cnt) if cnt.isdigit() else 5,
                      "zone": arg(td, "VillainMap").lower(),
                      "what": line(td, "VillainDescription", v)}
    elif t["type"] == "deliver":
        npc = v.sub(arg(td, "DeliveryTargetName")).lower()
        t["deliver"] = {"npc": npc, "contact": npc_contact.get(npc, "")}
    elif t["type"] == "visit":
        t["visit"] = {"location": arg(td, "VisitLocationName").lower()}
    elif t["type"] == "mission":
        md = kid(td, "MissionDef")
        if md is None:
            return None
        t["mission"] = parse_mission(md, v)
    out[tid] = t
    return tid


def task_force(c, v):
    """A task force contact's rules (TaskForceName set), else None: the team size it needs,
    the names it gives the team (one picked) and its refusal lines (docs/story.md)."""
    if kid(c, "TaskForceName") is None:
        return None
    names = []
    tn = (kid(c, "TaskForceName").get("a") or [""])[0]
    src = next((x for x in kids(c, "var") if (x.get("a") or [""])[0].upper() == tn.upper()), None)
    if src is not None:
        names = [n for n in (clean(text_of(src, i)) for i in range(2, len(src["a"])))
                 if n and "never referenced" not in n.lower()]
    elif tn and not tn.upper().startswith("VAR_"):
        names = [clean(text_of(kid(c, "TaskForceName")))]
    size = arg(c, "MinTaskForceSize", 0, "1")
    adj = arg(c, "TaskForceLevelAdjust", 0, "0")
    tf = {"names": names, "min_size": int(size) if size.isdigit() else 1,
          "level_adjust": int(adj) if adj.lstrip("-").isdigit() else 0}
    for key, field in (("invite", "TaskForceInvite"), ("too_low", "PlayerLevelTooLow"),
                       ("too_high", "PlayerLevelTooHigh"), ("need_large_team", "NeedLargeTeam"),
                       ("need_leader", "NeedTeamLeader"), ("need_team_here", "NeedTeamOnMap"),
                       ("bad_team_level", "BadTeamLevel"), ("first_visit", "SOLFirstVisitString")):
        tf[key] = line(c, field, v)
    return tf


def reward_tables(story_dir, names):
    """Reward tables the tasks name (items/rewards.json, coh_items.py), per
    level: the XP and influence always given (rows with no Requires) and the
    drop rolls [chance %, [item sets]]."""
    path = os.path.join(os.path.dirname(os.path.abspath(story_dir)), "items", "rewards.json")
    if not os.path.isfile(path):
        print("no %s: tasks give no XP or influence of their own" % path)
        return {}
    raw = json.load(open(path, encoding="utf-8"))
    by_name = {}
    for defs in raw.values():
        for rt in defs:
            if rt["k"] == "RewardTable" and rt.get("a"):
                by_name[rt["a"][0].lower()] = rt
    out = {}
    for name in sorted(names):
        rt = by_name.get(name.lower())
        if rt is None:
            continue
        levels = {}
        for lv in kids(rt, "Level"):
            lvl = (lv.get("a") or ["0"])[0]
            xp = inf = 0
            drops = []
            for ch in kids(lv, "Chance"):
                if kid(ch, "Requires") is not None:
                    continue
                a = ch.get("a") or ["0"]
                if "Always" in a:
                    try:
                        xp += int(arg(ch, "Experience", 0, "0"))
                        inf += int(arg(ch, "Influence", 0, "0"))
                    except ValueError:
                        pass
                sets = [arg(dg, "ItemSetName") for dg in kids(ch, "DropGroup")]
                sets = [x for x in sets if x]
                if sets:
                    try:
                        drops.append([float(a[0]), sets])
                    except ValueError:
                        pass
            levels[lvl] = {"xp": xp, "inf": inf, "drops": drops}
        out[name] = levels
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    d = sys.argv[1]
    load = lambda n: json.load(open(os.path.join(d, n), encoding="utf-8"))
    contacts, tasksets, arcs_raw = load("contacts.json"), load("tasksets.json"), load("storyarcs.json")
    npcs, points = load("npcs.json"), load("world_points.json")["zones"]
    INCS.update(load("spawnincs.json") if os.path.isfile(os.path.join(d, "spawnincs.json")) else {})

    npc_contact, npc_model, npc_by_name = {}, {}, {}
    for key, defs in npcs.items():
        for n in defs:
            if n["k"] != "NPCDef":
                continue
            name = (n.get("a") or [os.path.basename(key)])[0].lower()
            c = norm(arg(n, "Contact"))
            npc_by_name[name] = key
            npc_model[key] = arg(n, "Model")
            if c:
                npc_contact[name] = c
                npc_contact[key] = c

    # an NPC with no Contact line: the contact file of the same name
    by_base = {}
    for ck in contacts:
        by_base.setdefault(os.path.splitext(os.path.basename(ck))[0], ck)
    for name in list(npc_by_name):
        if name not in npc_contact and name in by_base:
            npc_contact[name] = by_base[name]

    placed = {}            # contact -> (zone, point)
    for zone, z in points.items():
        for p in z["npcs"]:
            c = npc_contact.get(p["npc"])
            if c and "world_cm" in p and c not in placed:
                placed[c] = (zone, p)
    # deliveries go to the NPC's contact; if the NPC is not a contact, to its placement
    for zone, z in points.items():
        for p in z["npcs"]:
            base = os.path.splitext(os.path.basename(p["npc"]))[0]
            npc_contact.setdefault(base, npc_contact.get(p["npc"], ""))

    tasks, arcs, out_contacts = {}, {}, {}
    taskset_cache = {}

    def taskset_ids(path):
        key = norm(path)
        if key in taskset_cache:
            return taskset_cache[key]
        ids = []
        for root in tasksets.get(key, []):
            defs = [root] if root["k"] == "TaskDef" else kids(root, "TaskDef")
            rv = Vars().take(root)
            for td in defs:
                name = arg(td, "Name") or str(len(ids))
                tid = compile_task(td, "%s#%s" % (key, name), rv, npc_contact, tasks)
                if tid:
                    ids.append(tid)
        taskset_cache[key] = ids
        return ids

    def arc_ids(path):
        key = norm(path)
        if key in arcs:
            return key
        for root in arcs_raw.get(key, []):
            v = Vars().take(root)
            take_clues(root, key)
            eps = []
            for i, ep in enumerate(kids(root, "Episode")):
                td = kid(ep, "TaskDef")
                if td is None:
                    continue
                tid = compile_task(td, "%s#%d" % (key, i + 1), v, npc_contact, tasks)
                if not tid:
                    continue
                ret, cp, reward = dialog_of(kid(ep, "ReturnSuccess"), v)
                last = tid
                while tasks[last].get("next"):
                    last = tasks[last]["next"]
                if ret:
                    tasks[last]["return"] = ret
                tasks[last]["contact_points"] += cp
                tasks[last]["reward"] = reward or tasks[last]["reward"]
                add_secondary(tasks[last], secondary_of(kid(ep, "ReturnSuccess")))
                rc = clues_of(kid(ep, "ReturnSuccess"))
                if rc:
                    have = tasks[last].setdefault("clues", {}).setdefault("return", {})
                    for k, x in rc.items():
                        have[k] = have.get(k, []) + x
                eps.append(tid)
            for a, b in zip(eps, eps[1:]):
                last = a
                while tasks[last].get("next"):
                    last = tasks[last]["next"]
                tasks[last]["next"] = b
            lo, hi = arg(root, "minplayerlevel", 0, "1"), arg(root, "maxplayerlevel", 0, "54")
            arcs[key] = {"name": clean(text_of(kid(root, "name"))),
                         "min_level": int(lo) if lo.isdigit() else 1,
                         "max_level": int(hi) if hi.isdigit() else 54,
                         "episodes": eps}
            for e in eps:
                tasks[e]["arc"] = key
        return key if key in arcs else None

    for ckey, (zone, p) in sorted(placed.items()):
        roots = contacts.get(ckey)
        if not roots:
            continue
        c = roots[0]
        if arg(c, "Alliance", 0, "Hero").lower() not in ("hero", "both", "neutral"):
            continue
        v = Vars().take(c)
        flags = [f.lower() for fl in kids(c, "Flags") for f in fl.get("a", [])]
        hello = []
        h = kid(c, "HelloString")
        if h is not None:
            hv = (h.get("a") or [""])[0]
            src = next((x for x in kids(c, "var") if (x.get("a") or [""])[0] == hv), None)
            if src is not None:
                hello = [clean(text_of(src, i)) for i in range(2, len(src["a"]))]
            else:
                hello = [clean(text_of(h))]
        store = []
        st = kid(c, "Store")
        if st is not None:
            for tier in st.get("c", []):
                for it in kids(tier, "Item"):
                    pr = arg(it, "Price", 0, "0")
                    store.append({"tier": tier["k"], "price": int(pr) if pr.isdigit() else 0,
                                  "item": (kid(it, "Power") or {}).get("a", [])})
        tids = []
        for inc in kids(c, "TaskInclude"):
            tids += taskset_ids((inc.get("a") or [""])[0])
        arc_list = [a for a in (arc_ids((s.get("a") or [""])[0]) for s in kids(c, "StoryArc")) if a]
        def num(key, default):
            x = arg(c, key, 0, str(default))
            return int(x) if x.lstrip("-").isdigit() else default
        out_contacts[ckey] = {
            "name": line(c, "Name", v), "profession": line(c, "ProfessionString", v),
            "description": line(c, "DescriptionString", v), "location": line(c, "LocationString", v),
            "zone": zone, "npc": p["npc"], "model": npc_model.get(p["npc"], ""),
            "pos": p["world_cm"], "yaw": p["yaw_deg"],
            "min_level": num("MinPlayerLevel", 1), "max_level": num("MaxPlayerLevel", 54),
            "complete_level": num("CompletePlayerLevel", 54), "failsafe_level": num("FailsafePlayerLevel", 54),
            "friend_cp": num("FriendCP", 10), "confidant_cp": num("ConfidantCP", 20),
            "complete_cp": num("CompleteCP", 30),
            "requires": (kid(c, "ContactRequires") or {}).get("a", []),
            "stature_set": arg(c, "StatureSet"), "next_stature_set": arg(c, "NextStatureSet"),
            "flags": flags, "task_force": task_force(c, v),
            "hello": [x for x in hello if x],
            "first_visit": line(c, "FirstVisitString", v), "dont_know": line(c, "IDontKnowYouString", v),
            "no_tasks": line(c, "NoTasksRemainingString", v), "busy": line(c, "PlayerBusyString", v),
            "come_back": line(c, "ComeBackLaterString", v),
            "to_friend": line(c, "RelationshipChangeString_ToFriend", v),
            "to_confidant": line(c, "RelationshipChangeString_ToConfidant", v),
            "introduce_one": line(c, "IntroduceOneContact", v),
            "store": store, "stores": (kid(c, "Stores") or {}).get("a", []),
            "tasks": tids, "arcs": arc_list}

    used = set()
    for c in out_contacts.values():
        used.update(c["tasks"])
        for a in c["arcs"]:
            used.update(arcs[a]["episodes"])
    # keep the parts that follow a used task too
    frontier = list(used)
    while frontier:
        t = tasks.get(frontier.pop())
        if t and t.get("next") and t["next"] not in used:
            used.add(t["next"])
            frontier.append(t["next"])
    tasks = {k: v for k, v in tasks.items() if k in used}
    used_arcs = {a for c in out_contacts.values() for a in c["arcs"]}
    # persistent NPCs who are not contacts (delivery targets, people to talk to)
    people = {}
    targets = {t["deliver"]["npc"] for t in tasks.values() if t["type"] == "deliver"}
    for zone, z in points.items():
        for p in z["npcs"]:
            if npc_contact.get(p["npc"]) in out_contacts or "world_cm" not in p:
                continue
            nd = next((n for n in npcs.get(p["npc"], []) if n["k"] == "NPCDef"), None)
            if nd is None:
                continue
            name = (nd.get("a") or [""])[0].lower()
            if name in people or (name not in targets and kid(nd, "DisplayName") is None):
                continue
            people[name] = {"name": line(nd, "DisplayName", None) or name, "zone": zone, "store": arg(nd, "Store"),
                            "model": arg(nd, "Model"), "pos": p["world_cm"], "yaw": p["yaw_deg"],
                            "line": line(nd, "Dialog", None), "npc": p["npc"]}
    result = {"contacts": out_contacts, "tasks": tasks, "people": people,
              "arcs": {k: v for k, v in arcs.items() if k in used_arcs},
              "visits": {z: [{"name": p["name"], "pos": p["world_cm"]} for p in zp["visits"] if "world_cm" in p]
                         for z, zp in points.items()},
              "doors": {z: [{"lair": p["lair"], "pos": p["world_cm"], "yaw": p["yaw_deg"]}
                            for p in zp["doors"] if "world_cm" in p] for z, zp in points.items()},
              "spawns": {z: [{"name": p["name"], "pos": p["world_cm"], "yaw": p["yaw_deg"]}
                             for p in zp["spawns"] if "world_cm" in p] for z, zp in points.items()}}
    souvenirs = {}
    if os.path.isfile(os.path.join(d, "souvenirs.json")):
        for defs in load("souvenirs.json").values():
            for sc in defs:
                if sc["k"] == "SouvenirClueDef" and sc.get("a"):
                    souvenirs[sc["a"][0].lower()] = {"name": clean(text_of(kid(sc, "Name"))),
                                                     "text": clean(text_of(kid(sc, "DetailString")))}
    result["souvenirs"] = souvenirs
    # clues of the kept tasks only
    scopes = {k.split("#")[0] for k in tasks}
    result["clues"] = {k: c for k, c in CLUES.items() if k.split("#")[0] in scopes}
    result["rewards"] = reward_tables(d, {t[k] for t in tasks.values()
                                          for k in ("reward", "complete_reward") if t.get(k)}
                                      | {x for t in tasks.values()
                                         for x in t.get("secondary", []) + t.get("return_secondary", [])})
    with open(os.path.join(d, "story_game.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    by_type = {}
    for t in tasks.values():
        by_type[t["type"]] = by_type.get(t["type"], 0) + 1
    print("contacts placed %d, with tasks %d, tasks %d %s, arcs %d" % (
        len(out_contacts), sum(1 for c in out_contacts.values() if c["tasks"] or c["arcs"]),
        len(tasks), by_type, len(result["arcs"])))
    kinds = {}
    for t in tasks.values():
        for sp in t.get("mission", {}).get("spawns", []):
            kinds[sp["kind"]] = kinds.get(sp["kind"], 0) + 1
    print("mission spawns %s, clues %d, souvenirs %d" % (kinds, len(result["clues"]), len(souvenirs)))


if __name__ == "__main__":
    main()

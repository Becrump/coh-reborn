"""Talk-to-target simulator for the AI speech system (CoH Reborn).

Mirrors what the host will do in Unreal for one conversation turn, so the
prompts, rules and model can be tested before any game code exists:

  snapshot (who / where / what happened / what the hero knows)
    -> game rules: combat check, word filter, approach, secret mentions,
       Resolve, clue unlock, sway roll            (the game decides)
    -> model writes {say, think, emote} for that result (the model words it)
    -> checks: length, filter, no leaked locked secrets, emote on the list
    -> word balloon (fallback line if anything fails)

    python tools/talk/talk_sim.py --selftest                 # rules only, no model
    python tools/talk/talk_sim.py --npc thug --hero blue_comet            # chat, fallback lines
    python tools/talk/talk_sim.py --npc cinder --hero blue_comet --gguf model.gguf
    python tools/talk/talk_sim.py --npc thug --hero ironjaw --server http://127.0.0.1:8080
    python tools/talk/talk_sim.py --script tools/talk/mock_script.json --server http://127.0.0.1:8080 --log out.jsonl

--server talks to llama.cpp's llama-server (OpenAI-style /v1/chat/completions),
which is what the game will run. --gguf loads the model in-process through
llama-cpp-python (handy in the cloud). With neither, fallback lines are used.
Standard library only, except for --gguf.
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "talk_data.json")
WORLD = os.path.join(HERE, "mock_world.json")

EMOTES = ["none", "laugh", "cower", "point", "shrug", "salute", "angry", "wave", "think", "plead"]
VILLAIN_KINDS = ("informant", "rival")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- game rules

def tier_for(data, rep):
    for t in data["reputation_tiers"]:
        if rep >= t["min"]:
            return t
    return data["reputation_tiers"][-1]


def words(text):
    return re.findall(r"[a-z']+", text.lower())


def filtered(data, text):
    low = " " + " ".join(words(text)) + " "
    return any(" " + w + " " in low for w in data["word_filter"]["words"])


def mentions(text, secrets):
    """Secrets whose keywords appear in text (whole words or phrases)."""
    low = " " + " ".join(words(text)) + " "
    return [s for s in secrets if any(" " + " ".join(words(k)) + " " in low for k in s["keywords"])]


KEYWORD_APPROACH = [
    ("threaten", r"\b(or else|hurt|break|smash|pain|jail|zig|last chance|talk now|i'll make you)\b"),
    ("ask_clue", r"\b(where|who|what.*plan|plan|boss|hiding|working with|next job|tell me)\b"),
    ("sympathize", r"\b(family|kid|daughter|son|mother|mom|brother|how did you|ended up|sorry)\b"),
    ("persuade", r"\b(help you|better|deal|leniency|good word|don't have to|walk away|right thing|you can)\b"),
]


def keyword_approach(text, allowed):
    low = text.lower()
    for a, rx in KEYWORD_APPROACH:
        if a in allowed and re.search(rx, low):
            return a
    return "chat"


def allowed_approaches(npc, state):
    ok = ["chat", "ask_clue"]
    if npc["kind"] in VILLAIN_KINDS:
        ok += ["persuade", "threaten", "sympathize"]
    if npc["kind"] == "rival" and (state.get("showdown") or state.get("parley")):
        ok.append("speech")
    return ok


def state_showdown(snap):
    st = snap.get("state", {})
    return snap["npc"]["kind"] == "rival" and bool(st.get("showdown") or st.get("parley"))


def apply_rules(data, snap, approach, said, rng):
    """The game's half of a turn. Returns a 'result' dict the model must word. Mutates npc/hero state."""
    npc, hero = snap["npc"], snap["hero"]
    tier = tier_for(data, hero["reputation"])
    known = set(hero.get("known", []))
    res = {"approach": approach, "tier": tier["id"], "outcome": "talk", "clue": None, "secret_hits": [],
           "resolve_before": npc.get("resolve"), "rep_delta": 0}

    if npc["kind"] in VILLAIN_KINDS:
        temp = data["temperaments"][npc.get("temperament", "Arrogant")]
        found = [s for s in npc.get("secrets", []) if s["id"] in known]
        res["secret_hits"] = [s["id"] for s in mentions(said, found)]

        if state_showdown(snap) and approach in ("persuade", "sympathize", "speech"):
            approach = res["approach"] = "speech"   # at a showdown, any appeal is the heroic speech
        if approach == "speech":
            mot = sum(1 for s in found if s["id"] in res["secret_hits"] and s["type"] == "motive")
            weak = sum(1 for s in found if s["id"] in res["secret_hits"] and s["type"] == "weakness")
            sw = data["sway"]
            chance = temp["sway_base"] + mot * sw["per_motive_secret"] + weak * sw["per_weakness_secret"] \
                + sw["reputation_scale"] * hero["reputation"] / 100.0
            chance = max(0.0, min(data["limits"]["sway_cap"], chance))
            roll = rng.random()
            res.update(sway_chance=round(chance, 2), roll=round(roll, 2),
                       outcome="swayed" if roll < chance else "enraged")
            res["rep_delta"] = data["reputation_events"]["villain_talked_down"] if roll < chance else 0
            return res

        delta = temp.get(approach, 0)
        scale = data["temperaments"]["rep_scale"] * hero["reputation"] / 100.0
        if approach in ("persuade", "sympathize"):
            delta -= scale            # beloved heroes persuade better
        elif approach == "threaten":
            delta += scale            # feared heroes threaten better
            res["rep_delta"] = data["reputation_events"]["brutal_interrogation"]
        delta -= 6 * len(res["secret_hits"])   # naming a found secret rattles them
        npc["resolve"] = max(0, min(100, npc.get("resolve", 60) + round(delta)))
        res["resolve_after"] = npc["resolve"]

        th = dict(data["clue_thresholds"])
        bonus = th["telepath_bonus"] if hero.get("telepath") else 0
        if approach in ("ask_clue", "persuade", "threaten", "sympathize"):
            for c in npc.get("clues", []) + [dict(id=s["id"], tier="secret", text=npc["name"] + " " + s["text"])
                                                for s in npc.get("secrets", [])]:
                if c["id"] in known:
                    continue
                if npc["resolve"] <= th[c["tier"]] + bonus:
                    res["clue"] = c
                    break
        res["outcome"] = "crack" if res["clue"] else ("resist" if npc["resolve"] > 20 else "broken")
    elif npc["kind"] == "rescued_civilian":
        new = [c for c in npc.get("clues", []) if c["id"] not in known]
        if new and approach in ("ask_clue", "chat"):
            res["clue"] = new[0]
            res["outcome"] = "crack"
    if res["clue"]:
        hero.setdefault("known", []).append(res["clue"]["id"])
    return res


# ---------------------------------------------------------------- prompts

def persona(data, snap):
    npc, hero, place = snap["npc"], snap["hero"], snap["place"]
    kind = data["kinds"][npc["kind"]]
    tier = tier_for(data, hero["reputation"])
    fill = {
        "name": npc["name"], "zone": place["zone"], "hero": hero["name"], "faction": npc.get("faction", ""),
        "rank": npc.get("rank", ""), "stage_title": npc.get("stage_title", ""), "boss": npc.get("boss", "the boss"),
        "voice": data["faction_voices"].get(npc.get("faction", ""), ""),
        "temperament_lc": npc.get("temperament", "").lower(),
        "history": "; ".join(npc.get("history", [])) or "none yet",
        "grounding": npc.get("grounding", ""),
    }
    lines = [kind["persona"].format(**fill),
             "Your attitude toward this hero: " + tier["tone"][kind["audience"]],
             "Where: %s, %s, %s." % (place["zone"], place["landmark"], place["time"]),
             "The hero is %s, a level %d %s with %s." % (hero["name"], hero["level"], hero["archetype"],
                                                         ", ".join(hero["powers"]))]
    if snap.get("events"):
        lines.append("Recent events you may mention: " + " ".join(snap["events"]))
    known = set(hero.get("known", []))
    shared = [c["text"] for c in npc.get("clues", []) if c["id"] in known]
    if shared:
        lines.append("Things the hero already knows: " + " ".join(shared))
    found = [s for s in npc.get("secrets", []) if s["id"] in known]
    if found:
        lines.append("The hero has found out that you " + "; and that you ".join(s["text"] for s in found) + ".")
    lines.append("Setting: City of Heroes, a comic-book superhero city. Keep it PG-13, no gore, no slurs. "
                 "Never invent places, names or plans that are not given to you here.")
    return "\n".join(lines)


def outcome_note(res, npc, hero):
    o = res["outcome"]
    if o == "crack":
        return ("You give in and reveal exactly this, in your own words: \"%s\" Do not add other details."
                % res["clue"]["text"])
    if o == "resist":
        return "You refuse to give up any information. Stay in character."
    if o == "broken":
        return "You are scared and beaten but genuinely know nothing more. Say so."
    if o == "swayed":
        return "The hero's words got through to you. You give up your plan and stand down, emotionally."
    if o == "enraged":
        return "The hero touched a nerve and you are furious. You refuse and swear to fight harder."
    if npc["kind"] == "contact":
        return "Answer only from your briefing notes."
    return "Just chat. You have no secret information to share."


SAY_SCHEMA = {
    "type": "object",
    "properties": {"say": {"type": "string"}, "emote": {"type": "string", "enum": EMOTES}},
    "required": ["say", "emote"],
}

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "say": {"type": "string"},
        "think": {"type": "string"},
        "emote": {"type": "string", "enum": EMOTES},
    },
    "required": ["say", "think", "emote"],
}


def classify_messages(snap, text, allowed, approaches):
    menu = "\n".join("- %s: %s" % (a, approaches[a]["desc"]) for a in allowed)
    return [
        {"role": "system", "content": "You label what a superhero player is trying to do when talking to an NPC. "
                                      "Pick exactly one label.\n" + menu + "\n/no_think"},
        {"role": "user", "content": "NPC: %s (%s)\nPlayer says: %s" % (snap["npc"]["name"], snap["npc"]["kind"], text)},
    ]


def reply_messages(data, snap, text, res, tele=True):
    lim = data["limits"]
    fmt = ('Reply as JSON: "say" = what you say out loud (1-2 short sentences, max %d words). '
           'Speak in first person as %s only: no narration, no asterisks, no stage directions, no quotes. '
           % (lim["reply_max_words"], snap["npc"]["name"]))
    if tele:
        fmt += '"think" = your private thought (max %d words). ' % lim["thought_max_words"]
    fmt += '"emote" = one of %s.\n/no_think' % ", ".join(EMOTES)
    sys_msg = (persona(data, snap) + "\n\nGAME RESULT (must follow): "
               + outcome_note(res, snap["npc"], snap["hero"]) + "\n" + fmt)
    msgs = [{"role": "system", "content": sys_msg}]
    for turn in snap.get("conversation", [])[-lim["history_turns"]:]:
        msgs.append({"role": "user" if turn["who"] == "hero" else "assistant", "content": turn["text"]})
    msgs.append({"role": "user", "content": "%s says: %s" % (snap["hero"]["name"], text)})
    return msgs


# ---------------------------------------------------------------- model backends

def strip_think(s):
    return re.sub(r"<think>.*?</think>", "", s or "", flags=re.S).strip()


class HttpModel:
    """llama.cpp llama-server, the program the game will launch next to itself."""

    def __init__(self, url, timeout):
        self.url, self.timeout = url.rstrip("/"), timeout

    def chat(self, messages, schema, max_tokens):
        body = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.7,
                "response_format": {"type": "json_object", "schema": schema},
                "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request(self.url + "/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.load(r)
        return strip_think(out["choices"][0]["message"]["content"])


class LocalModel:
    """Same thing in-process through llama-cpp-python (cloud testing)."""

    def __init__(self, path, threads):
        from llama_cpp import Llama
        self.llm = Llama(model_path=path, n_ctx=4096, n_threads=threads, verbose=False)

    def chat(self, messages, schema, max_tokens):
        out = self.llm.create_chat_completion(messages=messages, max_tokens=max_tokens, temperature=0.7,
                                              response_format={"type": "json_object", "schema": schema})
        return strip_think(out["choices"][0]["message"]["content"])


# ---------------------------------------------------------------- one turn

def fallback(data, snap, res, rng):
    fb, npc, hero = data["fallback_lines"], snap["npc"], snap["hero"]
    kind, tier = npc["kind"], res["tier"]
    table = fb.get(kind, {})
    key = res["outcome"] if res["outcome"] in table else (tier if tier in table else ("any" if "any" in table else None))
    if kind in VILLAIN_KINDS and key is None:
        key = "flavor" if "flavor" in table else "resist"
    pool = table.get(key) or ["..."]
    clue = res["clue"]["text"] if res.get("clue") else ""
    return rng.choice(pool).format(hero=hero["name"], zone=snap["place"]["zone"], clue=clue)


def clean_reply(reply):
    """Strips stage directions the small models like to add (*sigh*, 'You smirk.')."""
    for f in ("say", "think"):
        t = reply.get(f)
        if isinstance(t, str):
            t = re.sub(r"\*[^*]{0,60}\*", "", t)
            t = re.sub(r"^(you|he|she|they)\s+\w+[^.!?']{0,60}[.,]\s*", "", t, flags=re.I) if f == "say" else t
            reply[f] = re.sub(r"\s{2,}", " ", t).strip().strip("'\"}").strip()
    return reply


def check_reply(data, snap, res, reply):
    """Host-side checks before a model line is shown. Returns a reason string or None."""
    lim = data["limits"]
    reply.setdefault("think", "")
    if not isinstance(reply.get("say"), str) or not reply["say"].strip():
        return "missing say"
    if len(words(reply["say"])) > lim["reply_max_words"] + 10:
        return "too long"
    if reply.get("emote") not in EMOTES:
        return "bad emote"
    if filtered(data, reply["say"]) or filtered(data, str(reply["think"])):
        return "word filter"
    known = set(snap["hero"].get("known", []))
    locked = [s for s in snap["npc"].get("secrets", []) if s["id"] not in known]
    if mentions(reply["say"], locked):
        return "leaked a locked secret"
    if res["outcome"] == "crack":
        need = [w for w in words(res["clue"]["text"]) if len(w) > 5]
        if need and not any(w in words(reply["say"]) for w in need):
            return "clue missing from reply"
    return None


def talk_turn(data, snap, text, model=None, rng=None):
    rng = rng or random.Random()
    npc, hero, state = snap["npc"], snap["hero"], snap.setdefault("state", {})
    out = {"npc": npc["name"], "hero": hero["name"], "player": text, "thinking": "\U0001F4AD"}
    if state.get("hero_in_combat") or state.get("npc_in_combat"):
        out.update(blocked="combat", say=None)
        return out
    if filtered(data, text):
        out.update(say=rng.choice(data["word_filter"]["filtered"]), source="filter", think="", emote="angry")
        return out

    t0 = time.time()
    allowed = allowed_approaches(npc, state)
    approach = keyword_approach(text, allowed)
    if model and npc["kind"] not in ("civilian", "police", "contact"):
        try:
            raw = model.chat(classify_messages(snap, text, allowed, data["approaches"]),
                             {"type": "object", "properties": {"approach": {"type": "string", "enum": allowed}},
                              "required": ["approach"]}, 24)
            pick = json.loads(raw).get("approach")
            if pick in allowed:
                approach = pick
        except Exception as e:  # noqa: BLE001 - any failure keeps the keyword guess
            out["classify_error"] = str(e)[:120]
    t1 = time.time()

    res = apply_rules(data, snap, approach, text, rng)
    out["rules"] = res
    reply, why = None, "no model"
    if model:
        try:
            tele = bool(hero.get("telepath"))
            schema = REPLY_SCHEMA if tele else SAY_SCHEMA   # only telepaths need the hidden thought
            raw = model.chat(reply_messages(data, snap, text, res, tele), schema, 110 if tele else 70)
            reply = clean_reply(json.loads(raw))
            why = check_reply(data, snap, res, reply)
        except Exception as e:  # noqa: BLE001
            why = "model error: " + str(e)[:120]
    t2 = time.time()
    if why:
        reply = {"say": fallback(data, snap, res, rng), "think": "", "emote": "none"}
        out["fallback_reason"] = why
    out.update(say=reply["say"], think=reply.get("think", "") if hero.get("telepath") else "(hidden: not a telepath)",
               think_raw=reply.get("think", ""), emote=reply["emote"], source="fallback" if why else "model",
               ms_classify=round((t1 - t0) * 1000), ms_reply=round((t2 - t1) * 1000))
    snap.setdefault("conversation", []).extend([{"who": "hero", "text": text}, {"who": "npc", "text": reply["say"]}])
    return out


def make_snapshot(world, npc_id, hero_id, state=None):
    snap = {"npc": json.loads(json.dumps(world["npcs"][npc_id])), "hero": json.loads(json.dumps(world["heroes"][hero_id])),
            "place": world["place"], "events": world["events"], "state": dict(state or {}), "conversation": []}
    snap["npc"].setdefault("resolve", 60)
    return snap


def show(out):
    if out.get("blocked"):
        print("  [blocked: %s]" % out["blocked"])
        return
    r = out.get("rules", {})
    print("  %s> %s" % (out["hero"], out["player"]))
    print("  \U0001F4AC %s: %s  [%s]" % (out["npc"], out["say"], out.get("emote")))
    print("  \U0001F4AD %s" % out.get("think_raw", ""))
    print("     approach=%s outcome=%s resolve %s->%s clue=%s secrets=%s sway=%s src=%s %s ms+%s ms%s" % (
        r.get("approach"), r.get("outcome"), r.get("resolve_before"), r.get("resolve_after", "-"),
        (r.get("clue") or {}).get("id"), r.get("secret_hits"), r.get("sway_chance", "-"), out.get("source"),
        out.get("ms_classify"), out.get("ms_reply"),
        (" (" + out["fallback_reason"] + ")") if out.get("fallback_reason") else ""))


def summary(outs, a):
    done = [o for o in outs if "ms_reply" in o]
    if not done:
        return
    rep = sorted(o["ms_reply"] for o in done)
    cls = [o["ms_classify"] for o in done if o["ms_classify"]]
    fb = sum(1 for o in done if o.get("source") == "fallback")
    line = ("SUMMARY model=%s turns=%d reply_ms avg=%d median=%d max=%d classify_ms avg=%d fallbacks=%d"
            % (a.server or a.gguf or "none", len(done), sum(rep) / len(rep), rep[len(rep) // 2], rep[-1],
               (sum(cls) / len(cls)) if cls else 0, fb))
    print("\n" + line)


# ---------------------------------------------------------------- self test

def selftest():
    data, world = load(DATA), load(WORLD)
    rng = random.Random(1)
    # combat blocks talk
    s = make_snapshot(world, "thug", "blue_comet", {"hero_in_combat": True})
    assert talk_turn(data, s, "where is cinder?", None, rng)["blocked"] == "combat"
    # coward thug cracks under threats from a feared hero, gives the minor clue first
    s = make_snapshot(world, "thug", "ironjaw")
    o = talk_turn(data, s, "Talk now or I'll make you hurt. Where is your boss?", None, rng)
    assert o["rules"]["approach"] == "threaten" and o["rules"]["clue"]["id"] == "clue_thug_warehouse", o
    assert o["rules"]["rep_delta"] < 0
    # street civilians never hold clues
    s = make_snapshot(world, "civilian", "blue_comet")
    assert talk_turn(data, s, "where is cinder hiding?", None, rng)["rules"]["clue"] is None
    # rescued civilian shares what they overheard
    s = make_snapshot(world, "rescued", "blue_comet")
    assert talk_turn(data, s, "Are you okay? Did you hear anything?", None, rng)["rules"]["clue"]["id"] == "clue_rescued_substation"
    # only DISCOVERED secrets count in a speech; guessing does nothing
    s = make_snapshot(world, "cinder", "mindwave", {"showdown": True})
    s["hero"]["known"] = []
    o = talk_turn(data, s, "Stop this. Think of your daughter, Lily.", None, rng)
    assert o["rules"]["approach"] == "speech" or o["rules"]["secret_hits"] == [], o["rules"]
    s = make_snapshot(world, "cinder", "blue_comet", {"showdown": True})
    r = apply_rules(data, s, "speech", "Don't do this. I know about your daughter Lily.", random.Random(3))
    assert r["secret_hits"] == ["secret_cinder_daughter"] and 0 < r["sway_chance"] <= 0.9, r
    # leak check catches a locked secret in a model reply
    s = make_snapshot(world, "cinder", "mindwave")
    bad = {"say": "My scar from the blaze? Whatever.", "think": "x", "emote": "none"}
    assert check_reply(data, s, {"outcome": "talk"}, bad) == "leaked a locked secret"
    # filter
    assert filtered(data, "just kys") and not filtered(data, "skyscraper")
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--npc", default="thug")
    ap.add_argument("--hero", default="blue_comet")
    ap.add_argument("--showdown", action="store_true")
    ap.add_argument("--server", help="llama-server URL, e.g. http://127.0.0.1:8080")
    ap.add_argument("--gguf", help="model file for in-process llama-cpp-python")
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--script", help="JSON list of {npc, hero, state, lines[]} to run")
    ap.add_argument("--log", help="append each turn as JSON lines")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    data, world = load(DATA), load(WORLD)
    rng = random.Random(a.seed)
    model = None
    if a.server:
        model = HttpModel(a.server, data["limits"]["model_timeout_s"] * 5)
    elif a.gguf:
        model = LocalModel(a.gguf, a.threads)
    log = open(a.log, "a", encoding="utf-8") if a.log else None

    outs = []

    def run(snap, line):
        out = talk_turn(data, snap, line, model, rng)
        outs.append(out)
        show(out)
        if log:
            log.write(json.dumps(out, ensure_ascii=False) + "\n")

    if a.script:
        for scene in load(a.script):
            print("\n== %s talks to %s %s" % (scene["hero"], scene["npc"], scene.get("state", "")))
            snap = make_snapshot(world, scene["npc"], scene["hero"], scene.get("state"))
            for line in scene["lines"]:
                run(snap, line)
        summary(outs, a)
        return
    snap = make_snapshot(world, a.npc, a.hero, {"showdown": a.showdown})
    print("Talking to %s as %s. Empty line quits." % (snap["npc"]["name"], snap["hero"]["name"]))
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            break
        run(snap, line)


if __name__ == "__main__":
    sys.exit(main())

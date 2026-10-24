"""Write one upgrade batch per enemy group from the export index.

    python tools/upgrade/make_batches.py <characters dir> <work root>

Rules below decide which costumes get a shared new head and glove. Unique
named characters, robots (Clockwork), animals, demons, huge bodies and
Rikti keep their own pieces and only get the upscale + smooth pass. Every
upgraded character is imported into Unreal under /Game/Upgraded/<Group>/
without being placed in the level.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE = ("stylized modern video game character, clean sculpt, studio "
         "lighting, plain light grey background, isolated")
HEAD = ("3D character bust, {d}, front view facing the camera, symmetrical, "
        "head and neck only, " + STYLE)
HAND = ("3D render of a single {who} right human hand, {d}, fingers relaxed "
        "and slightly spread, back of the hand facing the camera, forearm cut "
        "off cleanly at the wrist, " + STYLE)

# group -> {part name: description}, then costume regex -> (head, hand)
PARTS = {
    "Hellions": {
        "hellion_boss_head": HEAD.format(d="a street gang boss, his whole face is a dark crimson demon mask with a snarling mouth of sharp teeth, two long curved ivory bone spikes jut outward from each cheek like tusks, short olive brown flat-top hair, thick neck"),
        "hellion_minion_head": HEAD.format(d="a young male street gang thug, lower face covered by a dark red bandana printed with white skulls, red baseball cap worn backwards, angry eyes"),
        "hellion_glove": HAND.format(who="muscular", d="wearing a red fingerless leather glove with white studs on the knuckles"),
    },
    "Skulls": {
        "skull_male_head": HEAD.format(d="a male street gang member whose face is painted as a white skull with black eye sockets and painted teeth, shaved head"),
        "skull_female_head": HEAD.format(d="a female street gang member whose face is painted as a white skull with black eye sockets and painted teeth, long black hair"),
        "skull_glove_m": HAND.format(who="male", d="wearing a black fingerless leather glove with a small white skull on the back"),
        "skull_glove_f": HAND.format(who="slender female", d="wearing a black fingerless leather glove with a small white skull on the back"),
    },
    "Outcasts": {
        "outcast_head": HEAD.format(d="a male punk street gang member with a tall spiked mohawk, facial piercings, smirking, wearing dark sunglasses"),
        "outcast_glove": HAND.format(who="male", d="wearing a black studded fingerless glove with a metal wristband"),
    },
    "Trolls": {
        "troll_head": HEAD.format(d="a hulking troll gang member with rough green rocky skin, small spikes growing from the scalp and brow, heavy jaw, angry"),
        "troll_hand": HAND.format(who="huge muscular", d="with rough green rocky skin and thick dark nails, no glove"),
    },
    "Vahzilok": {
        "reaper_head": HEAD.format(d="a sinister surgeon cultist wearing a white surgical cap, a blood-stained surgical mask over nose and mouth and round brass goggles"),
        "reaper_glove": HAND.format(who="male", d="wearing a pale blue latex surgical glove with blood stains"),
    },
    "TheLost": {
        "lost_head": HEAD.format(d="a homeless male cultist wearing a ragged dark grey hood, gaunt pale face, stubble, wild staring eyes"),
        "lost_hand": HAND.format(who="thin dirty male", d="with grimy skin and cracked nails, a strip of dirty cloth wrapped around the wrist"),
    },
    "CircleOfThorns": {
        "cot_head_m": HEAD.format(d="a male dark mage wearing a deep hood, face hidden behind a carved bone-white ritual mask with thorn patterns"),
        "cot_head_f": HEAD.format(d="a female dark mage wearing a deep hood, face hidden behind a carved bone-white ritual mask with thorn patterns"),
        "cot_glove_m": HAND.format(who="male", d="wearing a dark leather glove wrapped with thorny vine patterns"),
        "cot_glove_f": HAND.format(who="slender female", d="wearing a dark leather glove wrapped with thorny vine patterns"),
    },
    "5thColumn": {
        "fog_head": HEAD.format(d="a soldier in a dark grey military helmet and a full gas mask with round glass eyepieces"),
        "fog_glove": HAND.format(who="male", d="wearing a black military tactical glove"),
    },
    "Council": {
        "council_head": HEAD.format(d="a soldier wearing a dark military helmet with a red visor band over the eyes and a high armoured collar"),
        "council_glove": HAND.format(who="male", d="wearing a black armoured tactical glove"),
    },
}
RULES = {
    "Hellions": [(r"^Thug_Hellion_Boss_\d+$", "hellion_boss_head", "hellion_glove"),
                 (r"^Thug_Hellion_\d+$", "hellion_minion_head", "hellion_glove")],
    "Skulls": [(r"^Thug_Skull_Male_(Minion|Lieutenant|Boss|Death)", "skull_male_head", "skull_glove_m"),
               (r"^Thug_Skull_Female_", "skull_female_head", "skull_glove_f")],
    "Outcasts": [(r"^Thug_Outcast(_Boss)?_\d+$", "outcast_head", "outcast_glove")],
    "Trolls": [(r"^Thug_Troll(_Boss)?_\d+$", "troll_head", "troll_hand")],
    "Vahzilok": [(r"^Reaper_\d+$", "reaper_head", "reaper_glove")],
    "TheLost": [(r"^Lost_\d+$", "lost_head", "lost_hand")],
    "CircleOfThorns": [(r"^CoT_(Minion_Male|Lt|Boss)", "cot_head_m", "cot_glove_m"),
                       (r"^CoT_Minion_Female", "cot_head_f", "cot_glove_f")],
    "5thColumn": [(r"^5thFog_\d+$", "fog_head", "fog_glove")],
    "Council": [(r"^Council_(Nebula|Penumbra|Galaxy)_", "council_head", "council_glove")],
}
HUMAN = ("male/skel_ready2", "fem/skel_ready2")
# per-head fitting tweaks found by checking the renders: long hair makes a
# head read wider than its skull, so scale it up to the old head's size
HEAD_TUNING = {"skull_female_head": {"width_scale": 1.55},
               "outcast_head": {"top_offset": 0.14, "width_band": [0.4, 0.7]},
               "fog_head": {"width_scale": 1.35, "top_offset": 0.03}}


def main(chars_dir, work_root):
    index = json.load(open(os.path.join(chars_dir, "index.json")))
    os.makedirs(os.path.join(HERE, "jobs"), exist_ok=True)
    groups = sorted({e["group"] for e in index})
    for g in groups:
        chars = []
        used = set()
        for e in sorted(index, key=lambda e: e["costume"]):
            if e["group"] != g:
                continue
            item = {"costume": e["costume"],
                    "unreal": {"dest": "/Game/Upgraded/%s/%s" % (g, e["costume"]),
                               "label": e["costume"] + "_Upgraded",
                               "place": None}}
            if e["skeleton"] in HUMAN and "Hand_R" in e["parts"]:
                for pat, head, hand in RULES.get(g, []):
                    if re.search(pat, e["costume"]):
                        item["head"], item["hand"] = head, hand
                        used.update((head, hand))
                        break
            chars.append(item)
        parts = {}
        for name in sorted(used):
            p = {"prompt": PARTS[g][name], "seed": 20261007}
            if "head" in name:
                p.update(faces=18000, replace=["Head", "Hair", "EyeDetail"])
                p.update(HEAD_TUNING.get(name, {}))
            else:
                p.update(faces=9000, is_right_hand=True)
            parts[name] = p
        batch = {"fit_hands": False,      # heads only for now
                 "characters_dir": chars_dir.replace("\\", "/"),
                 "work_dir": os.path.join(work_root, g).replace("\\", "/"),
                 "parts": parts, "characters": chars}
        path = os.path.join(HERE, "jobs", "%s.json" % g)
        with open(path, "w") as f:
            json.dump(batch, f, indent=1)
        print("%-15s %3d characters, %2d with new parts, %d parts to generate"
              % (g, len(chars), sum(1 for c in chars if c.get("head")),
                 len(parts)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

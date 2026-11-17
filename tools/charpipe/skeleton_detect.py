"""Detect a humanoid skeleton's bone names and build a retarget2 family map at runtime (Blender).

Handles AccuRig / Character Creator (CC_Base_L_Upperarm ...), Unreal mannequin / MetaHuman (upperarm_l ...),
Mixamo (mixamorig:LeftArm ...), and charpipe / Meshy (LeftArm ...), including fingers.

    import skeleton_detect as SD
    fam = SD.detect(arm)                 # dict canonical joint -> bone name, plus 'fingers' info
    SD.register(R, arm, "auto")          # R = retarget2; then R.retarget(src, "coh", arm, "auto", ...)
"""
import re

FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"]


def _side(n):
    s = n.replace("mixamorig:", "").replace("CC_Base_", "")
    if re.search(r"(^|[_\.\s:])(l|left)([_\.\s]|$)", s, re.I) or re.match(r"^left", s, re.I) or re.search(r"_l$", s, re.I):
        return "l"
    if re.search(r"(^|[_\.\s:])(r|right)([_\.\s]|$)", s, re.I) or re.match(r"^right", s, re.I) or re.search(r"_r$", s, re.I):
        return "r"
    return None


def _core(n):
    """lower-case name without prefixes, side tokens and separators"""
    s = n.replace("mixamorig:", "").replace("CC_Base_", "").lower()
    s = re.sub(r"(^|[_\.\s])(l|r|left|right)(?=[_\.\s]|$)", "_", s)
    s = re.sub(r"^(left|right)", "", s)
    s = re.sub(r"_(l|r)$", "", s)
    return re.sub(r"[_\.\s:]+", "", s)


LIMB_RX = [("clav", r"^(clavicle|shoulder|collar)$"), ("uarm", r"^(upperarm|uparm|arm)$"),
           ("larm", r"^(forearm|lowerarm|elbow)$"), ("hand", r"^(hand|wrist)$"),
           ("uleg", r"^(thigh|upleg|upperleg)$"), ("lleg", r"^(calf|shin|leg|lowerleg|knee)$"),
           ("foot", r"^(foot|ankle)$"), ("toe", r"^(toebase|toe|ball|toes)$")]


def detect(arm):
    B = arm.data.bones
    names = [b.name for b in B]
    m = {}
    for n in names:
        c, sd = _core(n), _side(n)
        if sd:
            for key, rx in LIMB_RX:
                if re.match(rx, c) and key + "_" + sd not in m:
                    m[key + "_" + sd] = n
    # torso by hierarchy: hips = parent of both thighs' chain root, spine chain up to the neck
    hips = next((n for n in names if _core(n) in ("hip", "hips", "pelvis")), None)
    neck = next((n for n in names if re.match(r"^neck(01|1|twist01)?$", _core(n))), None)
    head = next((n for n in names if _core(n) == "head"), None)
    if hips is None and "uleg_l" in m:
        hips = B[m["uleg_l"]].parent.name if B[m["uleg_l"]].parent else None
    if hips and neck:
        chain = []
        b = B[neck].parent
        while b and b.name != hips and len(chain) < 8:
            chain.append(b.name)
            b = b.parent
        chain.reverse()  # bottom -> top (may include 'pelvis'-like helpers; keep the deforming spine ones)
        chain = [c for c in chain if not re.search(r"twist|ik|root|bone", c, re.I)]
        if chain:
            m["spine1"] = chain[0]
            m["spine2"] = chain[len(chain) // 2] if len(chain) > 2 else chain[0]
            m["chest"] = chain[-1]
    m.update({k: v for k, v in (("hips", hips), ("neck", neck), ("head", head)) if v})
    for sd in "lr":
        if "hand_" + sd in m:
            kids = [c for c in B[m["hand_" + sd]].children_recursive if re.search("middle", c.name, re.I) and "meta" not in c.name.lower()]
            if kids:
                m["hand_end_" + sd] = sorted(kids, key=lambda c: len(c.parent_recursive))[0].name
        th = finger(arm, "Left" if sd == "l" else "Right", "Thumb", 1)
        if th:
            m["thumb_" + sd] = th
    return m


def finger(arm, S, F, j):
    """bone name of finger F segment j (1 = knuckle) on side S ('Left'/'Right'), any naming convention"""
    B = arm.data.bones
    s, L = S[0].lower(), S[0]
    for cand in ("%s%s%d" % (S, F, j), "%s_%02d_%s" % (F.lower(), j, s), "CC_Base_%s_%s%d" % (L, F, j),
                 "mixamorig:%sHand%s%d" % (S, F, j), "%sHand%s%d" % (S, F, j), "%s_%s%d" % (L, F, j)):
        if cand in B:
            return cand
    rx = re.compile(r"%s.*?%d$" % (F.lower(), j))
    for b in B:
        if _side(b.name) == s and rx.search(b.name.lower().replace("_0", "_")) and "meta" not in b.name.lower():
            return b.name
    return None


def register(R, arm, family="auto"):
    fam = detect(arm)
    R.SKELETONS[family] = fam
    return fam


def missing(fam):
    need = ["hips", "spine1", "chest", "neck", "head"] + ["%s_%s" % (k, s) for k in ("uarm", "larm", "hand", "uleg", "lleg", "foot") for s in "lr"]
    return [k for k in need if k not in fam]

"""Skeleton-agnostic retargeter (Blender) with one shared bone mapping per body type.

Canonical joints -> bone names for each skeleton family. Torso joints copy
the source's world-space rotation change from its rest pose; limb joints are
carried by their parent, swung to the source limb direction, and (fix
'bend') twisted about the upper limb so the elbow/knee hinge plane matches
the source -> no backwards elbows / candy-wrapped shoulders. Hips height is
scaled by leg length; optional 'ground' pass keeps the lowest foot on the
floor (no floating / sinking when proportions differ).
"""
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

SKELETONS = {
    # CoH male/skel_ready2 (also used by the Hellion enemy costumes)
    "coh": {"hips": "HIPS", "spine1": "WAIST", "chest": "CHEST", "neck": "NECK", "head": "HEAD",
            "clav_l": "COL_L", "uarm_l": "UARML", "larm_l": "LARML", "hand_l": "HANDL", "hand_end_l": "RINGL",
            "uleg_l": "ULEGL", "lleg_l": "LLEGL", "foot_l": "FOOTL", "toe_l": "TOEL",
            "clav_r": "COL_R", "uarm_r": "UARMR", "larm_r": "LARMR", "hand_r": "HANDR", "hand_end_r": "RINGR",
            "uleg_r": "ULEGR", "lleg_r": "LLEGR", "foot_r": "FOOTR", "toe_r": "TOER",
            "thumb_l": "T3_L", "thumb_r": "T3_R",
            "fingers_l": ["RINGL", "F2_L", "F1_L"], "fingers_r": ["RINGR", "F2_R", "F1_R"]},
    # Meshy auto-rig biped (24 bones, no fingers)
    "meshy": {"hips": "Hips", "spine1": "Spine02", "spine2": "Spine01", "chest": "Spine", "neck": "neck", "head": "Head",
              "clav_l": "LeftShoulder", "uarm_l": "LeftArm", "larm_l": "LeftForeArm", "hand_l": "LeftHand", "hand_end_l": "LeftHand:tail",
              "uleg_l": "LeftUpLeg", "lleg_l": "LeftLeg", "foot_l": "LeftFoot", "toe_l": "LeftToeBase",
              "clav_r": "RightShoulder", "uarm_r": "RightArm", "larm_r": "RightForeArm", "hand_r": "RightHand", "hand_end_r": "RightHand:tail",
              "uleg_r": "RightUpLeg", "lleg_r": "RightLeg", "foot_r": "RightFoot", "toe_r": "RightToeBase"},
}
TORSO = ["hips", "spine1", "spine2", "chest", "neck", "head"]
LIMBS = []  # (joint, parent joint, end joint, bend partner)
for s in "lr":
    LIMBS += [("clav_" + s, "chest", "uarm_" + s, None),
              ("uarm_" + s, "clav_" + s, "larm_" + s, "larm_" + s),
              ("larm_" + s, "uarm_" + s, "hand_" + s, None),
              ("hand_" + s, "larm_" + s, "hand_end_" + s, None),
              ("uleg_" + s, "hips", "lleg_" + s, "lleg_" + s),
              ("lleg_" + s, "uleg_" + s, "foot_" + s, None),
              ("foot_" + s, "lleg_" + s, "toe_" + s, None)]
LIMB_END = {j: e for j, _, e, _ in LIMBS}
# anatomical hinge axis of elbows/knees in a T-pose facing -Y (world): the
# rest limbs are straight, so the rest bend can't define the hinge plane.
HINGE = {"uarm_l": Vector((0, 0, -1)), "uarm_r": Vector((0, 0, 1)),
         "uleg_l": Vector((1, 0, 0)), "uleg_r": Vector((1, 0, 0))}


def _q(m):
    return m.to_3x3().normalized().to_quaternion()


class Rig:
    def __init__(self, arm, family):
        self.arm, self.map = arm, SKELETONS[family]
        self.W = arm.matrix_world.copy()
        self.Wq = _q(self.W)
        self.bones = arm.data.bones

    def name(self, j):
        n = self.map.get(j)
        return n if n and n.split(":")[0] in self.bones else None

    def rest_pos(self, j):
        n = self.name(j)
        if n.endswith(":tail"):
            return self.W @ self.bones[n[:-5]].tail_local
        return self.W @ self.bones[n].head_local

    def rest_q(self, j):
        return _q(self.W @ self.bones[self.name(j).split(":")[0]].matrix_local)

    def pose_pos(self, j):
        n = self.name(j)
        if n.endswith(":tail"):
            return self.W @ self.arm.pose.bones[n[:-5]].tail
        return self.W @ self.arm.pose.bones[n].head

    def pose_q(self, j):
        return _q(self.W @ self.arm.pose.bones[self.name(j)].matrix)


def _parent_chain_order(bones):
    out, seen = [], set()

    def visit(b):
        if b.name in seen:
            return
        if b.parent:
            visit(b.parent)
        seen.add(b.name)
        out.append(b)
    for b in bones:
        visit(b)
    return out


def retarget(src_arm, src_family, tgt_arm, tgt_family, name, frames=None, bend_fix=True, ground=True, in_place=True,
             fist=0.0, scale_hips=True):
    """Bake src_arm's active action onto tgt_arm; returns the new action and per-frame log."""
    sc = bpy.context.scene
    S, T = Rig(src_arm, src_family), Rig(tgt_arm, tgt_family)
    act = src_arm.animation_data.action
    if frames is None:
        a, b = act.frame_range
        frames = list(range(int(math.ceil(a)), int(math.floor(b)) + 1))
    torso = [j for j in TORSO if T.name(j)]
    limbs = [l for l in LIMBS if T.name(l[0]) and S.name(l[0]) and T.name(l[2]) and S.name(l[2])]
    t_rest_q = {j: T.rest_q(j) for j in torso + [l[0] for l in limbs]}
    s_rest_q = {j: S.rest_q(j) for j in TORSO if S.name(j)}
    s_hips0, t_hips0 = S.rest_pos("hips"), T.rest_pos("hips")
    ratio = t_hips0.z / max(s_hips0.z, 1e-3) if scale_hips else 1.0
    feet = [j for j in ("foot_l", "foot_r", "toe_l", "toe_r") if T.name(j)]
    FWD = Vector((0, -1, 0))  # Meshy rest is a T-pose with palms down -> thumbs point forward

    def thumb_rest(rig, side):
        if rig.name("thumb_" + side):
            return rig.rest_pos("thumb_" + side) - rig.rest_pos("hand_" + side)
        return FWD.copy()
    t_thumb0 = {sd: thumb_rest(T, sd) for sd in "lr"}
    s_thumb0 = {sd: thumb_rest(S, sd) for sd in "lr"}
    s_hand_rest = {sd: S.rest_q("hand_" + sd) for sd in "lr" if S.name("hand_" + sd)}
    log_twist = {"forearm_twist_max_deg": 0.0}
    t_floor = min(T.rest_pos(j).z for j in feet)
    s_feet = [j for j in ("foot_l", "foot_r", "toe_l", "toe_r") if S.name(j)]
    s_floor = min(S.rest_pos(j).z for j in s_feet)

    # sample the source in world space
    recs = []
    for f in frames:
        sc.frame_set(int(f))
        rec = {"q": {}, "p": {}}
        for j in S.map:
            if j.startswith("fingers") or (j.startswith("thumb") and not S.name(j)):
                continue
            if S.name(j):
                rec["p"][j] = S.pose_pos(j)
                if not S.name(j).endswith(":tail"):
                    rec["q"][j] = S.pose_q(j)
        recs.append(rec)

    # bake
    if tgt_arm.animation_data is None:
        tgt_arm.animation_data_create()
    tgt_arm.animation_data.action = None
    for pb in tgt_arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.matrix_basis.identity()
    new = bpy.data.actions.new(name)
    tgt_arm.animation_data.action = new
    order = _parent_chain_order(list(T.bones))
    jt = {T.name(j): j for j in torso + [l[0] for l in limbs]}
    prevq, log = {}, {"ground_shift_max_m": 0.0, "bend_twist_max_deg": 0.0}
    fingers = [n for k in ("fingers_l", "fingers_r") for n in T.map.get(k, [])]
    for i, rec in enumerate(recs):
        wq = {}
        for j in torso:
            if S.name(j) and j in rec["q"]:
                d = rec["q"][j] @ s_rest_q[j].inverted()
            elif j == "spine2":  # source has no middle spine: halfway between spine1 and chest
                d1 = rec["q"]["spine1"] @ s_rest_q["spine1"].inverted()
                d2 = rec["q"]["chest"] @ s_rest_q["chest"].inverted()
                d = d1.slerp(d2, 0.5)
            else:
                continue
            wq[j] = d @ t_rest_q[j]
        for j, par, end, partner in limbs:
            pd = wq[par] @ t_rest_q[par].inverted() if par in wq else Quaternion()
            carried = pd @ t_rest_q[j]
            rest_dir = (T.rest_pos(end) - T.rest_pos(j)).normalized()
            cur = pd @ rest_dir
            sdir = (rec["p"][end] - rec["p"][j]).normalized()
            q = cur.rotation_difference(sdir) @ carried
            if bend_fix and partner and T.name(LIMB_END[partner]) and S.name(LIMB_END[partner]):
                # hinge plane of source upper/lower limb
                s_low = (rec["p"][LIMB_END[partner]] - rec["p"][partner]).normalized()
                ns = sdir.cross(s_low)
                # target lower limb as carried by the new upper rotation (rest bend)
                qd = q @ t_rest_q[j].inverted()
                # hinge from this rig's own rest limb direction: elbows bend toward the
                # front (limb x forward), knees toward the back (limb x backward); works for
                # T-pose and arms-down rests alike (the lieutenant rig rests arms-down).
                rdir = (T.rest_pos(end) - T.rest_pos(j)).normalized()
                hinge = rdir.cross(Vector((0, -1, 0)) if j.startswith("uarm") else Vector((0, 1, 0)))
                if hinge.length < 0.3:
                    hinge = HINGE[j].copy()
                nt = qd @ hinge.normalized()
                nt = nt - sdir * nt.dot(sdir)
                if ns.length > 0.2 and nt.length > 0.2:
                    ns.normalize()
                    nt.normalize()
                    ang = math.atan2(nt.cross(ns).dot(sdir), nt.dot(ns))
                    q = Quaternion(sdir, ang) @ q
                    log["bend_twist_max_deg"] = max(log["bend_twist_max_deg"], abs(math.degrees(ang)))
            if bend_fix and j.startswith("larm_"):
                sd = j[-1]
                if S.name("thumb_" + sd):
                    th_s = rec["p"]["thumb_" + sd] - rec["p"]["hand_" + sd]
                else:
                    th_s = (rec["q"]["hand_" + sd] @ s_hand_rest[sd].inverted()) @ s_thumb0[sd]
                th_t = (q @ t_rest_q[j].inverted()) @ t_thumb0[sd]
                a_ = th_s - sdir * th_s.dot(sdir)
                b_ = th_t - sdir * th_t.dot(sdir)
                if a_.length > 1e-4 and b_.length > 1e-4:
                    a_.normalize()
                    b_.normalize()
                    ang = math.atan2(b_.cross(a_).dot(sdir), b_.dot(a_))
                    q = Quaternion(sdir, ang) @ q
                    log_twist["forearm_twist_max_deg"] = max(log_twist["forearm_twist_max_deg"], abs(math.degrees(ang)))
            wq[j] = q
        off = (rec["p"]["hips"] - s_hips0) * ratio
        if in_place:
            off = Vector((0, 0, off.z))
        hips_w = t_hips0 + off

        def solve(hips_world):
            Marm, basis = {}, {}
            for bone in order:
                rest = bone.matrix_local
                chain = rest.copy() if bone.parent is None else Marm[bone.parent.name] @ bone.parent.matrix_local.inverted() @ rest
                j = jt.get(bone.name)
                if j is None:
                    Marm[bone.name] = chain
                    continue
                R = (T.Wq.inverted() @ wq[j]).to_matrix().to_4x4()
                loc = T.W.inverted() @ hips_world if j == "hips" else chain.translation
                desired = Matrix.Translation(loc) @ R
                Marm[bone.name] = desired
                basis[bone.name] = chain.inverted() @ desired
            return Marm, basis

        Marm, basis = solve(hips_w)
        if ground and feet:
            lows = []
            for j in feet:
                bn = T.name(j)
                lows.append((T.W @ Marm[bn].translation).z)
            # keep the source's lowest-foot height above its own floor (scaled):
            # planted feet stay on the ground, run/jump airtime is preserved
            s_lift = (min(rec["p"][j].z for j in s_feet) - s_floor) * ratio
            shift = (t_floor + max(s_lift, 0.0)) - min(lows)
            if abs(shift) < 0.25:
                hips_w = hips_w + Vector((0, 0, shift))
                log["ground_shift_max_m"] = max(log["ground_shift_max_m"], abs(shift))
                Marm, basis = solve(hips_w)
        for bn, B in basis.items():
            pb = tgt_arm.pose.bones[bn]
            q = B.to_quaternion()
            if bn in prevq:
                q.make_compatible(prevq[bn])
            prevq[bn] = q
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=i)
            if jt[bn] == "hips":
                pb.location = B.translation
                pb.keyframe_insert("location", frame=i)
        for fb in fingers:
            pb = tgt_arm.pose.bones.get(fb)
            if pb:
                pb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(70 * fist))
                pb.keyframe_insert("rotation_quaternion", frame=i)
    log.update(log_twist)
    log = {k: round(v, 3) for k, v in log.items()}
    return new, log


def impact_frame(rig_arm, family, frames):
    """Frame where a hand/foot reaches furthest in front of the hips (-Y = forward)."""
    R = Rig(rig_arm, family)
    best, bf = -1e9, frames[0]
    for f in frames:
        bpy.context.scene.frame_set(int(f))
        hip = R.pose_pos("hips")
        for j in ("hand_end_l", "hand_end_r", "toe_l", "toe_r"):
            if not R.name(j):
                continue
            p = R.pose_pos(j)
            # a strike, not a bow: fists above the hips, kicks not below hip-0.3 m
            if p.z < hip.z + (0.15 if j.startswith("hand") else -0.3):
                continue
            reach = -(p.y - hip.y) * (0.9 if j.startswith("toe") else 1.0)
            if reach > best:
                best, bf = reach, f
    return bf

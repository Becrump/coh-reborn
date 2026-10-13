"""Reader for City of Heroes .anim skeleton/animation tracks.

Format follows Common/seq/animtrack.h (SkeletonAnimTrack, BoneAnimTrack,
SkeletonHeirarchy) and the key unpacking in animtrackanimate.c of the
Thunderspies/CityOfHeroes source. A .anim file is a raw memory image with
32-bit pointers stored as offsets from the start of the file.
"""
import math
import struct

# Common/seq/bones.h, BoneId enum order.
BONE_NAMES = (
    "HIPS WAIST CHEST NECK HEAD COL_R COL_L UARMR UARML LARMR LARML HANDR "
    "HANDL F1_R F1_L F2_R F2_L T1_R T1_L T2_R T2_L T3_R T3_L ULEGR ULEGL "
    "LLEGR LLEGL FOOTR FOOTL TOER TOEL FACE DUMMY BREAST BELT GLOVEL GLOVER "
    "BOOTL BOOTR RINGL RINGR WEPL WEPR HAIR EYES EMBLEM SPADL SPADR BACK "
    "NECKLINE CLAWL CLAWR GUN RWING1 RWING2 RWING3 RWING4 LWING1 LWING2 "
    "LWING3 LWING4 MYSTIC SLEEVEL SLEEVER ROBE BENDMYSTIC COLLAR BROACH "
    "BOSOMR BOSOML TOP SKIRT SLEEVES BROW CHEEKS CHIN CRANIUM JAW NOSE "
    "HIND_ULEGL HIND_LLEGL HIND_FOOTL HIND_TOEL HIND_ULEGR HIND_LLEGR "
    "HIND_FOOTR HIND_TOER FORE_ULEGL FORE_LLEGL FORE_FOOTL FORE_TOEL "
    "FORE_ULEGR FORE_LLEGR FORE_FOOTR FORE_TOER LEG_L_JET1 LEG_L_JET2 "
    "LEG_R_JET1 LEG_R_JET2").split()
BONE_IDS = {n: i for i, n in enumerate(BONE_NAMES)}


def bone_id_from_text(text):
    """bone_IdFromText: longest enum name the text starts with (case-blind)."""
    t = text.upper()
    for i in range(len(BONE_NAMES) - 1, -1, -1):
        if t.startswith(BONE_NAMES[i]):
            return i
    return -1


ROT_UNCOMP, ROT_5BYTE, ROT_8BYTE = 1, 2, 4
POS_UNCOMP, POS_6BYTE = 8, 16
ROT_NONLINEAR = 0x80
_MAXV = 1.0 / math.sqrt(2.0)
_HEADER = struct.Struct("<i256s256sffiiiii")
_TRACK = struct.Struct("<iiHHHHbBH")


def _unpack5(b):
    word = struct.unpack_from("<I", b, 1)[0]
    i2 = word & 0xFFF
    i1 = (word >> 12) & 0xFFF
    i0 = ((word >> 24) & 0xFF) | ((b[0] & 0x0F) << 8)
    return (i0, i1, i2), (b[0] >> 4) & 0x0F


def _expand_quat(idxs, missing, nonlinear):
    q = [0.0, 0.0, 0.0, 0.0]
    k = 0
    for i in range(4):
        if i == missing:
            continue
        v = idxs[k]
        k += 1
        if nonlinear:
            # unpackQuatElemQuarterPi(v, 12)
            f = v * (math.pi / 2) / 4096.0 - math.pi / 4
            q[i] = max(-_MAXV, min(_MAXV, math.sin(f)))
        else:
            q[i] = 2.0 * _MAXV * (v / 4096.0) - _MAXV
    s = 1.0 - sum(c * c for c in q)
    q[missing] = math.sqrt(s) if s > 0 else 0.0
    return tuple(q)


class BoneTrack:
    def __init__(self, bone_id, rots, poss):
        self.bone_id = bone_id
        self.rots = rots    # [(x, y, z, w)], key k = frame k
        self.poss = poss    # [(x, y, z)]


class AnimTrack:
    def __init__(self, data):
        (_hs, name, base, self.max_hip, self.length, tracks_off, count,
         _rc, _pc, heir_off) = _HEADER.unpack_from(data, 0)
        self.name = name.split(b"\0", 1)[0].decode("latin-1")
        self.base_name = base.split(b"\0", 1)[0].decode("latin-1")
        self.tracks = {}
        for i in range(count):
            (rot_off, pos_off, _rfk, _pfk, rot_count, pos_count, bone_id,
             flags, _pad) = _TRACK.unpack_from(data, tracks_off + i * 20)
            self.tracks[bone_id] = BoneTrack(
                bone_id, self._rots(data, rot_off, rot_count, flags),
                self._poss(data, pos_off, pos_count, flags))
        self.hierarchy = None
        if heir_off:
            root = struct.unpack_from("<i", data, heir_off)[0]
            # some prop skeletons are written short; read the links present
            n = min(100, (len(data) - heir_off - 4) // 12)
            links = [struct.unpack_from("<3i", data, heir_off + 4 + 12 * i)
                     for i in range(n)]
            links += [(-1, -1, -1)] * (100 - n)
            self.hierarchy = (root, links)

    @staticmethod
    def _rots(d, off, n, flags):
        out = []
        for k in range(n):
            if flags & ROT_5BYTE or flags & ROT_NONLINEAR:
                idxs, missing = _unpack5(d[off + 5 * k:off + 5 * k + 5])
                out.append(_expand_quat(idxs, missing,
                                        not (flags & ROT_5BYTE)))
            elif flags & ROT_8BYTE:
                out.append(tuple(v * 1e-4 for v in
                                 struct.unpack_from("<4h", d, off + 8 * k)))
            elif flags & ROT_UNCOMP:
                out.append(struct.unpack_from("<4f", d, off + 16 * k))
            else:
                raise ValueError("unknown rotation packing 0x%x" % flags)
        return out

    @staticmethod
    def _poss(d, off, n, flags):
        out = []
        for k in range(n):
            if flags & POS_6BYTE:
                out.append(tuple(v / 32000.0 for v in
                                 struct.unpack_from("<3h", d, off + 6 * k)))
            elif flags & POS_UNCOMP:
                out.append(struct.unpack_from("<3f", d, off + 12 * k))
            else:
                raise ValueError("unknown position packing 0x%x" % flags)
        return out

    def parents(self):
        """{bone_id: parent bone_id or -1} from the hierarchy (skel files)."""
        root, links = self.hierarchy
        out = {}

        def walk(idx, parent):
            while idx != -1:
                child, nxt, bid = links[idx]
                out[bid] = parent
                if child != -1:
                    walk(child, bid)
                idx = nxt
        walk(root, -1)
        return out


def frame_count(track, first, last):
    """Number of frames for an Anim line (lastFrame 0 means track length)."""
    if not last:
        last = int(track.length)
    return max(1, last - first + 1)


def sample(bt, frame):
    """Rotation and position of a bone track at integer frame (clamped)."""
    r = bt.rots[min(frame, len(bt.rots) - 1)] if len(bt.rots) > 1 \
        else bt.rots[0]
    p = bt.poss[min(frame, len(bt.poss) - 1)] if len(bt.poss) > 1 \
        else bt.poss[0]
    return r, p

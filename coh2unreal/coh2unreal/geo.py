"""Reader for City of Heroes .geo model files.

Format follows Common/seq/anim.c (geoLoadStubs, readModel, uncompressDeltas)
in the Thunderspies/CityOfHeroes source. Only the parts needed to rebuild
static meshes are decoded: positions, normals, UVs and per-texture triangles.
"""
import struct
import zlib

PACK_F32, PACK_U32 = 0, 1


class GeoModel:
    def __init__(self):
        self.name = ""
        self.radius = 0.0
        self.vert_count = 0
        self.tri_count = 0
        self.tex_ids = []      # [(texture name, triangle count)]
        self.min = (0, 0, 0)
        self.max = (0, 0, 0)
        self.packs = {}        # field -> (packsize, unpacksize, offset)
        self.has_bones = False


class Geo:
    def __init__(self, data, name=""):
        self.name = name
        self.data = data
        self.models = []
        self.version = 0
        self._parse()

    # ---------------------------------------------------------------- header
    def _parse(self):
        d = self.data
        ziplen, headersize = struct.unpack_from("<iI", d, 0)
        pos = 8
        if headersize == 0:
            (version,) = struct.unpack_from("<i", d, pos)
            pos += 4
            if not (2 <= version <= 8 and version != 6):
                raise ValueError("unsupported geo version %d" % version)
            (headersize,) = struct.unpack_from("<I", d, pos)
            pos += 4
            zipped = d[pos:pos + ziplen - 12]
            self.data_offset = ziplen + 4
        else:
            version = 0
            zipped = d[pos:pos + ziplen - 4]
            self.data_offset = ziplen + 8
        self.version = version
        hdr = zlib.decompress(zipped)
        if len(hdr) < headersize:
            raise ValueError("short geo header")

        p = 0
        _datasize, texname_bs, objname_bs, texidx_bs = \
            struct.unpack_from("<4i", hdr, p)
        p += 16
        lodinfo_bs = 0
        if 2 <= version <= 6:
            (lodinfo_bs,) = struct.unpack_from("<i", hdr, p)
            p += 4

        texnames = _unpack_names(hdr, p)
        if not texnames:
            texnames = ["white"]
        p += texname_bs
        objnames_base = p
        p += objname_bs
        texidx_base = p
        p += texidx_bs
        p += lodinfo_bs
        # ModelHeader on disk: char name[124]; 4 ptr/float fields.
        (model_count,) = struct.unpack_from("<i", hdr, p + 136)
        p += 140

        for _ in range(model_count):
            m, size = self._read_model(hdr, p, version, objnames_base,
                                       texidx_base, texnames)
            self.models.append(m)
            p += size

    def _read_model(self, h, p, version, objbase, texbase, texnames):
        m = GeoModel()
        if version < 3:
            # ModelFormatOnDisk_v2 (32-bit layout, 216 bytes)
            (_flags, m.radius, _vbo, tex_count, _id, _bm, _ls, boneinfo,
             _trick, m.vert_count, m.tri_count, tex_idx) = \
                struct.unpack_from("<IfIihBBIIiiI", h, p)
            name_off = struct.unpack_from("<I", h, p + 80)[0]
            m.min = struct.unpack_from("<3f", h, p + 104)
            m.max = struct.unpack_from("<3f", h, p + 116)
            pk = p + 132
            fields = ["tris", "verts", "norms", "sts", "weights", "matidxs",
                      "grid"]
            size = 216
        else:
            (size, m.radius, tex_count, boneinfo, m.vert_count,
             m.tri_count) = struct.unpack_from("<ifiIii", h, p)
            q = p + 24
            if version >= 8:
                q += 4  # reflection_quad_count
            (tex_idx,) = struct.unpack_from("<I", h, q)
            q += 4
            q += 32  # PolyGrid
            (name_off,) = struct.unpack_from("<I", h, q)
            q += 8   # name, api
            q += 12  # scale
            m.min = struct.unpack_from("<3f", h, q)
            m.max = struct.unpack_from("<3f", h, q + 12)
            pk = q + 24
            fields = ["tris", "verts", "norms", "sts", "sts3", "weights",
                      "matidxs", "grid"]
        for i, fld in enumerate(fields):
            m.packs[fld] = struct.unpack_from("<iII", h, pk + i * 12)
        m.has_bones = bool(boneinfo)
        m.boneinfo = boneinfo
        end = h.index(b"\0", objbase + name_off)
        m.name = h[objbase + name_off:end].decode("latin-1")
        for i in range(tex_count):
            tid, cnt = struct.unpack_from("<HH", h, texbase + tex_idx + i * 4)
            tname = texnames[tid] if tid < len(texnames) else "white"
            m.tex_ids.append((tname, cnt))
        return m, size

    # ------------------------------------------------------------------ data
    def _pack_bytes(self, m, field):
        packsize, unpacksize, offset = m.packs.get(field, (0, 0, 0))
        if not unpacksize:
            return None
        start = self.data_offset + offset
        if packsize:
            return zlib.decompress(self.data[start:start + packsize])
        return self.data[start:start + unpacksize]

    def mesh(self, m):
        """Returns dict with positions, normals, uvs, and per-texture tris."""
        pos = _deltas(self._pack_bytes(m, "verts"), 3, m.vert_count, PACK_F32)
        nrm = _deltas(self._pack_bytes(m, "norms"), 3, m.vert_count, PACK_F32)
        uv = _deltas(self._pack_bytes(m, "sts"), 2, m.vert_count, PACK_F32)
        tris = _deltas(self._pack_bytes(m, "tris"), 3, m.tri_count, PACK_U32)
        groups = []
        t = 0
        for tname, cnt in m.tex_ids:
            groups.append((tname, tris[t * 3:(t + cnt) * 3] if tris else []))
            t += cnt
        return {"positions": pos, "normals": nrm, "uvs": uv,
                "groups": groups}

    def skin(self, m):
        """Per-vertex skinning for a boned model, or None.

        Returns [(bone_id0, bone_id1, w0)] per vertex: two influences with
        w1 = 1 - w0. The BoneInfo block (anim.h) sits in the data section:
        i32 numbones, i32 bone_ID[15], then the weights/matidxs pointers.
        matidxs are stored times 3 (model_cache.c).
        """
        if not m.has_bones:
            return None
        base = self.data_offset + m.boneinfo
        numbones = struct.unpack_from("<i", self.data, base)[0]
        ids = struct.unpack_from("<15i", self.data, base + 4)[:numbones]
        w = self._pack_bytes(m, "weights")
        mi = self._pack_bytes(m, "matidxs")
        out = []
        for v in range(m.vert_count):
            w0 = (w[v] / 255.0) if w else 1.0
            s0 = mi[2 * v] // 3 if mi else 0
            s1 = mi[2 * v + 1] // 3 if mi else 0
            out.append((ids[s0], ids[s1] if s1 < numbones else ids[s0], w0))
        return out


def _unpack_names(h, p):
    (count,) = struct.unpack_from("<i", h, p)
    offs = struct.unpack_from("<%di" % count, h, p + 4)
    base = p + 4 + 4 * count
    out = []
    for o in offs:
        end = h.index(b"\0", base + o)
        out.append(h[base + o:end].decode("latin-1"))
    return out


def _deltas(src, stride, count, pack_type):
    """Port of uncompressDeltas() from Common/seq/anim.c."""
    if src is None or not count:
        return []
    nbits = 2 * count * stride
    bitbytes = (nbits + 7) // 8
    bits = int.from_bytes(src[:bitbytes], "little")
    b = bitbytes
    scale = 1 << src[b]
    b += 1
    inv = 1.0 / scale
    out = [0] * (count * stride)
    last = [0] * stride
    o = 0
    is_float = pack_type == PACK_F32
    for _ in range(count):
        for j in range(stride):
            code = bits & 3
            bits >>= 2
            if code == 0:
                delta = 0
            elif code == 1:
                delta = src[b] - 0x7F
                b += 1
            elif code == 2:
                delta = (src[b] | (src[b + 1] << 8)) - 0x7FFF
                b += 2
            else:
                raw = src[b:b + 4]
                b += 4
            if is_float:
                if code == 3:
                    fd = struct.unpack("<f", raw)[0]
                else:
                    fd = delta * inv
                last[j] = last[j] + fd
            else:
                if code == 3:
                    delta = struct.unpack("<i", raw)[0]
                last[j] = (last[j] + delta + 1) & 0xFFFFFFFF
            out[o] = last[j]
            o += 1
    return out

"""Reader for City of Heroes .pigg archives.

Format follows libs/UtilitiesLib/src/utils/piglib.c and datapool.c in the
Thunderspies/CityOfHeroes source.
"""
import struct
import zlib

PIG_HEADER_FLAG = 0x0123
PIG_FILE_HEADER_FLAG = 0x3456
PIG_STRING_POOL_FLAG = 0x6789
PIG_HEADER_DATA_POOL_FLAG = 0x9ABC


class PiggEntry:
    __slots__ = ("name", "size", "offset", "pack_size", "timestamp")

    def __init__(self, name, size, offset, pack_size, timestamp):
        self.name = name
        self.size = size
        self.offset = offset
        self.pack_size = pack_size
        self.timestamp = timestamp


def _read_pool(f, expected_flag):
    flag, count, total = struct.unpack("<III", f.read(12))
    if flag != expected_flag:
        raise ValueError("bad data pool flag 0x%x" % flag)
    data = f.read(total)
    items = []
    pos = 0
    for _ in range(count):
        (size,) = struct.unpack_from("<i", data, pos)
        pos += 4
        items.append(data[pos:pos + size])
        pos += size
    return items


class Pigg:
    """An open .pigg archive. Entries are keyed by lower-case path."""

    def __init__(self, path):
        self.path = path
        self.entries = {}
        with open(path, "rb") as f:
            flag, _creator, required, header_size, file_header_size, count = \
                struct.unpack("<IHHHHI", f.read(16))
            if flag != PIG_HEADER_FLAG:
                raise ValueError("%s is not a pigg archive" % path)
            if required > 2:
                raise ValueError("%s needs pigg version %d" % (path, required))
            f.seek(header_size - 16, 1)
            raw = []
            for _ in range(count):
                rec = f.read(file_header_size)
                (fflag, name_id, size, timestamp, offset, _reserved,
                 _hdr_id) = struct.unpack_from("<IiIIIIi", rec, 0)
                (pack_size,) = struct.unpack_from("<I", rec, 44)
                if fflag != PIG_FILE_HEADER_FLAG:
                    raise ValueError("bad file header in %s" % path)
                raw.append((name_id, size, timestamp, offset, pack_size))
            names = _read_pool(f, PIG_STRING_POOL_FLAG)
        for name_id, size, timestamp, offset, pack_size in raw:
            name = names[name_id].split(b"\0", 1)[0].decode("latin-1")
            name = name.replace("\\", "/").lower()
            self.entries[name] = PiggEntry(name, size, offset, pack_size,
                                           timestamp)

    def read(self, name):
        e = self.entries[name.lower()]
        with open(self.path, "rb") as f:
            f.seek(e.offset)
            if e.pack_size:
                data = zlib.decompress(f.read(e.pack_size))
            else:
                data = f.read(e.size)
        if len(data) != e.size:
            raise ValueError("size mismatch for %s" % name)
        return data


class AssetStore:
    """Finds game files in extracted folders and/or .pigg archives.

    Later sources win, matching the game's sorted archive order.
    """

    def __init__(self, data_dirs=(), pigg_paths=()):
        import os
        self._files = {}
        for p in sorted(pigg_paths, key=lambda s: os.path.basename(s).lower()):
            pig = Pigg(p)
            for name in pig.entries:
                self._files[name] = (pig, name)
        for d in data_dirs:
            for root, _dirs, files in os.walk(d):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, d).replace("\\", "/").lower()
                    self._files[rel] = (None, full)
        self._by_base = {}
        for rel in self._files:
            base = rel.rsplit("/", 1)[-1]
            self._by_base.setdefault(base, []).append(rel)

    def __contains__(self, rel):
        return rel.lower() in self._files

    def names(self):
        return self._files.keys()

    def find_basename(self, base):
        return self._by_base.get(base.lower(), [])

    def read(self, rel):
        pig, ref = self._files[rel.lower()]
        if pig is None:
            with open(ref, "rb") as f:
                return f.read()
        return pig.read(ref)

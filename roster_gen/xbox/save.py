"""High-level Xbox 360 save handling: the EA DB inside a CON package.

A 360 roster save is an STFS ("CON") package whose single file is a 56-byte
``MC02`` wrapper followed by the same EA TDB database the PS3 version uses.
That means everything above this layer - team matching, ratings, roster and
depth-chart writes - is shared with the PS3 path.

The MC02 wrapper is preserved byte for byte.  The STFS signature is left as
found; see ``stfs.py`` for what that means on a retail console.
"""
import os

from roster_gen.xbox import stfs

# NCAA 14 uses DB version 8; the second "DB" hit inside player data is v7.
DB_VERSION = b"\x00\x08"


def is_xbox_save(path):
    """True if ``path`` looks like an Xbox 360 STFS package."""
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "rb") as f:
            return f.read(4) in stfs.MAGICS
    except OSError:
        return False


def find_db(payload):
    """Return the offset of the EA TDB header inside a 360 save payload.

    Saves start with a small ``MC02`` wrapper, so the DB is not at offset 0.
    Scan for the header rather than trusting a fixed offset.
    """
    pos = 0
    while True:
        i = payload.find(b"DB", pos)
        if i < 0:
            break
        if (i + 24 <= len(payload)
                and payload[i + 2:i + 4] == DB_VERSION
                and payload[i + 4] == 1):
            db_size = int.from_bytes(payload[i + 8:i + 12], "big")
            num_tables = int.from_bytes(payload[i + 16:i + 20], "big")
            if 1 <= num_tables <= 64 and 0 < db_size <= len(payload) - i:
                return i
        pos = i + 2
    raise ValueError("no EA DB found in this Xbox 360 save")


class XboxSave:
    """A roster save read off an Xbox 360 (``ROSTER-*`` copied from USB)."""

    platform = "xbox360"

    def __init__(self, path):
        self.path = os.path.abspath(os.path.expanduser(path))
        self.package = stfs.load(self.path)
        files = self.package.files()
        if not files:
            raise ValueError(f"{self.path}: STFS package contains no files")
        rosters = [e for e in files if e.name.upper().startswith("ROSTER")]
        self.entry = rosters[0] if rosters else files[0]
        self.name = self.entry.name
        self.payload = self.package.read(self.name)
        self.db_offset = find_db(self.payload)
        self.db_size = int.from_bytes(self.payload[self.db_offset + 8:self.db_offset + 12], "big")
        self.profile_id = self.package.profile_id
        self.title_id = self.package.title_id
        self.content_type = self.package.content_type

    @property
    def db_bytes(self):
        """The original EA DB, exactly ``db_size`` bytes: safe to parse."""
        return self.payload[self.db_offset:self.db_offset + self.db_size]

    def replace_db(self, data):
        """Swap in a rebuilt DB, keeping the container's size unchanged."""
        if len(data) > self.db_size:
            raise ValueError(
                f"rebuilt DB is {len(data)} bytes but the save allocates "
                f"{self.db_size}; cannot grow an Xbox 360 save in place")
        if len(data) < self.db_size:
            data = data + b"\x00" * (self.db_size - len(data))
        self.payload = (self.payload[:self.db_offset] + data
                        + self.payload[self.db_offset + self.db_size:])

    def content_dir(self, out_dir):
        """``<out>/Xbox360/Content/<XUID>/<title id>/<content type>``."""
        return os.path.join(
            os.path.abspath(os.path.expanduser(out_dir)), "Xbox360", "Content",
            self.profile_id, f"{self.title_id:08X}", f"{self.content_type:08d}")

    def save(self, out_dir):
        """Repack and write the save in the USB layout the console expects."""
        out_path = os.path.join(self.content_dir(out_dir), self.name)
        self.package.write(self.name, self.payload)
        self.package.rebuild_hashes()
        problems = self.package.verify_hashes()
        if problems:
            raise ValueError(f"rehash failed: {problems[:5]}")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        stfs.save(self.package, out_path)
        return out_path

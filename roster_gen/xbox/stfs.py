"""Xbox 360 STFS ("CON") container support.

Only the parts an NCAA 14 roster save needs: read the file table, pull one
file's bytes out, put new bytes back, and rebuild the SHA-1 hash tree that the
console checks before loading.

Layout, as used by retail saves:

    [header]                     0x000 .. header_size
    [hash tables + data blocks]  interleaved, 0x1000 bytes per block

Data block N's physical offset is ``block_offset(N)``.  Its SHA-1 lives in the
level-0 hash table for its group (``N // 170``), that table's SHA-1 lives in the
level-1 table, and the level-1 table's SHA-1 is the "top hash" stored in the
header.  CON packages keep two copies of every hash table and pick one with
the active-index bits; NCAA 14 saves use two, with the first active.

The RSA signature is deliberately not touched.  Rewriting it needs Microsoft's
private key, so the output is a *rehashed* package: good for consoles with the
content-signature check patched (DashLaunch ``contpatch``), and for everyone
else the file can be passed through Horizon's "Rehash & Resign".

References:
  - https://free60.org/System-Software/Formats/STFS/
  - Xenia, src/xenia/vfs/devices/stfs_container_device.cc and stfs_xbox.h
"""
import hashlib
import struct

BLOCK_SIZE = 0x1000
HASH_SIZE = 0x14
ENTRY_SIZE = 0x18
ENTRIES_PER_TABLE = 170
HASH_LEVEL_BLOCKS = (ENTRIES_PER_TABLE, 28900, 4913000)
END_OF_CHAIN = 0xFFFFFF

MAGICS = (b"CON ", b"PIRS", b"LIVE")

HEADER_SIZE_OFF = 0x340
TITLE_ID_OFF = 0x360
PROFILE_ID_OFF = 0x371
VOLUME_DESCRIPTOR_OFF = 0x379
TOP_HASH_OFF = 0x381
TOTAL_BLOCKS_OFF = 0x395

# Entry flags byte.
FLAG_NAME_LENGTH = 0x3F
FLAG_CONTIGUOUS = 0x40
FLAG_DIRECTORY = 0x80

# Volume descriptor flags byte.
FLAG_READ_ONLY = 0x01
FLAG_ROOT_ACTIVE = 0x02

# Hash entry info word (big-endian) bits.
INFO_ACTIVE_INDEX = 0x40000000


def _u16(data, off):
    return struct.unpack_from(">H", data, off)[0]


def _u32(data, off):
    return struct.unpack_from(">I", data, off)[0]


def _u24(data, off):
    return data[off] | (data[off + 1] << 8) | (data[off + 2] << 16)


def _round_up(value, unit):
    return (value + unit - 1) & ~(unit - 1)


class StfsEntry:
    """One file (or directory) record from the STFS file table."""

    def __init__(self, name, flags, start_block, valid_blocks, allocated_blocks,
                 directory_index, size, table_offset):
        self.name = name
        self.flags = flags
        self.start_block = start_block
        self.valid_blocks = valid_blocks
        self.allocated_blocks = allocated_blocks
        self.directory_index = directory_index
        self.size = size
        self.table_offset = table_offset

    @property
    def contiguous(self):
        return bool(self.flags & FLAG_CONTIGUOUS)

    @property
    def directory(self):
        return bool(self.flags & FLAG_DIRECTORY)

    def __repr__(self):
        kind = "dir" if self.directory else "file"
        return (f"StfsEntry({self.name!r}, {kind}, start={self.start_block}, "
                f"blocks={self.allocated_blocks}, size={self.size})")


class StfsPackage:
    """A parsed CON/PIRS/LIVE package."""

    def __init__(self, data):
        self.data = bytearray(data)
        if len(self.data) < 0x344:
            raise ValueError("not an STFS package: too short")
        self.magic = bytes(self.data[:4])
        if self.magic not in MAGICS:
            raise ValueError(f"not an STFS package: bad magic {self.magic!r}")

        self.header_size = _u32(self.data, HEADER_SIZE_OFF)
        self.base_offset = _round_up(self.header_size, BLOCK_SIZE)
        self.content_type = _u32(self.data, 0x344)
        self.title_id = _u32(self.data, TITLE_ID_OFF)
        self.profile_id = bytes(self.data[PROFILE_ID_OFF:PROFILE_ID_OFF + 8]).hex().upper()

        vd = VOLUME_DESCRIPTOR_OFF
        self.descriptor_length = self.data[vd]
        self.flags_byte = self.data[vd + 2]
        self.file_table_block_count = _u16(self.data, vd + 3)
        self.file_table_block = _u24(self.data, vd + 5)
        self.top_hash = bytes(self.data[vd + 8:vd + 8 + HASH_SIZE])
        self.total_blocks = _u32(self.data, TOTAL_BLOCKS_OFF)
        self.free_blocks = _u32(self.data, TOTAL_BLOCKS_OFF + 4)
        self.blocks_per_hash_table = 1 if self.flags_byte & FLAG_READ_ONLY else 2
        self.root_active = bool(self.flags_byte & FLAG_ROOT_ACTIVE)

        self.entries = []
        self._read_file_table()

    # -- block addressing -------------------------------------------------

    def block_offset(self, block):
        """Physical byte offset of data block ``block``."""
        physical = block
        base = HASH_LEVEL_BLOCKS[0]
        for _ in range(len(HASH_LEVEL_BLOCKS)):
            physical += ((block + base) // base) * self.blocks_per_hash_table
            if block < base:
                break
            base *= HASH_LEVEL_BLOCKS[0]
        return self.base_offset + physical * BLOCK_SIZE

    def hash_block_number(self, block, level):
        """Block number of the hash table that covers ``block`` at ``level``."""
        step0 = HASH_LEVEL_BLOCKS[0] + self.blocks_per_hash_table
        step1 = HASH_LEVEL_BLOCKS[1] + (HASH_LEVEL_BLOCKS[0] + 1) * self.blocks_per_hash_table

        if level == 0:
            if block < HASH_LEVEL_BLOCKS[0]:
                return 0
            number = (block // HASH_LEVEL_BLOCKS[0]) * step0
            number += ((block // HASH_LEVEL_BLOCKS[1]) + 1) * self.blocks_per_hash_table
            if block < HASH_LEVEL_BLOCKS[1]:
                return number
            return number + self.blocks_per_hash_table

        if level == 1:
            if block < HASH_LEVEL_BLOCKS[1]:
                return step0
            number = (block // HASH_LEVEL_BLOCKS[1]) * step1
            return number + self.blocks_per_hash_table

        return step1

    def _hash_table_offset(self, block, level):
        """Offset of the *active* hash table block for ``block`` at ``level``."""
        offset = self.base_offset + self.hash_block_number(block, level) * BLOCK_SIZE
        if self.blocks_per_hash_table == 1:
            return offset

        if level >= 2:
            return offset + (BLOCK_SIZE if self.root_active else 0)

        if level == 1:
            # The highest level is selected by the header flag; below it, each
            # parent entry picks the primary or secondary child table.
            if self.total_blocks <= HASH_LEVEL_BLOCKS[1]:
                return offset + (BLOCK_SIZE if self.root_active else 0)
            parent = self._hash_table_offset(block, 2)
            record = (block // HASH_LEVEL_BLOCKS[1]) % ENTRIES_PER_TABLE
            return offset + (BLOCK_SIZE if self._info(parent, record) & INFO_ACTIVE_INDEX else 0)

        parent = self._hash_table_offset(block, 1)
        record = (block // HASH_LEVEL_BLOCKS[0]) % ENTRIES_PER_TABLE
        return offset + (BLOCK_SIZE if self._info(parent, record) & INFO_ACTIVE_INDEX else 0)

    def _info(self, table_offset, record):
        off = table_offset + record * ENTRY_SIZE + HASH_SIZE
        return _u32(self.data, off)

    def _set_hash(self, table_offset, record, digest):
        off = table_offset + record * ENTRY_SIZE
        self.data[off:off + HASH_SIZE] = digest

    def hash_entry_offset(self, block, level):
        """Offset of ``block``'s 0x18-byte hash entry at ``level``."""
        record = block
        for _ in range(level):
            record //= ENTRIES_PER_TABLE
        return (self._hash_table_offset(block, level)
                + (record % ENTRIES_PER_TABLE) * ENTRY_SIZE)

    def get_hash(self, block, level=0):
        off = self.hash_entry_offset(block, level)
        return bytes(self.data[off:off + HASH_SIZE])

    def next_block(self, block):
        """Block that follows ``block`` in the level-0 chain."""
        return self._info(self._hash_table_offset(block, 0), block % ENTRIES_PER_TABLE) & 0xFFFFFF

    # -- file table -------------------------------------------------------

    def _read_file_table(self):
        block = self.file_table_block
        seen = 0
        while block != END_OF_CHAIN and seen < 64:
            table_offset = self.block_offset(block)
            for index in range(BLOCK_SIZE // 0x40):
                off = table_offset + index * 0x40
                if self.data[off] == 0:
                    break
                name = bytes(self.data[off:off + 0x28]).split(b"\x00")[0].decode("latin1")
                flags = self.data[off + 0x28]
                self.entries.append(StfsEntry(
                    name=name,
                    flags=flags,
                    valid_blocks=_u24(self.data, off + 0x29),
                    allocated_blocks=_u24(self.data, off + 0x2C),
                    start_block=_u24(self.data, off + 0x2F),
                    directory_index=_u16(self.data, off + 0x32),
                    size=_u32(self.data, off + 0x34),
                    table_offset=off,
                ))
            block = self.next_block(block)
            seen += 1

    def files(self):
        return [e for e in self.entries if not e.directory]

    def entry(self, name):
        for e in self.entries:
            if e.name == name:
                return e
        raise KeyError(f"{name!r} is not in this package (have: "
                       + ", ".join(repr(e.name) for e in self.entries) + ")")

    # -- file data --------------------------------------------------------

    def read(self, name):
        """Return the bytes of one file, trimmed to its recorded size."""
        entry = self.entry(name)
        if entry.directory:
            raise IsADirectoryError(name)
        return self._read_entry(entry)

    def _read_entry(self, entry):
        if entry.size > entry.allocated_blocks * BLOCK_SIZE:
            raise ValueError(f"{entry.name}: size {entry.size} exceeds allocation")
        out = bytearray()
        block = entry.start_block
        remaining = entry.size
        for _ in range(entry.allocated_blocks):
            if remaining <= 0 or block == END_OF_CHAIN:
                break
            off = self.block_offset(block)
            take = min(BLOCK_SIZE, remaining)
            out += self.data[off:off + take]
            remaining -= take
            block = block + 1 if entry.contiguous else self.next_block(block)
        if len(out) != entry.size:
            raise ValueError(f"{entry.name}: read {len(out)} of {entry.size} bytes")
        return bytes(out)

    def write(self, name, payload):
        """Replace a file's contents in place.

        Bytes past ``payload`` inside the allocation are left alone, so
        ``write(name, read(name))`` is byte-identical.  Growing a file beyond
        its existing allocation is not supported.
        """
        entry = self.entry(name)
        if entry.directory:
            raise IsADirectoryError(name)
        capacity = entry.allocated_blocks * BLOCK_SIZE
        if len(payload) > capacity:
            raise ValueError(
                f"{name}: {len(payload)} bytes does not fit in the existing "
                f"{capacity}-byte allocation")
        block = entry.start_block
        pos = 0
        for _ in range(entry.allocated_blocks):
            if pos >= len(payload) or block == END_OF_CHAIN:
                break
            off = self.block_offset(block)
            take = min(BLOCK_SIZE, len(payload) - pos)
            self.data[off:off + take] = payload[pos:pos + take]
            pos += take
            block = block + 1 if entry.contiguous else self.next_block(block)
        if pos != len(payload):
            raise ValueError(f"{name}: only wrote {pos} of {len(payload)} bytes")
        if len(payload) != entry.size:
            self._set_entry_size(entry, len(payload))

    def _set_entry_size(self, entry, size):
        if size > entry.allocated_blocks * BLOCK_SIZE:
            raise ValueError("new size exceeds the file's allocated blocks")
        struct.pack_into(">I", self.data, entry.table_offset + 0x34, size)
        needed = (size + BLOCK_SIZE - 1) // BLOCK_SIZE
        for off in (entry.table_offset + 0x29, entry.table_offset + 0x2C):
            self.data[off:off + 3] = bytes((needed & 0xFF, (needed >> 8) & 0xFF, (needed >> 16) & 0xFF))
        entry.size = size
        entry.valid_blocks = needed if size else 0

    # -- integrity --------------------------------------------------------

    def used_blocks(self):
        """Number of data blocks that are actually allocated.

        ``free_block_count`` is authoritative for saves laid out by the
        console; the file extent is used as a floor in case it is stale.
        """
        last = 0
        for entry in self.files():
            last = max(last, entry.start_block + entry.allocated_blocks)
        used = max(self.total_blocks - self.free_blocks, last, 1)
        return min(used, self.total_blocks)

    def rebuild_hashes(self):
        """Recompute the whole SHA-1 tree after the data area changed."""
        used = self.used_blocks()
        for block in range(used):
            off = self.block_offset(block)
            digest = hashlib.sha1(self.data[off:off + BLOCK_SIZE]).digest()
            self._set_hash(self._hash_table_offset(block, 0), block % ENTRIES_PER_TABLE, digest)

        tables = (used + ENTRIES_PER_TABLE - 1) // ENTRIES_PER_TABLE
        for group in range(tables):
            block = group * ENTRIES_PER_TABLE
            table_offset = self._hash_table_offset(block, 0)
            digest = hashlib.sha1(self.data[table_offset:table_offset + BLOCK_SIZE]).digest()
            self._set_hash(self._hash_table_offset(block, 1), group, digest)

        top_offset = self._hash_table_offset(0, 1)
        digest = hashlib.sha1(self.data[top_offset:top_offset + BLOCK_SIZE]).digest()
        self.data[TOP_HASH_OFF:TOP_HASH_OFF + HASH_SIZE] = digest
        self.top_hash = digest

    def verify_hashes(self):
        """Return a list of blocks whose stored hash does not match."""
        bad = []
        used = self.used_blocks()
        for block in range(used):
            off = self.block_offset(block)
            actual = hashlib.sha1(self.data[off:off + BLOCK_SIZE]).digest()
            if self.get_hash(block, 0) != actual:
                bad.append(block)
        tables = (used + ENTRIES_PER_TABLE - 1) // ENTRIES_PER_TABLE
        for group in range(tables):
            block = group * ENTRIES_PER_TABLE
            table_offset = self._hash_table_offset(block, 0)
            actual = hashlib.sha1(self.data[table_offset:table_offset + BLOCK_SIZE]).digest()
            if self.get_hash(block, 1) != actual:
                bad.append(("level1", group))
        top_offset = self._hash_table_offset(0, 1)
        if bytes(self.data[TOP_HASH_OFF:TOP_HASH_OFF + HASH_SIZE]) != \
                hashlib.sha1(self.data[top_offset:top_offset + BLOCK_SIZE]).digest():
            bad.append("top")
        return bad

    def tobytes(self):
        return bytes(self.data)


def load(path):
    with open(path, "rb") as f:
        return StfsPackage(f.read())


def save(package, path):
    with open(path, "wb") as f:
        f.write(package.tobytes())

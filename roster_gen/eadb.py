#!/usr/bin/env python3
"""
eadb.py -- reader/writer for the EA "TDB" database used by NCAA Football 14 (PS3)
and other last-gen EA Sports games (Madden, NCAA, Head Coach).

Format documented in docs/EA_DB_FORMAT.md.
Independently cross-checked against bep713/madden-file-tools (TDBParser/TDBWriter).

Quick use:
    python3 eadb.py FILE                    # header + table summary
    python3 eadb.py FILE --selftest         # byte-identical round-trip proof
    python3 eadb.py FILE --verify           # recompute every CRC
    python3 eadb.py FILE --fields PLAY      # dump a table's field map
    python3 eadb.py FILE --player Manziel   # find players
    python3 eadb.py FILE --rebuild OUT      # parse + write a new file
"""
import struct
import sys

# ------------------------------------------------------------------ constants

BE = 1
LE = 0
MAGIC = 0x4442                       # "DB" read big-endian
POLY = 0x04C11DB7

ALLOC_FIXED = (2, 6, 10, 14)         # data size = lengthBytes * maxRecords
ALLOC_VARIABLE = (34, 66)            # data size = up to next table


# ------------------------------------------------------------------ CRC

def crc32_ea(data, crc=0):
    """CRC used by the EA TDB code (the *complement* of the stored value).

    poly 0x04C11DB7, init 0xFFFFFFFF, refin/refout=false, xorout 0xFFFFFFFF
    (this is CRC-32/BZIP2).  The reference JS calls this ``crc.crc32_be`` and
    then stores ``~result``."""
    crc = (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) & 0xFFFFFFFF) ^ POLY
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc ^ 0xFFFFFFFF


def stored_crc(data):
    """The big-endian u32 value written into the file.

    Equals CRC-32/MPEG-2 (poly 0x04C11DB7, init 0xFFFFFFFF, xorout 0),
    i.e. ``~crc32_ea(data)``.  Test vector: stored_crc(b'123456789') ==
    0x0376E6E7."""
    return (~crc32_ea(data)) & 0xFFFFFFFF


# ------------------------------------------------------------------ bit io

def read_bits(buf, bit_off, bit_len):
    """MSB-first unsigned bitfield read."""
    v = 0
    for i in range(bit_len):
        b = bit_off + i
        v = (v << 1) | ((buf[b >> 3] >> (7 - (b & 7))) & 1)
    return v


def write_bits(buf, bit_off, bit_len, value):
    """MSB-first unsigned bitfield write, in place."""
    for i in range(bit_len):
        b = bit_off + i
        bit = (value >> (bit_len - 1 - i)) & 1
        mask = 1 << (7 - (b & 7))
        if bit:
            buf[b >> 3] |= mask
        else:
            buf[b >> 3] &= ~mask


def _rev4(raw):
    """4-byte names are written reversed on big-endian files -> reverse back."""
    return bytes(raw)[::-1].decode('latin1')


# ------------------------------------------------------------------ model

class Field:
    """One 16-byte field descriptor inside a table header."""
    __slots__ = ('type', 'bit_offset', 'name', 'bits')

    def __init__(self, type_, bit_offset, name, bits):
        self.type = type_          # 0=string 2=sint 3=uint 4=float (32 bit)
        self.bit_offset = bit_offset
        self.name = name
        self.bits = bits

    @property
    def is_string(self):
        return self.type == 0

    @property
    def byte_offset(self):
        return self.bit_offset // 8

    @property
    def nbytes(self):
        return (self.bits + 7) // 8

    def __repr__(self):
        return (f'<Field {self.name} type={self.type} '
                f'bit={self.bit_offset} bits={self.bits}>')


class Table:
    def __init__(self, name, offset, header_buf, endian):
        self.name = name
        self.offset = offset                     # relative to 0x18+8*numTables
        self.header = bytearray(header_buf)      # 0x28 bytes, kept verbatim
        self.endian = endian
        self.fields = []
        self.field_buf = b''       # raw descriptor block
        self.data = bytearray()    # record block (fixed size unless variable)
        self.index_buf = b''

    # -- header fields (re-read from header bytes) -------------------------
    @property
    def prior_crc(self):
        return struct.unpack('>I', self.header[0:4])[0]

    @prior_crc.setter
    def prior_crc(self, v):
        struct.pack_into('>I', self.header, 0, v)

    @property
    def alloc_type(self):
        return struct.unpack('>I', self.header[4:8])[0]

    @property
    def length_bytes(self):
        return struct.unpack('>I', self.header[8:12])[0]

    @property
    def length_bits(self):
        return struct.unpack('>I', self.header[12:16])[0]

    @property
    def max_records(self):
        return struct.unpack('>H', self.header[20:22])[0]

    @max_records.setter
    def max_records(self, v):
        struct.pack_into('>H', self.header, 20, v)

    @property
    def current_records(self):
        return struct.unpack('>H', self.header[22:24])[0]

    @current_records.setter
    def current_records(self, v):
        struct.pack_into('>H', self.header, 22, v)

    @property
    def num_fields(self):
        return self.header[28]

    @property
    def index_count(self):
        return self.header[29]

    @property
    def header_crc(self):
        return struct.unpack('>I', self.header[36:40])[0]

    @header_crc.setter
    def header_crc(self, v):
        struct.pack_into('>I', self.header, 36, v)

    # -- record access -----------------------------------------------------
    @property
    def stride(self):
        return self.length_bytes

    def row_count(self):
        """Number of rows physically present in the record block."""
        return len(self.data) // self.length_bytes if self.length_bytes else 0

    def record(self, i):
        n = self.length_bytes
        return memoryview(self.data)[i * n:(i + 1) * n]

    def field(self, name):
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f'{self.name}.{name}')

    def get_int(self, rec, name):
        f = self.field(name)
        v = read_bits(rec, f.bit_offset, f.bits)
        if f.type == 2 and v & (1 << (f.bits - 1)):
            v -= 1 << f.bits                      # sign extend
        elif f.type == 4 and f.bits == 32:
            return struct.unpack('>f', struct.pack('>I', v))[0]
        return v

    def set_int(self, rec, name, value):
        f = self.field(name)
        if f.type == 4 and f.bits == 32:
            value = struct.unpack('>I', struct.pack('>f', value))[0]
        elif value < 0:
            value += 1 << f.bits
        write_bits(rec, f.bit_offset, f.bits, value)

    def get_str(self, rec, name):
        f = self.field(name)
        start = f.bit_offset >> 3
        n = f.nbytes
        return bytes(rec[start:start + n]).split(b'\x00')[0].decode('latin1')

    def set_str(self, rec, name, text):
        f = self.field(name)
        n = f.nbytes
        raw = text.encode('latin1')
        if len(raw) > n:
            raise ValueError(f'{name}: {text!r} longer than {n} bytes')
        start = f.bit_offset >> 3
        rec[start:start + n] = raw.ljust(n, b'\x00')

    def __repr__(self):
        return (f'<Table {self.name} stride={self.length_bytes} '
                f'max={self.max_records} cur={self.current_records} '
                f'fields={self.num_fields}>')


class TDBFile:
    def __init__(self, data):
        self.buf = bytearray(data)
        b = self.buf
        self.digit, self.version = struct.unpack('>HH', b[0:4])
        if self.digit != MAGIC:
            raise ValueError('not a DB/TDB file (magic != "DB")')
        self.endian = b[4]
        self.header = bytearray(b[0:0x18])
        self.num_tables = struct.unpack('>I', b[16:20])[0]
        self.defs_start = 0x18
        self.defs_len = self.num_tables * 8
        self.data_start = self.defs_start + self.defs_len
        # definitions in file order: (name, rel_offset, raw bytes position)
        self.definitions = []
        for i in range(self.num_tables):
            o = self.defs_start + i * 8
            raw = b[o:o + 4]
            name = _rev4(raw) if self.endian == BE else raw.decode('latin1')
            off = struct.unpack('>I', b[o + 4:o + 8])[0]
            self.definitions.append([name, off])
        self.tables = []
        self._parse()

    @property
    def db_size(self):
        return struct.unpack('>I', self.buf[8:12])[0]

    @property
    def header_crc(self):
        return struct.unpack('>I', self.buf[20:24])[0]

    # -- parsing -----------------------------------------------------------
    def _parse(self):
        b = self.buf
        for name, off in sorted(self.definitions, key=lambda d: d[1]):
            start = self.data_start + off
            t = Table(name, off, b[start:start + 0x28], self.endian)
            self.tables.append(t)
            p = start + 0x28
            for _ in range(t.num_fields):
                type_, foff = struct.unpack('>II', b[p:p + 8])
                raw = b[p + 8:p + 12]
                fname = _rev4(raw) if self.endian == BE else raw.decode('latin1')
                bits = struct.unpack('>I', b[p + 12:p + 16])[0]
                t.fields.append(Field(type_, foff, fname, bits))
                p += 16
            t.field_buf = bytes(b[start + 0x28:p])
            alloc = t.alloc_type
            if alloc in ALLOC_FIXED:
                dlen = t.length_bytes * t.max_records
            elif alloc in ALLOC_VARIABLE:
                nxt = [d[1] for d in self.definitions if d[1] > off]
                end_rel = min(nxt) if nxt else self.db_size - self.data_start - 4
                dlen = (self.data_start + end_rel) - p
            else:
                dlen = t.length_bytes * t.current_records
            t.data = bytearray(b[p:p + dlen])
            p += dlen
            ilen = 0x10 * t.index_count
            t.index_buf = bytes(b[p:p + ilen])
            p += ilen
            t.file_start = start
            t.file_end = p
        self.eof_crc = bytes(b[self.tables[-1].file_end:
                               self.tables[-1].file_end + 4])

    def table(self, name):
        for t in self.tables:
            if t.name == name:
                return t
        raise KeyError(name)

    # -- structural verification ------------------------------------------
    def verify(self):
        """Recompute every checksum. Returns a list of human-readable problems.

        Coverage (all verified against this file):
          * file header CRC @0x14  = crc(bytes 0x00..0x13)
          * table[0].priorCrc      = crc(directory 0x18..data_start)
          * table[i].headerCrc     = crc(table[i].header[0x04..0x23])
          * table[i+1].priorCrc    = crc(table[i].fieldDefs + data + index)
          * EOF CRC @dbSize-4      = crc(last table's fieldDefs + data + index)
        """
        problems = []
        b = self.buf

        want = stored_crc(bytes(b[0:0x14]))
        if self.header_crc != want:
            problems.append(f'file header CRC {self.header_crc:08x} != {want:08x}')

        if self.tables:
            want = stored_crc(bytes(b[self.defs_start:self.data_start]))
            if self.tables[0].prior_crc != want:
                problems.append(f'{self.tables[0].name}.priorCrc '
                                f'{self.tables[0].prior_crc:08x} != {want:08x}')

        for i, t in enumerate(self.tables):
            want = stored_crc(bytes(t.header[4:0x24]))
            if t.header_crc != want:
                problems.append(f'{t.name}.headerCrc {t.header_crc:08x} != {want:08x}')
            tail = stored_crc(t.field_buf + bytes(t.data) + t.index_buf)
            if i + 1 < len(self.tables):
                got = self.tables[i + 1].prior_crc
                where = f'{self.tables[i + 1].name}.priorCrc'
            else:
                got = struct.unpack('>I', b[self.db_size - 4:self.db_size])[0]
                where = 'EOF CRC'
            if got != tail:
                problems.append(f'{t.name} tail CRC {tail:08x} != {where} {got:08x}')
        return problems

    # -- convenience -------------------------------------------------------
    def find_player(self, first=None, last=None):
        t = self.table('PLAY')
        out = []
        for i in range(t.current_records):
            r = t.record(i)
            if ((first is None or t.get_str(r, 'PFNA') == first) and
                    (last is None or t.get_str(r, 'PLNA') == last)):
                out.append(i)
        return out

    def team_of(self, tgid):
        """Return TEAM table row whose TEAM.TGID == tgid."""
        t = self.table('TEAM')
        for i in range(t.row_count()):
            r = t.record(i)
            if t.get_int(r, 'TGID') == tgid:
                return i, t.get_str(r, 'TDNA')
        return None, None

    # -- serialization -----------------------------------------------------
    def build(self):
        """Serialize and fix every offset/size/CRC. Returns the DB bytes."""
        # 1. prior CRC of the first table covers the directory buffer, which
        #    itself depends on the offsets we are about to compute, so iterate
        #    until stable (a single pass is enough because CRCs do not feed back
        #    into layout, but the definition bytes must be final first).
        n = self.num_tables
        defs_len = n * 8
        data_start = 0x18 + defs_len

        # initial offsets from current loaded values (used only on first pass)
        offsets = {d[0]: d[1] for d in self.definitions}
        for _ in range(2):
            body = bytearray()
            for t in self.tables:
                t.offset = len(body)
                body += bytes(t.header) + t.field_buf + bytes(t.data) + t.index_buf
            next_off = {t.name: t.offset for t in self.tables}
            if next_off == offsets:
                break
            offsets = next_off

        # 2. definitions buffer (original order, new offsets)
        defs = bytearray()
        for name, _old in self.definitions:
            t = self.table(name)
            defs += name[::-1].encode('latin1') if self.endian == BE else name.encode('latin1')
            defs += struct.pack('>I', t.offset)

        # 3. per-table CRCs (must be written into the *next* table's header)
        chunks = []
        prev_crc = stored_crc(bytes(defs))
        for i, t in enumerate(self.tables):
            t.prior_crc = prev_crc
            t.header_crc = stored_crc(bytes(t.header[4:0x24]))
            chunk = bytes(t.header) + t.field_buf + bytes(t.data) + t.index_buf
            chunks.append(chunk)
            prev_crc = stored_crc(t.field_buf + bytes(t.data) + t.index_buf)
        eof = struct.pack('>I', prev_crc)      # CRC of last table

        # 4. file header
        db_size = data_start + sum(len(c) for c in chunks) + 4
        hdr = bytearray(self.header)
        struct.pack_into('>I', hdr, 8, db_size)
        struct.pack_into('>I', hdr, 20, stored_crc(bytes(hdr[0:0x14])))

        return bytes(hdr) + bytes(defs) + b''.join(chunks) + eof

    def rebuild(self):
        new = self.build()
        self.__init__(new)
        return new


# ------------------------------------------------------------------ cli

def _summary(path):
    f = TDBFile(open(path, 'rb').read())
    print(f'file      : {path}  ({len(f.buf)} bytes, db_size={f.db_size})')
    print(f'magic     : {chr(f.digit >> 8)}{chr(f.digit & 0xFF)}  '
          f'version={f.version}  endian={f.endian}  numTables={f.num_tables}  '
          f'header_crc={f.header_crc:08X}')
    print(f'data start: {f.data_start:#x} '
          f'(directory offsets are relative to this)')
    if len(f.buf) > f.db_size:
        tail = f.buf[f.db_size:]
        print(f'padding   : {len(tail)} bytes after db_size '
              f'({"all zero" if not any(tail) else "NON-ZERO - inspect"})')
    print()
    print(f'{"table":6} {"hdr@":>9} {"stride":>6} {"max":>6} {"used":>6} '
          f'{"fields":>6} {"alloc":>5} {"priorCRC":>9} {"hdrCRC":>9}')
    for t in f.tables:
        print(f'{t.name:6} {t.file_start:#9x} {t.length_bytes:6d} '
              f'{t.max_records:6d} {t.current_records:6d} {t.num_fields:6d} '
              f'{t.alloc_type:5d} {t.prior_crc:08x} {t.header_crc:08x}')


def _selftest(path):
    data = open(path, 'rb').read()
    f = TDBFile(data)
    rebuilt = f.build()
    ok = rebuilt == data[:f.db_size]
    print(f'round-trip identical: {ok}  ({len(rebuilt)} bytes vs '
          f'db_size {f.db_size})')
    if not ok:
        for i in range(min(len(rebuilt), f.db_size)):
            if rebuilt[i] != data[i]:
                print(f'  first diff at {i:#x}: {rebuilt[i]:02x} != {data[i]:02x}')
                break
        return 1

    probs = f.verify()
    print(f'checksum verification: {"PASS" if not probs else "FAIL"}')
    for p in probs:
        print('  ' + p)

    # mutate a name in place (no size change), rebuild, reparse
    p = f.table('PLAY')
    row = f.find_player('Johnny', 'Manziel')[0]
    rec = p.record(row)
    old = p.get_str(rec, 'PFNA')
    p.set_str(rec, 'PFNA', 'JohnnyX')
    f.rebuild()
    row2 = f.find_player('JohnnyX', 'Manziel')[0]
    print(f'mutation test: renamed row {row} {old!r}->JohnnyX, '
          f'reparsed at row {row2}, PASS={row2 == row and not f.verify()}')
    assert f.build() == f.buf[:f.db_size]

    # add a row (uses spare capacity: PLAY 9100-8631 = 469 rows)
    f2 = TDBFile(data)
    p2 = f2.table('PLAY')
    assert p2.max_records == p2.row_count()
    p2.current_records += 1
    newrec = p2.record(p2.current_records - 1)
    p2.set_int(newrec, 'PGID', 65000)
    p2.set_int(newrec, 'POID', 65000)
    p2.set_int(newrec, 'TGID', 1)
    p2.set_int(newrec, 'PPOS', 0)
    p2.set_str(newrec, 'PFNA', 'Test')
    p2.set_str(newrec, 'PLNA', 'Player')
    out = f2.rebuild()
    f3 = TDBFile(out)
    p3 = f3.table('PLAY')
    i3 = f3.find_player('Test', 'Player')[0]
    print(f'append test: current_records={p3.current_records} '
          f'new row={i3} name={p3.get_str(p3.record(i3), "PFNA")} '
          f'PASS={p3.current_records == 8632 and i3 == 8631 and not f3.verify()}')

    # grow past maxRecords: data grows, every later table/dir offset moves
    f4 = TDBFile(data)
    p4 = f4.table('PLAY')
    for _ in range(10):
        p4.data.extend(b'\x00' * p4.length_bytes)
    p4.max_records += 10
    p4.current_records += 10
    r4 = p4.record(p4.current_records - 1)
    p4.set_int(r4, 'PGID', 65001)
    p4.set_int(r4, 'POID', 65001)
    p4.set_int(r4, 'TGID', 1)
    p4.set_int(r4, 'PPOS', 0)
    p4.set_str(r4, 'PFNA', 'Grown')
    p4.set_str(r4, 'PLNA', 'Player')
    old_db = f4.db_size
    out4 = f4.rebuild()
    f5 = TDBFile(out4)
    grown = f5.find_player('Grown', 'Player')
    print(f'grow test: db_size {old_db}->{f5.db_size}, '
          f'PLAY max={f5.table("PLAY").max_records} cur={f5.table("PLAY").current_records}, '
          f'new row={grown}, TEAM dir offset={f5.table("TEAM").offset:#x}, '
          f'PASS={bool(grown) and not f5.verify() and f5.build() == out4}')
    return 0 if ok and not probs else 1


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = argv[1]
    if '--selftest' in argv:
        return _selftest(path)
    if '--verify' in argv:
        f = TDBFile(open(path, 'rb').read())
        probs = f.verify()
        print(f'{"PASS" if not probs else "FAIL"}: {len(probs)} problem(s)')
        for p in probs:
            print('  ' + p)
        return 0 if not probs else 1
    if '--fields' in argv:
        f = TDBFile(open(path, 'rb').read())
        t = f.table(argv[argv.index('--fields') + 1])
        print(f'# {t.name} stride={t.length_bytes} bytes '
              f'max={t.max_records} used={t.current_records} '
              f'fields={t.num_fields}')
        print(f'{"abbrev":8} {"type":5} {"bit@":>6} {"bits":>5} {"byte@":>6}')
        for fl in t.fields:
            print(f'{fl.name:8} {fl.type:5d} {fl.bit_offset:6d} '
                  f'{fl.bits:5d} {fl.bit_offset // 8:6d}')
        return 0
    if '--player' in argv:
        f = TDBFile(open(path, 'rb').read())
        q = argv[argv.index('--player') + 1]
        p = f.table('PLAY')
        for i in range(p.current_records):
            r = p.record(i)
            full = f'{p.get_str(r, "PFNA")} {p.get_str(r, "PLNA")}'
            if q.lower() in full.lower():
                tg = p.get_int(r, 'TGID')
                _, team = f.team_of(tg)
                print(f'row {i}: {full!r} PGID={p.get_int(r, "PGID")} '
                      f'TGID={tg} ({team}) PPOS={p.get_int(r, "PPOS")} '
                      f'POVR={p.get_int(r, "POVR")}')
        return 0
    if '--rebuild' in argv:
        out = argv[argv.index('--rebuild') + 1]
        f = TDBFile(open(path, 'rb').read())
        data = f.build()
        open(out, 'wb').write(data)
        print(f'wrote {out} ({len(data)} bytes)')
        return 0
    _summary(path)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

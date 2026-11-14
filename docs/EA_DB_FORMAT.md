# NCAA Football 14 (PS3) roster database - EA "TDB" format

Reverse-engineered from `/tmp/opencode/USR-DATA.dec2` (BLUS31159, NCAA Football 14).
Fact-finding only: the source file was not modified.

Companion implementation: `/tmp/opencode/eadb.py` (parser, writer, CRC verifier and self-test).

Cross-checked against the public `bep713/madden-file-tools` implementation (`TDBParser.js`, `TDBWriter.js`, `CRC.js`, `TDBField.js`). The field/record layout, allocation-type rules and CRC definition agree byte-for-byte with that code and with this file.

## TL;DR

- Container magic `DB`, version **8**, endian flag **1** (1 = big-endian), **10** tables.
- `dbSize` (file header +0x08) = **1,320,160** bytes (0x1424E0). The decrypted copy is 1,433,600 bytes, so **113,440 trailing bytes are zero padding, not part of the DB**.
- File header is 24 bytes; then N x 8-byte directory entries; then N table blocks in directory-offset order; the last 4 bytes of `dbSize` are the EOF CRC.
- A table block = `0x28` header + `numFields*0x10` field descriptors + `lengthBytes*maxRecords` record bytes (fixed allocation) + `indexCount*0x10` index bytes.
- Records are **bit-packed, MSB-first**. Every field is located by an explicit `(bitOffset, bits)` pair; use those, not the XML.
- PLAY: **133 fields, 112-byte records, 8,631 used / 9,100 allocated**.
- TEAM: **146 fields, 260-byte records, 141 used / 146 allocated**.
- Player names are fixed-width, NUL-padded Latin-1/ASCII: first name 11 bytes, last name 13 bytes.
- `PLAY.TGID` joins to `TEAM.TGID` (the field, not the row number). `DCHT.PGID` joins to `PLAY.PGID`.
- Any edit must fix the checksum chain: file-header CRC, each table-header CRC, each table `priorCrc`, and the EOF CRC (section 12).

## 1. Conventions

- All multi-byte integers in the DB are **big-endian** for this PS3 file. The endian flag is byte 4 of the file header (1 = big-endian, 0 = little-endian).
- Addresses are shown in hex, sizes in decimal unless suffixed `h`/`0x`.
- `data_start = 0x18 + 8*numTables`. For this file `numTables=10`, so `data_start = 0x68`.
- Directory offsets are **relative to `data_start`**. Absolute table header = `data_start + directory_offset`.
- On big-endian files the 4-byte table and field names are stored **reversed** (`PLAY` is on disk as `YALP`, `PFNA` as `ANFP`). Reverse before decoding.
- Records are addressed in **bits from the start of the record**, with bit 0 = MSB of byte 0.
- Stored CRCs are big-endian `uint32`.

## 2. File layout

```
0x00  file header (0x18 bytes)
0x18  directory: numTables * 8 bytes  (4-byte name + u32 relative offset)
0x68  table[0] block
      table[1] block
      ...
      table[n-1] block
dbSize-4  EOF CRC (u32)
dbSize .. original file length: optional zero padding (113,440 bytes here)
```

Table blocks are written in increasing `directory_offset` order. Each block is contiguous and immediately followed by the next one; there is no alignment padding between blocks in this file.

The size relationship is exact:

```
dbSize = data_start + sum(0x28 + 0x10*numFields_i + lengthBytes_i*maxRecords_i
                        + 0x10*indexCount_i) + 4
```

For this file: `1320160 = 0x68 + 1320052 + 4`.

## 3. File header (0x18 bytes)

| offset | size | type | name | value in this file |
|---|---|---|---|---|
| 0x00 | 2 | u16 | digit / magic | 0x4442 (`DB`) |
| 0x02 | 2 | u16 | version | 8 |
| 0x04 | 1 | u8 | endian | 1 (1 = big-endian) |
| 0x05 | 1 | u8 | unknown1 | 0 |
| 0x06 | 2 | u16 | unknown2 | 0 |
| 0x08 | 4 | u32 | dbSize | 0x1424E0 (1,320,160) |
| 0x0C | 4 | u32 | zero | 0 |
| 0x10 | 4 | u32 | numTables | 10 |
| 0x14 | 4 | u32 | headerCrc | 0x05B4D7E4 |

`headerCrc` is the stored CRC of bytes **0x00..0x13** (everything above except the CRC itself). It therefore covers `dbSize` and `numTables`, so it must be recomputed after either changes. The reference code calls this field `unknown3`.

Raw header bytes:

```
44 42 00 08 01 00 00 00 00 14 24 e0 00 00 00 00 00 00 00 0a 05 b4 d7 e4
```

## 4. Directory (definitions)

At `0x18`, `numTables` entries of 8 bytes:

| offset | size | meaning |
|---|---|---|
| +0x00 | 4 | table name, 4 ASCII bytes, reversed on disk (BE) |
| +0x04 | 4 | u32 offset of the table header, relative to `data_start` |

The directory ends at `data_start` and its raw bytes are covered by the first table's `priorCrc`.

This file:

| # | table | rel. offset | entry at | header at | block ends at |
|---|---|---|---|---|---|
| 0 | CSKL | 0x0 | 0x18 | 0x68 | 0x2FEC |
| 1 | COCH | 0x2F84 | 0x20 | 0x2FEC | 0x10354 |
| 2 | CONF | 0x102EC | 0x28 | 0x10354 | 0x106A4 |
| 3 | DCHT | 0x1063C | 0x30 | 0x106A4 | 0x26D4C |
| 4 | DIVI | 0x26CE4 | 0x38 | 0x26D4C | 0x2717C |
| 5 | INJY | 0x27114 | 0x40 | 0x2717C | 0x27204 |
| 6 | PLAY | 0x2719C | 0x48 | 0x27204 | 0x1207BC |
| 7 | STAD | 0x120754 | 0x50 | 0x1207BC | 0x1379B4 |
| 8 | TUNI | 0x13794C | 0x58 | 0x1379B4 | 0x13874C |
| 9 | TEAM | 0x1386E4 | 0x60 | 0x13874C | 0x1424DC |

The first entry has offset 0, i.e. its header is at `data_start` (0x68).

`directory_offset` is **not** an absolute file offset; adding `0x68` gives the absolute header position. If the size of any table changes, every later `relative offset` must be recomputed.

## 5. Table header (0x28 bytes)

| offset | size | type | name | meaning |
|---|---|---|---|---|
| +0x00 | 4 | u32 | priorCrc | CRC of the previous chunk (see 12) |
| +0x04 | 4 | u32 | dataAllocType | 2, 6, 10, 14 fixed; 34, 66 variable |
| +0x08 | 4 | u32 | lengthBytes | record stride in bytes |
| +0x0C | 4 | u32 | lengthBits | always 8*lengthBytes - 1 in this file |
| +0x10 | 4 | u32 | zero | 0 |
| +0x14 | 2 | u16 | maxRecords | allocated row slots |
| +0x16 | 2 | u16 | currentRecords | valid rows, indices 0..current-1 |
| +0x18 | 4 | u32 | unknown2 | 0x0000FFFF |
| +0x1C | 1 | u8 | numFields | field descriptor count |
| +0x1D | 1 | u8 | indexCount | index entries (0 here) |
| +0x1E | 2 | u16 | zero2 | 0 |
| +0x20 | 4 | u32 | zero3 | 0 |
| +0x24 | 4 | u32 | headerCrc | CRC of header bytes 0x04..0x23 |

Immediately after the header: `numFields` field descriptors of 16 bytes each. Then the record block. If `indexCount > 0`, an index block of `indexCount * 16` bytes follows the records. All tables in this file have `indexCount = 0`.

`headerCrc` covers `+0x04..+0x23`; it deliberately excludes `priorCrc` (+0x00..+0x03) and itself (+0x24..+0x27). This is why updating `priorCrc` does not invalidate `headerCrc`. Verified for all 10 tables:

| table | stored | recomputed | result |
|---|---|---|---|
| CSKL | 0xE89EA8F7 | 0xE89EA8F7 | OK |
| COCH | 0x3FEA6447 | 0x3FEA6447 | OK |
| CONF | 0x7F5AFCD3 | 0x7F5AFCD3 | OK |
| DCHT | 0x07FF994C | 0x07FF994C | OK |
| DIVI | 0xDE3C3D92 | 0xDE3C3D92 | OK |
| INJY | 0x2544A3B9 | 0x2544A3B9 | OK |
| PLAY | 0x4C08B0C4 | 0x4C08B0C4 | OK |
| STAD | 0xA23578C3 | 0xA23578C3 | OK |
| TUNI | 0xAB2B60B9 | 0xAB2B60B9 | OK |
| TEAM | 0x4EAB4756 | 0x4EAB4756 | OK |

Example - PLAY header bytes:

```
d8 44 f1 e6 00 00 00 06 00 00 00 70 00 00 03 7f 00 00 00 00 23 8c 21 b7 00 00 ff ff 85 00 00 00 00 00 00 00 4c 08 b0 c4
```

## 6. Field descriptors (16 bytes each)

| offset | size | type | name | meaning |
|---|---|---|---|---|
| +0x00 | 4 | u32 | type | 0 string, 1 binary, 2 sint, 3 uint, 4 float32, 13/14 varchar |
| +0x04 | 4 | u32 | bitOffset | bit offset from start of record |
| +0x08 | 4 | char[4] | name | 4-byte abbreviation, reversed on disk (BE) |
| +0x0C | 4 | u32 | bits | field width in bits |

For string fields (`type=0`), `bits` is exactly `8 * byte_length` and `bitOffset` is byte-aligned (all 31 string fields in this file satisfy this).

Descriptor order is arbitrary: in PLAY the first descriptor is `BSAA`, while `PGID` sits at bit 0 and `PFNA` at bit 32. Locate fields by name and use `bitOffset`, never by descriptor position.

Example - PFNA descriptor (type 0, bit 32, name `ANFP` on disk, 88 bits):

```
00000000 00000020 414e4650 00000058
```

Type codes observed in this file:

| code | meaning | fields | notes |
|---|---|---|---|
| 0 | string | 31 | fixed-width bytes, NUL padded |
| 2 | signed int | 9 | two's-complement, e.g. TEAM.TCHS -6..21 |
| 3 | unsigned int | 737 | bit field |
| 4 | float32 | 3 | IEEE-754 big-endian; STAD lon/lat/rotation |

Types 1 (binary), 13 and 14 (varchar with extra data) do not occur here. In a `sint` field, sign-extend from the declared `bits` width. In a `float` field, interpret the 32 raw bits as IEEE-754 big-endian.

## 7. Records and bit packing

- The record block is `maxRecords * lengthBytes` bytes for allocation types 2, 6, 10, 14. Types 34/66 are variable-length and are not present here.
- Valid rows are indices `0 .. currentRecords-1`. Rows from `currentRecords` to `maxRecords-1` are unused spare slots; in this file every unused slot is all zero (verified for every table).
- Fields are bit-packed MSB-first. To read `bits` bits at `bitOffset`, take bit `bitOffset` as the most significant bit of the result. Multi-byte integer fields therefore behave as big-endian. Fields may cross byte boundaries (e.g. PLAY.TGID starts at bit 346).
- Trailing bits of each record are padding and are zero. Keep them zero.
- Strings are raw bytes in the record; they are not length-prefixed. A string occupies its full declared width; short values are NUL-padded, and a value that exactly fills the field has no NUL terminator.

Record accounting per table:

| table | fields | stride B | stride bits | last used bit | pad bits | max | used | spare |
|---|---|---|---|---|---|---|---|---|
| CSKL | 42 | 28 | 224 | 201 | 23 | 409 | 378 | 31 |
| COCH | 108 | 128 | 1024 | 1022 | 2 | 409 | 403 | 6 |
| CONF | 5 | 28 | 224 | 198 | 26 | 26 | 25 | 1 |
| DCHT | 4 | 8 | 64 | 37 | 27 | 11464 | 11068 | 396 |
| DIVI | 4 | 44 | 352 | 330 | 22 | 22 | 22 | 0 |
| INJY | 6 | 8 | 64 | 44 | 20 | 0 | 0 | 0 |
| PLAY | 133 | 112 | 896 | 874 | 22 | 9100 | 8631 | 469 |
| STAD | 117 | 464 | 3712 | 3682 | 30 | 200 | 197 | 3 |
| TUNI | 215 | 416 | 3328 | 3312 | 16 | 0 | 0 | 0 |
| TEAM | 146 | 260 | 2080 | 2061 | 19 | 146 | 141 | 5 |

## 8. Table inventory

All tables use `dataAllocType = 6` (fixed records) except INJY and TUNI, which use type 2 with `maxRecords = 0` (no data block).

| table | meaning | dir off | header at | fields | stride | max | used | spare | record B | alloc |
|---|---|---|---|---|---|---|---|---|---|---|
| CSKL | Coach Skills | 0x0 | 0x68 | 42 | 28 | 409 | 378 | 31 | 11452 | 6 |
| COCH | Coaches | 0x2F84 | 0x2FEC | 108 | 128 | 409 | 403 | 6 | 52352 | 6 |
| CONF | Conference | 0x102EC | 0x10354 | 5 | 28 | 26 | 25 | 1 | 728 | 6 |
| DCHT | Depth Chart | 0x1063C | 0x106A4 | 4 | 8 | 11464 | 11068 | 396 | 91712 | 6 |
| DIVI | Divisions | 0x26CE4 | 0x26D4C | 4 | 44 | 22 | 22 | 0 | 968 | 6 |
| INJY | Injury | 0x27114 | 0x2717C | 6 | 8 | 0 | 0 | 0 | 0 | 2 |
| PLAY | Player Info | 0x2719C | 0x27204 | 133 | 112 | 9100 | 8631 | 469 | 1019200 | 6 |
| STAD | Stadiums | 0x120754 | 0x1207BC | 117 | 464 | 200 | 197 | 3 | 92800 | 6 |
| TUNI | Uniforms | 0x13794C | 0x1379B4 | 215 | 416 | 0 | 0 | 0 | 0 | 2 |
| TEAM | Teams | 0x1386E4 | 0x13874C | 146 | 260 | 146 | 141 | 5 | 37960 | 6 |

Block sizes and exact tiling:

| table | header | field defs | records | index | total | ends at |
|---|---|---|---|---|---|---|
| CSKL | 40 | 672 | 11452 | 0 | 12164 | 0x2FEC |
| COCH | 40 | 1728 | 52352 | 0 | 54120 | 0x10354 |
| CONF | 40 | 80 | 728 | 0 | 848 | 0x106A4 |
| DCHT | 40 | 64 | 91712 | 0 | 91816 | 0x26D4C |
| DIVI | 40 | 64 | 968 | 0 | 1072 | 0x2717C |
| INJY | 40 | 96 | 0 | 0 | 136 | 0x27204 |
| PLAY | 40 | 2128 | 1019200 | 0 | 1021368 | 0x1207BC |
| STAD | 40 | 1872 | 92800 | 0 | 94712 | 0x1379B4 |
| TUNI | 40 | 3440 | 0 | 0 | 3480 | 0x13874C |
| TEAM | 40 | 2336 | 37960 | 0 | 40336 | 0x1424DC |

Sum of blocks = 1,320,052; `dbSize - data_start - 4` = 1,320,052. Exact match.

EOF CRC at `0x1424DC` = `0xAB10EF2A`.

## 9. Mapping to Xan's roster config XML

The XML is a third-party editor UI description, **not** an EA schema. It has no per-field record offsets. The only `<Offset>` element is on `PHGT` and has the value `-65`; that is a UI combo-box index offset (5'5" = 65 inches), not a bit/byte offset in the record.

Mapping rule: join XML `<Field><Abbreviation>` to the DB descriptor `name` (after reversing the 4 bytes). That is the only reliable link.

- XML defines **764** `<Field>` elements; the DB uses **763** distinct abbreviations (780 descriptors, since abbreviations repeat across tables). Every DB abbreviation exists in the XML; the one unused XML field is `OVR*` (the UI-only overall-rating pseudo-field), so there is no name mismatch.
- **39** XML fields have an empty `<Type>`; they still map by abbreviation. Where the XML has a type, it matches the DB type code one-to-one (string=0, sint=2, uint=3, float=4).
- **13** XML fields have a non-empty `<ControlLink>`. Twelve declare foreign-key joins and one (`OVR*`) is a calculated field, not a stored one. The declared joins are listed in section 9.1; all were re-verified against the record data.
- The XML `<Table>` list names the tables: `COCH`=Coaches, `CONF`=Conference, `CSKL`=Coach Skills, `DCHT`=Depth Chart, `DIVI`=Divisions, `INJY`=Injury, `PLAY`=Player Info, `STAD`=Stadiums, `TEAM`=Teams, `TUNI`=Uniforms.

### 9.1 Joins declared in the XML

| XML field | abbrev appears in | target table | index field | display field(s) |
|---|---|---|---|---|
| `CCID` | CSKL, COCH | Coaches | Coach ID | Coach's First/Last Name |
| `CHFT` | COCH | Teams | Team ID | Team Name |
| `CGID` | CONF, DIVI, TEAM | Conference | Conference ID | Conference Name |
| `DGID` | DIVI, TEAM | Divisions | Division ID | Division Name |
| `PGID` | DCHT, INJY, PLAY | Player Info | Player ID | First/Last Name |
| `SGID` | STAD, TEAM | Stadiums | Stadium ID | Stadium Name |
| `TGID` | COCH, DCHT, INJY, PLAY, TUNI, TEAM | Teams | Team ID | Team Name |
| `TMPI` | TEAM | Player Info | Player ID | First/Last Name |
| `TPIO` | TEAM | Player Info | Player ID | First/Last Name |
| `TRIV` | TEAM | Teams | Team ID | Team Name |
| `TSI1` | TEAM | Player Info | Player ID | First/Last Name |
| `TSI2` | TEAM | Player Info | Player ID | First/Last Name |

All 12 map to real fields. The team/conference/division/stadium/coach joins resolve for every row; `TSI1`/`TMPI`/`TPIO` resolve only on the 126 FBS teams (the 15 FCS/HS rows hold ids with no `PLAY` row), and `TSI2` is always `0xFFFF`. This matches the joins derived independently in section 10.6.

UI semantics embedded in the XML:

- `PPOS` ControlItems are `(0) QB` through `(24) LS`; see section 10.
- `PHGT` ControlItems are 20 entries from `5'5"` to `7'0"`; the stored value is **height in inches**, so combo index = `stored - 65`.
- `PWGT` ControlItems are 241 entries from `160` to `400`; the stored value is **pounds - 160**, so pounds = `stored + 160`. The 8-bit field can hold 160..415 lb; the UI stops at 400.

## 10. PLAY and TEAM schemas, names and joins

### 10.1 PLAY (Player Info) - 133 fields, 112-byte stride

Key fields (full map in Appendix A):

| abbrev | XML name | type | bit@ | bits | byte@ |
|---|---|---|---|---|---|
| PGID | Player ID | 3 | 0 | 16 | 0 |
| POID | Org. Player ID | 3 | 16 | 16 | 2 |
| PFNA | First Name | 0 | 32 | 88 | 4 |
| PLNA | Last Name | 0 | 120 | 104 | 15 |
| PWGT | Weight | 3 | 224 | 8 | 28 |
| TGID | Team ID | 3 | 346 | 10 | 43 |
| PPOS | Position | 3 | 706 | 5 | 88 |
| POVR | Overall | 3 | 648 | 7 | 81 |
| PHGT | Height | 3 | 752 | 7 | 94 |
| PJEN | Jersey # | 3 | 548 | 7 | 68 |
| PYEA | Year | 3 | 244 | 3 | 30 |
| PRSD | Redshirt | 3 | 366 | 2 | 45 |

Physical start of every PLAY record:

```
bits   0.. 15  PGID  (u16)
bits  16.. 31  POID  (u16; equals PGID in all 8,631 rows)
bits  32..119  PFNA  (11 bytes, first name)
bits 120..223  PLNA  (13 bytes, last name)
bits 224..231  PWGT  (u8, pounds-160)
... remaining fields per Appendix A, last used bit is 873 (end offset 874),
then 22 pad bits to fill the 896-bit / 112-byte stride ...
```

### 10.2 TEAM (Teams) - 146 fields, 260-byte stride

Key fields (full map in Appendix B):

| abbrev | XML name | type | bit@ | bits | byte@ |
|---|---|---|---|---|---|
| TGID | Team ID | 3 | 1575 | 10 | 196 |
| TOID | Org Team ID | 3 | 1585 | 10 | 198 |
| TDNA | Team Name | 0 | 336 | 176 | 42 |
| TLNA | Team Long Name | 0 | 512 | 136 | 64 |
| TMNA | Team Mascot Name | 0 | 648 | 144 | 81 |
| TSNA | Team Short Name | 0 | 792 | 56 | 99 |
| CGID | Conference ID | 3 | 1555 | 5 | 194 |
| DGID | Division ID | 3 | 1560 | 5 | 195 |
| SGID | Stadium ID | 3 | 1565 | 10 | 195 |
| TTYP | Team Type | 3 | 1796 | 5 | 224 |
| TSI1 | Impact Player 1 | 3 | 32 | 16 | 4 |
| TSI2 | Impact Player 2 | 3 | 48 | 16 | 6 |
| TMPI | Impact Player 3 | 3 | 176 | 16 | 22 |
| TPIO | Impact Player 4 | 3 | 192 | 16 | 24 |
| TORD | Team Roster Order | 3 | 1605 | 10 | 200 |

The four team-name fields are contiguous at bytes 42..106: `TDNA` 22 bytes, `TLNA` 17, `TMNA` 18, `TSNA` 7. They are fixed-width and NUL-padded like player names.

### 10.3 Player-name encoding and limits

- `PFNA` = 88 bits = 11 bytes at bit 32; `PLNA` = 104 bits = 13 bytes at bit 120.
- Stored as raw bytes, NUL-padded on the right. No length prefix, no encoding marker. All 8,631 players in this file are 7-bit ASCII, so ASCII/Latin-1 decoding is safe here. Accented/non-ASCII handling is untested.
- Longest first name is 11 bytes (`Christopher`), longest last name is 13 bytes (`David Mims II`). 16 first names and 27 last names exactly fill their field and therefore have **no NUL terminator**. A reader must stop at 11/13 bytes, not search past the field. A writer must reject longer values.
- Bytes after the first NUL are zero in every name field. There is no junk after the terminator.

### 10.4 Positions

`PPOS` is a 5-bit code (`DCHT.PPOS` at bit 26, `PLAY.PPOS` at bit 706). XML ControlItems:

| code | position | code | position |
|---|---|---|---|
| 0 | QB | 1 | HB |
| 2 | FB | 3 | WR |
| 4 | TE | 5 | LT |
| 6 | LG | 7 | C |
| 8 | RG | 9 | RT |
| 10 | LE | 11 | RE |
| 12 | DT | 13 | LLB |
| 14 | MLB | 15 | RLB |
| 16 | CB | 17 | FS |
| 18 | SS | 19 | K |
| 20 | P | 21 | KR |
| 22 | PR | 23 | KO |
| 24 | LS |  |  |

PLAY rows use only codes 0..20 (verified); DCHT uses 0..24, including KR/PR/KO/LS (21..24) which appear only in the depth chart.

### 10.5 Height, weight, jersey

- `PHGT` (7 bits): height in **inches**. Display = `floor(in/12)' in%12"`. XML combo offset is -65 (5'5"); Manziel 73 = 6'1".
- `PWGT` (8 bits): **pounds - 160**. Manziel 40 = 200 lb; Clowney 114 = 274 lb.
- `PJEN` (7 bits): jersey number 0..127.

### 10.6 Joins and foreign keys

| from | to | key | evidence |
|---|---|---|---|
| PLAY.TGID | TEAM.TGID | 10-bit team id | all 8,631 PLAY values found; 126 distinct FBS teams |
| DCHT.TGID | TEAM.TGID | 10-bit team id | all 11,068 values found |
| DCHT.PGID | PLAY.PGID | 16-bit player id | all 11,068 values found; 6,534 distinct players |
| COCH.TGID | TEAM.TGID | 10-bit team id | all 403 values found |
| COCH.CHFT | TEAM.TGID | 10-bit team id (alma mater) | all 403 values found; 111 distinct |
| TEAM.TRIV | TEAM.TGID | 10-bit team id (rival) | all 141 values found; 101 distinct |
| CSKL.CCID | COCH.CCID | coach id | all 378 values found |
| TEAM.CGID | CONF.CGID | 5-bit conference id | all 141 values found |
| TEAM.DGID | DIVI.DGID | 5-bit division id | 0..21 found; 30 = no division |
| TEAM.SGID | STAD.SGID | 10-bit stadium id | 0..279 found; 1023 = none |
| TEAM.TSI1 / TMPI / TPIO | PLAY.PGID | 16-bit player id | valid for all 126 FBS teams |
| TEAM.TSI2 | PLAY.PGID | 16-bit player id | always 0xFFFF (none) here |

Important: `PLAY.PGID` is a persistent player id, **not** the row index. `PLAY.POID` equals `PGID` in every row of this file. A new player needs a new unique `PGID`; other tables reference that id. `PLAY` row order itself is not referenced by any other table, but valid rows must stay contiguous (0..currentRecords-1).

`TEAM.TGID` is also not the row number for all teams. Rows 0..114 have `TGID = row+1`; exceptions:

| TEAM row | name | TGID | CGID | DGID | SGID | TTYP |
|---|---|---|---|---|---|---|
| 115 | Troy | 143 | 13 | 30 | 142 | 0 |
| 116 | USF | 144 | 3 | 30 | 143 | 0 |
| 117 | FCS East | 160 | 17 | 30 | 1023 | 1 |
| 118 | FCS West | 161 | 17 | 30 | 1023 | 1 |
| 119 | FCS Northwest | 162 | 17 | 30 | 1023 | 1 |
| 120 | FCS Midwest | 163 | 17 | 30 | 1023 | 1 |
| 121 | FCS Southeast | 164 | 17 | 30 | 1023 | 1 |
| 122 | UMass | 181 | 7 | 2 | 221 | 0 |
| 123 | Western Kentucky | 211 | 13 | 30 | 222 | 0 |
| 124 | Texas State | 218 | 13 | 30 | 220 | 0 |
| 125 | Florida Atlantic | 229 | 4 | 8 | 240 | 0 |
| 126 | FIU | 230 | 4 | 8 | 241 | 0 |
| 127 | UTSA | 232 | 4 | 9 | 219 | 0 |
| 128 | Georgia State | 233 | 13 | 30 | 223 | 0 |
| 129 | Old Dominion | 234 | 5 | 30 | 224 | 0 |
| 130 | South Alabama | 235 | 13 | 30 | 225 | 0 |
| 131 | User HS team | 610 | 24 | 0 | 1023 | 8 |
| 132 | CPU HS team 1 | 611 | 24 | 0 | 1023 | 7 |
| 133 | CPU HS team 2 | 612 | 24 | 0 | 1023 | 7 |
| 134 | CPU HS team 3 | 613 | 24 | 0 | 1023 | 7 |
| 135 | CPU HS team 4 | 614 | 24 | 9 | 1023 | 7 |
| 136 | CPU HS team 5 | 615 | 24 | 0 | 1023 | 7 |
| 137 | CPU HS team 6 | 616 | 24 | 0 | 1023 | 7 |
| 138 | CPU HS team 7 | 617 | 24 | 0 | 1023 | 7 |
| 139 | CPU HS team 8 | 618 | 24 | 0 | 1023 | 7 |
| 140 | CPU HS team 9 | 619 | 24 | 9 | 1023 | 7 |

Rows 141..145 are all-zero spare slots (`currentRecords=141`, `maxRecords=146`). `TGID` is unique in the table (1..619 with gaps). `TOID` equals `TGID` in all 141 rows. `TTYP`: 0 normal/FBS (126 rows), 1 FCS (5), 7 CPU HS (9), 8 user HS (1).

`TEAM.SGID = 1023` is the "no stadium" sentinel for the 5 FCS and 10 HS teams. All other teams resolve to a `STAD` row by matching `STAD.SGID` (not row order). `TEAM.DGID = 30` means "no division" for 40 teams; `DIVI` only defines 0..21.

## 11. Validation against known 2013 players

Decoded with `eadb.py`, using only the field descriptors and the XML abbreviation map. Heights are inches (`ft'in"`), weights stored+160.

| player | PLAY row | PGID | TGID | team | pos | POVR | height | weight lb |
|---|---|---|---|---|---|---|---|---|
| Johnny Manziel | 6369 | 6574 | 93 | Texas A&M | QB | 96 | 73 (6'1") | 200 |
| AJ McCarron | 175 | 248 | 3 | Alabama | QB | 93 | 76 (6'4") | 214 |
| Jadeveon Clowney | 5698 | 5890 | 84 | South Carolina | RE | 99 | 78 (6'6") | 274 |
| Teddy Bridgewater | 2970 | 3108 | 44 | Louisville | QB | 97 | 75 (6'3") | 218 |
| Marcus Mariota | 5030 | 5208 | 74 | Oregon | QB | 96 | 76 (6'4") | 211 |
| Blake Bortles | 1202 | 1299 | 18 | UCF | QB | 96 | 76 (6'4") | 227 |
| Jameis Winston | 1906 | 2020 | 28 | Florida State | QB | 96 | 76 (6'4") | 225 |
| Bishop Sankey | 7475 | 7709 | 110 | Washington | HB | 93 | 70 (5'10") | 203 |
| Tre Mason | 567 | 648 | 9 | Auburn | HB | 93 | 70 (5'10") | 205 |
| Sammy Watkins | 1429 | 1531 | 21 | Clemson | WR | 97 | 73 (6'1") | 205 |
| Mike Evans | 6351 | 6556 | 93 | Texas A&M | WR | 96 | 77 (6'5") | 225 |
| Brandin Cooks | 5077 | 5256 | 75 | Oregon State | WR | 93 | 70 (5'10") | 186 |
| Eric Ebron | 4236 | 4395 | 62 | North Carolina | TE | 97 | 76 (6'4") | 245 |
| Jace Amaro | 6419 | 6625 | 94 | Texas Tech | TE | 93 | 77 (6'5") | 260 |
| Aaron Donald | 5217 | 5400 | 77 | Pittsburgh | DT | 96 | 72 (6'0") | 285 |
| Khalil Mack | 967 | 1058 | 15 | Buffalo | LLB | 96 | 75 (6'3") | 245 |
| Anthony Barr | 6752 | 6966 | 99 | UCLA | RLB | 98 | 76 (6'4") | 248 |
| Roberto Aguayo | 1882 | 1996 | 28 | Florida State | K | 82 | 73 (6'1") | 208 |

Additional checks:

- Texas A&M row 92 has `TPIO = 6574`, exactly Manziel's `PGID`.
- DCHT contains Manziel `PGID 6574` at Texas A&M (`TGID 93`).
- `find_player` scans `currentRecords` rows only; row numbers above are the actual record indices in the PLAY block, not `PGID-1`.

CLI:

```
$ python3 eadb.py USR-DATA.dec2 --player Manziel
row 6369: 'Johnny Manziel' PGID=6574 TGID=93 (Texas A&M) PPOS=0 POVR=96
$ python3 eadb.py USR-DATA.dec2 --player McCarron
row 175: 'AJ McCarron' PGID=248 TGID=3 (Alabama) PPOS=0 POVR=93
```

## 12. What must stay consistent when editing

There are four checksum layers plus the size/offset bookkeeping. Everything below was verified against the untouched file.

### 12.1 Checksum definition

```python
POLY = 0x04C11DB7
def crc32_ea(data, crc=0):          # CRC-32/BZIP2
    crc = (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) & 0xFFFFFFFF) ^ (POLY if crc & 0x80000000 else 0)
    return crc ^ 0xFFFFFFFF

def stored_crc(data):                # CRC-32/MPEG-2, the u32 written in the file
    return (~crc32_ea(data)) & 0xFFFFFFFF
```

Test vector: `stored_crc(b"123456789") == 0x0376E6E7`. The stored values are big-endian u32. Do not use `zlib.crc32` (reflected polynomial, different result).

### 12.2 Coverage

| stored value | location | covers |
|---|---|---|
| file header CRC | 0x14 | file header bytes 0x00..0x13 |
| table[0].priorCrc | table[0] +0x00 (0x68 here) | directory bytes 0x18..data_start |
| table[i].priorCrc (i>0) | table[i] +0x00 | table[i-1] field descriptors + record data + index block |
| table[i].headerCrc | table[i] +0x24 | table[i] header bytes +0x04..+0x23 |
| EOF CRC | dbSize-4 | last table field descriptors + data + index block |

The index-block term is the only uncertainty: `indexCount` is 0 for every table here, so it never contributes. `eadb.py` includes it if present; the bep713 writer covers only field descriptors + record data. This does not affect this file.

Verified chain in this file:

| table | stored priorCrc | recomputed tail | written into | result |
|---|---|---|---|---|
| CSKL | 0xD7B86B5E | 0xB918A7BE | COCH.priorCrc | OK |
| COCH | 0xB918A7BE | 0x9D8783A0 | CONF.priorCrc | OK |
| CONF | 0x9D8783A0 | 0x926F85A9 | DCHT.priorCrc | OK |
| DCHT | 0x926F85A9 | 0xF3DF5DC9 | DIVI.priorCrc | OK |
| DIVI | 0xF3DF5DC9 | 0x9E3EAE44 | INJY.priorCrc | OK |
| INJY | 0x9E3EAE44 | 0xD844F1E6 | PLAY.priorCrc | OK |
| PLAY | 0xD844F1E6 | 0x6A483F73 | STAD.priorCrc | OK |
| STAD | 0x6A483F73 | 0x8ACC6478 | TUNI.priorCrc | OK |
| TUNI | 0x8ACC6478 | 0x90697572 | TEAM.priorCrc | OK |
| TEAM | 0x90697572 | 0xAB10EF2A | EOF CRC | OK |

### 12.3 Edit recipes

**A. Edit a value or name in place (same width).**

1. Change the record bits/bytes.
2. Recompute the edited table's tail CRC (descriptors + data + index).
3. Write it into the next table's `priorCrc`; if the edited table is last, write it to the EOF CRC.
4. Nothing else changes: `currentRecords`, stride, `dbSize`, directory and header CRCs are all unaffected.

**B. Add a row within spare capacity (`currentRecords < maxRecords`).**

1. Zero the row at index `currentRecords` (never reuse stale bytes).
2. Write its fields; assign a fresh unique `PGID`.
3. Increment `currentRecords` at table header +0x16.
4. Recompute that table's `headerCrc` (+0x24) because currentRecords changed.
5. Recompute the table's tail CRC and write it to the next `priorCrc` (or EOF CRC).
6. `dbSize`, directory offsets and file-header CRC do **not** change.

**C. Remove a row.**

1. Decrement `currentRecords` (+0x16); zero the vacated row if you want the same "spare rows are zero" invariant.
2. Recompute this table's `headerCrc` and tail CRC; update next `priorCrc` or EOF CRC.
3. If you instead shift rows to keep them packed, update the affected record bytes; the same two CRCs still cover it.

**D. Grow beyond `maxRecords`, or add/remove a field.**

1. Update `maxRecords` (+0x14), and/or `lengthBytes` (+0x08) and `lengthBits` (+0x0C = 8*lengthBytes-1), and/or `numFields` (+0x1C).
2. Resize the descriptor block and/or record block so the block size formula still holds.
3. Recompute every later directory offset; the changed table and all later tables move by the size delta.
4. Recompute `dbSize` (+0x08) = `data_start + sum(blocks) + 4`.
5. Recompute the file-header CRC (+0x14) last: it covers `dbSize` and `numTables`.
6. Recompute table[0].priorCrc from the new directory bytes.
7. Recompute each changed table's `headerCrc`, and the whole `priorCrc` chain in offset order; write the last tail CRC to the EOF.

**E. Change a table name.** Only the 4 directory name bytes change, so only table[0].priorCrc (directory coverage) must be recomputed. Changing `numTables` additionally moves `data_start` and every absolute table position.

Ordering that always works: lay out tables -> write directory -> compute `dbSize` -> compute all table header CRCs -> compute first `priorCrc` from directory -> compute each table tail CRC into the next `priorCrc` / EOF -> compute file-header CRC. `headerCrc` and `priorCrc` do not cover each other, so their relative order is free.

### 12.4 Spare capacity

| table | used | max | free rows |
|---|---|---|---|
| CSKL | 378 | 409 | 31 |
| COCH | 403 | 409 | 6 |
| CONF | 25 | 26 | 1 |
| DCHT | 11068 | 11464 | 396 |
| DIVI | 22 | 22 | 0 |
| INJY | 0 | 0 | 0 |
| PLAY | 8631 | 9100 | 469 |
| STAD | 197 | 200 | 3 |
| TUNI | 0 | 0 | 0 |
| TEAM | 141 | 146 | 5 |

PLAY has 469 free slots, DCHT 396, TEAM 5, STAD 3, CSKL 31, COCH 6, CONF 1; DIVI is full; INJY and TUNI have `maxRecords=0` and no data block. Adding rows within spare capacity does not move any table.

### 12.5 Trailing bytes

The file is 1,433,600 bytes but `dbSize` is 1,320,160. The extra 113,440 bytes are all zero and are not referenced by any offset or CRC. Some roster saves in the wild are exactly `dbSize` bytes; others are padded to a 16-byte multiple (1,433,600 bytes). When writing, emit exactly `dbSize` bytes if the target accepts that, or append zero bytes to the original container length. Never include the padding in `dbSize` or in the EOF CRC.

## 13. Reproducing and proving the format

`eadb.py` parses the file, rebuilds every byte, and compares against the source. Self-test output on this file:

```
$ python3 eadb.py USR-DATA.dec2 --selftest
round-trip identical: True  (1320160 bytes vs db_size 1320160)
checksum verification: PASS
mutation test: renamed row 6369 'Johnny'->JohnnyX, reparsed at row 6369, PASS=True
append test: current_records=8632 new row=8631 name=Test PASS=True
grow test: db_size 1320160->1321280, PLAY max=9110 cur=8641, new row=[8640], TEAM dir offset=0x138b44, PASS=True
```

What the test proves:

1. **Round trip:** `TDBFile.build()` regenerates the first `dbSize` bytes exactly, including every directory offset, table header, descriptor, record byte, CRCs and the EOF CRC. If any layout assumption were wrong, the compare would fail.
2. **Checksum verification:** `verify()` independently recomputes the file header CRC, all 10 table header CRCs, the directory-seeded first `priorCrc`, the full `priorCrc` chain and the EOF CRC.
3. **In-place mutation:** renaming Manziel changes only record bytes plus one downstream `priorCrc`; the page still reparses at the same row.
4. **Append within capacity:** incrementing `currentRecords`, writing the new row and fixing the two affected CRCs yields a file that reparses with the new player at row 8,631.
5. **Grow past capacity:** adding 10 PLAY rows grows the data block by 1,120 bytes; every later directory offset, `dbSize`, both header CRCs, the whole `priorCrc` chain and the EOF CRC are recomputed, and the result still round-trips byte-for-byte.

Other commands:

```
python3 eadb.py FILE                    # header + table summary
python3 eadb.py FILE --verify           # recompute every CRC
python3 eadb.py FILE --fields PLAY      # dump a table field map
python3 eadb.py FILE --player Manziel   # find players
python3 eadb.py FILE --rebuild OUT      # parse + write a new DB
```

Python API: `TDBFile(data)`, `.tables`, `.table(name)`, `.verify()`, `.build()`, `.rebuild()`, `.find_player(first,last)`, `.team_of(tgid)`; `Table.get_int/get_str/set_int/set_str/record/field`; `Field(type, bit_offset, name, bits)`.

## 14. Uncertainties and notes

1. **Index-block CRC coverage.** `indexCount` is 0 in every table here, so the index block never exists and its CRC treatment is unverified. `eadb.py` includes it in the tail CRC; bep713's writer covers only descriptors + data.
2. **Table `headerCrc` is not recomputed by the bep713 writer.** It recomputes the file-header CRC and the `priorCrc` chain only. In the untouched file every `headerCrc` equals `stored_crc(header[4:0x24])`, so `eadb.py` recomputes it. The game may or may not validate it.
3. **Non-ASCII names.** All 8,631 names are 7-bit ASCII, so Latin-1 vs UTF-8 is untestable here. EA's other tools treat these as raw bytes; Latin-1 is the safest assumption.
4. **Allocation types 34/66 and field types 1/13/14** do not occur in this file. Their behavior is taken from the reference parser, not re-derived here.
5. **Padding length is container-dependent.** `dbSize` is authoritative. This decrypted copy is 1,433,600 bytes; the roster save itself may be exactly 1,320,160 bytes.
6. **TEAM impact-player fields on FCS/HS rows** contain ids that do not exist in PLAY (those teams have no player rows). `TSI2` is `0xFFFF` on every row. Only the 126 FBS teams have valid impact-player links.
7. **`lengthBits`** is always `8*lengthBytes - 1` in this file. It appears to be a derived mask/limit, not an independent field; keep the relation if you edit stride.
8. **`dataAllocType` 2 vs 6.** Both are treated as fixed-size by the reference parser. INJY and TUNI use 2 with `maxRecords=0`, so the distinction is not observable beyond "no rows".
9. **XML is community metadata.** Names/control items are useful but are not part of the binary format and may be wrong or incomplete (39 blank types). The binary descriptors are authoritative.

---

## Appendix A - PLAY field map (sorted by bit offset)

Descriptor order on disk is arbitrary; this is a record map. `byte@` is `bit@ // 8`. Full XML names are shown where the XML defines one.

| # | abbrev | XML Name | DB type | XML type | bit@ | bits | byte@ |
|---|---|---|---|---|---|---|---|
| 0 | PGID | Player ID | 3 | uint | 0 | 16 | 0 |
| 1 | POID | Org. Player ID | 3 | uint | 16 | 16 | 2 |
| 2 | PFNA | First Name | 0 | string | 32 | 88 | 4 |
| 3 | PLNA | Last Name | 0 | string | 120 | 104 | 15 |
| 4 | PWGT | Weight | 3 | uint | 224 | 8 | 28 |
| 5 | BSAA | Arm Def | 3 | uint | 232 | 4 | 29 |
| 6 | BSBA | Butt Def | 3 | uint | 236 | 4 | 29 |
| 7 | BSCA | Calf Def | 3 | uint | 240 | 4 | 30 |
| 8 | PYEA | Year | 3 | uint | 244 | 3 | 30 |
| 9 | BSFA | Foot Def | 3 | uint | 247 | 4 | 30 |
| 10 | BSGA | Gut Def | 3 | uint | 251 | 4 | 31 |
| 11 | PLHA | Left Hand | 3 | uint | 255 | 5 | 31 |
| 12 | PRHA | Right Hand | 3 | uint | 260 | 5 | 32 |
| 13 | PTHA | Throwing Accuracy | 3 | uint | 265 | 7 | 33 |
| 14 | BSPA | Pad Def | 3 | uint | 272 | 4 | 34 |
| 15 | BSSA | Chest Def | 3 | uint | 276 | 5 | 34 |
| 16 | BSTA | Thigh Def | 3 | uint | 281 | 4 | 35 |
| 17 | PSTA | Stamina | 3 | uint | 285 | 7 | 35 |
| 18 | BSWA | Waist Def | 3 | uint | 292 | 4 | 36 |
| 19 | PLBB | Left Bicep | 3 | uint | 296 | 2 | 37 |
| 20 | PRBB | Right Bicep | 3 | uint | 298 | 2 | 37 |
| 21 | PLCB | Left Calf | 3 | uint | 300 | 2 | 37 |
| 22 | PRCB | Right Calf | 3 | uint | 302 | 2 | 37 |
| 23 | PLFB | Left Forearm | 3 | uint | 304 | 2 | 38 |
| 24 | PRFB | Right Forearm | 3 | uint | 306 | 2 | 38 |
| 25 | PKAC | Kick Accuracy | 3 | uint | 308 | 7 | 38 |
| 26 | PACC | Acceleration | 3 | uint | 315 | 7 | 39 |
| 27 | PMPC | Mouthpiece | 3 | uint | 322 | 3 | 40 |
| 28 | PPRC | Play Recognition | 3 | uint | 325 | 7 | 40 |
| 29 | RCHD | Hometown Desc | 3 | uint | 332 | 14 | 41 |
| 30 | TGID | Team ID | 3 | uint | 346 | 10 | 43 |
| 31 | PUND | - | 3 | uint | 356 | 2 | 44 |
| 32 | PHPD | - | 3 | uint | 358 | 1 | 44 |
| 33 | PSPD | Speed | 3 | uint | 359 | 7 | 44 |
| 34 | PRSD | Redshirt | 3 | uint | 366 | 2 | 45 |
| 35 | PGHE | Face | 3 | uint | 368 | 9 | 46 |
| 36 | PUHE | Head | 3 | uint | 377 | 10 | 47 |
| 37 | PPOE | - | 3 | uint | 387 | 7 | 48 |
| 38 | PBRE | Nasal Strip | 3 | uint | 394 | 3 | 49 |
| 39 | PEYE | Eye Paint | 3 | uint | 397 | 1 | 49 |
| 40 | TRAF | Catch In Traffic | 3 | uint | 398 | 7 | 49 |
| 41 | PPBF | Pass Blocking Footwrk | 3 | uint | 405 | 7 | 50 |
| 42 | PBSH | Block Shedding | 3 | uint | 412 | 7 | 51 |
| 43 | PLSH | Left Shoe | 3 | uint | 419 | 4 | 52 |
| 44 | PRSH | Right Shoe | 3 | uint | 423 | 4 | 52 |
| 45 | PCTH | Catch | 3 | uint | 427 | 7 | 53 |
| 46 | PLTH | Left Thigh | 3 | uint | 434 | 2 | 54 |
| 47 | PRTH | Right Thigh | 3 | uint | 436 | 2 | 54 |
| 48 | PAGI | Agility | 3 | uint | 438 | 7 | 54 |
| 49 | PPRI | - | 3 | uint | 445 | 6 | 55 |
| 50 | PINJ | Injury | 3 | uint | 451 | 7 | 56 |
| 51 | PBAK | Back Plate | 3 | uint | 458 | 1 | 57 |
| 52 | PTAK | Tackling | 3 | uint | 459 | 7 | 57 |
| 53 | PPBK | Pass Blocking | 3 | uint | 466 | 7 | 58 |
| 54 | PRBK | Run Blocking | 3 | uint | 473 | 7 | 59 |
| 55 | PNEK | Neckpad | 3 | uint | 480 | 4 | 60 |
| 56 | PFLK | Flack Jacket | 3 | uint | 484 | 1 | 60 |
| 57 | PFMK | Facemask | 3 | uint | 485 | 6 | 60 |
| 58 | PTRK | Trucking | 3 | uint | 491 | 7 | 61 |
| 59 | PBTK | Break Tackle | 3 | uint | 498 | 7 | 62 |
| 60 | PTAL | Left Tattoo | 3 | uint | 505 | 4 | 63 |
| 61 | PIBL | Impact Blocking | 3 | uint | 509 | 7 | 63 |
| 62 | PHCL | Hair Color | 3 | - | 516 | 3 | 64 |
| 63 | PLEL | Left Elbow | 3 | uint | 519 | 5 | 64 |
| 64 | PREL | Right Elbow | 3 | uint | 524 | 5 | 65 |
| 65 | PLKL | Left Knee Brace | 3 | uint | 529 | 1 | 66 |
| 66 | PSPL | Left Ankle | 3 | uint | 530 | 3 | 66 |
| 67 | PLSL | Left Sleeve | 3 | uint | 533 | 4 | 66 |
| 68 | PHLM | Helmet | 3 | uint | 537 | 3 | 67 |
| 69 | PSTM | - | 3 | uint | 540 | 7 | 67 |
| 70 | PHAN | Prefferred Hand | 3 | uint | 547 | 1 | 68 |
| 71 | PJEN | Jersey # | 3 | uint | 548 | 7 | 68 |
| 72 | PTEN | Tendency | 3 | uint | 555 | 5 | 69 |
| 73 | PLHN | - | 3 | uint | 560 | 3 | 70 |
| 74 | PRHN | - | 3 | uint | 563 | 3 | 70 |
| 75 | PLKN | Left Knee | 3 | uint | 566 | 3 | 70 |
| 76 | PRKN | Right Knee | 3 | uint | 569 | 3 | 71 |
| 77 | PLSO | Sock Length | 3 | uint | 572 | 3 | 71 |
| 78 | PTHP | Throwing Power | 3 | uint | 575 | 7 | 71 |
| 79 | PIMP | Importance | 3 | uint | 582 | 7 | 72 |
| 80 | PJMP | Jump | 3 | uint | 589 | 7 | 73 |
| 81 | PTYP | Type | 3 | uint | 596 | 2 | 74 |
| 82 | PCAR | Carry | 3 | uint | 598 | 7 | 74 |
| 83 | PSAR | Stiff Arm | 3 | uint | 605 | 7 | 75 |
| 84 | PTAR | Right Tattoo | 3 | uint | 612 | 4 | 76 |
| 85 | PLCR | - | 3 | uint | 616 | 1 | 77 |
| 86 | PJER | Jersey Sleeves | 3 | uint | 617 | 2 | 77 |
| 87 | PLKR | Right Knee Brace | 3 | uint | 619 | 1 | 77 |
| 88 | PKPR | Kick Power | 3 | uint | 620 | 7 | 77 |
| 89 | PSPR | Right Ankle | 3 | uint | 627 | 3 | 78 |
| 90 | PLSR | Right Sleeve | 3 | uint | 630 | 4 | 78 |
| 91 | PRTR | Route Running | 3 | uint | 634 | 7 | 79 |
| 92 | PSTR | Strength | 3 | uint | 641 | 7 | 80 |
| 93 | POVR | Overall | 3 | uint | 648 | 7 | 81 |
| 94 | PAWR | Awareness | 3 | uint | 655 | 7 | 81 |
| 95 | PLWR | Left Wrist | 3 | uint | 662 | 5 | 82 |
| 96 | PRWR | Right Wrist | 3 | uint | 667 | 5 | 83 |
| 97 | PPBS | Pass Blocking Str | 3 | uint | 672 | 7 | 84 |
| 98 | PRBS | Run Blocking Str | 3 | uint | 679 | 7 | 84 |
| 99 | PDIS | Discipline | 3 | uint | 686 | 3 | 85 |
| 100 | PVIS | Visor | 3 | uint | 689 | 3 | 86 |
| 101 | RELS | Release | 3 | uint | 692 | 7 | 86 |
| 102 | PRNS | - | 3 | uint | 699 | 7 | 87 |
| 103 | PPOS | Position | 3 | uint | 706 | 5 | 88 |
| 104 | PPRS | Pursuit | 3 | uint | 711 | 7 | 88 |
| 105 | PYRS | Press | 3 | uint | 718 | 7 | 89 |
| 106 | BSAT | Arm Size | 3 | uint | 725 | 5 | 90 |
| 107 | BSBT | Butt Size | 3 | uint | 730 | 5 | 91 |
| 108 | SPCT | Spec Catch | 3 | uint | 735 | 7 | 91 |
| 109 | BSCT | Calf Size | 3 | uint | 742 | 5 | 92 |
| 110 | BSFT | Foot Size | 3 | uint | 747 | 5 | 93 |
| 111 | PHGT | Height | 3 | uint | 752 | 7 | 94 |
| 112 | BSGT | Gut Size | 3 | uint | 759 | 5 | 94 |
| 113 | PHIT | Hit Power | 3 | uint | 764 | 7 | 95 |
| 114 | BSPT | Pad Size | 3 | uint | 771 | 5 | 96 |
| 115 | PKRT | Kick Return | 3 | uint | 776 | 7 | 97 |
| 116 | BSST | Chest Size | 3 | uint | 783 | 5 | 97 |
| 117 | BSTT | Thigh Size | 3 | uint | 788 | 5 | 98 |
| 118 | BSWT | Waist Size | 3 | uint | 793 | 5 | 99 |
| 119 | PBCV | Ball Carrier Vision | 3 | uint | 798 | 7 | 99 |
| 120 | PMCV | Man Coverage | 3 | uint | 805 | 7 | 100 |
| 121 | PZCV | Zone Coverage | 3 | uint | 812 | 7 | 101 |
| 122 | PFMV | Finesse Moves | 3 | uint | 819 | 7 | 102 |
| 123 | PJMV | Juke Move | 3 | uint | 826 | 7 | 103 |
| 124 | PPMV | Power Moves | 3 | uint | 833 | 7 | 104 |
| 125 | PSMV | Spin Move | 3 | uint | 840 | 7 | 105 |
| 126 | PESV | Elusiveness | 3 | uint | 847 | 7 | 105 |
| 127 | PBFW | Run Blocking Footwrk | 3 | uint | 854 | 7 | 106 |
| 128 | PLHW | Hand Warmer | 3 | uint | 861 | 2 | 107 |
| 129 | PLTW | Towel | 3 | uint | 863 | 1 | 107 |
| 130 | PLSY | - | 3 | uint | 864 | 3 | 108 |
| 131 | PSTY | Throwing Style | 3 | - | 867 | 2 | 108 |
| 132 | sgmp | Games Played | 3 | - | 869 | 5 | 108 |

## Appendix B - TEAM field map (sorted by bit offset)

| # | abbrev | XML Name | DB type | XML type | bit@ | bits | byte@ |
|---|---|---|---|---|---|---|---|
| 0 | NCID | - | 3 | uint | 0 | 32 | 0 |
| 1 | TSI1 | Impact Player 1 | 3 | uint | 32 | 16 | 4 |
| 2 | TSI2 | Impact Player 2 | 3 | uint | 48 | 16 | 6 |
| 3 | TRPA | - | 3 | uint | 64 | 16 | 8 |
| 4 | TFFB | - | 3 | uint | 80 | 16 | 10 |
| 5 | TFOB | - | 3 | uint | 96 | 16 | 12 |
| 6 | LGID | League ID | 3 | uint | 112 | 16 | 14 |
| 7 | TFRD | - | 3 | uint | 128 | 16 | 16 |
| 8 | TFFG | - | 3 | uint | 144 | 16 | 18 |
| 9 | TFOG | - | 3 | uint | 160 | 16 | 20 |
| 10 | TMPI | Impact Player 3 | 3 | uint | 176 | 16 | 22 |
| 11 | TPIO | Impact Player 4 | 3 | uint | 192 | 16 | 24 |
| 12 | DCAP | - | 3 | uint | 208 | 16 | 26 |
| 13 | OCAP | - | 3 | uint | 224 | 16 | 28 |
| 14 | TMCP | - | 3 | uint | 240 | 16 | 30 |
| 15 | TRCP | - | 3 | uint | 256 | 16 | 32 |
| 16 | TFOR | - | 3 | uint | 272 | 16 | 34 |
| 17 | TTVS | - | 3 | uint | 288 | 16 | 36 |
| 18 | TCPT | Coach's Poll Points | 3 | uint | 304 | 16 | 38 |
| 19 | tmpp | Media Poll Points | 3 | uint | 320 | 16 | 40 |
| 20 | TDNA | Team Name | 0 | string | 336 | 176 | 42 |
| 21 | TLNA | Team Long Name | 0 | string | 512 | 136 | 64 |
| 22 | TMNA | Team Mascot Name | 0 | string | 648 | 144 | 81 |
| 23 | TSNA | Team Short Name | 0 | string | 792 | 56 | 99 |
| 24 | TB2B | - | 3 | uint | 848 | 8 | 106 |
| 25 | TBCB | - | 3 | uint | 856 | 8 | 107 |
| 26 | TRDB | Team Rating DB | 3 | uint | 864 | 8 | 108 |
| 27 | TRLB | Team Rating LB | 3 | uint | 872 | 8 | 109 |
| 28 | TDPB | Def Playbook | 3 | uint | 880 | 8 | 110 |
| 29 | TOPB | Off Playbook | 3 | uint | 888 | 8 | 111 |
| 30 | TRQB | Team Rating QB | 3 | uint | 896 | 8 | 112 |
| 31 | TRRB | Team Rating RB | 3 | uint | 904 | 8 | 113 |
| 32 | TMCC | Team Culture Point | 0 | string | 912 | 184 | 114 |
| 33 | TMNC | Nickname | 0 | string | 1096 | 136 | 137 |
| 34 | MSID | - | 3 | uint | 1232 | 8 | 154 |
| 35 | TRDE | Team Rating DE | 3 | uint | 1240 | 8 | 155 |
| 36 | TROF | Team Rating Off | 3 | uint | 1248 | 8 | 156 |
| 37 | TB2G | - | 3 | uint | 1256 | 8 | 157 |
| 38 | TBCG | - | 3 | uint | 1264 | 8 | 158 |
| 39 | TCRK | Coach's Poll Rank | 3 | uint | 1272 | 8 | 159 |
| 40 | TMRK | Media Poll Rank | 3 | uint | 1280 | 8 | 160 |
| 41 | TRDL | Team Rating DL | 3 | uint | 1288 | 8 | 161 |
| 42 | TROL | Team Rating OL | 3 | uint | 1296 | 8 | 162 |
| 43 | INPO | - | 3 | uint | 1304 | 8 | 163 |
| 44 | NCDP | - | 3 | uint | 1312 | 8 | 164 |
| 45 | TB2R | - | 3 | uint | 1320 | 8 | 165 |
| 46 | TBCR | - | 3 | uint | 1328 | 8 | 166 |
| 47 | TTFR | - | 3 | uint | 1336 | 8 | 167 |
| 48 | TDPR | Def Pass Rating | 3 | uint | 1344 | 8 | 168 |
| 49 | TOPR | - | 3 | uint | 1352 | 8 | 169 |
| 50 | TDRR | Def Run Rating | 3 | uint | 1360 | 8 | 170 |
| 51 | TORR | - | 3 | uint | 1368 | 8 | 171 |
| 52 | TWRR | - | 3 | uint | 1376 | 8 | 172 |
| 53 | CSAT | College Stadium | 0 | string | 1384 | 56 | 173 |
| 54 | TGPT | - | 3 | uint | 1440 | 8 | 180 |
| 55 | TRST | Team Rating Special Teams | 3 | uint | 1448 | 8 | 181 |
| 56 | TROV | Team Rating Overall | 3 | uint | 1456 | 8 | 182 |
| 57 | TEZ1 | Team Endzone 1 | 3 | uint | 1464 | 10 | 183 |
| 58 | TEZ2 | Team Endzone 2 | 3 | uint | 1474 | 10 | 184 |
| 59 | TMAA | Team Avg Attendence | 3 | uint | 1484 | 17 | 185 |
| 60 | TMIA | - | 3 | uint | 1501 | 7 | 187 |
| 61 | TLSA | - | 3 | uint | 1508 | 9 | 188 |
| 62 | UDBC | - | 3 | uint | 1517 | 1 | 189 |
| 63 | TEBC | - | 3 | uint | 1518 | 3 | 189 |
| 64 | TSCC | - | 3 | uint | 1521 | 14 | 190 |
| 65 | THMC | - | 3 | uint | 1535 | 1 | 191 |
| 66 | NUMC | Conf. Champs | 3 | uint | 1536 | 10 | 192 |
| 67 | TCID | - | 3 | uint | 1546 | 9 | 193 |
| 68 | CGID | Conference ID | 3 | uint | 1555 | 5 | 194 |
| 69 | DGID | Division ID | 3 | uint | 1560 | 5 | 195 |
| 70 | SGID | Stadium ID | 3 | uint | 1565 | 10 | 195 |
| 71 | TGID | Team ID | 3 | uint | 1575 | 10 | 196 |
| 72 | TOID | Org Team ID | 3 | uint | 1585 | 10 | 198 |
| 73 | TSID | - | 3 | uint | 1595 | 10 | 199 |
| 74 | TORD | Team Roster Order | 3 | uint | 1605 | 10 | 200 |
| 75 | TCHE | - | 3 | uint | 1615 | 1 | 201 |
| 76 | TCRE | - | 3 | uint | 1616 | 1 | 202 |
| 77 | TCTI | All Time Ties | 3 | uint | 1617 | 10 | 202 |
| 78 | TCWI | All Time Wins | 3 | uint | 1627 | 10 | 203 |
| 79 | CRCL | - | 3 | uint | 1637 | 10 | 204 |
| 80 | TMFL | - | 3 | uint | 1647 | 10 | 205 |
| 81 | TLGL | Team Logo | 3 | uint | 1657 | 9 | 207 |
| 82 | TCHL | - | 3 | uint | 1666 | 10 | 208 |
| 83 | CBOL | Bowl Losses | 3 | uint | 1676 | 10 | 209 |
| 84 | TPSL | Team Prior Season Losses | 3 | uint | 1686 | 6 | 210 |
| 85 | TFTL | - | 3 | uint | 1692 | 7 | 211 |
| 86 | TNTL | - | 3 | uint | 1699 | 6 | 212 |
| 87 | TRTL | - | 3 | uint | 1705 | 6 | 213 |
| 88 | GOWL | - | 3 | uint | 1711 | 6 | 213 |
| 89 | TCAM | - | 3 | uint | 1717 | 9 | 214 |
| 90 | DISN | Division Place | 3 | uint | 1726 | 3 | 215 |
| 91 | NCYN | Nat'l Champs | 3 | uint | 1729 | 10 | 216 |
| 92 | TSHO | - | 3 | uint | 1739 | 1 | 217 |
| 93 | TUHO | - | 3 | uint | 1740 | 4 | 217 |
| 94 | TCLO | All Time Losses | 3 | uint | 1744 | 10 | 218 |
| 95 | TFLO | - | 3 | uint | 1754 | 1 | 219 |
| 96 | ATTO | - | 3 | uint | 1755 | 10 | 219 |
| 97 | TAUO | - | 3 | uint | 1765 | 5 | 220 |
| 98 | TCFP | Coach's Poll 1st Votes | 3 | uint | 1770 | 7 | 221 |
| 99 | TCRP | - | 3 | uint | 1777 | 9 | 222 |
| 100 | TGRP | - | 3 | uint | 1786 | 10 | 223 |
| 101 | TTYP | Team Type | 3 | uint | 1796 | 5 | 224 |
| 102 | TMAR | Team Academic Rating | 3 | uint | 1801 | 4 | 225 |
| 103 | ATTR | Attendence Record | 3 | uint | 1805 | 17 | 225 |
| 104 | SDUR | Sanction Duration | 3 | uint | 1822 | 3 | 227 |
| 105 | FCYR | - | 3 | uint | 1825 | 10 | 228 |
| 106 | NCYR | - | 3 | uint | 1835 | 10 | 229 |
| 107 | TLGS | Roster Helmet | 3 | uint | 1845 | 9 | 230 |
| 108 | TCHS | - | 2 | sint | 1854 | 10 | 231 |
| 109 | TVIS | - | 3 | uint | 1864 | 1 | 233 |
| 110 | THPS | Has Pride Stickers | 3 | - | 1865 | 1 | 233 |
| 111 | TVQS | - | 3 | uint | 1866 | 1 | 233 |
| 112 | TPRS | Team Pride Sticker | 3 | uint | 1867 | 7 | 233 |
| 113 | DSUS | - | 3 | uint | 1874 | 2 | 234 |
| 114 | SNCT | NCAA Sanction | 3 | uint | 1876 | 3 | 234 |
| 115 | CRCT | - | 3 | uint | 1879 | 10 | 234 |
| 116 | TCHT | - | 3 | uint | 1889 | 10 | 236 |
| 117 | CBOT | Bowl Ties | 3 | uint | 1899 | 10 | 237 |
| 118 | TDPT | - | 3 | uint | 1909 | 13 | 238 |
| 119 | TPST | Team Prior Season Ties | 3 | uint | 1922 | 6 | 240 |
| 120 | PSAV | - | 3 | uint | 1928 | 4 | 241 |
| 121 | PTDV | Tradition | 3 | uint | 1932 | 4 | 241 |
| 122 | PAFV | Faciliteis | 3 | uint | 1936 | 4 | 242 |
| 123 | PPFV | Pro Potential | 3 | uint | 1940 | 4 | 242 |
| 124 | PCHV | Championships | 3 | uint | 1944 | 4 | 243 |
| 125 | TRIV | Team Rival ID | 3 | uint | 1948 | 10 | 243 |
| 126 | PCLV | Coach Loyalty | 3 | uint | 1958 | 4 | 244 |
| 127 | TENV | - | 3 | uint | 1962 | 2 | 245 |
| 128 | PAPV | Academics | 3 | uint | 1964 | 4 | 245 |
| 129 | PCPV | Coach Prestige | 3 | uint | 1968 | 4 | 246 |
| 130 | TMPV | Media 1st Place Votes | 3 | uint | 1972 | 7 | 246 |
| 131 | PPSV | Program Stabilty | 3 | uint | 1979 | 4 | 247 |
| 132 | PTVV | TV Exposure | 3 | uint | 1983 | 4 | 247 |
| 133 | TUAW | - | 3 | uint | 1987 | 4 | 248 |
| 134 | CRCW | - | 3 | uint | 1991 | 10 | 248 |
| 135 | TCHW | - | 3 | uint | 2001 | 10 | 250 |
| 136 | CBOW | Bowl Wins | 3 | uint | 2011 | 10 | 251 |
| 137 | TSOW | - | 3 | uint | 2021 | 1 | 252 |
| 138 | TPSW | Team Prior Season Wins | 3 | uint | 2022 | 6 | 252 |
| 139 | TNTW | Nat'l TV Wins | 3 | uint | 2028 | 6 | 253 |
| 140 | TRTW | - | 3 | uint | 2034 | 6 | 254 |
| 141 | GOWW | - | 3 | uint | 2040 | 6 | 255 |
| 142 | TPRX | Team Prestige | 3 | uint | 2046 | 3 | 255 |
| 143 | ATTY | - | 3 | uint | 2049 | 10 | 256 |
| 144 | TAth | - | 3 | uint | 2059 | 1 | 257 |
| 145 | TAss | - | 3 | uint | 2060 | 1 | 257 |

## Appendix C - other table field maps (compact)

Format: `abbrev type bit@ bits byte@  XML name`. Sorted by bit offset.

```
CSKL = Coach Skills  stride=28B max=409 used=378 fields=42
abbrev type bit@ bits byte@  XML name
CCID      3     0   16     0  Coach ID
CSGA      3    16    4     2  Road Warrior (GM)
CSGB      3    20    4     2  Light A Fire (GM)
CSRB      3    24    4     3  Locksmith (RC)
CSRC      3    28    4     3  Insta-Commit (RC)
CSHD      3    32    4     4  Raw Talent (DC)
CSRI      3    36    4     4  Scouting (RC)
CSGK      3    40    4     5  Antifreeze (GM)
CLVL      3    44    7     5  Coach Level
NLVL      3    51    1     6  
CSRM      3    52    4     6  Pipelines (RC)
CSHO      3    56    4     7  Athlete (OC)
CSRO      3    60    4     7  The Opener (RC)
CSGP      3    64    4     8  Pure Instinct (DC)
CEXP      3    68   22     8  Coach Experience
PABR      3    90    4    11  Great Wall (OC)
RUBR      3    94    4    11  Bulldozer (OC)
TACR      3    98    4    12  Tackling (DC)
MNCR      3   102    4    12  Shutdown (DC)
ZNCR      3   106    4    13  No Fly Zone (DC)
TODR      3   110    4    13  Recharge (DC)
BSER      3   114    4    14  Ball Sercurity (OC)
BIGR      3   118    4    14  Big Game (GM)
STHR      3   122    4    15  Kitchen Sink(RC)
TAKR      3   126    4    15  Ball Burglar (DC)
RUNR      3   130    4    16  Daylight (OC)
TOOR      3   134    4    16  Up Tempo (OC)
PLPR      3   138    4    17  Coachstradamus (GM)
PARR      3   142    4    17  Charge (DC)
SARR      3   146    4    18  Setup Artist (GM)
PFRR      3   150    4    18  Clean Laundry (GM)
CSRR      3   154    4    19  The Closer (RC)
AWRR      3   158    4    19  Mathlete (OC)
PASR      3   162    4    20  Cannon (OC)
CATR      3   166    4    20  Air Traffic Control (OC)
RSTR      3   170    4    21  Road Closed (DC)
CLUR      3   174    4    21  Clutch (GM)
BLCS      3   178    4    22  
CSRS      3   182    4    22  Letter of Intent (RC)
CSGU      3   186    4    23  Matchup (GM)
CSKU      3   190    7    23  Upgrades Available
CSRV      3   197    4    24  Royal Treatment (RC)
```

```
COCH = Coaches  stride=128B max=409 used=403 fields=108
abbrev type bit@ bits byte@  XML name
CCID      3     0   16     0  Coach ID
CLTF      3    16   16     2  Coach Last Team
CCWI      3    32   16     4  Career Wins
COTL      3    48   16     6  Team Losses
CTTL      3    64   16     8  Top 25 Losses
CRVL      3    80   16    10  Rival Losses
CTWN      3    96   16    12  Team Wins
CCLO      3   112   16    14  Career Losses
CCLS      3   128   16    16  Losing Seasons
CCWS      3   144   16    18  Winning Seasons
CTTW      3   160   16    20  Top 25 Wins
CRVW      3   176   16    22  Rival Wins
CLNA      0   192  128    24  Coach Pos Name
CDTA      3   320    8    40  Def Playcalling Agr
COTA      3   328    8    41  Off Playcalling Agr
PCTL      3   336    8    42  
CFNM      0   344  128    43  Coach's First Name
CLNM      0   472  128    59  Coach's Last Name
COIN      3   600    8    75  
CDTR      3   608    8    76  Sim Def Run/Pass Ratio
COTR      3   616    8    77  Sim Off Run/Pass Ratio
CDTS      3   624    8    78  CPU Def Sub Rate
COTS      3   632    8    79  CPU Off Sub Rate
CHGT      3   640    8    80  Head
PCTW      3   648    8    81  
COTY      3   656    8    82  Coach Off Strategy
CBSZ      3   664    8    83  
CThg      2   672    8    84  Apparel
CNAA      3   680   12    85  All Americans
CFFA      3   692    1    86  Sign New Players
CYRA      3   693    7    86  Coach Of The Year
CFLB      3   700    1    87  
CSPC      3   701    2    87  Coach Specialty
CARC      3   703   14    87  Avg Recruiting Ranking
CFRC      3   717    1    89  
CFSC      3   718    1    89  
CCTC      3   719    5    89  
CNTC      3   724    7    90  Top 25 Classes
CFUC      3   731    1    91  User Controlled
CYCD      3   732    7    91  Years Coaching
CDID      3   739    9    92  Def Playbook
TGID      3   748   10    93  Team ID
TOID      3   758   10    94  Org Team ID
CPID      3   768    9    96  Playbook
PPID      3   777    2    97  
PTID      3   779   10    97  Prior Team
CAGE      3   789    7    98  Age
CFRE      3   796    3    99  
CCBI      3   799    2    99  CB Imp
CFBI      3   801    2   100  FB/TE Imp
CHBI      3   803    2   100  HB Imp
CLBI      3   805    2   100  LB Imp
CQBI      3   807    2   100  QB Imp
CSFI      3   809    2   101  S Imp
CSKI      3   811    3   101  Skin Color
COLI      3   814    2   101  OL Imp
CWRI      3   816    2   102  WR Imp
CCTI      3   818   10   102  Career Ties
CDTI      3   828    2   103  DT Imp
COPK      3   830   10   103  
ROFL      3   840    1   105  
CFHL      3   841    1   105  
CBLL      3   842    7   105  Coach Bowl Losses
CWPL      3   849    1   106  
CDEM      3   850    2   106  
COPM      3   852   10   106  
CCLN      3   862    3   107  Contract Length
PCLN      3   865    3   108  
CRRP      3   868    1   108  
COSP      3   869    3   108  
CSXP      3   872   13   109  Portrait
CHAR      3   885    3   110  Hair
CFFR      3   888    1   111  Fill Rosters
CFRR      3   889    1   111  Manage Depth Chart
CCYR      3   890    4   111  Years Into Contract
CTYR      3   894    7   111  Years With Team
CSAS      3   901    1   112  
TNHS      3   902    2   112  No Huddle Style
CLPS      3   904    1   113  
COPS      3   905    2   113  Coach Position
CEQS      3   907    3   113  
RCTS      3   910    2   113  
CEXS      3   912    3   114  
CRAT      3   915    7   114  Coach Rating
CFBT      3   922    2   115  FB/TE Ten
CHBT      3   924    2   115  HB Ten
CLBT      3   926    2   115  LB Ten
CQBT      3   928    2   116  QB Ten
CRBT      3   930    7   116  Run Strat
CDET      3   937    2   117  DE Ten
CHFT      3   939   10   117  Alma Mater
CSFT      3   949    2   118  S Ten
COHT      3   951    3   118  
COLT      3   954    2   119  OL Ten
CWRT      3   956    2   119  WR Ten
CDST      3   958    4   119  Coach Def ST
COST      3   962    4   120  Coach Off ST
CDTT      3   966    2   120  DT Ten
PHPV      3   968    4   121  Home Proximity
CNAW      3   972   10   121  Player Awards
CBLW      3   982    7   122  Coach Bowl Wins
CCTW      3   989    7   123  Conference Championships
CHTW      3   996    7   124  Heisman Winners
CNTW      3  1003    7   125  National Championships
CCBX      3  1010    2   126  CB Ten
CDTY      3  1012    7   126  Coach Def Strategy
CHTY      3  1019    2   127  Hat Type
CTgw      3  1021    1   127  Glasses
```

```
CONF = Conference  stride=28B max=26 used=25 fields=5
abbrev type bit@ bits byte@  XML name
LGID      3     0   16     0  League ID
NCcl      3    16   16     2  
CNAM      0    32  160     4  Conference Name
CGID      3   192    5    24  Conference ID
CNPR      3   197    1    24  
```

```
DCHT = Depth Chart  stride=8B max=11464 used=11068 fields=4
abbrev type bit@ bits byte@  XML name
PGID      3     0   16     0  Player ID
TGID      3    16   10     2  Team ID
PPOS      3    26    5     3  Position
ddep      3    31    6     3  Depth
```

```
DIVI = Divisions  stride=44B max=22 used=22 fields=4
abbrev type bit@ bits byte@  XML name
DNAM      0     0  160     0  Division Name
SDNM      0   160  160    20  Sub Division Name
CGID      3   320    5    40  Conference ID
DGID      3   325    5    40  Division ID
```

```
INJY = Injury  stride=8B max=0 used=0 fields=6
abbrev type bit@ bits byte@  XML name
PGID      3     0   16     0  Player ID
INJL      3    16    8     2  Injury Length
INJT      3    24    8     3  Injury Type
TGID      3    32   10     4  Team ID
INIR      3    42    1     5  Injury Reserved
INJR      3    43    1     5  
```

```
STAD = Stadiums  stride=464B max=200 used=197 fields=117
abbrev type bit@ bits byte@  XML name
SLON      4     0   32     0  
SLAT      4    32   32     4  
STRT      4    64   32     8  
SCUE      3    96   16    12  Upper Endzone
SCLL      3   112   16    14  Lower Level
SCML      3   128   16    16  Mid Level
SCUL      3   144   16    18  Upper Level
SRES      3   160   16    20  
STfc      3   176   16    22  
STlc      3   192   16    24  
Stlc      3   208   16    26  
STrf      3   224   16    28  
STri      3   240   16    30  
STcl      3   256   16    32  
STll      3   272   16    34  
STrl      3   288   16    36  
STRr      3   304   16    38  
stcr      3   320   16    40  
STlr      3   336   16    42  
STrr      3   352   16    44  
STS1      0   368  512    46  
STS2      0   880  512   110  
STAA      0  1392  256   174  
TDNA      0  1648  176   206  Team Name
TMNA      0  1824  144   228  Team Mascot Name
EZTA      0  1968  128   246  
EZTB      0  2096  128   262  
WCLC      0  2224  120   278  
EZTC      3  2344   24   293  
FLID      0  2368  256   296  
SORD      3  2624    8   328  
STOF      2  2632    8   329  
EZBG      3  2640   24   330  
SNAM      0  2664  320   333  Stadium Name
STNN      0  2984  152   373  Stadium Nickname
SCAP      3  3136   24   392  Seating Capacity
SFSP      3  3160    8   395  
STDR      2  3168    8   396  
STHS      3  3176    8   397  
STAT      3  3184    8   398  State
SFFT      3  3192    8   399  
SCIT      0  3200  168   400  Stadium City
EZTT      3  3368   24   421  
STwp      2  3392    8   424  
STts      2  3400    8   425  
STjt      2  3408    8   426  
STfw      2  3416    8   427  
SP00      3  3424    3   428  North Endzone 1st Deck
SP10      3  3427    3   428  East Sideline 1st Deck
SP20      3  3430    5   428  Info Sideline Pattern
SP01      3  3435    3   429  North Endzone 2nd Deck
SP11      3  3438    3   429  East Sideline 2nd Deck
SP21      3  3441    3   430  Grass Type
SP02      3  3444    3   430  North Endzone 3rd Deck
SP12      3  3447    3   430  East Sideline 3rd Deck
SP22      3  3450    4   431  
SP03      3  3454    3   431  1st Deck Northwest Corner
SP13      3  3457    3   432  West Sideline 1st Deck
SP23      3  3460    4   432  
SP04      3  3464    3   433  1st Deck Northeast Corner
SP14      3  3467    3   433  West Sideline 2nd Deck
SP24      3  3470    3   433  Endzone Background
SP05      3  3473    3   434  South Endzone 1st Deck
SP15      3  3476    3   434  West Sideline 3rd Deck
SP25      3  3479    4   434  Background
SP06      3  3483    3   435  South Endzone 2nd Deck
SP16      3  3486    3   435  Roof Lights
SP07      3  3489    3   436  South Endzone 3rd Deck
SP17      3  3492    3   436  Roof
SP08      3  3495    3   436  1st Deck Southwest Corner
SP18      3  3498    3   437  
SP09      3  3501    3   437  1st Deck Southeat Corner
SP19      3  3504    5   438  Info Enzone Walls
STCA      3  3509    1   438  
STFA      3  3510    3   438  
SFBB      3  3513    1   439  
SUGB      3  3514    1   439  
SCLB      3  3515   10   439  Luxury Box
SGID      3  3525   10   440  Stadium ID
SUID      3  3535    9   441  
SCYD      3  3544    9   443  
SCRE      3  3553    1   444  
SFWE      3  3554    2   444  
MPTH      3  3556    1   444  
SORI      3  3557    2   444  
SFTI      3  3559    2   444  
SFBM      3  3561    1   445  
STFN      3  3562    5   445  
STGN      3  3567    2   445  
SYRO      3  3569    7   446  Stadium Years
SWFP      3  3576    7   447  
SWRP      3  3583    7   447  
SWSP      3  3590    7   448  
SWWP      3  3597    7   449  
STYP      3  3604    3   450  
STPR      3  3607    1   450  
SFBS      3  3608    1   451  
SCCS      3  3609   14   451  Club Seats
SMFS      2  3623    2   452  
SRAT      3  3625    7   453  
SGNT      3  3632    1   454  
SIOT      3  3633    1   454  
SGPT      3  3634    3   454  
SGRT      3  3637    3   454  
SBST      3  3640    3   455  
SFUT      3  3643    1   455  
SMLX      3  3644    9   455  
SMLY      3  3653    9   456  
STRY      3  3662    2   457  
SFTY      3  3664    4   458  
SKTY      3  3668    2   458  
SFbb      3  3670    3   458  
SUTf      3  3673    1   459  
STgg      3  3674    1   459  
SSft      3  3675    2   459  
STxt      3  3677    1   459  
STtv      3  3678    4   459  
```

```
TUNI = Uniforms  stride=416B max=0 used=0 fields=215
abbrev type bit@ bits byte@  XML name
CPAA      3     0   16     0  
CPBA      3    16   16     2  
CJEA      3    32   16     4  
CJFA      3    48   16     6  
CHOA      3    64   16     8  
CJOA      3    80   16    10  
CHTA      3    96   16    12  
CJTA      3   112   16    14  
UFID      3   128   16    16  Uniform ID
CPCA      3   144    8    18  
CPEA      3   152    8    19  
PRLA      3   160    8    20  
JCTA      0   168   80    21  
CPDB      3   248    8    31  
PFLB      3   256    8    32  
JCTB      0   264   80    33  
CPDC      3   344    8    43  
JCTC      0   352   80    44  
PFLD      3   432    8    54  
JCTD      0   440   80    55  
JENF      3   520    8    65  
JFNF      3   528    8    66  
JONF      3   536    8    67  
JTNF      3   544    8    68  
CPDG      3   552    8    69  
CPCN      3   560    8    70  
TUCO      3   568    8    71  Uniform Color
JEFO      3   576    8    72  
JFFO      3   584    8    73  
JOFO      3   592    8    74  
JTFO      3   600    8    75  
CPCP      3   608    8    76  
CPDQ      3   616    8    77  
PRLR      3   624    8    78  
CPDS      3   632    8    79  
CPDU      3   640    8    80  
CPDW      3   648    8    81  
CPDY      3   656    8    82  
PDAA      3   664   26    83  
CSAA      3   690    1    86  
CSBA      3   691    1    86  
JCCA      3   692   26    86  
JTCA      3   718   26    89  
JEEA      3   744   26    93  
JFEA      3   770   26    96  
JOEA      3   796   26    99  
JTEA      3   822   26   102  
JCFA      3   848    2   106  
CPFA      3   850   26   106  
CSHA      3   876    1   109  
JFLA      3   877    3   109  
PFLA      3   880   26   110  
JOLA      3   906    3   113  
POLA      3   909    3   113  
JRLA      3   912    3   114  
JTLA      3   915    3   114  
PTLA      3   918    3   114  
JEOA      3   921   26   115  
JFOA      3   947   26   118  
JOOA      3   973   26   121  
CPOA      3   999   26   124  
JTOA      3  1025   26   128  
JCSA      3  1051    2   131  
JETA      3  1053   26   131  
JFTA      3  1079   26   134  
JOTA      3  1105   26   138  
CPTA      3  1131   26   141  
JTTA      3  1157   26   144  
JCUA      3  1183    1   147  
CPAB      3  1184   26   148  
CPBB      3  1210   26   151  
JCCB      3  1236   26   154  
CPCB      3  1262   26   157  
JTCB      3  1288   26   161  
JEEB      3  1314   26   164  
JFEB      3  1340   26   167  
CJEB      3  1366   26   170  
JOEB      3  1392   26   174  
JTEB      3  1418   26   177  
JCFB      3  1444    2   180  
CJFB      3  1446   26   180  
CSHB      3  1472    1   184  
JFLB      3  1473    3   184  
JOLB      3  1476    3   184  
POLB      3  1479    3   184  
JRLB      3  1482    3   185  
PRLB      3  1485   26   185  
JTLB      3  1511    3   188  
PTLB      3  1514    3   189  
JEOB      3  1517   26   189  
JFOB      3  1543   26   192  
CHOB      3  1569   26   196  
CJOB      3  1595   26   199  
JOOB      3  1621   26   202  
JTOB      3  1647   26   205  
JCSB      3  1673    2   209  
JETB      3  1675   26   209  
JFTB      3  1701   26   212  
CHTB      3  1727   26   215  
CJTB      3  1753   26   219  
JOTB      3  1779   26   222  
JTTB      3  1805   26   225  
JCUB      3  1831    1   228  
CPAC      3  1832   26   229  
CPBC      3  1858   26   232  
JCCC      3  1884   26   235  
CPCC      3  1910   26   238  
JTCC      3  1936   26   242  
JCFC      3  1962    2   245  
JFLC      3  1964    3   245  
PFLC      3  1967   26   245  
JOLC      3  1993    3   249  
POLC      3  1996    3   249  
JRLC      3  1999    3   249  
JTLC      3  2002    3   250  
PTLC      3  2005    3   250  
HONC      3  2008   26   251  
HTNC      3  2034   26   254  
CHOC      3  2060   26   257  
JCSC      3  2086    2   260  
CHTC      3  2088   26   261  
JCUC      3  2114    1   264  
JCCD      3  2115   26   264  
JTCD      3  2141   26   267  
JCFD      3  2167    2   270  
TGID      3  2169   10   271  Team ID
JFLD      3  2179    3   272  
JOLD      3  2182    3   272  
POLD      3  2185    3   273  
JRLD      3  2188    3   273  
PRLD      3  2191   26   273  
JTLD      3  2217    3   277  
PTLD      3  2220    3   277  
JCSD      3  2223    2   277  
JCUD      3  2225    1   278  
JFLE      3  2226    3   278  
JOLE      3  2229    3   278  
JRLE      3  2232    3   279  
JTLE      3  2235    3   279  
CHOE      3  2238   26   279  
CHTE      3  2264   26   283  
JFLF      3  2290    3   286  
JOLF      3  2293    3   286  
JRLF      3  2296    3   287  
JTLF      3  2299    3   287  
CHOF      3  2302   26   287  
CHTF      3  2328   26   291  
CPCG      3  2354   26   294  
JFLG      3  2380    3   297  
JOLG      3  2383    3   297  
JRLG      3  2386    3   298  
JTLG      3  2389    3   298  
JENG      3  2392   26   299  
JFNG      3  2418   26   302  
JONG      3  2444   26   305  
JTNG      3  2470   26   308  
JFLH      3  2496    3   312  
JOLH      3  2499    3   312  
JRLH      3  2502    3   312  
JTLH      3  2505    3   313  
JFLI      3  2508    3   313  
JOLI      3  2511    3   313  
JRLI      3  2514    3   314  
JTLI      3  2517    3   314  
JFLJ      3  2520    3   315  
JOLJ      3  2523    3   315  
JRLJ      3  2526    3   315  
JTLJ      3  2529    3   316  
JFIL      3  2532    1   316  
JOIL      3  2533    1   316  
JRIL      3  2534    1   316  
JTIL      3  2535    1   316  
JZIL      3  2536    1   317  
CPDN      3  2537   26   317  
JFSN      3  2563    1   320  
JOSN      3  2564    1   320  
JRSN      3  2565    1   320  
JTSN      3  2566    1   320  
HOLO      3  2567    3   320  
HTLO      3  2570    3   321  
JFSO      3  2573    1   321  
CPDP      3  2574   26   321  
JEFP      3  2600   26   325  
JFFP      3  2626   26   328  
JOFP      3  2652   26   331  
JTFP      3  2678   26   334  
JFSP      3  2704    1   338  
CPDR      3  2705   26   338  
JFFR      3  2731   26   341  
JOFR      3  2757   26   344  
JRFR      3  2783   26   347  
JTFR      3  2809   26   351  
JFNR      3  2835   26   354  
JONR      3  2861   26   357  
JRNR      3  2887   26   360  
JTNR      3  2913   26   364  
JFIS      3  2939    1   367  
JOIS      3  2940    1   367  
JTIS      3  2941    1   367  
CPDT      3  2942   26   367  
JEFT      3  2968   26   371  
JFFT      3  2994   26   374  
JOFT      3  3020   26   377  
JTFT      3  3046   26   380  
HOLT      3  3072    3   384  
HTLT      3  3075    3   384  
JENT      3  3078   26   384  
JFNT      3  3104   26   388  
JONT      3  3130   26   391  
JTNT      3  3156   26   394  
CHOT      3  3182   26   397  
CHTT      3  3208   26   401  
CPDV      3  3234   26   404  
CPDX      3  3260   26   407  
CPDZ      3  3286   26   410  
```

## Appendix D - TEAM rows

Row order in the table, with the foreign keys. `TGID` is the value PLAY/DCHT/COCH use; `TOID == TGID` in all rows.

| row | TGID | team | CGID | DGID | SGID | TTYP | TORD |
|---|---|---|---|---|---|---|---|
| 0 | 1 | Air Force | 9 | 20 | 0 | 0 | 0 |
| 1 | 2 | Akron | 7 | 2 | 1 | 0 | 1 |
| 2 | 3 | Alabama | 11 | 5 | 2 | 0 | 2 |
| 3 | 4 | Arizona | 10 | 1 | 3 | 0 | 3 |
| 4 | 5 | Arizona State | 10 | 1 | 4 | 0 | 4 |
| 5 | 6 | Arkansas | 11 | 5 | 5 | 0 | 5 |
| 6 | 7 | Arkansas State | 13 | 30 | 6 | 0 | 6 |
| 7 | 8 | Army | 5 | 30 | 7 | 0 | 7 |
| 8 | 9 | Auburn | 11 | 5 | 8 | 0 | 8 |
| 9 | 10 | Ball State | 7 | 3 | 9 | 0 | 9 |
| 10 | 11 | Baylor | 2 | 30 | 10 | 0 | 10 |
| 11 | 12 | Boise State | 9 | 20 | 11 | 0 | 11 |
| 12 | 13 | Boston College | 0 | 6 | 12 | 0 | 12 |
| 13 | 14 | Bowling Green | 7 | 2 | 13 | 0 | 13 |
| 14 | 15 | Buffalo | 7 | 2 | 14 | 0 | 14 |
| 15 | 16 | BYU | 5 | 30 | 15 | 0 | 15 |
| 16 | 17 | California | 10 | 0 | 16 | 0 | 16 |
| 17 | 18 | UCF | 3 | 30 | 17 | 0 | 103 |
| 18 | 19 | Central Michigan | 7 | 3 | 18 | 0 | 17 |
| 19 | 20 | Cincinnati | 3 | 30 | 19 | 0 | 18 |
| 20 | 21 | Clemson | 0 | 6 | 20 | 0 | 19 |
| 21 | 22 | Colorado | 10 | 1 | 21 | 0 | 20 |
| 22 | 23 | Colorado State | 9 | 20 | 22 | 0 | 21 |
| 23 | 24 | Duke | 0 | 7 | 23 | 0 | 23 |
| 24 | 25 | ECU | 4 | 8 | 24 | 0 | 24 |
| 25 | 26 | Eastern Michigan | 7 | 3 | 25 | 0 | 25 |
| 26 | 27 | Florida | 11 | 4 | 26 | 0 | 26 |
| 27 | 28 | Florida State | 0 | 6 | 27 | 0 | 29 |
| 28 | 29 | Fresno State | 9 | 21 | 28 | 0 | 30 |
| 29 | 30 | Georgia | 11 | 4 | 29 | 0 | 31 |
| 30 | 31 | Georgia Tech | 0 | 7 | 30 | 0 | 33 |
| 31 | 32 | Hawai'i | 9 | 21 | 31 | 0 | 34 |
| 32 | 33 | Houston | 3 | 30 | 32 | 0 | 35 |
| 33 | 34 | Idaho | 5 | 30 | 33 | 0 | 36 |
| 34 | 35 | Illinois | 1 | 10 | 34 | 0 | 37 |
| 35 | 36 | Indiana | 1 | 10 | 35 | 0 | 38 |
| 36 | 37 | Iowa | 1 | 11 | 36 | 0 | 39 |
| 37 | 38 | Iowa State | 2 | 30 | 37 | 0 | 40 |
| 38 | 39 | Kansas | 2 | 30 | 38 | 0 | 41 |
| 39 | 40 | Kansas State | 2 | 30 | 39 | 0 | 42 |
| 40 | 41 | Kent State | 7 | 2 | 40 | 0 | 43 |
| 41 | 42 | Kentucky | 11 | 4 | 41 | 0 | 44 |
| 42 | 43 | Louisiana Tech | 4 | 9 | 42 | 0 | 45 |
| 43 | 44 | Louisville | 3 | 30 | 43 | 0 | 46 |
| 44 | 45 | LSU | 11 | 5 | 44 | 0 | 47 |
| 45 | 46 | Marshall | 4 | 8 | 45 | 0 | 48 |
| 46 | 47 | Maryland | 0 | 6 | 46 | 0 | 49 |
| 47 | 48 | Memphis | 3 | 30 | 47 | 0 | 50 |
| 48 | 49 | Miami | 0 | 7 | 48 | 0 | 51 |
| 49 | 50 | Miami University | 7 | 2 | 49 | 0 | 52 |
| 50 | 51 | Michigan | 1 | 11 | 50 | 0 | 53 |
| 51 | 52 | Michigan State | 1 | 11 | 51 | 0 | 54 |
| 52 | 53 | Mid Tenn State | 4 | 8 | 52 | 0 | 55 |
| 53 | 54 | Minnesota | 1 | 11 | 53 | 0 | 56 |
| 54 | 55 | Mississippi State | 11 | 5 | 54 | 0 | 57 |
| 55 | 56 | Missouri | 11 | 4 | 55 | 0 | 58 |
| 56 | 57 | Navy | 5 | 30 | 56 | 0 | 59 |
| 57 | 58 | Nebraska | 1 | 11 | 57 | 0 | 61 |
| 58 | 59 | Nevada | 9 | 21 | 58 | 0 | 62 |
| 59 | 60 | New Mexico | 9 | 20 | 59 | 0 | 63 |
| 60 | 61 | New Mexico State | 5 | 30 | 60 | 0 | 64 |
| 61 | 62 | North Carolina | 0 | 7 | 61 | 0 | 65 |
| 62 | 63 | NC State | 0 | 6 | 62 | 0 | 60 |
| 63 | 64 | North Texas | 4 | 9 | 63 | 0 | 66 |
| 64 | 65 | UL Monroe | 13 | 30 | 64 | 0 | 106 |
| 65 | 66 | Northern Illinois | 7 | 3 | 65 | 0 | 67 |
| 66 | 67 | Northwestern | 1 | 11 | 66 | 0 | 68 |
| 67 | 68 | Notre Dame | 5 | 30 | 67 | 0 | 69 |
| 68 | 69 | Ohio | 7 | 2 | 68 | 0 | 70 |
| 69 | 70 | Ohio State | 1 | 10 | 69 | 0 | 71 |
| 70 | 71 | Oklahoma | 2 | 30 | 70 | 0 | 72 |
| 71 | 72 | Oklahoma State | 2 | 30 | 71 | 0 | 73 |
| 72 | 73 | Ole Miss | 11 | 5 | 72 | 0 | 75 |
| 73 | 74 | Oregon | 10 | 0 | 73 | 0 | 76 |
| 74 | 75 | Oregon State | 10 | 0 | 74 | 0 | 77 |
| 75 | 76 | Penn State | 1 | 10 | 75 | 0 | 78 |
| 76 | 77 | Pittsburgh | 0 | 7 | 76 | 0 | 79 |
| 77 | 78 | Purdue | 1 | 10 | 77 | 0 | 80 |
| 78 | 79 | Rice | 4 | 9 | 78 | 0 | 81 |
| 79 | 80 | Rutgers | 3 | 30 | 79 | 0 | 82 |
| 80 | 81 | San Diego State | 9 | 21 | 80 | 0 | 83 |
| 81 | 82 | San Jose State | 9 | 21 | 81 | 0 | 84 |
| 82 | 83 | SMU | 3 | 30 | 82 | 0 | 85 |
| 83 | 84 | South Carolina | 11 | 4 | 83 | 0 | 87 |
| 84 | 85 | Southern Miss | 4 | 8 | 84 | 0 | 88 |
| 85 | 86 | UL Lafayette | 13 | 30 | 85 | 0 | 105 |
| 86 | 87 | Stanford | 10 | 0 | 86 | 0 | 89 |
| 87 | 88 | Syracuse | 0 | 6 | 87 | 0 | 90 |
| 88 | 89 | TCU | 2 | 30 | 88 | 0 | 91 |
| 89 | 90 | Temple | 3 | 30 | 89 | 0 | 92 |
| 90 | 91 | Tennessee | 11 | 4 | 90 | 0 | 93 |
| 91 | 92 | Texas | 2 | 30 | 91 | 0 | 94 |
| 92 | 93 | Texas A&M | 11 | 5 | 92 | 0 | 95 |
| 93 | 94 | Texas Tech | 2 | 30 | 93 | 0 | 97 |
| 94 | 95 | Toledo | 7 | 3 | 94 | 0 | 98 |
| 95 | 96 | Tulane | 4 | 9 | 95 | 0 | 100 |
| 96 | 97 | Tulsa | 4 | 9 | 96 | 0 | 101 |
| 97 | 98 | UAB | 4 | 8 | 97 | 0 | 102 |
| 98 | 99 | UCLA | 10 | 1 | 98 | 0 | 104 |
| 99 | 100 | Connecticut | 3 | 30 | 99 | 0 | 22 |
| 100 | 101 | UNLV | 9 | 21 | 100 | 0 | 108 |
| 101 | 102 | USC | 10 | 1 | 101 | 0 | 109 |
| 102 | 103 | Utah | 10 | 1 | 102 | 0 | 111 |
| 103 | 104 | Utah State | 9 | 20 | 103 | 0 | 112 |
| 104 | 105 | UTEP | 4 | 9 | 104 | 0 | 113 |
| 105 | 106 | Vanderbilt | 11 | 4 | 105 | 0 | 115 |
| 106 | 107 | Virginia | 0 | 7 | 106 | 0 | 116 |
| 107 | 108 | Virginia Tech | 0 | 7 | 107 | 0 | 117 |
| 108 | 109 | Wake Forest | 0 | 6 | 108 | 0 | 118 |
| 109 | 110 | Washington | 10 | 0 | 109 | 0 | 119 |
| 110 | 111 | Washington State | 10 | 0 | 110 | 0 | 120 |
| 111 | 112 | West Virginia | 2 | 30 | 111 | 0 | 121 |
| 112 | 113 | Western Michigan | 7 | 3 | 112 | 0 | 123 |
| 113 | 114 | Wisconsin | 1 | 10 | 113 | 0 | 124 |
| 114 | 115 | Wyoming | 9 | 20 | 114 | 0 | 125 |
| 115 | 143 | Troy | 13 | 30 | 142 | 0 | 99 |
| 116 | 144 | USF | 3 | 30 | 143 | 0 | 110 |
| 117 | 160 | FCS East | 17 | 30 | 1023 | 1 | 428 |
| 118 | 161 | FCS West | 17 | 30 | 1023 | 1 | 429 |
| 119 | 162 | FCS Northwest | 17 | 30 | 1023 | 1 | 430 |
| 120 | 163 | FCS Midwest | 17 | 30 | 1023 | 1 | 431 |
| 121 | 164 | FCS Southeast | 17 | 30 | 1023 | 1 | 432 |
| 122 | 181 | UMass | 7 | 2 | 221 | 0 | 107 |
| 123 | 211 | Western Kentucky | 13 | 30 | 222 | 0 | 122 |
| 124 | 218 | Texas State | 13 | 30 | 220 | 0 | 96 |
| 125 | 229 | Florida Atlantic | 4 | 8 | 240 | 0 | 27 |
| 126 | 230 | FIU | 4 | 8 | 241 | 0 | 28 |
| 127 | 232 | UTSA | 4 | 9 | 219 | 0 | 114 |
| 128 | 233 | Georgia State | 13 | 30 | 223 | 0 | 32 |
| 129 | 234 | Old Dominion | 5 | 30 | 224 | 0 | 74 |
| 130 | 235 | South Alabama | 13 | 30 | 225 | 0 | 86 |
| 131 | 610 | User HS team | 24 | 0 | 1023 | 8 | 610 |
| 132 | 611 | CPU HS team 1 | 24 | 0 | 1023 | 7 | 611 |
| 133 | 612 | CPU HS team 2 | 24 | 0 | 1023 | 7 | 612 |
| 134 | 613 | CPU HS team 3 | 24 | 0 | 1023 | 7 | 613 |
| 135 | 614 | CPU HS team 4 | 24 | 9 | 1023 | 7 | 614 |
| 136 | 615 | CPU HS team 5 | 24 | 0 | 1023 | 7 | 615 |
| 137 | 616 | CPU HS team 6 | 24 | 0 | 1023 | 7 | 616 |
| 138 | 617 | CPU HS team 7 | 24 | 0 | 1023 | 7 | 617 |
| 139 | 618 | CPU HS team 8 | 24 | 0 | 1023 | 7 | 618 |
| 140 | 619 | CPU HS team 9 | 24 | 9 | 1023 | 7 | 619 |

## Appendix E - CONF and DIVI rows

Conference (`CONF`):

| CGID | LGID | name |
|---|---|---|
| 0 | 0 | ACC |
| 1 | 0 | Big Ten |
| 2 | 0 | Big 12 |
| 3 | 0 | American |
| 4 | 0 | C-USA |
| 5 | 0 | Independents |
| 6 | 1 | Ivy League |
| 7 | 0 | MAC |
| 8 | 1 | MEAC |
| 9 | 0 | MWC |
| 10 | 0 | Pac-12 |
| 11 | 0 | SEC |
| 12 | 1 | SWAC |
| 13 | 0 | Sun Belt |
| 14 | 5 | WAC |
| 15 | 2 | Historic |
| 16 | 3 | Fantasy |
| 17 | 1 | Generic |
| 18 | 1 | Atlantic 10 |
| 19 | 1 | Big Sky |
| 20 | 1 | Gateway |
| 21 | 1 | Southern |
| 22 | 1 | Southland |
| 23 | 1 | Ohio Valley |
| 24 | 4 | High School |

Division (`DIVI`):

| DGID | name | sub-division |
|---|---|---|
| 0 | PAC-12 (North) | North |
| 1 | PAC-12 (South) | South |
| 2 | MAC (East) | East |
| 3 | MAC (West) | West |
| 4 | SEC (East) | East |
| 5 | SEC (West) | West |
| 6 | ACC (Atlantic) | Atlantic |
| 7 | ACC (Coastal) | Coastal |
| 8 | C-USA (East) | East |
| 9 | C-USA (West) | West |
| 10 | Big Ten (Leaders) | Leaders |
| 11 | Big Ten (Legends) | Legends |
| 12 | Big 12 (Div A) | Div A |
| 13 | Big 12 (Div B) | Div B |
| 14 | American (Div A) | Div A |
| 15 | American (Div B) | Div B |
| 16 | Sun Belt (Div A) | Div A |
| 17 | Sun Belt (Div B) | Div B |
| 18 | WAC (Div A) | Div A |
| 19 | WAC (Div B) | Div B |
| 20 | MWC (Mountain) | Mountain |
| 21 | MWC (West) | West |


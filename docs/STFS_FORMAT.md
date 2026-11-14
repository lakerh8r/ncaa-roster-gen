# Xbox 360 STFS ("CON") save format

Notes on the container that holds an NCAA Football 14 roster save on Xbox 360,
and what this project does with it. The implementation lives in
`roster_gen/xbox/stfs.py` (container) and `roster_gen/xbox/save.py` (EA DB
inside it).

## The short version

An Xbox 360 save is a single file with a 4-byte magic of `CON `, `PIRS`, or
`LIVE`. Inside is a small filesystem. NCAA 14 rosters contain one file named
`ROSTER-ROSTER14`, a 56-byte `MC02` wrapper followed by the **same EA TDB
database** used by the PS3 version (`USR-DATA`).

Because the database is identical, all the roster logic (team matching, ratings,
position mapping, depth charts, Top 25) is shared. Only the outer container
differs.

## Header

| Offset | Field |
|---|---|
| `0x000` | magic (`CON ` / `PIRS` / `LIVE`) |
| `0x340` | header size (big-endian `u32`) |
| `0x344` | content type (`u32`; `1` = saved game) |
| `0x360` | title ID (`u32`; NCAA 14 = `0x454109B6`) |
| `0x371` | profile ID / XUID (8 bytes, hex in the path) |
| `0x379` | volume descriptor |
| `0x381` | top hash (SHA-1 of the level-1 hash table) |
| `0x395` | total allocated blocks (`u32`) |
| `0x399` | free blocks (`u32`) |

The volume descriptor at `0x379` contains:

| Offset | Field |
|---|---|
| `+0` | descriptor length (`u8`) |
| `+2` | flags (`u8`): bit 0 = read-only, bit 1 = root hash table active |
| `+3` | file-table block count (`u16`) |
| `+5` | first file-table block (`u24`) |
| `+8` | top hash (20 bytes, mirrored at `0x381`) |

Data starts at `round_up(header_size, 0x1000)`; for the retail NCAA 14 save that
is `0xA000`.

## Block mapping

Files are stored in 4 KiB blocks. Hash tables are interleaved with data, so a
data block's physical offset is not `data_start + block * 0x1000`.

```text
base = 170
physical = block
repeat 3 times:
    physical += ((block + base) // base) * blocks_per_hash_table
    if block < base: stop
    base *= 170
offset = data_start + physical * 0x1000
```

`blocks_per_hash_table` is 1 for read-only packages and 2 otherwise (CON saves
keep a backup copy of every hash table).

For the retail roster save:

| Thing | Block | Offset |
|---|---|---|
| file table | 0 | `0xC000` |
| roster payload | 1..351 | `0xD000` |
| level-0 table (blocks 0..169) | — | `0xA000` |
| level-0 table (blocks 170..339) | — | `0xB8000` |
| level-0 table (blocks 340..352) | — | `0x164000` |
| level-1 table | — | `0xB6000` |

Only the first `total_blocks - free_blocks` blocks are hashed (352 of 353 here).
Hashing the unused block makes the file differ from the original even though the
data is unchanged.

## Hash tree

Each 4 KiB data block has a 24-byte entry in a level-0 hash table:

- `0x00..0x13`: SHA-1 of the block
- `0x14..0x17`: big-endian info word. Low 24 bits are the next block in the
  file's chain; `0x40000000` marks the active copy of a child hash table.

A level-0 table has 170 entries. Its own SHA-1 goes into the level-1 table. The
level-1 table's SHA-1 goes into the header at `0x381`.

Record index for a data block:

- level 0: `block % 170`
- level 1: `(block // 170) % 170`

CON packages store two copies of each hash table. The root copy is chosen by the
header flag; lower copies are chosen by the active bit in the parent's entry.

`StfsPackage.verify_hashes()` walks this tree and reports mismatches, and
`rebuild_hashes()` rewrites it after the payload changes.

## File table

The file table is a normal data block (block 0 here). Entries are 0x40 bytes:

| Offset | Field |
|---|---|
| `0x00` | name, 0x28 bytes, NUL-padded |
| `0x28` | flags: `0x80` directory, `0x40` contiguous, low 6 bits name length |
| `0x29` | valid blocks (`u24`) |
| `0x2C` | allocated blocks (`u24`) |
| `0x2F` | start block (`u24`) |
| `0x32` | directory index (`u16`) |
| `0x34` | file size (`u32`) |

Entry 0 with an empty name ends the table. If the contiguous flag is clear, the
next block comes from the level-0 hash entry's info word.

## The MC02 payload

`ROSTER-ROSTER14` starts with a 56-byte `MC02` wrapper:

| Offset | Value in this save | Meaning |
|---|---|---|
| `0x00` | `MC02` | magic |
| `0x04` | `0x0015E038` | total payload size (1,433,656) |
| `0x08` | `0x0000001C` | 28 |
| `0x0C` | `0x0015E000` | data size (1,433,600) |
| `0x10` | 12 bytes | unknown; preserved unchanged |
| `0x1C` | `0x0015E01C` | 28 + data size |
| `0x38` | — | EA TDB database (1,320,160 bytes) |

The fields in `0x10..0x1B` do not match MD5, SHA-1, SHA-256, or CRC-32 of any
obvious slice, so this project leaves the whole wrapper untouched. The EA
database starts at payload offset 56.

## Signing

The header also carries an RSA signature over the package. Recomputing it needs
Microsoft's private key, which this project does not have and will not include.

So the output is **rehashed, not resigned**:

- On a console with the content-signature check patched (DashLaunch
  `contpatch`), a rehashed save loads directly.
- On a stock console, pass the file through a tool that can re-sign, such as
  Horizon's **Rehash & Resign**, or build the save from a profile that already
  has the right signature and only change the payload — which is not possible
  once the database bytes change.

Changing any byte of the payload invalidates the signature, so a re-signed file
must be produced after generation, not before.

## Why the DB must be sliced exactly

`TDBFile` verifies CRCs between tables and the end-of-file record. Reading the
payload with a contiguous file slice (instead of STFS block mapping) pulls in
hash tables and fails verification; passing the full 1,433,656-byte payload
instead of exactly `db_size` (1,320,160) bytes has the same effect. `XboxSave`
slices `payload[56:56+db_size]`.

## References

- [Free60 STFS](https://free60.org/System-Software/Formats/STFS/)
- Xenia: `src/xenia/vfs/devices/stfs_container_device.cc`,
  `stfs_container_device.h`, `stfs_xbox.h`
- EA TDB notes: [`docs/EA_DB_FORMAT.md`](EA_DB_FORMAT.md)

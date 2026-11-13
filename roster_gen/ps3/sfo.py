"""Minimal PARAM.SFO reader/writer (little-endian, standard PS3 format)."""
import struct


def _parse(data):
    magic = data[0:4]
    assert magic == b"\x00PSF", "not a PARAM.SFO"
    ver, kt, dt, n = struct.unpack("<IIII", data[4:20])
    keypool = kt
    entries = []
    for i in range(n):
        off = 20 + i * 16
        key_off, fmt = struct.unpack("<HH", data[off:off + 4])
        plen, pmax, doff = struct.unpack("<III", data[off + 4:off + 16])
        kend = data.find(b"\x00", keypool + key_off)
        key = data[keypool + key_off:kend].decode("ascii", "replace")
        if fmt in (0x0004, 0x0204, 0x0404):
            raw = data[dt + doff:dt + doff + plen]
            val = raw.split(b"\x00")[0].decode("utf-8", "replace")
        else:
            val = data[dt + doff:dt + doff + plen]
        entries.append({"key": key, "fmt": fmt, "len": plen, "max": pmax,
                        "doff": doff, "value": val, "off": off})
    return ver, kt, dt, n, entries


def read_sfo(path):
    data = open(path, "rb").read()
    ver, kt, dt, n, entries = _parse(data)
    return {e["key"]: e["value"] for e in entries}


def write_sfo(path, updates):
    """Update string (and int) values in a PARAM.SFO. updates: {key: new_value}."""
    data = bytearray(open(path, "rb").read())
    ver, kt, dt, n, entries = _parse(data)
    for e in entries:
        if e["key"] not in updates:
            continue
        new_val = updates[e["key"]]
        if isinstance(new_val, str):
            raw = new_val.encode("utf-8") + b"\x00"
            assert len(raw) <= e["max"], f"{e['key']}: value too long ({len(raw)} > {e['max']})"
            slot = dt + e["doff"]
            # clear slot
            data[slot:slot + e["max"]] = b"\x00" * e["max"]
            data[slot:slot + len(raw)] = raw
            # update plen in entry
            struct.pack_into("<I", data, e["off"] + 4, len(raw))
        else:
            # int32/int64
            if e["fmt"] == 0x0204:
                struct.pack_into("<I", data, dt + e["doff"], int(new_val))
            elif e["fmt"] == 0x0404:
                struct.pack_into("<Q", data, dt + e["doff"], int(new_val))
    open(path, "wb").write(data)


def update_sfo_for_save(path, folder_name, title=None, sub_title=None, account_id=None):
    # If account_id is provided, overwrite ACCOUNT_ID (16 hex chars, no NUL).
    if account_id is not None:
        data = bytearray(open(path, "rb").read())
        ver, kt, dt, n = struct.unpack("<IIII", data[4:20])
        for i in range(n):
            off = 20 + i * 16
            key_off, fmt = struct.unpack("<HH", data[off:off + 4])
            plen, pmax, doff = struct.unpack("<III", data[off + 4:off + 16])
            kend = data.find(b"\x00", kt + key_off)
            key = data[kt + key_off:kend].decode("ascii", "replace")
            if key == "ACCOUNT_ID":
                slot = dt + doff
                val = account_id.encode("ascii")
                assert len(val) == 16, "ACCOUNT_ID must be 16 hex chars"
                data[slot:slot + 16] = val
                struct.pack_into("<I", data, off + 4, 16)
        open(path, "wb").write(data)
    updates = {"SAVEDATA_DIRECTORY": folder_name}
    if sub_title is not None:
        updates["SUB_TITLE"] = sub_title
    if title is not None:
        updates["TITLE"] = title
    write_sfo(path, updates)

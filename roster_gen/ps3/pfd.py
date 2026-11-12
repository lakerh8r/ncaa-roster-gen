"""PARAM.PFD parser/builder for PS3 saves (version 4)."""
import os
from binascii import hexlify, unhexlify
from Crypto.Cipher import AES
from Crypto.Hash import HMAC, SHA

from roster_gen.ps3.keys import SYSCON_MANAGER_KEY, KEYGEN_KEY, NCAA14_SFI


def _b2i(d):
    return int(hexlify(d), 16)


class PFD:
    def __init__(self, folder, sfid=None):
        self.folder = folder
        self.sfid = sfid if sfid is not None else NCAA14_SFI
        with open(os.path.join(folder, "PARAM.PFD"), "rb") as f:
            self.magic = f.read(8)
            self.version = f.read(8)
            self.iv = f.read(16)
            enc = f.read(64)
            dec = AES.new(SYSCON_MANAGER_KEY, AES.MODE_CBC, self.iv).decrypt(enc)
            self.y_hmac = dec[:20]
            self.x_hmac = dec[20:40]
            self.file_hmac_key = dec[40:60]
            self.pad = dec[60:64]
            if _b2i(self.version) == 3:
                self.realkey = self.file_hmac_key
            else:
                h = HMAC.new(KEYGEN_KEY, None, SHA)
                h.update(self.file_hmac_key)
                self.realkey = unhexlify(h.hexdigest())
            self.x_res = f.read(8)
            self.pf_res = f.read(8)
            self.pf_used = f.read(8)
            self.x_table = [hexlify(f.read(8)).decode() for _ in range(_b2i(self.x_res))]
            self.entries = []
            for _ in range(_b2i(self.pf_used)):
                e = {
                    "vid": f.read(8),
                    "name": f.read(65),
                    "pad0": f.read(7),
                    "key": f.read(64),
                    "hashes": [f.read(20) for _ in range(4)],
                    "pad1": f.read(40),
                    "size": f.read(8),
                }
                self.entries.append(e)
            self.space = f.read((_b2i(self.pf_res) - _b2i(self.pf_used)) * 272)
            self.y_table = [hexlify(f.read(20)).decode() for _ in range(_b2i(self.x_res))]
            self.padding = f.read(44)

    def entry(self, name):
        for e in self.entries:
            if e["name"].rstrip(b"\x00").decode(errors="replace") == name:
                return e
        raise KeyError(name)

    def _entry_key(self, e):
        return AES.new(SYSCON_MANAGER_KEY, AES.MODE_CBC, self.sfid[:16]).decrypt(e["key"])[:16]

    def decrypt_file(self, name, data=None):
        e = self.entry(name)
        if data is None:
            data = open(os.path.join(self.folder, name), "rb").read()
        k = self._entry_key(e)
        out = bytearray()
        for i in range(len(data) // 16):
            stream = AES.new(k, AES.MODE_ECB).encrypt(unhexlify("{:016x}".format(i)) + b"\x00" * 8)
            dec = AES.new(k, AES.MODE_ECB).decrypt(data[i * 16:(i + 1) * 16])
            out += bytes(a ^ b for a, b in zip(dec, stream))
        return bytes(out)

    def encrypt_file(self, name, plaintext):
        e = self.entry(name)
        k = self._entry_key(e)
        assert len(plaintext) % 16 == 0
        out = bytearray()
        for i in range(len(plaintext) // 16):
            stream = AES.new(k, AES.MODE_ECB).encrypt(unhexlify("{:016x}".format(i)) + b"\x00" * 8)
            x = bytes(a ^ b for a, b in zip(plaintext[i * 16:(i + 1) * 16], stream))
            out += AES.new(k, AES.MODE_ECB).encrypt(x)
        return bytes(out)

    def file_hash(self, data):
        h = HMAC.new(self.sfid, None, SHA)
        h.update(data)
        return h.digest()

    def _xy_index(self, filename):
        h1 = 0
        for c in filename:
            h1 = (h1 << 5) - h1 + ord(c)
        return h1 % _b2i(self.x_res)

    def _hash_data(self, e):
        return e["name"] + e["key"] + b"".join(e["hashes"]) + e["pad1"] + e["size"]

    def _calc_y(self, filename):
        h = HMAC.new(self.realkey, None, SHA)
        i = self._xy_index(filename)
        j = int(self.x_table[i], 16)
        while j < 0x72:
            ee = self.entries[j]
            h.update(self._hash_data(ee))
            j = int(hexlify(ee["vid"]), 16)
        return h.hexdigest()

    def rebuild(self, folder, file_data):
        """file_data: dict filename->bytes for every protected file (except PARAM.SFO)."""
        # update per-file hashes
        for e in self.entries:
            name = e["name"].rstrip(b"\x00").decode(errors="replace")
            if name == "PARAM.SFO":
                continue
            if name in file_data:
                e["hashes"][0] = self.file_hash(file_data[name])
                e["size"] = len(file_data[name]).to_bytes(8, "big")
        # update y table
        for e in self.entries:
            name = e["name"].rstrip(b"\x00").decode(errors="replace")
            if name == "PARAM.SFO":
                continue
            self.y_table[self._xy_index(name)] = self._calc_y(name)
        # update header hmacs
        h = HMAC.new(self.realkey, None, SHA)
        h.update(b"".join(unhexlify(w) for w in self.y_table))
        self.y_hmac = h.digest()
        h = HMAC.new(self.realkey, None, SHA)
        h.update(self.x_res + self.pf_res + self.pf_used)
        h.update(b"".join(unhexlify(w) for w in self.x_table))
        self.x_hmac = h.digest()
        # encrypt header table
        hdr = AES.new(SYSCON_MANAGER_KEY, AES.MODE_CBC, self.iv).encrypt(
            self.y_hmac + self.x_hmac + self.file_hmac_key + self.pad
        )
        # write
        out_path = os.path.join(folder, "PARAM.PFD")
        with open(out_path, "wb") as f:
            f.write(self.magic)
            f.write(self.version)
            f.write(self.iv)
            f.write(hdr)
            f.write(self.x_res)
            f.write(self.pf_res)
            f.write(self.pf_used)
            f.write(b"".join(unhexlify(w) for w in self.x_table))
            for e in self.entries:
                f.write(e["vid"])
                f.write(e["name"])
                f.write(e["pad0"])
                f.write(e["key"])
                f.write(b"".join(e["hashes"]))
                f.write(e["pad1"])
                f.write(e["size"])
            f.write(self.space)
            f.write(b"".join(unhexlify(w) for w in self.y_table))
            f.write(self.padding)
        return out_path
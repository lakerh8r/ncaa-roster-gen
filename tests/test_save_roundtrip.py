import os, tempfile
from roster_gen.ps3.save import decrypt_save, encrypt_save

BASE = "/home/lakerh8r/Downloads/NCAA14RosterPack/13-14 Release Year NCAA14/PS3 end of season 2013-14 Roster posted by majesty95/PS3 end of season 2013-14 Roster posted by majesty95/PS3/SAVEDATA/BLUS31159-ROSTER-JHASLEY10"


def test_pfd_and_usrdata_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        work = os.path.join(td, "work")
        out = os.path.join(td, "out")
        decrypt_save(BASE, work)
        encrypt_save(work, out, BASE)
        for name in ("PARAM.PFD", "USR-DATA", "PARAM.SFO", "HED-DATA"):
            a = open(os.path.join(BASE, name), "rb").read()
            b = open(os.path.join(out, name), "rb").read()
            assert a == b, f"{name} differs ({len(a)} vs {len(b)})"


def test_db_roundtrip():
    from roster_gen.ps3.save import decrypt_save
    from roster_gen.eadb import TDBFile
    with tempfile.TemporaryDirectory() as td:
        work = os.path.join(td, "work")
        db_path, _ = decrypt_save(BASE, work)
        data = open(db_path, "rb").read()
        db = TDBFile(data)
        assert db.verify() == []
        rebuilt = db.build()
        assert rebuilt == data[:db.db_size]

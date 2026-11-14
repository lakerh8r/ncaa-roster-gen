"""Round-trip tests for the PS3 save pipeline.

These need a real base save folder (PARAM.PFD + USR-DATA). Point the
NCAA_BASE_SAVE environment variable at one to run them; otherwise they skip.
"""
import os
import tempfile

import pytest

BASE = os.environ.get("NCAA_BASE_SAVE", "")

pytestmark = pytest.mark.skipif(
    not BASE or not os.path.isdir(BASE),
    reason="set NCAA_BASE_SAVE to a PS3 roster save folder to run these tests",
)


def test_pfd_and_usrdata_roundtrip():
    from roster_gen.ps3.save import decrypt_save, encrypt_save

    with tempfile.TemporaryDirectory() as td:
        work = os.path.join(td, "work")
        out = os.path.join(td, "out")
        decrypt_save(BASE, work)
        encrypt_save(work, out, BASE)
        for name in ("PARAM.PFD", "USR-DATA", "HED-DATA"):
            a = open(os.path.join(BASE, name), "rb").read()
            b = open(os.path.join(out, name), "rb").read()
            assert a == b, f"{name} differs ({len(a)} vs {len(b)})"
        # PARAM.SFO is intentionally rewritten (account id + directory name)
        assert os.path.exists(os.path.join(out, "PARAM.SFO"))


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

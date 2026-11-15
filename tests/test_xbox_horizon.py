"""Tests for Horizon detection and re-sign helper."""
import os
import stat
import tempfile

import pytest

from roster_gen.xbox import horizon, resign


def test_find_horizon_returns_none_when_missing(monkeypatch):
    monkeypatch.delenv("NCAA_HORIZON_PATH", raising=False)
    monkeypatch.setattr(horizon.shutil, "which", lambda x: None)
    # Force no candidate to exist by pointing home at empty dir
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(horizon.Path, "home", lambda: __import__("pathlib").Path(td))
        assert horizon.find_horizon() is None


def test_find_horizon_env_override(tmp_path):
    fake = tmp_path / "Horizon.exe"
    fake.write_bytes(b"")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    os.environ["NCAA_HORIZON_PATH"] = str(fake)
    try:
        assert horizon.find_horizon() == fake.resolve()
    finally:
        del os.environ["NCAA_HORIZON_PATH"]


def test_horizon_version_none_on_crash(tmp_path):
    fake = tmp_path / "noisy.exe"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    # Should not raise; returns whatever or None
    horizon.horizon_version(fake)


def test_resign_no_horizon():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"x" * 64)
        path = f.name
    try:
        r = resign.resign_with_horizon(path, horizon_path="/no/such/horizon.exe",
                                      launch_gui=False)
        assert r.ok is False
        assert r.mode == "none"
    finally:
        os.unlink(path)


def test_resign_missing_file():
    r = resign.resign_with_horizon("/tmp/definitely-not-a-file.ROSTER",
                                   horizon_path="/bin/true", launch_gui=False)
    assert r.ok is False
    assert r.mode == "none"


def test_resign_cli_success(tmp_path):
    import shutil
    src = tmp_path / "save.ROSTER"
    shutil.copy("/home/lakerh8r/Downloads/NCAA14-360-base/ROSTER-ROSTER14", src)
    # fake horizon: flip a header byte (outside hashed blocks) and exit 0
    fake = tmp_path / "horizon_ok"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "p = sys.argv[-1]\n"
        "d = bytearray(open(p, 'rb').read())\n"
        "d[0x100] ^= 1\n"
        "open(p, 'wb').write(d)\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    r = resign.resign_with_horizon(str(src), horizon_path=str(fake), launch_gui=False)
    assert r.ok is True
    assert r.mode == "cli"
    assert src.with_name(src.name + ".bak").exists()


def test_resign_cli_failure_restores(tmp_path):
    import shutil
    src = tmp_path / "save2.ROSTER"
    shutil.copy("/home/lakerh8r/Downloads/NCAA14-360-base/ROSTER-ROSTER14", src)
    original = src.read_bytes()
    fake = tmp_path / "horizon_fail"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    r = resign.resign_with_horizon(str(src), horizon_path=str(fake), launch_gui=False)
    assert r.ok is False
    assert src.read_bytes() == original
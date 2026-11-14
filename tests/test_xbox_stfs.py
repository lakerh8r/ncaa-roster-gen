"""Round-trip tests for the Xbox 360 STFS container.

Point NCAA_XBOX_BASE at a 360 roster file (``ROSTER-*`` copied off a USB
stick) to run these; otherwise they skip.
"""
import os

import pytest

from roster_gen.xbox.stfs import StfsPackage, load

BASE = os.environ.get("NCAA_XBOX_BASE", "")

pytestmark = pytest.mark.skipif(
    not BASE or not os.path.isfile(BASE),
    reason="set NCAA_XBOX_BASE to an Xbox 360 ROSTER-* file to run these tests",
)


@pytest.fixture(scope="module")
def package():
    return load(BASE)


@pytest.fixture(scope="module")
def roster(package):
    files = [e.name for e in package.files()]
    assert files, "package has no files"
    return files[0]


def test_header(package):
    assert package.magic in (b"CON ", b"PIRS", b"LIVE")
    assert package.base_offset % 0x1000 == 0
    assert package.total_blocks > 0
    assert len(package.profile_id) == 16
    assert len(package.top_hash) == 20


def test_stored_hashes_are_valid(package):
    assert package.verify_hashes() == []


def test_rewrite_is_byte_identical(package, roster):
    original = open(BASE, "rb").read()
    payload = package.read(roster)
    package.write(roster, payload)
    package.rebuild_hashes()
    assert package.tobytes() == original


def test_changed_byte_rehashes(package, roster):
    original = open(BASE, "rb").read()
    changed = StfsPackage(original)
    payload = bytearray(changed.read(roster))
    payload[-1] ^= 0xFF
    changed.write(roster, bytes(payload))
    changed.rebuild_hashes()

    assert changed.verify_hashes() == []
    assert changed.tobytes() != original
    # Everything outside the hash tables and the one changed byte is intact.
    diff = [i for i in range(len(original)) if changed.data[i] != original[i]]
    assert len(diff) <= 80          # one hash + two parent hashes + 1 data byte
    assert changed.read(roster) == bytes(payload)

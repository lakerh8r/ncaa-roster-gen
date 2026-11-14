"""Portable default locations. Nothing here hardcodes a user's home directory.

Every path can be overridden with an environment variable, which is handy for
CI or for people who keep their saves somewhere unusual.
"""
import os
import tempfile
from pathlib import Path

HOME = Path.home()


def _env_dir(name, default):
    value = os.environ.get(name)
    if value:
        return Path(value).expanduser()
    return default


# Where generated saves are written when the user does not pick a folder.
DEFAULT_OUT = _env_dir("NCAA_OUT_DIR", HOME / "Downloads" / "NCAA14RosterPack")

# Optional pre-filled base save. Empty by default: the user browses to their
# own PS3 roster save, since it cannot be bundled with this tool.
DEFAULT_BASE = os.environ.get("NCAA_BASE_SAVE", "")

# Scratch space for decrypted saves.
WORK_DIR = _env_dir("NCAA_WORK_DIR", Path(tempfile.gettempdir()) / "ncaa-roster-gen")

# ESPN response cache (speeds up repeat runs).
CACHE_DIR = _env_dir("NCAA_CACHE_DIR", HOME / ".cache" / "ncaa-roster-gen")

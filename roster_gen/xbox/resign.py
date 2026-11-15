"""Re-sign a generated Xbox 360 roster using the user's own Horizon install.

Horizon is never bundled; this module only drives a copy the user already has.
Re-signing is opt-in and the file is backed up first.
"""
import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from roster_gen.xbox.horizon import find_horizon
from roster_gen.xbox.stfs import load as stfs_load

CLI_CANDIDATES = (
    ("/rehash", "/resign"),
    ("--rehash", "--resign"),
    ("/resign"),
    ("--resign",),
)


@dataclass
class ResignResult:
    ok: bool
    mode: str
    message: str
    backup_path: Optional[str] = None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _hashes_ok(path):
    try:
        return stfs_load(str(path)).verify_hashes() == []
    except Exception:
        return False


def resign_with_horizon(save_path, horizon_path=None, launch_gui=True, timeout=120):
    save_path = Path(save_path).expanduser()
    if not save_path.is_file():
        return ResignResult(False, "none", "Save file not found: " + str(save_path))
    if horizon_path is None:
        horizon_path = find_horizon()
    if horizon_path is None:
        return ResignResult(
            False, "none",
            "Horizon not found. Install Horizon (Windows) or use a modded console "
            "with DashLaunch contpatch, then re-run with --resign.")
    horizon_path = Path(horizon_path).expanduser()
    if not horizon_path.is_file():
        return ResignResult(False, "none", "Horizon executable not found: " + str(horizon_path))

    backup = save_path.with_name(save_path.name + ".bak")
    try:
        shutil.copy2(save_path, backup)
    except OSError as e:
        return ResignResult(False, "none", "Could not back up save: " + str(e))

    before_hash = _sha256(save_path)

    for extra in CLI_CANDIDATES:
        cmd = [str(horizon_path), *extra, str(save_path)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            code = r.returncode
            out = (r.stdout or "") + (r.stderr or "")
        except (OSError, subprocess.SubprocessError) as e:
            code = -1
            out = str(e)
        after_hash = _sha256(save_path)
        changed = after_hash != before_hash
        if code == 0 and changed and _hashes_ok(save_path):
            return ResignResult(
                True, "cli",
                "Re-signed with Horizon (" + " ".join(extra) + ").",
                str(backup))
        if changed and not _hashes_ok(save_path):
            try:
                shutil.copy2(backup, save_path)
            except OSError:
                pass

    if _sha256(save_path) != before_hash:
        try:
            shutil.copy2(backup, save_path)
        except OSError:
            pass

    if launch_gui:
        try:
            subprocess.Popen([str(horizon_path), str(save_path)])
        except OSError as e:
            return ResignResult(
                False, "manual",
                "Could not launch Horizon (" + str(e) + "). Open Horizon manually "
                "and use Rehash & Resign on: " + str(save_path), str(backup))
    return ResignResult(
        False, "manual",
        "Horizon opened with the file. In Horizon: File -> Rehash & Resign, then "
        "Save. Confirm the file size is unchanged afterwards. File: " + str(save_path),
        str(backup))
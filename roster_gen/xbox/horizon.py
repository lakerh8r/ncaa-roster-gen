"""Detect a Horizon (Xbox 360 save editor) installation.

Horizon is the tool stock-console users need to re-sign a generated roster.
We never bundle it; we only detect it and, if present, invoke the user's own
copy. Detection is best-effort and never raises.
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def _candidate_paths():
    out = []
    env = os.environ.get("NCAA_HORIZON_PATH")
    if env:
        out.append(Path(env).expanduser())
    found = shutil.which("Horizon") or shutil.which("Horizon.exe")
    if found:
        out.append(Path(found))
    if os.name == "nt":
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        pf64 = os.environ.get("ProgramFiles", r"C:\Program Files")
        la = os.environ.get("LOCALAPPDATA", "")
        for base in (pf86, pf64, la):
            if not base:
                continue
            for name in ("Horizon.exe", "horizon.exe"):
                out.append(Path(base) / "Horizon" / name)
    home = Path.home()
    for prefix in (home / ".wine", home / ".local/share/wineprefixes/default"):
        for rel in ("drive_c/Program Files (x86)/Horizon/Horizon.exe",
                    "drive_c/Program Files/Horizon/Horizon.exe"):
            out.append(prefix / rel)
    return out


def find_horizon() -> Optional[Path]:
    """Return the first existing Horizon executable, or None."""
    for p in _candidate_paths():
        try:
            if p.is_file():
                return p.resolve()
        except OSError:
            continue
    return None


def horizon_version(path) -> Optional[str]:
    """Best-effort version string; None if Horizon won't report one."""
    path = Path(path)
    for args in (["--version"], ["-v"], ["/version"], ["/?"]):
        try:
            r = subprocess.run(
                [str(path), *args], capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        out = (r.stdout or r.stderr or "").strip()
        if out:
            return out.splitlines()[0][:120]
    return None


def is_horizon_available() -> bool:
    return find_horizon() is not None
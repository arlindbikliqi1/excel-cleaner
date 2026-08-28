"""Gjen Python-in e venv të projektit (Mac/Linux + Windows)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _safe_is_file(path: Path) -> bool:
    """Kontroll i sigurt — symlink i prishur në Windows nuk hedh OSError."""
    try:
        return path.is_file()
    except OSError:
        return False


def project_python() -> Path | None:
    if sys.platform == "win32":
        candidates = [
            ROOT / "venv" / "Scripts" / "python.exe",
            ROOT / "venv" / "Scripts" / "python3.exe",
        ]
    else:
        candidates = [
            ROOT / "venv" / "bin" / "python3",
            ROOT / "venv" / "bin" / "python",
            ROOT / "venv" / "Scripts" / "python.exe",
        ]
    for path in candidates:
        if _safe_is_file(path):
            return path
    return None


def ensure_project_venv() -> None:
    """Rinis skriptin me Python-in e venv kur ekziston."""
    venv_py = project_python()
    if venv_py is None:
        return
    try:
        same = Path(sys.executable).resolve() == venv_py.resolve()
    except OSError:
        same = False
    if same:
        return
    if sys.platform == "win32":
        # os.execv nuk punon mirë në Windows — bat/skripti thërret direkt venv\Scripts\python.exe
        return
    import os

    os.execv(str(venv_py), [str(venv_py), *sys.argv])

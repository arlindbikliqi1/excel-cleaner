"""Gjen Python-in e venv të projektit (Mac/Linux + Windows)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def project_python() -> Path | None:
    candidates = [
        ROOT / "venv" / "bin" / "python3",
        ROOT / "venv" / "bin" / "python",
        ROOT / "venv" / "Scripts" / "python.exe",
        ROOT / "venv" / "Scripts" / "python3.exe",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def ensure_project_venv() -> None:
    """Rinis skriptin me Python-in e venv kur ekziston."""
    venv_py = project_python()
    if venv_py is None:
        return
    if Path(sys.executable).resolve() == venv_py.resolve():
        return
    import os

    os.execv(str(venv_py), [str(venv_py), *sys.argv])

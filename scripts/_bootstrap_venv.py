"""Përdor Python-in e venv të projektit kur skripti niset me python3 të sistemit."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / "venv" / "bin" / "python3"


def ensure_project_venv() -> None:
    if not VENV_PY.exists():
        return
    if Path(sys.executable).resolve() == VENV_PY.resolve():
        return
    os.execv(str(VENV_PY), [str(VENV_PY), *sys.argv])

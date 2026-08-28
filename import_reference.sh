#!/usr/bin/env bash
# Importon të gjitha listat LINDI nga uploads/ (Mac/Linux/Git Bash)
set -e
cd "$(dirname "$0")"

PY=""
if [[ -x venv/bin/python3 ]]; then
  PY="venv/bin/python3"
elif [[ -x venv/Scripts/python.exe ]]; then
  PY="venv/Scripts/python.exe"
fi

if [[ -z "$PY" ]]; then
  echo "Krijimi i venv..."
  python3 -m venv venv
  if [[ -x venv/bin/python3 ]]; then
    PY="venv/bin/python3"
  else
    PY="venv/Scripts/python.exe"
  fi
  "$PY" -m pip install -q -r requirements.txt
fi

"$PY" scripts/import_cleaned_reference.py

#!/usr/bin/env bash
# Nisje e shpejtë (pa debug/reloader — nuk nis dy herë)
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

export FLASK_DEBUG=0
export PORT="${PORT:-5001}"
echo "Excel Cleaner: http://127.0.0.1:${PORT}"
exec "$PY" app.py

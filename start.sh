#!/usr/bin/env bash
# Nisje e shpejtë (pa debug/reloader — nuk nis dy herë)
set -e
cd "$(dirname "$0")"

if [[ ! -d venv ]]; then
  echo "Krijimi i venv..."
  python3 -m venv venv
  source venv/bin/activate
  pip install -q -r requirements.txt
else
  source venv/bin/activate
fi

export FLASK_DEBUG=0
export PORT="${PORT:-5001}"
echo "Excel Cleaner: http://127.0.0.1:${PORT}"
exec python app.py

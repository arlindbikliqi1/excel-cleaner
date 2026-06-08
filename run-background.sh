#!/usr/bin/env bash
# Mbaje aplikacionin aktiv në background (lokal)
set -e
cd "$(dirname "$0")"

PIDFILE=".excel-cleaner.pid"
LOGFILE="logs/app.log"
mkdir -p logs

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Tashmë po punon (PID $(cat "$PIDFILE")). http://127.0.0.1:5000"
  exit 0
fi

source venv/bin/activate 2>/dev/null || {
  echo "Së pari: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
}

export FLASK_DEBUG=0
nohup python app.py >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
echo "U nis në background (PID $(cat "$PIDFILE"))."
echo "URL: http://127.0.0.1:5000"
echo "Log: $LOGFILE"
echo "Ndalo: ./stop.sh"

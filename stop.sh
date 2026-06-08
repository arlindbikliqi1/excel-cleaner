#!/usr/bin/env bash
cd "$(dirname "$0")"
PIDFILE=".excel-cleaner.pid"

if [[ ! -f "$PIDFILE" ]]; then
  echo "Nuk po punon (s'ka PID file)."
  exit 0
fi

PID=$(cat "$PIDFILE")
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "U ndal (PID $PID)."
else
  echo "Procesi nuk ekziston më."
fi
rm -f "$PIDFILE"

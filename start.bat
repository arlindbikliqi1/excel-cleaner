@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  if exist "venv" (
    echo Venv i vjeter i prishur ^(Mac/Linux^) — rikrijimi...
    rmdir /s /q venv
  )
  echo Krijimi i venv...
  python -m venv venv
  if errorlevel 1 (
    echo Gabim: python nuk u gjet. Instaloni Python 3 nga python.org
    exit /b 1
  )
  venv\Scripts\python.exe -m pip install -q -r requirements.txt
)

set FLASK_DEBUG=0
if not defined PORT set PORT=5001
echo Excel Cleaner: http://127.0.0.1:%PORT%
venv\Scripts\python.exe app.py
endlocal

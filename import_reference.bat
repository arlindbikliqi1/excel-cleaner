@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  echo Krijimi i venv...
  python -m venv venv
  if errorlevel 1 (
    echo Gabim: python nuk u gjet. Instaloni Python 3 nga python.org
    exit /b 1
  )
  venv\Scripts\python.exe -m pip install -q -r requirements.txt
)

echo Importimi i listave LINDI referencë...
venv\Scripts\python.exe scripts\import_cleaned_reference.py
if errorlevel 1 exit /b 1

echo.
echo Gati. Tani nisni: start.bat
endlocal

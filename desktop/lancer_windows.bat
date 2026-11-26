@echo off
setlocal
cd /d "%~dp0"

set "PY_CMD="
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.12 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.12"
  if not defined PY_CMD (
    py -3.11 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.11"
  )
  if not defined PY_CMD (
    py -3.10 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.10"
  )
  if not defined PY_CMD set "PY_CMD=py -3"
) else (
  set "PY_CMD=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo Creation de l'environnement Python...
  %PY_CMD% -m venv .venv
  if %errorlevel% neq 0 (
    echo Erreur: Python 3.10 a 3.12 est requis ^(https://www.python.org/downloads/^).
    pause
    exit /b 1
  )
  echo Installation des dependances ^(une seule fois^)...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if %errorlevel% neq 0 (
    echo Erreur lors de l'installation des dependances.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" frankleboeuf.py
endlocal

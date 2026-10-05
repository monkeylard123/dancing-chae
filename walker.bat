@echo off
rem Double-click to start the desktop walker. The first run sets up a private Python environment (.venv).
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto run

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python 3 is not installed. Get it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then run this again.
    pause
    exit /b 1
)

echo Setting up the walker for the first time...
%PY% -m venv .venv || goto fail
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto fail

:run
start "" ".venv\Scripts\pythonw.exe" walker.py %*
exit /b 0

:fail
echo Setup failed. Delete the .venv folder and try again.
rmdir /s /q .venv 2>nul
pause
exit /b 1

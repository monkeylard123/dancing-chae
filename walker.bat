@echo off
rem Double-click to start the desktop walker. The first run sets up a private Python environment (.venv).
setlocal
cd /d "%~dp0"
set "MADE="

if exist ".venv\Scripts\pythonw.exe" goto check

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
set "MADE=1"

:check
rem Also covers a .venv made by something else (an editor, the tests), or one from before a requirement was added.
".venv\Scripts\python.exe" -c "import aiohttp, certifi" >nul 2>nul && goto run
echo Installing what the walker needs...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto fail

:run
start "" ".venv\Scripts\pythonw.exe" walker.py %*
exit /b 0

:fail
echo Setup failed. Delete the .venv folder and try again.
if defined MADE rmdir /s /q .venv 2>nul
pause
exit /b 1

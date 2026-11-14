@echo off
rem One-click launcher for ncaa-roster-gen (Windows).
rem Double-click this file. First run creates .venv and installs dependencies.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\roster-gen.exe" (
  echo First run: installing dependencies. This takes a minute or two...
  py -m venv .venv
  if errorlevel 1 goto :fail
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -e .
  if errorlevel 1 goto :fail
)

echo Starting the roster generator...
rem stop any server left running from a previous window
taskkill /f /im roster-gen.exe >nul 2>&1
start "" powershell -NoProfile -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8765'"
echo.
echo Web UI:    http://127.0.0.1:8765
echo Keep this window open while you use the tool. Close it to stop the server.
echo.
".venv\Scripts\roster-gen.exe" serve
goto :eof

:fail
echo.
echo Setup failed.
echo Install Python 3.11 or newer from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup, then run this again.
echo.
pause

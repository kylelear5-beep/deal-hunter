@echo off
chcp 65001 >nul
set PYTHONUTF8=1
rem PyYAML: install its plain-Python version (no C++ build tools needed)
set PYYAML_FORCE_LIBYAML=0
setlocal
cd /d "%~dp0"
title Deal Hunter

rem ---- find Python 3.11 or newer (prefers 3.13 / 3.12 / 3.11) ------------
set "PY="
set "OKVER=import sys; sys.exit(0 if sys.version_info[:2] >= (3,11) else 1)"
for %%V in (3.13 3.12 3.11 3) do (
  if not defined PY (
    py -%%V -c "%OKVER%" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "%OKVER%" >nul 2>nul && set "PY=python"
)
if not defined PY goto :wrongpython

rem ---- clear a broken or wrong-version environment ------------------------
set "VPY=.venv\Scripts\python.exe"
if exist ".venv" (
  if not exist ".venv\installed.flag" (
    echo Cleaning up an unfinished install...
    rmdir /s /q ".venv"
  ) else (
    "%VPY%" -c "%OKVER%" >nul 2>nul || (
      echo Rebuilding the Python environment for a supported Python version...
      rmdir /s /q ".venv"
    )
  )
)

rem ---- one-time setup ----------------------------------------------------
if not exist "%VPY%" (
  echo [1/3] Creating Python environment...
  %PY% -m venv .venv || goto :fail
)

if not exist ".venv\installed.flag" (
  echo [2/3] Installing packages - first run takes a few minutes...
  "%VPY%" -m pip install --upgrade pip >nul
  "%VPY%" -m pip install -r requirements.txt || goto :fail
  echo [3/3] Installing the Chromium browser for Playwright...
  "%VPY%" -m playwright install chromium || goto :fail
  echo ok> ".venv\installed.flag"
)

rem ---- settings file -----------------------------------------------------
if not exist ".env" (
  copy ".env.example" ".env" >nul
  "%VPY%" -c "import secrets,pathlib;p=pathlib.Path('.env');s=p.read_text();p.write_text(s.replace('MASTER_API_KEY=\n','MASTER_API_KEY=dh_master_'+secrets.token_urlsafe(32)+'\n',1))"
  echo.
  echo ============================================================
  echo  Notepad is opening your settings file.
  echo  1. Paste your Gemini key after GEMINI_API_KEY=
  echo  2. Optional: Discord webhook / Telegram bot for alerts
  echo  3. Save ^(Ctrl+S^) and close Notepad to continue.
  echo ============================================================
  notepad ".env"
)

findstr /r /c:"^GEMINI_API_KEY=..*" ".env" >nul || (
  echo GEMINI_API_KEY is still empty. Opening .env again - paste the key, save, close.
  notepad ".env"
)

rem ---- run ----------------------------------------------------------------
echo.
echo Starting the API window (http://127.0.0.1:8000/docs)...
start "Deal Hunter API" cmd /k ""%VPY%" main.py api"
echo Starting the deal scanner. Leave this window open. Press Ctrl+C to stop.
echo.
"%VPY%" main.py loop
pause
exit /b 0

:nopython
echo.
echo Python was not found. Install Python 3.13 from https://www.python.org/downloads/
echo IMPORTANT: tick "Add python.exe to PATH" on the first installer screen.
pause
exit /b 1

:wrongpython
echo.
echo ============================================================
echo  Deal Hunter needs Python 3.11 or newer.
echo  It isn't installed on this computer yet.
echo.
echo  1. Go to https://www.python.org/downloads/
echo  2. Download Python 3.13 - "Windows installer (64-bit)"
echo  3. Tick "Add python.exe to PATH", then Install Now
echo  4. Double-click START-HERE.bat again
echo.
echo  You do NOT need to uninstall your other Python.
echo ============================================================
pause
exit /b 1

:fail
echo.
echo Setup failed - see the messages above. Just run START-HERE.bat again;
echo it cleans up the unfinished install by itself.
pause
exit /b 1

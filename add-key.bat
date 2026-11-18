@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run START-HERE.bat first. & pause & exit /b 1)
set "OWNER="
set "TIER="
set /p OWNER=Who is this API key for?
set /p TIER=Tier - press Enter for pro, or type free:
if "%OWNER%"=="" set "OWNER=customer"
if "%TIER%"=="" set "TIER=pro"
.venv\Scripts\python.exe main.py add-key --owner "%OWNER%" --tier %TIER%
pause

@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run START-HERE.bat first. & pause & exit /b 1)
echo Telegram chats your bot can see (copy the long numbers into .env):
echo.
.venv\Scripts\python.exe main.py find-chats
echo.
pause

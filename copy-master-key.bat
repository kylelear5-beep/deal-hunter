@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run START-HERE.bat first. & pause & exit /b 1)
.venv\Scripts\python.exe -c "from config import settings; print(settings.master_api_key, end='')" | clip
echo Your master API key is now copied. Paste it into the extension settings (Ctrl+V).
pause

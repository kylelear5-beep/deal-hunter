@echo off
chcp 65001 >nul
set PYTHONUTF8=1
setlocal
cd /d "%~dp0"
title Deal Hunter - upload to server

if not exist ".env" (echo Run START-HERE.bat first so your .env settings file exists. & pause & exit /b 1)

set "SERVER="
if exist "server.txt" set /p SERVER=<server.txt
if "%SERVER%"=="" set /p SERVER=Server IP address (from your server dashboard): 
if "%SERVER%"=="" (echo No IP entered. & pause & exit /b 1)
>server.txt echo %SERVER%

echo.
echo [1/3] Packing Deal Hunter...
tar -czf "%TEMP%\deal-hunter.tgz" --exclude=.venv --exclude=deals.db --exclude=logs --exclude=site --exclude=backups --exclude=__pycache__ --exclude=.pytest_cache --exclude=server.txt . || goto :fail

echo [2/3] Uploading. Type your server password when asked (it stays invisible while typing).
scp -o StrictHostKeyChecking=accept-new "%TEMP%\deal-hunter.tgz" root@%SERVER%:/root/deal-hunter.tgz || goto :fail

echo [3/3] Installing and starting on the server. Type the password once more if asked.
ssh -o StrictHostKeyChecking=accept-new root@%SERVER% "mkdir -p /root/deal-hunter && tar -xzf /root/deal-hunter.tgz -C /root/deal-hunter && bash /root/deal-hunter/deploy.sh" || goto :fail

echo.
echo ============================================================
echo  Done! Deal Hunter is running on your server 24/7.
echo  You'll get a Telegram message: "autopilot started".
echo  To update later, just run this file again.
echo ============================================================
pause
exit /b 0

:fail
echo.
echo Something went wrong - see the messages above. Check the IP and password and try again.
pause
exit /b 1

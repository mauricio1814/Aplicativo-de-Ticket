@echo off
cd /d "%~dp0"
set "HOST=127.0.0.1"
set "PORT=5100"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 server.py
) else (
  python server.py
)
pause

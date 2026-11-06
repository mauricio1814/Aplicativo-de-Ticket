@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  start "Mesa de ayuda - servidor" cmd /k py -3 server.py
) else (
  start "Mesa de ayuda - servidor" cmd /k python server.py
)
timeout /t 2 /nobreak >nul
start "" "http://localhost:5100"

@echo off
echo === Garmin Proxy Local Runner ===
echo.

REM Load tokens from file
set /p GARMIN_TOKENS=<"%~dp0GARMIN_TOKENS.txt"
set API_KEY=myhealthkey2026
set PORT=5000

echo Starting Flask proxy on port %PORT%...
echo Tokens loaded: %GARMIN_TOKENS:~0,20%...
echo.

cd /d "%~dp0"
.venv\Scripts\python.exe app.py

pause

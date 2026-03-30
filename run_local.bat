@echo off
echo === Garmin Proxy Local Runner ===
echo.

REM Load tokens from file
set /p GARMIN_TOKENS=<"%~dp0GARMIN_TOKENS.txt"
set PORT=5000

REM Load secrets from .env file (never committed — see .env.example)
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do set %%A=%%B

echo Starting Flask proxy on port %PORT%...
echo Tokens loaded: %GARMIN_TOKENS:~0,20%...
echo.

cd /d "%~dp0"
.venv\Scripts\python.exe app.py

pause

@echo off
cd /d "D:\Проэкты Клод\garmin-proxy"

:: Load token from file
set /p GARMIN_TOKENS=<GARMIN_TOKENS.txt
set PORT=5001

:: Load all secrets from .env file (never committed)
:: Create .env with: API_KEY, FATSECRET_CLIENT_ID, FATSECRET_CLIENT_SECRET,
::                   FATSECRET_USER, FATSECRET_PASS
for /f "usebackq tokens=1,* delims==" %%A in (".env") do set %%A=%%B

:: Anthropic key from separate file
set /p ANTHROPIC_API_KEY=<.env.anthropic_key

echo Starting Garmin Proxy on port %PORT%...
.venv\Scripts\python.exe app.py

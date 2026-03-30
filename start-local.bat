@echo off
cd /d "D:\Проэкты Клод\garmin-proxy"

:: Load token from file
set /p GARMIN_TOKENS=<GARMIN_TOKENS.txt
set API_KEY=myhealthkey2026
set PORT=5001

:: FatSecret credentials (API)
set FATSECRET_CLIENT_ID=fddbfa79a1a94a1d929a5df4b09a2b12
set FATSECRET_CLIENT_SECRET=76f131b4e1664a0d8db59742072841a2

:: FatSecret credentials (scraper login)
set FATSECRET_USER=al.shipunov1986@gmail.com
set FATSECRET_PASS=Al0634400474!

:: Anthropic (Claude Haiku) — for Russian/Ukrainian food query translation
set /p ANTHROPIC_API_KEY=<.env.anthropic_key

echo Starting Garmin Proxy on port %PORT%...
.venv\Scripts\python.exe app.py

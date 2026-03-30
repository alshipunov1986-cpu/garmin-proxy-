@echo off
cd /d "D:\Проэкты Клод\garmin-proxy"
set /p GARMIN_TOKENS=<GARMIN_TOKENS.txt
set API_KEY=myhealthkey2026
set PORT=5001
set FATSECRET_CLIENT_ID=fddbfa79a1a94a1d929a5df4b09a2b12
set FATSECRET_CLIENT_SECRET=76f131b4e1664a0d8db59742072841a2
start /B .venv\Scripts\python.exe app.py > proxy.log 2>&1

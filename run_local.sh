#!/bin/bash
cd "D:\Проэкты Клод\garmin-proxy"
export GARMIN_TOKENS=$(cat GARMIN_TOKENS.txt)
export API_KEY=myhealthkey2026
export PORT=5001
export FATSECRET_CLIENT_ID=fddbfa79a1a94a1d929a5df4b09a2b12
export FATSECRET_CLIENT_SECRET=76f131b4e1664a0d8db59742072841a2
export FATSECRET_USER=al.shipunov1986@gmail.com
export FATSECRET_PASS='Al0634400474!'
export ANTHROPIC_API_KEY=$(cat .env.anthropic_key 2>/dev/null || echo "")
.venv/Scripts/python.exe app.py

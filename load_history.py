#!/usr/bin/env python3
"""
Load last N days of Garmin data into Google Sheets.
Run locally:
    python load_history.py          # last 30 days
    python load_history.py 7        # last 7 days
"""
import os
import sys
import datetime
import time
import requests

BASE_URL = "http://localhost:5001"
API_KEY  = os.environ.get("API_KEY", "myhealthkey2026")
DAYS     = int(sys.argv[1]) if len(sys.argv) > 1 else 30
headers  = {"X-API-Key": API_KEY}

print(f"Loading {DAYS} days of Garmin history into Google Sheets...")
print(f"Target: {BASE_URL}/sheets/save-day")
print("-" * 55)

ok = err = 0
for i in range(DAYS, 0, -1):
    date = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
    try:
        resp = requests.post(
            f"{BASE_URL}/sheets/save-day",
            params={"date": date},
            headers=headers,
            timeout=60,
        )
        result = resp.json()
        if resp.status_code == 200:
            action = result.get("action", "?")
            row    = result.get("row", "?")
            data   = result.get("data") or {}
            steps  = data.get("steps", "-")
            sleep  = data.get("sleep_hours", "-")
            print(f"  {date}  {action:<8} row={row:<4}  steps={steps}  sleep={sleep}h")
            ok += 1
        else:
            print(f"  {date}  ERROR {resp.status_code}: {result.get('error', '?')[:80]}")
            err += 1
    except Exception as e:
        print(f"  {date}  EXCEPTION: {e}")
        err += 1

    time.sleep(1.2)  # gentle rate-limit for Garmin API

print("-" * 55)
print(f"Done: {ok} ok, {err} errors")

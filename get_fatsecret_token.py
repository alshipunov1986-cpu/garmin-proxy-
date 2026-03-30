#!/usr/bin/env python3
"""
Get permanent FatSecret OAuth 1.0a access tokens.

Usage:
    python get_fatsecret_token.py

Reads FATSECRET_CLIENT_ID and FATSECRET_CLIENT_SECRET from .env file.
Saves resulting tokens to fatsecret_tokens.txt
"""

import os
import sys

# ── Load .env ─────────────────────────────────────────────────────────────────
def load_dotenv(path=".env"):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env

env = load_dotenv()

CLIENT_ID     = env.get("FATSECRET_CLIENT_ID")     or os.environ.get("FATSECRET_CLIENT_ID", "")
CLIENT_SECRET = env.get("FATSECRET_CLIENT_SECRET") or os.environ.get("FATSECRET_CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    print("[ERROR] FATSECRET_CLIENT_ID и FATSECRET_CLIENT_SECRET не найдены.")
    print("   Создай файл .env в папке проекта:")
    print()
    print("   FATSECRET_CLIENT_ID=your_client_id")
    print("   FATSECRET_CLIENT_SECRET=your_client_secret")
    print()
    sys.exit(1)

print(f"[OK] Credentials loaded (ID: {CLIENT_ID[:8]}...)")

# ── OAuth 1.0a flow ───────────────────────────────────────────────────────────
import requests
from requests_oauthlib import OAuth1Session

REQUEST_TOKEN_URL = "https://www.fatsecret.com/oauth/request_token"
AUTHORIZE_URL     = "https://www.fatsecret.com/oauth/authorize"
ACCESS_TOKEN_URL  = "https://www.fatsecret.com/oauth/access_token"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Step 1: Get Request Token
print("\nRequesting Request Token from FatSecret...")
oauth = OAuth1Session(CLIENT_ID, client_secret=CLIENT_SECRET, callback_uri="oob")
oauth.headers.update(HEADERS)
try:
    fetch_response = oauth.fetch_request_token(REQUEST_TOKEN_URL)
except Exception as e:
    print(f"[ERROR] Failed to get Request Token: {e}")
    sys.exit(1)

resource_owner_key    = fetch_response.get("oauth_token")
resource_owner_secret = fetch_response.get("oauth_token_secret")
print(f"[OK] Request Token received: {resource_owner_key[:20]}...")

# Step 2: Authorization URL
auth_url = oauth.authorization_url(AUTHORIZE_URL)
print("\n" + "="*60)
print("Open in your browser:")
print()
print(f"   {auth_url}")
print()
print("Click 'Allow' on FatSecret website.")
print("The site will show a PIN code (verifier).")
print("="*60)

# Step 3: Enter PIN
verifier = input("\nEnter PIN code: ").strip()
if not verifier:
    print("[ERROR] No PIN entered. Exiting.")
    sys.exit(1)

# Step 4: Exchange PIN for Access Token
print("\nExchanging PIN for permanent Access Token...")
oauth = OAuth1Session(
    CLIENT_ID,
    client_secret=CLIENT_SECRET,
    resource_owner_key=resource_owner_key,
    resource_owner_secret=resource_owner_secret,
    verifier=verifier,
)
oauth.headers.update(HEADERS)
try:
    oauth_tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)
except Exception as e:
    print(f"[ERROR] Failed to get Access Token: {e}")
    sys.exit(1)

access_token        = oauth_tokens.get("oauth_token")
access_token_secret = oauth_tokens.get("oauth_token_secret")

# Step 5: Print and save
print("\n" + "="*60)
print("[OK] TOKENS RECEIVED")
print("="*60)
print(f"oauth_token:        {access_token}")
print(f"oauth_token_secret: {access_token_secret}")
print("="*60)

output_file = os.path.join(os.path.dirname(__file__), "fatsecret_tokens.txt")
with open(output_file, "w", encoding="utf-8") as f:
    f.write(f"oauth_token={access_token}\n")
    f.write(f"oauth_token_secret={access_token_secret}\n")
    f.write(f"client_id={CLIENT_ID}\n")
    f.write(f"client_secret={CLIENT_SECRET}\n")

print(f"\n[OK] Saved to: {output_file}")
print("\nDone! Tokens saved to fatsecret_tokens.txt")

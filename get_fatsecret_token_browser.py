#!/usr/bin/env python3
"""
Get FatSecret OAuth 1.0a permanent tokens via headless browser (Playwright).

Usage:
  Step 1 - get request token and authorization URL:
    python get_fatsecret_token_browser.py

  Step 2 - exchange PIN for access token:
    python get_fatsecret_token_browser.py PIN_CODE
"""

import os, sys, time, json
from urllib.parse import parse_qs, quote
import hmac, hashlib, base64, random, string

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

REQUEST_TOKEN_URL = "https://www.fatsecret.com/oauth/request_token"
AUTHORIZE_URL     = "https://www.fatsecret.com/oauth/authorize"
ACCESS_TOKEN_URL  = "https://www.fatsecret.com/oauth/access_token"
STATE_FILE        = os.path.join(BASE_DIR, "fatsecret_oauth_state.json")
TOKENS_FILE       = os.path.join(BASE_DIR, "fatsecret_tokens.txt")

# ── Load .env ──────────────────────────────────────────────────────────────────
def load_dotenv(path=None):
    path = path or os.path.join(BASE_DIR, ".env")
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

env = load_dotenv()
CLIENT_ID     = env.get("FATSECRET_CLIENT_ID")      or os.environ.get("FATSECRET_CLIENT_ID", "")
CLIENT_SECRET = env.get("FATSECRET_CONSUMER_SECRET") or env.get("FATSECRET_CLIENT_SECRET") or os.environ.get("FATSECRET_CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    print("[ERROR] Credentials not found in .env")
    sys.exit(1)

# ── OAuth 1.0a signing ─────────────────────────────────────────────────────────
def make_oauth_header(method, url, consumer_key, consumer_secret,
                      token="", token_secret="", verifier="", callback="oob"):
    ts    = str(int(time.time()))
    nonce = "".join(random.choices(string.ascii_letters + string.digits, k=32))
    params = {
        "oauth_callback":         callback,
        "oauth_consumer_key":     consumer_key,
        "oauth_nonce":            nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        ts,
        "oauth_version":          "1.0",
    }
    if token:    params["oauth_token"]    = token
    if verifier: params["oauth_verifier"] = verifier

    sorted_str = "&".join(f"{quote(k,'')  }={quote(v,'')  }"
                          for k, v in sorted(params.items()))
    base  = "&".join([method.upper(), quote(url, ""), quote(sorted_str, "")])
    key   = quote(consumer_secret, "") + "&" + quote(token_secret, "")
    sig   = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    params["oauth_signature"] = base64.b64encode(sig).decode()
    parts = ", ".join(f'{k}="{quote(v,"")}"' for k, v in sorted(params.items()))
    return f"OAuth {parts}"

# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — exchange PIN for access token (standard requests, not Cloudflare)
# ══════════════════════════════════════════════════════════════════════════════
if len(sys.argv) > 1:
    verifier = sys.argv[1].strip()
    if not os.path.exists(STATE_FILE):
        print("[ERROR] State file not found. Run step 1 first.")
        sys.exit(1)

    with open(STATE_FILE) as f:
        state = json.load(f)

    request_token        = state["oauth_token"]
    request_token_secret = state["oauth_token_secret"]
    print(f"[OK] Loaded request token from state file")
    print(f"[OK] Verifier (PIN): {verifier}")

    import requests
    auth_hdr = make_oauth_header(
        "GET", ACCESS_TOKEN_URL, CLIENT_ID, CLIENT_SECRET,
        token=request_token, token_secret=request_token_secret, verifier=verifier
    )
    r = requests.get(ACCESS_TOKEN_URL, headers={
        "Authorization": auth_hdr,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    }, timeout=15)

    print(f"    Status: {r.status_code}")
    print(f"    Response: {r.text[:300]}")

    if r.status_code != 200 or "oauth_token" not in r.text:
        print("[ERROR] Failed to get access token")
        sys.exit(1)

    tokens = parse_qs(r.text)
    access_token        = tokens["oauth_token"][0]
    access_token_secret = tokens["oauth_token_secret"][0]

    print("\n" + "="*60)
    print("[OK] PERMANENT TOKENS RECEIVED")
    print("="*60)
    print(f"oauth_token:        {access_token}")
    print(f"oauth_token_secret: {access_token_secret}")
    print("="*60)

    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        f.write(f"oauth_token={access_token}\n")
        f.write(f"oauth_token_secret={access_token_secret}\n")
        f.write(f"client_id={CLIENT_ID}\n")
        f.write(f"client_secret={CLIENT_SECRET}\n")

    os.remove(STATE_FILE)
    print(f"\n[OK] Saved to: {TOKENS_FILE}")
    sys.exit(0)

# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — get request token via headless Playwright
# ══════════════════════════════════════════════════════════════════════════════
print(f"[OK] Client ID: {CLIENT_ID[:8]}...")
print(f"[OK] Secret:    {CLIENT_SECRET[:8]}...")
print("\n[1/2] Getting Request Token via headless browser...")

from playwright.sync_api import sync_playwright

auth_hdr = make_oauth_header("GET", REQUEST_TOKEN_URL, CLIENT_ID, CLIENT_SECRET)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    # Intercept the request to inject Authorization header
    def add_auth(route, request):
        route.continue_(headers={**request.headers, "Authorization": auth_hdr})

    page.route(REQUEST_TOKEN_URL, add_auth)
    page.goto(REQUEST_TOKEN_URL, wait_until="domcontentloaded", timeout=30000)

    # Wait for Cloudflare challenge to pass if needed
    for _ in range(10):
        content = page.content()
        if "Just a moment" in content or "challenge" in content.lower():
            print("    Waiting for Cloudflare challenge...")
            time.sleep(3)
            content = page.content()
        else:
            break

    # Extract body text
    body = page.evaluate("document.body.innerText || document.body.textContent")
    status = 200 if "oauth_token" in body else 403
    browser.close()

print(f"    Status: {status}")
print(f"    Response: {body[:200]}")

if status != 200 or "oauth_token" not in body:
    print(f"[ERROR] Failed to get Request Token")
    sys.exit(1)

tokens = parse_qs(body)
request_token        = tokens["oauth_token"][0]
request_token_secret = tokens["oauth_token_secret"][0]

# Save state for step 2
with open(STATE_FILE, "w") as f:
    json.dump({"oauth_token": request_token, "oauth_token_secret": request_token_secret}, f)

auth_url = f"{AUTHORIZE_URL}?oauth_token={request_token}"

print(f"\n[OK] Request Token: {request_token[:20]}...")
print("\n" + "="*60)
print("[2/2] Open this URL in your browser:")
print()
print(f"  {auth_url}")
print()
print("  Log in, click Allow, get the PIN code.")
print("  Then run:")
print(f"  python get_fatsecret_token_browser.py YOUR_PIN")
print("="*60)

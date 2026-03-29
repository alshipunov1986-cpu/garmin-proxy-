"""
FatSecret daily diary scraper.
Reads Chrome cookies → fetches diary page → POSTs parsed data to local proxy.
Run at 21:25 via Windows Task Scheduler.
"""
import re
import json
import datetime
import sys
import requests
import browser_cookie3

PROXY_URL = "http://127.0.0.1:5001/fatsecret/update"
API_KEY   = "myhealthkey2026"
DIARY_URL = "https://foods.fatsecret.com/Diary.aspx?pa=fj"
UA        = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def get_diary_html():
    """Fetch FatSecret diary using Chrome's live cookie session."""
    cookiejar = browser_cookie3.chrome(domain_name="fatsecret.com")
    session = requests.Session()
    session.cookies.update(cookiejar)
    session.headers["User-Agent"] = UA
    resp = session.get(DIARY_URL, timeout=20, allow_redirects=True)
    if "Auth.aspx" in resp.url or "Sign in" in resp.text[:500]:
        raise RuntimeError(f"Redirected to login — not authenticated. Final URL: {resp.url}")
    return resp.text


def parse_diary(html):
    """Parse FatSecret diary HTML → structured nutrition dict."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"[ \t]+", " ", text)

    # Total line (Fat Carbs Prot Cals header followed by numbers)
    total = None
    tm = re.search(r"Fat\s+Carbs\s+Prot\s+Cals\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)", text)
    if tm:
        total = {"fat": float(tm[1]), "carbs": float(tm[2]),
                 "protein": float(tm[3]), "calories": int(tm[4])}

    # Per-meal breakdown
    meals = {}
    for m in re.finditer(
            r"(Breakfast|Lunch|Dinner|Snacks/Other)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)", text):
        key = m[1].lower().replace("/", "_")
        meals[key] = {"fat": float(m[2]), "carbs": float(m[3]),
                      "protein": float(m[4]), "calories": int(m[5])}

    date_m = re.search(r"Today,\s+\w+\s+(\d+\s+\w+\s+\d{4})", text)
    return {
        "date": datetime.date.today().isoformat(),
        "date_label": date_m.group(1) if date_m else "",
        "total": total,
        "meals": meals,
        "updated_at": datetime.datetime.now().isoformat(),
    }


def post_to_proxy(data):
    resp = requests.post(
        PROXY_URL,
        json=data,
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    try:
        print("Fetching FatSecret diary...")
        html = get_diary_html()
        data = parse_diary(html)
        print(f"Parsed: {json.dumps(data['total'])} | meals: {list(data['meals'].keys())}")
        result = post_to_proxy(data)
        print(f"Saved to proxy: {result}")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

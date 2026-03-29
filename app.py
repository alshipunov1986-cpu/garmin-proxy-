import os
import json
import re
import datetime
import base64
import time
import requests
from functools import wraps

from flask import Flask, jsonify, request, redirect
from garminconnect import Garmin

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/fatsecret/update", methods=["OPTIONS"])
def fatsecret_update_preflight():
    return "", 204

API_KEY = os.environ.get("API_KEY", "")
GARMIN_TOKENS = os.environ.get("GARMIN_TOKENS", "")
FATSECRET_CLIENT_ID = os.environ.get("FATSECRET_CLIENT_ID", "")
FATSECRET_CLIENT_SECRET = os.environ.get("FATSECRET_CLIENT_SECRET", "")
FATSECRET_USER = os.environ.get("FATSECRET_USER", "")
FATSECRET_PASS = os.environ.get("FATSECRET_PASS", "")

_fs_token_cache = {"token": None, "expires_at": 0}

_garmin_client = None


def init_garmin():
    """Init Garmin client from OAuth tokens stored in GARMIN_TOKENS env var."""
    if not GARMIN_TOKENS:
        raise RuntimeError("GARMIN_TOKENS env variable is not set")
    client = Garmin()
    client.garth.loads(GARMIN_TOKENS)
    # Restore display_name from garth profile (needed for stats/HR endpoints)
    profile = client.garth.profile or {}
    client.display_name = profile.get("displayName")
    client.full_name = profile.get("fullName")
    return client


def get_garmin():
    """Lazy-init Garmin client with session reuse."""
    global _garmin_client
    if _garmin_client is None:
        _garmin_client = init_garmin()
    return _garmin_client


def reinit_garmin():
    """Force re-init client (e.g. after token expiry)."""
    global _garmin_client
    _garmin_client = init_garmin()
    return _garmin_client


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "")
        if not API_KEY or key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def garmin_call(func):
    """Call a Garmin API function; retry once on failure."""
    try:
        return func(get_garmin())
    except Exception:
        return func(reinit_garmin())


def today():
    return datetime.date.today().isoformat()

def yesterday():
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

def days_ago(n):
    return (datetime.date.today() - datetime.timedelta(days=n)).isoformat()


@app.route("/")
def index():
    return jsonify({
        "status": "ok",
        "endpoints": [
            "/sleep", "/hrv", "/body-battery", "/activities",
            "/stats", "/steps", "/stress", "/respiration",
            "/spo2", "/heart-rate", "/weekly-stats", "/debug-token"
        ]
    })


# ── SLEEP ────────────────────────────────────────────────────────────────────
# Garmin stores sleep under the WAKE-UP date, so today() = last night's sleep
@app.route("/sleep")
@require_api_key
def sleep_data():
    date = request.args.get("date", today())
    data = garmin_call(lambda g: g.get_sleep_data(date))
    return jsonify(data)


# ── HRV ──────────────────────────────────────────────────────────────────────
@app.route("/hrv")
@require_api_key
def hrv_data():
    date = request.args.get("date", today())
    data = garmin_call(lambda g: g.get_hrv_data(date))
    return jsonify(data)


# ── BODY BATTERY ─────────────────────────────────────────────────────────────
@app.route("/body-battery")
@require_api_key
def body_battery():
    start = request.args.get("start", yesterday())
    end = request.args.get("end", today())
    data = garmin_call(lambda g: g.get_body_battery(start, end))
    return jsonify(data)


# ── ACTIVITIES (workouts) ─────────────────────────────────────────────────────
@app.route("/activities")
@require_api_key
def activities():
    end = request.args.get("end", today())
    start = request.args.get("start", days_ago(7))
    limit = int(request.args.get("limit", 10))
    data = garmin_call(lambda g: g.get_activities_by_date(start, end)[:limit])
    return jsonify(data)


# ── DAILY STATS (steps, calories, stress, HR, floors, intensity minutes) ─────
@app.route("/stats")
@require_api_key
def daily_stats():
    date = request.args.get("date", yesterday())
    data = garmin_call(lambda g: g.get_stats(date))
    return jsonify(data)


# ── STEPS ─────────────────────────────────────────────────────────────────────
@app.route("/steps")
@require_api_key
def steps():
    date = request.args.get("date", today())
    data = garmin_call(lambda g: g.get_steps_data(date))
    return jsonify(data)


# ── STRESS ────────────────────────────────────────────────────────────────────
@app.route("/stress")
@require_api_key
def stress():
    date = request.args.get("date", today())
    data = garmin_call(lambda g: g.get_stress_data(date))
    return jsonify(data)


# ── RESPIRATION (breathing rate) ──────────────────────────────────────────────
@app.route("/respiration")
@require_api_key
def respiration():
    date = request.args.get("date", today())
    data = garmin_call(lambda g: g.get_respiration_data(date))
    return jsonify(data)


# ── SpO2 (blood oxygen) ───────────────────────────────────────────────────────
@app.route("/spo2")
@require_api_key
def spo2():
    date = request.args.get("date", today())
    data = garmin_call(lambda g: g.get_spo2_data(date))
    return jsonify(data)


# ── HEART RATE (resting + throughout day) ─────────────────────────────────────
@app.route("/heart-rate")
@require_api_key
def heart_rate():
    date = request.args.get("date", today())
    data = garmin_call(lambda g: g.get_heart_rates(date))
    return jsonify(data)


# ── WEEKLY STATS (7-day summary) ──────────────────────────────────────────────
@app.route("/weekly-stats")
@require_api_key
def weekly_stats():
    results = {}
    for i in range(7):
        day = days_ago(i)
        try:
            stats = garmin_call(lambda g: g.get_stats(day))
            results[day] = {
                "totalSteps": stats.get("totalSteps"),
                "totalKilocalories": stats.get("totalKilocalories"),
                "averageStressLevel": stats.get("averageStressLevel"),
                "maxStressLevel": stats.get("maxStressLevel"),
                "restingHeartRate": stats.get("restingHeartRate"),
                "totalDistanceMeters": stats.get("totalDistanceMeters"),
                "floorsAscended": stats.get("floorsAscended"),
                "moderateIntensityMinutes": stats.get("moderateIntensityMinutes"),
                "vigorousIntensityMinutes": stats.get("vigorousIntensityMinutes"),
                "averageMonitoringEnvironmentAltitude": stats.get("averageMonitoringEnvironmentAltitude"),
            }
        except Exception as e:
            results[day] = {"error": str(e)}
    return jsonify(results)


# ── ALL TODAY (convenience endpoint — all data in one call) ───────────────────
@app.route("/all-today")
@require_api_key
def all_today():
    result = {}
    date_today = today()
    date_yesterday = yesterday()

    # Sleep (last night = today's date in Garmin)
    try:
        sleep = garmin_call(lambda g: g.get_sleep_data(date_today))
        sd = sleep.get("dailySleepDTO", {}) if isinstance(sleep, dict) else {}
        result["sleep"] = {
            "score": sd.get("sleepScores", {}).get("overall", {}).get("value") if isinstance(sd.get("sleepScores"), dict) else None,
            "duration_seconds": sd.get("sleepTimeSeconds"),
            "deep_seconds": sd.get("deepSleepSeconds"),
            "light_seconds": sd.get("lightSleepSeconds"),
            "rem_seconds": sd.get("remSleepSeconds"),
            "awake_seconds": sd.get("awakeSleepSeconds"),
            "avg_overnight_hrv": sleep.get("avgOvernightHrv"),
            "avg_skin_temp_deviation_c": sleep.get("avgSkinTempDeviationC"),
            "breathing_disruptions": sleep.get("breathingDisruptionIndex"),
        }
    except Exception as e:
        result["sleep"] = {"error": str(e)}

    # HRV
    try:
        hrv = garmin_call(lambda g: g.get_hrv_data(date_today))
        hs = hrv.get("hrvSummary", {}) if isinstance(hrv, dict) else {}
        result["hrv"] = {
            "weekly_avg": hs.get("weeklyAvg"),
            "last_night_avg": hs.get("lastNight"),
            "last_night_5_min_high": hs.get("lastNight5MinHigh"),
            "status": hs.get("status"),
        }
    except Exception as e:
        result["hrv"] = {"error": str(e)}

    # Daily stats: steps, resting HR, intensity minutes, calories
    try:
        stats = garmin_call(lambda g: g.get_stats(date_yesterday))
        result["daily_stats"] = {
            "steps": stats.get("totalSteps"),
            "distance_m": stats.get("totalDistanceMeters"),
            "active_calories": stats.get("activeKilocalories"),
            "bmr_calories": stats.get("bmrKilocalories"),
            "floors_ascended": round(stats.get("floorsAscended", 0) or 0),
            "moderate_intensity_min": stats.get("moderateIntensityMinutes"),
            "vigorous_intensity_min": stats.get("vigorousIntensityMinutes"),
            "resting_hr": stats.get("restingHeartRate"),
            "resting_hr_7day_avg": stats.get("lastSevenDaysAvgRestingHeartRate"),
            "avg_stress": stats.get("averageStressLevel"),
            "max_stress": stats.get("maxStressLevel"),
            "body_battery_wake": stats.get("bodyBatteryAtWakeTime"),
        }
    except Exception as e:
        result["daily_stats"] = {"error": str(e)}

    # Body battery (yesterday to today)
    try:
        bb = garmin_call(lambda g: g.get_body_battery(date_yesterday, date_today))
        if isinstance(bb, list) and len(bb) > 0:
            charged = sum(d.get("charged", 0) for d in bb if isinstance(d, dict))
            drained = sum(d.get("drained", 0) for d in bb if isinstance(d, dict))
            result["body_battery"] = {"charged": charged, "drained": drained}
        else:
            result["body_battery"] = bb
    except Exception as e:
        result["body_battery"] = {"error": str(e)}

    # Stress
    try:
        stress = garmin_call(lambda g: g.get_stress_data(date_yesterday))
        result["stress_timeline"] = stress
    except Exception as e:
        result["stress_timeline"] = {"error": str(e)}

    # Respiration
    try:
        resp = garmin_call(lambda g: g.get_respiration_data(date_yesterday))
        result["respiration"] = resp
    except Exception as e:
        result["respiration"] = {"error": str(e)}

    # SpO2
    try:
        spo2 = garmin_call(lambda g: g.get_spo2_data(date_yesterday))
        result["spo2"] = spo2
    except Exception as e:
        result["spo2"] = {"error": str(e)}

    # Recent activities (last 3)
    try:
        acts = garmin_call(lambda g: g.get_activities_by_date(days_ago(3), date_today)[:3])
        result["recent_activities"] = [
            {
                "name": a.get("activityName"),
                "type": a.get("activityType", {}).get("typeKey"),
                "date": a.get("startTimeLocal"),
                "duration_sec": a.get("duration"),
                "distance_m": a.get("distance"),
                "avg_hr": a.get("averageHR"),
                "calories": a.get("calories"),
            }
            for a in (acts or [])
        ]
    except Exception as e:
        result["recent_activities"] = {"error": str(e)}

    # FatSecret nutrition diary (written by Chrome extension at 21:25)
    try:
        if os.path.exists(FS_DIARY_FILE):
            with open(FS_DIARY_FILE, encoding="utf-8") as f:
                fs_data = json.load(f)
            # Only include if data is from today
            if fs_data.get("date") == date_today:
                result["nutrition"] = {
                    "date": fs_data.get("date"),
                    "total": fs_data.get("total"),
                    "meals": fs_data.get("meals"),
                    "updated_at": fs_data.get("updated_at"),
                }
            else:
                result["nutrition"] = {"note": "No diary data for today yet", "last_date": fs_data.get("date")}
        else:
            result["nutrition"] = {"note": "Diary file not found — install Chrome extension"}
    except Exception as e:
        result["nutrition"] = {"error": str(e)}

    return jsonify(result)


# ── FATSECRET OAuth 2.0 Authorization Code ────────────────────────────────────
FS_AUTHORIZE_URL = "https://oauth.fatsecret.com/connect/authorize"
FS_TOKEN_URL     = "https://oauth.fatsecret.com/connect/token"
FS_API_URL       = "https://platform.fatsecret.com/rest/server.api"
FS_TOKEN_FILE    = os.path.join(os.path.dirname(__file__), "fatsecret_token.json")
FS_CALLBACK_URL  = "https://lenovo-15.tail1309d4.ts.net/fatsecret/auth/callback"


def load_fs_token():
    if os.path.exists(FS_TOKEN_FILE):
        with open(FS_TOKEN_FILE) as f:
            return json.load(f)
    env_token = os.environ.get("FATSECRET_TOKEN")
    if env_token:
        return json.loads(env_token)
    return None


def save_fs_token(data):
    data["saved_at"] = time.time()
    with open(FS_TOKEN_FILE, "w") as f:
        json.dump(data, f)


def get_fs_access_token():
    """Return valid access token, refreshing if needed."""
    t = load_fs_token()
    if not t:
        raise RuntimeError("FatSecret не авторизован. Откройте /fatsecret/auth/start")
    if time.time() > t.get("saved_at", 0) + t.get("expires_in", 3600) - 60:
        resp = requests.post(
            FS_TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": t.get("refresh_token"),
                  "scope": "basic"},
            auth=(FATSECRET_CLIENT_ID, FATSECRET_CLIENT_SECRET),
            timeout=10,
        )
        resp.raise_for_status()
        new_t = resp.json()
        save_fs_token(new_t)
        return new_t["access_token"]
    return t["access_token"]


def fs_api_call(method, extra_params=None):
    token = get_fs_access_token()
    params = {"method": method, "format": "json"}
    if extra_params:
        params.update(extra_params)
    resp = requests.get(
        FS_API_URL,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    return resp.json()


@app.route("/fatsecret/auth/start")
def fatsecret_auth_start():
    """Redirect browser to FatSecret OAuth2 authorization page."""
    import urllib.parse
    params = {
        "response_type": "code",
        "client_id": FATSECRET_CLIENT_ID,
        "redirect_uri": FS_CALLBACK_URL,
        "scope": "basic",
    }
    url = FS_AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)
    return redirect(url)


@app.route("/fatsecret/auth/callback")
def fatsecret_auth_callback():
    """Exchange authorization code for access+refresh tokens."""
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "No code in callback", "args": dict(request.args)}), 400
    resp = requests.post(
        FS_TOKEN_URL,
        data={"grant_type": "authorization_code", "code": code,
              "redirect_uri": FS_CALLBACK_URL, "scope": "basic"},
        auth=(FATSECRET_CLIENT_ID, FATSECRET_CLIENT_SECRET),
        timeout=10,
    )
    if resp.status_code != 200:
        return jsonify({"error": resp.text, "status": resp.status_code}), 500
    save_fs_token(resp.json())
    return jsonify({"status": "ok", "message": "✅ FatSecret авторизован! Токен сохранён."})


@app.route("/fatsecret/food-entries")
@require_api_key
def fatsecret_food_entries():
    """Return food diary entries for current month."""
    date_param = request.args.get("date")
    if date_param is None:
        epoch = datetime.date(1970, 1, 1)
        date_param = str((datetime.date.today() - epoch).days)
    try:
        data = fs_api_call("food_entries.get_month", {"date": date_param})
        return jsonify(data)
    except RuntimeError as e:
        return jsonify({"error": str(e), "auth_url": "/fatsecret/auth/start"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/fatsecret/search")
@require_api_key
def fatsecret_search():
    """Search FatSecret food database."""
    query       = request.args.get("q", "")
    max_results = request.args.get("max_results", 10)
    try:
        data = fs_api_call("foods.search", {"search_expression": query, "max_results": max_results})
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


FS_DIARY_FILE  = os.path.join(os.path.dirname(__file__), "fatsecret_diary.json")
FS_LOGIN_URL   = "https://foods.fatsecret.com/Auth.aspx?pa=s"
FS_DIARY_URL   = "https://foods.fatsecret.com/Diary.aspx?pa=fj"
_FS_BROWSER    = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _fs_parse_diary(html):
    """Parse FatSecret diary HTML → nutrition dict."""
    import re
    text = re.sub(r'<[^>]+>', ' ', html)   # strip tags
    text = re.sub(r'[ \t]+', ' ', text)

    total = None
    m = re.search(r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s', text)
    if m:
        total = {"fat": float(m[1]), "carbs": float(m[2]),
                 "protein": float(m[3]), "calories": int(m[4])}

    meals = {}
    for meal_m in re.finditer(
            r'(Breakfast|Lunch|Dinner|Snacks/Other)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)',
            text):
        meals[meal_m[1].lower()] = {
            "fat": float(meal_m[2]), "carbs": float(meal_m[3]),
            "protein": float(meal_m[4]), "calories": int(meal_m[5])
        }

    date_m = re.search(r'Today,\s+\w+\s+(\d+\s+\w+\s+\d{4})', text)
    return {
        "date": date_m.group(1) if date_m else str(datetime.date.today()),
        "total": total,
        "meals": meals,
    }


def _fs_scrape():
    """Login to FatSecret and scrape today's diary. Returns parsed dict."""
    if not FATSECRET_USER or not FATSECRET_PASS:
        raise RuntimeError("FATSECRET_USER / FATSECRET_PASS env vars not set")

    session = requests.Session()
    session.headers["User-Agent"] = _FS_BROWSER

    # Step 1: GET login page → extract VIEWSTATE
    login_page = session.get(FS_LOGIN_URL, timeout=15)
    login_page.raise_for_status()

    vs_m  = re.search(r'id="__VIEWSTATE"\s+value="([^"]+)"', login_page.text)
    vsg_m = re.search(r'id="__VIEWSTATEGENERATOR"\s+value="([^"]+)"', login_page.text)
    ev_m  = re.search(r'id="__EVENTVALIDATION"\s+value="([^"]+)"', login_page.text)

    # Step 2: POST credentials
    login_data = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": vs_m.group(1) if vs_m else "",
        "__VIEWSTATEGENERATOR": vsg_m.group(1) if vsg_m else "",
        "__EVENTVALIDATION": ev_m.group(1) if ev_m else "",
        "ctl00$ctl11$Logincontrol1$Name": FATSECRET_USER,
        "ctl00$ctl11$Logincontrol1$Password": FATSECRET_PASS,
        "ctl00$ctl11$Logincontrol1$Login": "Log In",
    }
    login_resp = session.post(FS_LOGIN_URL, data=login_data,
                              timeout=15, allow_redirects=True)
    if "Sign out" not in login_resp.text and "sign out" not in login_resp.text.lower():
        raise RuntimeError("FatSecret login failed — check credentials")

    # Step 3: GET diary
    diary_resp = session.get(FS_DIARY_URL, timeout=15)
    diary_resp.raise_for_status()
    return _fs_parse_diary(diary_resp.text)


@app.route("/fatsecret/update", methods=["POST"])
def fatsecret_update():
    """Receive nutrition data from bookmarklet and save to file."""
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400
    data["updated_at"] = datetime.date.today().isoformat()
    with open(FS_DIARY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return jsonify({"status": "ok", "saved": data["updated_at"]})


@app.route("/fatsecret/update-form", methods=["POST"])
def fatsecret_update_form():
    """Receive nutrition data via HTML form submit (bypasses CSP connect-src)."""
    payload_str = request.form.get("payload") or request.data.decode()
    if not payload_str:
        return "error: no payload", 400
    data = json.loads(payload_str)
    data["updated_at"] = datetime.date.today().isoformat()
    with open(FS_DIARY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return "<html><body><script>window.close();</script><p>✅ FatSecret данные сохранены: " + data["updated_at"] + "</p></body></html>"


@app.route("/fatsecret/sync")
@require_api_key
def fatsecret_sync():
    """Login to FatSecret, scrape today's diary, save and return."""
    try:
        data = _fs_scrape()
        data["updated_at"] = datetime.date.today().isoformat()
        with open(FS_DIARY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/fatsecret/diary")
@require_api_key
def fatsecret_diary():
    """Return today's saved nutrition data (last sync result)."""
    if not os.path.exists(FS_DIARY_FILE):
        return jsonify({"error": "No data yet. Call /fatsecret/sync first."}), 404
    with open(FS_DIARY_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)


# ── DEBUG TOKEN ───────────────────────────────────────────────────────────────
@app.route("/debug-token")
@require_api_key
def debug_token():
    token_prefix = GARMIN_TOKENS[:30] if GARMIN_TOKENS else "EMPTY"
    token_len = len(GARMIN_TOKENS)
    result = {"token_prefix": token_prefix, "token_len": token_len}
    try:
        decoded = json.loads(base64.b64decode(GARMIN_TOKENS))
        oauth2 = decoded[1]
        access_token = oauth2.get("access_token", "")
        result["access_token_prefix"] = access_token[:30]
        result["access_token_len"] = len(access_token)
        result["expires_at"] = oauth2.get("expires_at")
        import time
        result["expired"] = time.time() > oauth2.get("expires_at", 0)
        date = yesterday()
        url = f"https://connectapi.garmin.com/wellness-service/wellness/dailySleepData/None?date={date}&nonSleepBufferMinutes=60"
        r = requests.get(url, headers={"Authorization": f"Bearer {access_token}", "User-Agent": "GCM-iOS-5.7.2.1"}, timeout=15)
        result["direct_http_status"] = r.status_code
        if r.status_code != 200:
            result["direct_http_error"] = r.text[:200]
    except Exception as e:
        result["error"] = str(e)
    return jsonify(result)


# ── FOOD PWA ──────────────────────────────────────────────────────────────────
FOOD_APP_DIR   = os.path.join(os.path.dirname(__file__), "food_app")
FOOD_CARDS_FILE = os.path.join(os.path.dirname(__file__), "food_cards.json")


@app.route("/food")
@app.route("/food/")
def food_app():
    from flask import send_from_directory
    return send_from_directory(FOOD_APP_DIR, "index.html")


@app.route("/food/search")
def food_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {
        "search_terms": q,
        "json": 1,
        "page_size": 10,
        "fields": "product_name,brands,nutriments,serving_size",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        products = r.json().get("products", [])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    results = []
    for p in products:
        n = p.get("nutriments", {})
        kcal = n.get("energy-kcal_100g") or (n.get("energy_100g", 0) or 0) / 4.184
        if not kcal:
            continue
        name = p.get("product_name", "").strip()
        if not name:
            continue
        results.append({
            "name": name,
            "brand": p.get("brands", ""),
            "per100": {
                "calories": round(float(kcal), 1),
                "protein":  round(float(n.get("proteins_100g", 0) or 0), 1),
                "fat":      round(float(n.get("fat_100g", 0) or 0), 1),
                "carbs":    round(float(n.get("carbohydrates_100g", 0) or 0), 1),
            },
        })
    return jsonify(results)


@app.route("/food/cards", methods=["GET", "POST", "DELETE", "OPTIONS"])
def food_cards():
    if request.method == "OPTIONS":
        return "", 204
    cards = {}
    if os.path.exists(FOOD_CARDS_FILE):
        with open(FOOD_CARDS_FILE, encoding="utf-8") as f:
            cards = json.load(f)

    if request.method == "GET":
        return jsonify(cards)

    elif request.method == "POST":
        card = request.get_json(force=True)
        if not card or not card.get("name"):
            return jsonify({"error": "name required"}), 400
        cards[card["name"]] = card
        with open(FOOD_CARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "ok"})

    elif request.method == "DELETE":
        name = request.args.get("name", "")
        cards.pop(name, None)
        with open(FOOD_CARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "ok"})


@app.route("/food/diary", methods=["GET", "POST"])
def food_diary_api():
    """GET: return diary entries. POST: add an entry."""
    if request.method == "GET":
        date = request.args.get("date", datetime.date.today().isoformat())
        if os.path.exists(FS_DIARY_FILE):
            with open(FS_DIARY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == date:
                return jsonify(data)
        return jsonify({"date": date, "entries": [], "total": None})

    # POST — add food entry, recalculate totals, save
    entry = request.get_json(force=True)
    if not entry:
        return jsonify({"error": "no body"}), 400

    today = datetime.date.today().isoformat()
    data = {"date": today, "entries": [], "total": None, "meals": {}}
    if os.path.exists(FS_DIARY_FILE):
        with open(FS_DIARY_FILE, encoding="utf-8") as f:
            existing = json.load(f)
        if existing.get("date") == today:
            data = existing

    data.setdefault("entries", [])
    data["entries"].append(entry)

    # Recalculate totals from entries
    fat = carbs = protein = calories = 0.0
    for e in data["entries"]:
        factor = e.get("grams", 100) / 100.0
        p = e.get("per100", {})
        calories += (p.get("calories", 0) or 0) * factor
        protein  += (p.get("protein",  0) or 0) * factor
        fat      += (p.get("fat",      0) or 0) * factor
        carbs    += (p.get("carbs",    0) or 0) * factor

    data["total"] = {
        "calories": round(calories, 1),
        "protein":  round(protein,  1),
        "fat":      round(fat,      1),
        "carbs":    round(carbs,    1),
    }
    data["updated_at"] = datetime.datetime.now().isoformat()

    with open(FS_DIARY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "ok", "total": data["total"]})


@app.route("/food/diary/delete", methods=["POST"])
def food_diary_delete():
    """Remove one entry by index."""
    body = request.get_json(force=True) or {}
    idx = body.get("index")
    if idx is None:
        return jsonify({"error": "index required"}), 400
    today = datetime.date.today().isoformat()
    if not os.path.exists(FS_DIARY_FILE):
        return jsonify({"error": "no diary"}), 404
    with open(FS_DIARY_FILE, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("date") != today:
        return jsonify({"error": "diary date mismatch"}), 400
    entries = data.get("entries", [])
    if 0 <= idx < len(entries):
        entries.pop(idx)
    # Recalculate
    fat = carbs = protein = calories = 0.0
    for e in entries:
        factor = e.get("grams", 100) / 100.0
        p = e.get("per100", {})
        calories += (p.get("calories", 0) or 0) * factor
        protein  += (p.get("protein",  0) or 0) * factor
        fat      += (p.get("fat",      0) or 0) * factor
        carbs    += (p.get("carbs",    0) or 0) * factor
    data["total"] = {
        "calories": round(calories, 1),
        "protein":  round(protein,  1),
        "fat":      round(fat,      1),
        "carbs":    round(carbs,    1),
    }
    data["entries"] = entries
    with open(FS_DIARY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"status": "ok", "total": data["total"]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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
    result["date"] = date_today  # always explicit so n8n can verify

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
        stats = garmin_call(lambda g: g.get_stats(date_today))
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

    # Body battery
    try:
        # Get current level from daily stats (most reliable source)
        today_stats = garmin_call(lambda g: g.get_stats(date_today))
        current_level = today_stats.get("bodyBatteryMostRecentValue") if isinstance(today_stats, dict) else None
        wake_level = result.get("daily_stats", {}).get("body_battery_wake")
        # net_used = wake - current (0 if gained)
        net_used = None
        if wake_level is not None and current_level is not None:
            net_used = max(0, wake_level - current_level)
        result["body_battery"] = {
            "current_level": current_level,
            "net_used_since_wake": net_used,  # >0 used, 0 if recovered
            "highest": today_stats.get("bodyBatteryHighestValue") if isinstance(today_stats, dict) else None,
            "lowest": today_stats.get("bodyBatteryLowestValue") if isinstance(today_stats, dict) else None,
        }
    except Exception as e:
        result["body_battery"] = {"error": str(e)}

    # Stress
    try:
        stress = garmin_call(lambda g: g.get_stress_data(date_today))
        result["stress_timeline"] = stress
    except Exception as e:
        result["stress_timeline"] = {"error": str(e)}

    # Respiration
    try:
        resp = garmin_call(lambda g: g.get_respiration_data(date_today))
        result["respiration"] = resp
    except Exception as e:
        result["respiration"] = {"error": str(e)}

    # SpO2
    try:
        spo2 = garmin_call(lambda g: g.get_spo2_data(date_today))
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

    # Nutrition diary — PWA food_diary.json (primary) → fatsecret_diary.json (fallback)
    try:
        nutrition_data = None
        # 1. Try new PWA diary (food_diary.json)
        if os.path.exists(FOOD_DIARY_FILE):
            with open(FOOD_DIARY_FILE, encoding="utf-8") as f:
                all_diary = json.load(f)
            # multi-day format: {date_str: {entries, total}}
            if isinstance(all_diary, dict) and "entries" not in all_diary:
                day_data = all_diary.get(date_today, {})
                if day_data.get("total") and day_data["total"].get("calories", 0) > 0:
                    nutrition_data = {
                        "date":       date_today,
                        "source":     "pwa",
                        "total":      day_data.get("total"),
                        "entries":    day_data.get("entries", []),
                        "updated_at": day_data.get("updated_at", date_today),
                    }
        # 2. Fallback: old Chrome extension fatsecret_diary.json
        if nutrition_data is None and os.path.exists(FS_DIARY_FILE):
            with open(FS_DIARY_FILE, encoding="utf-8") as f:
                fs_data = json.load(f)
            if fs_data.get("date") == date_today:
                nutrition_data = {
                    "date":       fs_data.get("date"),
                    "source":     "fatsecret_ext",
                    "total":      fs_data.get("total"),
                    "meals":      fs_data.get("meals"),
                    "updated_at": fs_data.get("updated_at"),
                }
        result["nutrition"] = nutrition_data or {"note": "No nutrition data for today yet"}
    except Exception as e:
        result["nutrition"] = {"error": str(e)}

    return jsonify(result)


# ── FATSECRET OAuth 2.0 Authorization Code ────────────────────────────────────
FS_AUTHORIZE_URL = "https://oauth.fatsecret.com/connect/authorize"
FS_TOKEN_URL     = "https://oauth.fatsecret.com/connect/token"
FS_API_URL       = "https://platform.fatsecret.com/rest/server.api"
FS_TOKEN_FILE    = os.path.join(os.path.dirname(__file__), "fatsecret_token.json")
FS_CALLBACK_URL  = "https://lenovo-15.tail1309d4.ts.net/fatsecret/auth/callback"

# client_credentials token cache (for public food search — no user login needed)
_fs_cc_cache = {"token": None, "expires_at": 0}

def get_fs_client_token():
    """OAuth 2.0 client_credentials — for public food search (no user auth)."""
    global _fs_cc_cache
    if _fs_cc_cache["token"] and time.time() < _fs_cc_cache["expires_at"] - 60:
        return _fs_cc_cache["token"]
    resp = requests.post(
        FS_TOKEN_URL,
        data={"grant_type": "client_credentials", "scope": "basic"},
        auth=(FATSECRET_CLIENT_ID, FATSECRET_CLIENT_SECRET),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _fs_cc_cache["token"] = data["access_token"]
    _fs_cc_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
    return _fs_cc_cache["token"]

def fs_public_call(method, extra_params=None):
    """FatSecret API call using client_credentials (public data — food search)."""
    token = get_fs_client_token()
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

def parse_fs_food(food):
    """Parse FatSecret food object → unified format {name, brand, source, per100}."""
    import re
    desc = food.get("food_description", "")
    # "Per 100g - Calories: 165kcal | Fat: 3.57g | Carbs: 0.00g | Protein: 31.02g"
    cal   = re.search(r'Calories:\s*([\d.]+)', desc)
    fat   = re.search(r'Fat:\s*([\d.]+)',      desc)
    carbs = re.search(r'Carbs:\s*([\d.]+)',    desc)
    prot  = re.search(r'Protein:\s*([\d.]+)',  desc)
    return {
        "name":   food.get("food_name", "").strip(),
        "brand":  food.get("brand_name", "").strip(),
        "source": "fatsecret",
        "per100": {
            "calories": round(float(cal.group(1)),   1) if cal   else 0,
            "protein":  round(float(prot.group(1)),  1) if prot  else 0,
            "fat":      round(float(fat.group(1)),   1) if fat   else 0,
            "carbs":    round(float(carbs.group(1)), 1) if carbs else 0,
        },
    }


_translate_cache = {}

def translate_food_query(q):
    """
    Detect Cyrillic input and translate to English using Claude Haiku.
    Returns (translated_str, original_query) or (None, q) if no translation needed/possible.
    """
    if not any('\u0400' <= c <= '\u04FF' for c in q):
        return None, q  # not Cyrillic — no translation needed
    if not ANTHROPIC_API_KEY:
        return None, q  # no key — fall through gracefully
    if q in _translate_cache:
        return _translate_cache[q], q
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 64,
                "messages": [{
                    "role": "user",
                    "content": (
                        "Переведи название продукта питания на английский язык. "
                        "Верни ТОЛЬКО само название без пояснений, одной строкой. "
                        f"Продукт: {q}"
                    )
                }]
            },
            timeout=8,
        )
        resp.raise_for_status()
        translated = resp.json()["content"][0]["text"].strip().strip('"').strip("'")
        _translate_cache[q] = translated
        return translated, q
    except Exception:
        return None, q


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

    def _extract_meal(html, meal_name):
        """Extract fat/carbs/protein/calories from title attributes."""
        fat_m = re.search(rf'Total {meal_name} Fat:\s*([\d.]+)', html)
        carbs_m = re.search(rf'Total {meal_name} Carbohy\w*:\s*([\d.]+)', html)
        prot_m = re.search(rf'Total {meal_name} Protein:\s*([\d.]+)', html)
        cal_m = re.search(rf'Total {meal_name} Calories:\s*(\d+)', html)
        if cal_m and int(cal_m.group(1)) > 0:
            return {
                "fat": float(fat_m.group(1)) if fat_m else 0,
                "carbs": float(carbs_m.group(1)) if carbs_m else 0,
                "protein": float(prot_m.group(1)) if prot_m else 0,
                "calories": int(cal_m.group(1)),
            }
        return None

    meals = {}
    for meal in ["Breakfast", "Lunch", "Dinner", "Snacks/Other"]:
        data = _extract_meal(html, meal)
        if data:
            meals[meal.lower()] = data

    # Total: sum of meals or parse from page
    total = None
    if meals:
        total = {
            "fat": round(sum(m["fat"] for m in meals.values()), 2),
            "carbs": round(sum(m["carbs"] for m in meals.values()), 2),
            "protein": round(sum(m["protein"] for m in meals.values()), 2),
            "calories": sum(m["calories"] for m in meals.values()),
        }

    # Date from page
    text = re.sub(r'<[^>]+>', ' ', html)
    date_m = re.search(r'(?:Today|Yesterday),\s+\w+\s+(\d+\s+\w+\s+\d{4})', text)
    return {
        "date": date_m.group(1) if date_m else str(datetime.date.today()),
        "total": total,
        "meals": meals,
    }


def _fs_scrape(date_str=None):
    """Login to FatSecret and scrape diary. Returns parsed dict.
    date_str: optional YYYY-MM-DD (default: today).
    """
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

    # Step 3: GET diary (with optional date)
    url = FS_DIARY_URL
    if date_str:
        target = datetime.date.fromisoformat(date_str)
        epoch = datetime.date(1970, 1, 1)
        dd = (target - epoch).days
        url += f"&dd={dd}&dt={dd}"
    diary_resp = session.get(url, timeout=15)
    diary_resp.raise_for_status()
    result = _fs_parse_diary(diary_resp.text)
    if date_str:
        result["date"] = date_str
    return result


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
    """Login to FatSecret, scrape diary, save and return. ?date=YYYY-MM-DD optional."""
    try:
        date_param = request.args.get("date")
        data = _fs_scrape(date_param)
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
FOOD_APP_DIR    = os.path.join(os.path.dirname(__file__), "food_app")
FOOD_CARDS_FILE = os.path.join(os.path.dirname(__file__), "food_cards.json")
FOOD_DIARY_FILE = os.path.join(os.path.dirname(__file__), "food_diary.json")


@app.route("/food")
@app.route("/food/")
def food_app():
    from flask import send_from_directory
    return send_from_directory(FOOD_APP_DIR, "index.html")


@app.route("/food/search")
def food_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"results": [], "translated": ""})

    # ── 0. Detect Cyrillic → translate for FatSecret ──────────────────────────
    translated_q, orig_q = translate_food_query(q)
    fs_query = translated_q if translated_q else q

    results = []

    # ── 1. FatSecret — search with translated query ───────────────────────────
    try:
        fs_data = fs_public_call("foods.search", {"search_expression": fs_query, "max_results": 8})
        foods_wrap = fs_data.get("foods", {})
        fs_foods = foods_wrap.get("food", [])
        if isinstance(fs_foods, dict):   # single result → wrap in list
            fs_foods = [fs_foods]
        for f in fs_foods:
            parsed = parse_fs_food(f)
            if parsed["name"] and parsed["per100"]["calories"]:
                results.append(parsed)
    except Exception:
        pass  # FatSecret unavailable — continue with OFF

    # ── 2. Open Food Facts — search with original query (supports Cyrillic) ──
    off_results = []
    try:
        off_url = "https://world.openfoodfacts.org/cgi/search.pl"
        r = requests.get(off_url, params={
            "search_terms": q, "json": 1, "page_size": 8,
            "fields": "product_name,brands,nutriments",
        }, headers={
            "User-Agent": "GarminHealthProxy/1.0 (health tracker app; contact al.shipunov1986@gmail.com)"
        }, timeout=10)
        products = r.json().get("products", [])
        for p in products:
            n = p.get("nutriments", {})
            kcal = n.get("energy-kcal_100g") or (n.get("energy_100g", 0) or 0) / 4.184
            name = p.get("product_name", "").strip()
            if not name or not kcal:
                continue
            off_results.append({
                "name":   name,
                "brand":  p.get("brands", ""),
                "source": "off",
                "per100": {
                    "calories": round(float(kcal), 1),
                    "protein":  round(float(n.get("proteins_100g",       0) or 0), 1),
                    "fat":      round(float(n.get("fat_100g",            0) or 0), 1),
                    "carbs":    round(float(n.get("carbohydrates_100g",  0) or 0), 1),
                },
            })
    except Exception:
        pass

    results.extend(off_results)
    return jsonify({"results": results, "translated": translated_q or ""})


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


def _recalc_diary_totals(entries):
    fat = carbs = protein = calories = 0.0
    for e in entries:
        factor = e.get("grams", 100) / 100.0
        p = e.get("per100", {})
        calories += (p.get("calories", 0) or 0) * factor
        protein  += (p.get("protein",  0) or 0) * factor
        fat      += (p.get("fat",      0) or 0) * factor
        carbs    += (p.get("carbs",    0) or 0) * factor
    return {"calories": round(calories,1), "protein": round(protein,1),
            "fat": round(fat,1), "carbs": round(carbs,1)}

def _load_all_diary():
    """Load multi-day diary dict {date_str: {entries, total}}. Auto-migrates old format."""
    if not os.path.exists(FOOD_DIARY_FILE):
        return {}
    with open(FOOD_DIARY_FILE, encoding="utf-8") as f:
        data = json.load(f)
    # Migrate old single-day format {"date":..., "entries":...}
    if isinstance(data, dict) and "entries" in data and "date" in data:
        key = data["date"]
        migrated = {key: {"entries": data.get("entries",[]), "total": data.get("total")}}
        with open(FOOD_DIARY_FILE, "w", encoding="utf-8") as f:
            json.dump(migrated, f, ensure_ascii=False, indent=2)
        return migrated
    return data

def _load_diary(date_str=None):
    date_str = date_str or datetime.date.today().isoformat()
    all_data = _load_all_diary()
    day = all_data.get(date_str, {})
    return {"date": date_str, "entries": day.get("entries",[]), "total": day.get("total")}

def _save_diary(data):
    date_str = data.get("date", datetime.date.today().isoformat())
    all_data = _load_all_diary()
    all_data[date_str] = {"entries": data.get("entries",[]), "total": data.get("total"),
                          "updated_at": data.get("updated_at","")}
    with open(FOOD_DIARY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)


@app.route("/food/diary", methods=["GET", "POST"])
def food_diary_api():
    if request.method == "GET":
        date = request.args.get("date", datetime.date.today().isoformat())
        return jsonify(_load_diary(date))
    entry = request.get_json(force=True)
    if not entry:
        return jsonify({"error": "no body"}), 400
    data = _load_diary()
    data["entries"].append(entry)
    data["total"] = _recalc_diary_totals(data["entries"])
    data["updated_at"] = datetime.datetime.now().isoformat()
    _save_diary(data)
    return jsonify({"status": "ok", "total": data["total"]})


@app.route("/food/diary/today")
def food_diary_today():
    """Return today's nutrition totals — for n8n evening report."""
    data = _load_diary()
    total = data.get("total") or {"calories":0,"protein":0,"fat":0,"carbs":0}
    entries = data.get("entries", [])
    return jsonify({"date": data["date"], "calories": total.get("calories",0),
                    "protein": total.get("protein",0), "fat": total.get("fat",0),
                    "carbs": total.get("carbs",0), "entries": len(entries),
                    "logged": len(entries) > 0})


@app.route("/food/diary/stats")
def food_diary_stats():
    """Return calorie/macro history for last N days (default 7) — for stats chart."""
    days = int(request.args.get("days", 7))
    all_data = _load_all_diary()
    result = []
    for i in range(days - 1, -1, -1):
        d = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
        day = all_data.get(d, {})
        total = day.get("total") or {}
        result.append({"date": d, "calories": total.get("calories",0),
                        "protein": total.get("protein",0), "fat": total.get("fat",0),
                        "carbs": total.get("carbs",0)})
    logged = [r for r in result if r["calories"] > 0]
    avg = {k: round(sum(r[k] for r in logged)/len(logged), 1) if logged else 0
           for k in ["calories","protein","fat","carbs"]}
    return jsonify({"days": result, "avg": avg, "logged_days": len(logged)})


@app.route("/food/diary/delete", methods=["POST"])
def food_diary_delete():
    body = request.get_json(force=True) or {}
    idx  = body.get("index")
    date = body.get("date", datetime.date.today().isoformat())
    if idx is None:
        return jsonify({"error": "index required"}), 400
    data = _load_diary(date)
    entries = data.get("entries", [])
    if 0 <= idx < len(entries):
        entries.pop(idx)
    data["entries"] = entries
    data["total"] = _recalc_diary_totals(entries)
    _save_diary(data)
    return jsonify({"status": "ok", "total": data["total"]})


# ── GOOGLE SHEETS ─────────────────────────────────────────────────────────────
SPREADSHEET_ID   = "1bGEHnrvpCL6C_lwayP55W3oggNE4CKZQONOSeJLDCEc"
SHEET_NAME       = "Health Data"
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "google_credentials.json")

SHEET_HEADERS = [
    "Дата", "Сон (ч)", "Оценка сна", "Глубокий сон (мин)", "REM (мин)",
    "HRV (мс)", "HRV норма недели", "Пульс покоя", "Пульс норма 7д",
    "Body Battery утром", "Body Battery вечером", "Израсходовано BB",
    "Стресс средний", "Стресс пик", "Шаги", "Активные калории",
    "Температура кожи", "Тренировки", "SpO2",
    "Калории (еда)", "Белки (г)", "Жиры (г)", "Углеводы (г)",
]

_sheet_ws = None


def get_sheet():
    """Get authenticated Google Sheets worksheet (lazy init, cached)."""
    global _sheet_ws
    if _sheet_ws is not None:
        return _sheet_ws
    import gspread
    if os.path.exists(CREDENTIALS_FILE):
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
    else:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS")
        if not creds_json:
            raise RuntimeError("Google credentials not found (google_credentials.json or GOOGLE_CREDENTIALS env var)")
        gc = gspread.service_account_from_dict(json.loads(creds_json))
    sh = gc.open_by_key(SPREADSHEET_ID)
    # Get or create the worksheet
    try:
        ws = sh.worksheet(SHEET_NAME)
    except Exception:
        # Try renaming Sheet1 first, otherwise create new
        try:
            ws = sh.worksheet("Sheet1")
            ws.update_title(SHEET_NAME)
        except Exception:
            ws = sh.add_worksheet(title=SHEET_NAME, rows=2000, cols=25)
    # Ensure headers row is correct and complete
    first_row = ws.row_values(1)
    if first_row != SHEET_HEADERS:
        ws.update(range_name="A1", values=[SHEET_HEADERS])
        ws.format("A1:W1", {"textFormat": {"bold": True}})
    _sheet_ws = ws
    return ws


def _collect_day_data(date_str):
    """Collect all health metrics for a given date. Returns a flat dict."""
    d = {}

    # Sleep (Garmin stores sleep under the wake-up date)
    try:
        sleep = garmin_call(lambda g: g.get_sleep_data(date_str))
        sd = sleep.get("dailySleepDTO", {}) if isinstance(sleep, dict) else {}
        d["sleep_hours"] = round(sd.get("sleepTimeSeconds", 0) / 3600, 2) if sd.get("sleepTimeSeconds") else None
        scores = sd.get("sleepScores") or {}
        d["sleep_score"] = scores.get("overall", {}).get("value") if isinstance(scores.get("overall"), dict) else None
        d["deep_min"]   = round(sd.get("deepSleepSeconds", 0) / 60) if sd.get("deepSleepSeconds") else None
        d["rem_min"]    = round(sd.get("remSleepSeconds", 0) / 60)  if sd.get("remSleepSeconds")  else None
        d["skin_temp"]  = sleep.get("avgSkinTempDeviationC")
    except Exception:
        d.update({"sleep_hours": None, "sleep_score": None, "deep_min": None, "rem_min": None, "skin_temp": None})

    # HRV
    try:
        hrv = garmin_call(lambda g: g.get_hrv_data(date_str))
        hs = hrv.get("hrvSummary", {}) if isinstance(hrv, dict) else {}
        d["hrv"]          = hs.get("lastNight")
        d["hrv_weekly"]   = hs.get("weeklyAvg")
    except Exception:
        d.update({"hrv": None, "hrv_weekly": None})

    # Daily stats (steps, HR, stress, body battery wake)
    try:
        stats = garmin_call(lambda g: g.get_stats(date_str))
        d["resting_hr"]      = stats.get("restingHeartRate")
        d["resting_hr_7d"]   = stats.get("lastSevenDaysAvgRestingHeartRate")
        d["bb_wake"]         = stats.get("bodyBatteryAtWakeTime")
        d["avg_stress"]      = stats.get("averageStressLevel")
        d["max_stress"]      = stats.get("maxStressLevel")
        d["steps"]           = stats.get("totalSteps")
        d["active_calories"] = stats.get("activeKilocalories")
    except Exception:
        d.update({"resting_hr": None, "resting_hr_7d": None, "bb_wake": None,
                  "avg_stress": None, "max_stress": None, "steps": None, "active_calories": None})

    # Body battery — current level from stats (bodyBatteryMostRecentValue)
    try:
        # stats already fetched above, reuse it
        d["bb_current"] = stats.get("bodyBatteryMostRecentValue") if isinstance(stats, dict) else None
        bb_wake = d.get("bb_wake")
        bb_cur = d.get("bb_current")
        d["bb_net_used"] = max(0, bb_wake - bb_cur) if (bb_wake is not None and bb_cur is not None) else None
    except Exception:
        d.update({"bb_current": None, "bb_net_used": None})

    # Activities
    try:
        prev = (datetime.date.fromisoformat(date_str) - datetime.timedelta(days=1)).isoformat()
        acts = garmin_call(lambda g: g.get_activities_by_date(prev, date_str)[:5])
        d["workouts"] = ", ".join(
            a.get("activityType", {}).get("typeKey", "?") for a in (acts or [])
        )
    except Exception:
        d["workouts"] = ""

    # SpO2
    try:
        spo2 = garmin_call(lambda g: g.get_spo2_data(date_str))
        if isinstance(spo2, dict):
            d["spo2"] = spo2.get("averageSpo2") or spo2.get("latestSpo2")
        else:
            d["spo2"] = None
    except Exception:
        d["spo2"] = None

    # Nutrition (FatSecret scraper)
    try:
        if FATSECRET_USER and FATSECRET_PASS:
            fs = _fs_scrape(date_str)
            total = fs.get("total") or {}
            d["food_calories"] = total.get("calories")
            d["food_protein"]  = total.get("protein")
            d["food_fat"]      = total.get("fat")
            d["food_carbs"]    = total.get("carbs")
        else:
            d.update({"food_calories": None, "food_protein": None, "food_fat": None, "food_carbs": None})
    except Exception:
        d.update({"food_calories": None, "food_protein": None, "food_fat": None, "food_carbs": None})

    return d


def _day_data_to_row(date_str, d):
    """Map collected data dict → sheet row list (matches SHEET_HEADERS order)."""
    return [
        date_str,
        d.get("sleep_hours"),
        d.get("sleep_score"),
        d.get("deep_min"),
        d.get("rem_min"),
        d.get("hrv"),
        d.get("hrv_weekly"),
        d.get("resting_hr"),
        d.get("resting_hr_7d"),
        d.get("bb_wake"),
        d.get("bb_current"),
        d.get("bb_net_used"),
        d.get("avg_stress"),
        d.get("max_stress"),
        d.get("steps"),
        d.get("active_calories"),
        d.get("skin_temp"),
        d.get("workouts"),
        d.get("spo2"),
        d.get("food_calories"),
        d.get("food_protein"),
        d.get("food_fat"),
        d.get("food_carbs"),
    ]


@app.route("/sheets/save-day", methods=["GET", "POST"])
@require_api_key
def sheets_save_day():
    """Collect Garmin data for a date and save/update a row in Google Sheets.
    ?date=YYYY-MM-DD (default: yesterday)
    """
    date_str = request.args.get("date", yesterday())
    try:
        ws = get_sheet()
        # Find existing row for this date
        dates_col = ws.col_values(1)  # column A = Дата
        try:
            row_idx = dates_col.index(date_str) + 1  # 1-based
            row_exists = True
        except ValueError:
            row_idx = None
            row_exists = False

        data = _collect_day_data(date_str)
        row  = _day_data_to_row(date_str, data)

        if row_exists:
            ws.update(values=[row], range_name=f"A{row_idx}", value_input_option="USER_ENTERED")
            action = "updated"
        else:
            ws.append_row(row, value_input_option="USER_ENTERED")
            row_idx = len(dates_col) + 1
            action = "appended"

        return jsonify({"status": "ok", "date": date_str, "action": action, "row": row_idx, "data": data})
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()[-500:]}), 500


@app.route("/sheets/history")
@require_api_key
def sheets_history():
    """Return last N days from Google Sheets as JSON.
    ?days=30 (default: 30)
    """
    days = int(request.args.get("days", 30))
    try:
        ws = get_sheet()
        all_rows = ws.get_all_records(expected_headers=SHEET_HEADERS)
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        filtered = [r for r in all_rows if str(r.get("Дата", "")) >= cutoff]
        return jsonify({"days": days, "count": len(filtered), "data": filtered})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

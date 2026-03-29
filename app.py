import os
import json
import datetime
import base64
import time
import requests
from functools import wraps

from flask import Flask, jsonify, request, redirect
from garminconnect import Garmin

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "")
GARMIN_TOKENS = os.environ.get("GARMIN_TOKENS", "")
FATSECRET_CLIENT_ID = os.environ.get("FATSECRET_CLIENT_ID", "")
FATSECRET_CLIENT_SECRET = os.environ.get("FATSECRET_CLIENT_SECRET", "")

_fs_token_cache = {"token": None, "expires_at": 0}

_garmin_client = None


def init_garmin():
    """Init Garmin client from OAuth tokens stored in GARMIN_TOKENS env var."""
    if not GARMIN_TOKENS:
        raise RuntimeError("GARMIN_TOKENS env variable is not set")
    client = Garmin()
    client.garth.loads(GARMIN_TOKENS)
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

    return jsonify(result)


# ── FATSECRET OAuth 1.0a ──────────────────────────────────────────────────────
from requests_oauthlib import OAuth1Session

FS_REQUEST_TOKEN_URL = "https://www.fatsecret.com/oauth/request_token"
FS_AUTHORIZE_URL     = "https://www.fatsecret.com/oauth/authorize"
FS_ACCESS_TOKEN_URL  = "https://www.fatsecret.com/oauth/access_token"
FS_API_URL           = "https://platform.fatsecret.com/rest/server.api"
FS_TOKEN_FILE        = os.path.join(os.path.dirname(__file__), "fatsecret_token.json")

_fs_oauth_temp = {}  # stores request_token during auth flow


def load_fs_token():
    if os.path.exists(FS_TOKEN_FILE):
        with open(FS_TOKEN_FILE) as f:
            return json.load(f)
    env_token = os.environ.get("FATSECRET_TOKEN")
    if env_token:
        return json.loads(env_token)
    return None


def save_fs_token(token):
    with open(FS_TOKEN_FILE, "w") as f:
        json.dump(token, f)


def fs_session():
    t = load_fs_token()
    if not t:
        raise RuntimeError("FatSecret не авторизован. Откройте /fatsecret/auth/start")
    return OAuth1Session(
        FATSECRET_CLIENT_ID,
        client_secret=FATSECRET_CLIENT_SECRET,
        resource_owner_key=t["oauth_token"],
        resource_owner_secret=t["oauth_token_secret"],
    )


def fs_api_call(method, extra_params=None):
    session = fs_session()
    params = {"method": method, "format": "json"}
    if extra_params:
        params.update(extra_params)
    resp = session.get(FS_API_URL, params=params, timeout=15)
    return resp.json()


@app.route("/fatsecret/auth/start")
def fatsecret_auth_start():
    """Step 1: get request token, redirect user to FatSecret authorize page."""
    oauth = OAuth1Session(FATSECRET_CLIENT_ID, client_secret=FATSECRET_CLIENT_SECRET,
                          callback_uri="http://127.0.0.1:5001/fatsecret/auth/callback")
    tokens = oauth.fetch_request_token(FS_REQUEST_TOKEN_URL)
    _fs_oauth_temp["oauth_token"] = tokens["oauth_token"]
    _fs_oauth_temp["oauth_token_secret"] = tokens["oauth_token_secret"]
    auth_url = oauth.authorization_url(FS_AUTHORIZE_URL)
    return redirect(auth_url)


@app.route("/fatsecret/auth/callback")
def fatsecret_auth_callback():
    """Step 2: exchange verifier for access token, save to file."""
    verifier = request.args.get("oauth_verifier")
    if not verifier:
        return jsonify({"error": "No oauth_verifier in callback", "args": dict(request.args)}), 400
    oauth = OAuth1Session(
        FATSECRET_CLIENT_ID,
        client_secret=FATSECRET_CLIENT_SECRET,
        resource_owner_key=_fs_oauth_temp.get("oauth_token"),
        resource_owner_secret=_fs_oauth_temp.get("oauth_token_secret"),
        verifier=verifier,
    )
    tokens = oauth.fetch_access_token(FS_ACCESS_TOKEN_URL)
    save_fs_token(tokens)
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

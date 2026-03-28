import os
import json
import datetime
from functools import wraps

from flask import Flask, jsonify, request
from garminconnect import Garmin

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "")
GARMIN_TOKENS = os.environ.get("GARMIN_TOKENS", "")

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


@app.route("/")
def index():
    return jsonify({
        "status": "ok",
        "endpoints": ["/sleep", "/hrv", "/body-battery", "/activities", "/weekly-stats"]
    })


@app.route("/sleep")
@require_api_key
def sleep_data():
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    data = garmin_call(lambda g: g.get_sleep_data(yesterday))
    return jsonify(data)


@app.route("/hrv")
@require_api_key
def hrv_data():
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    data = garmin_call(lambda g: g.get_hrv_data(yesterday))
    return jsonify(data)


@app.route("/body-battery")
@require_api_key
def body_battery():
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    today = datetime.date.today().isoformat()
    data = garmin_call(lambda g: g.get_body_battery(yesterday, today))
    return jsonify(data)


@app.route("/activities")
@require_api_key
def activities():
    end = datetime.date.today().isoformat()
    start = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    data = garmin_call(lambda g: g.get_activities_by_date(start, end))
    return jsonify(data)


@app.route("/weekly-stats")
@require_api_key
def weekly_stats():
    today = datetime.date.today()
    results = {}
    for i in range(7):
        day = (today - datetime.timedelta(days=i)).isoformat()
        stats = garmin_call(lambda g: g.get_stats(day))
        results[day] = {
            "totalSteps": stats.get("totalSteps"),
            "totalKilocalories": stats.get("totalKilocalories"),
            "averageStressLevel": stats.get("averageStressLevel"),
            "maxStressLevel": stats.get("maxStressLevel"),
            "restingHeartRate": stats.get("restingHeartRate"),
        }
    return jsonify(results)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

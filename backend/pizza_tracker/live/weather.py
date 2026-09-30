"""Weather, air quality, sun and moon at an HQ. Open-Meteo: free, no key, updates ~15 min."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ..collectors.http import PoliteClient
from .cache import ttl_cache

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# WMO weather interpretation codes (subset that matters for a one-word summary).
WMO = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
       51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 61: "Rain", 63: "Rain", 65: "Heavy rain",
       71: "Snow", 73: "Snow", 75: "Heavy snow", 80: "Showers", 81: "Showers", 82: "Heavy showers",
       95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm"}

_client = PoliteClient(min_interval_s=1.0, cache_ttl_s=60)


def parse_weather(forecast: dict, air: dict | None) -> dict:
    cur = forecast.get("current", {})
    daily = forecast.get("daily", {})
    return {
        "time": cur.get("time"),
        "temp_f": cur.get("temperature_2m"),
        "humidity": cur.get("relative_humidity_2m"),
        "wind_mph": cur.get("wind_speed_10m"),
        "pressure_hpa": cur.get("surface_pressure"),
        "cloud_pct": cur.get("cloud_cover"),
        "summary": WMO.get(cur.get("weather_code"), "Unknown"),
        "sunrise": (daily.get("sunrise") or [None])[0],
        "sunset": (daily.get("sunset") or [None])[0],
        "us_aqi": (air or {}).get("current", {}).get("us_aqi"),
    }


@ttl_cache(600)
def fetch_weather(lat: float, lon: float) -> dict:
    forecast = _client.get(FORECAST_URL, params={
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,surface_pressure,cloud_cover,weather_code",
        "daily": "sunrise,sunset", "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
    }).json()
    try:
        air = _client.get(AIR_URL, params={"latitude": lat, "longitude": lon, "current": "us_aqi"}).json()
    except Exception:
        air = None  # AQI is a nice-to-have; weather still renders
    return parse_weather(forecast, air)


SYNODIC_DAYS = 29.530588853
KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
PHASES = ["New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
          "Full moon", "Waning gibbous", "Last quarter", "Waning crescent"]


def moon(at: datetime | None = None) -> dict:
    """Moon phase from the mean synodic month; good to within about half a day."""
    at = at or datetime.now(timezone.utc)
    age = ((at - KNOWN_NEW_MOON).total_seconds() / 86400) % SYNODIC_DAYS
    illum = (1 - math.cos(2 * math.pi * age / SYNODIC_DAYS)) / 2
    return {"phase": PHASES[int((age / SYNODIC_DAYS) * 8 + 0.5) % 8], "illumination_pct": round(illum * 100), "age_days": round(age, 1)}

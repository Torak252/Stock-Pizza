"""`cli doctor`: one live call per data source, with a plain-English fix for each failure.

Checks are independent: one failing source never hides the others. Nothing is written to
the database.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

import httpx

from .config import get_settings

APPLE_PARK = (37.3349, -122.0090)
SEATTLE = (47.6223, -122.3366)
CONSHOHOCKEN = (40.0759, -75.3031)


@dataclass
class Check:
    name: str
    status: str  # "ok" | "fail" | "skip"
    detail: str


def _host(exc: Exception) -> str:
    req = getattr(exc, "request", None)
    return urlparse(str(req.url)).netloc if req is not None else ""


def explain(exc: Exception) -> str:
    """Turn a network exception into the most likely fix."""
    host = _host(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return f"{host} refused the request (HTTP {code}): check the API key or User-Agent"
        return f"{host} returned HTTP {code}"
    if isinstance(exc, (httpx.ConnectError, httpx.ProxyError)):
        return f"cannot reach {host or 'the host'}: network blocked or offline (allow it in your firewall/proxy)"
    if isinstance(exc, httpx.TimeoutException):
        return f"{host or 'the host'} timed out"
    return f"{type(exc).__name__}: {exc}"


def check_caltrans() -> Check:
    from .collectors.cameras import CaltransProvider

    near = CaltransProvider().nearest(*APPLE_PARK, radius_m=5000, limit=50)
    return Check("Caltrans cameras", "ok" if near else "fail",
                 f"{len(near)} cameras within 5 km of Apple Park" if near else "feed parsed but no cameras near Apple Park")


def check_wsdot() -> Check:
    if not get_settings().wsdot_access_code:
        return Check("WSDOT cameras", "skip", "set SPT_WSDOT_ACCESS_CODE (free: https://wsdot.wa.gov/traffic/api/)")
    from .collectors.cameras import WSDOTProvider

    near = WSDOTProvider().nearest(*SEATTLE, radius_m=5000, limit=50)
    return Check("WSDOT cameras", "ok" if near else "fail", f"{len(near)} cameras within 5 km of Amazon HQ")


def check_511pa() -> Check:
    key = get_settings().pa511_api_key
    if not key:
        return Check("511PA cameras", "skip", "set SPT_PA511_API_KEY (free: https://www.511pa.com/developers)")
    from .collectors.cameras import Atis511Provider

    near = Atis511Provider("www.511pa.com", key, "511pa").nearest(*CONSHOHOCKEN, radius_m=8000, limit=50)
    return Check("511PA cameras", "ok" if near else "fail",
                 f"{len(near)} cameras within 8 km of Cencora" if near else "feed parsed but no cameras near Cencora; the payload shape may differ")


def check_edgar() -> Check:
    if not get_settings().contact_email:
        return Check("SEC EDGAR", "skip", "set SPT_CONTACT_EMAIL (the SEC requires it in the User-Agent)")
    from .collectors.market import EdgarClient

    filings = EdgarClient().recent_filings("AAPL")
    return Check("SEC EDGAR", "ok", f"{len(filings)} recent 8-K/10-Q/10-K filings for AAPL")


def check_yfinance() -> Check:
    if importlib.util.find_spec("yfinance") is None:
        return Check("Yahoo prices", "skip", "pip install yfinance")
    from .collectors.market import fetch_daily_bars

    bars = fetch_daily_bars("AAPL", period="5d")
    if bars.empty:
        return Check("Yahoo prices", "fail", "no bars returned (Yahoo may be rate-limiting; retry later)")
    return Check("Yahoo prices", "ok", f"AAPL last close {bars['close'].iloc[-1]:.2f} on {bars.index[-1].date()}")


def check_overpass() -> Check:
    from .collectors.places import find_venues

    venues = find_venues(*APPLE_PARK, radius_m=3000)
    return Check("OSM venues (Overpass)", "ok", f"{len(venues)} pizza places within 3 km of Apple Park")


def check_nominatim() -> Check:
    from .collectors.geocode import geocode

    hit = geocode("One Apple Park Way, Cupertino, CA")
    return Check("OSM geocoding (Nominatim)", "ok" if hit else "fail", hit.display_name[:70] if hit else "no match")


def check_vision() -> Check:
    missing = [m for m in ("cv2", "ultralytics") if importlib.util.find_spec(m) is None]
    if missing:
        return Check("YOLO vehicle counting", "skip", 'pip install -e ".[vision]"')
    from .vision.detector import _model

    _model()  # downloads yolo11n.pt from GitHub on first use
    return Check("YOLO vehicle counting", "ok", "model loaded")


def check_weather() -> Check:
    from .live.weather import fetch_weather

    w = fetch_weather(*APPLE_PARK)
    return Check("Weather + AQI (Open-Meteo)", "ok", f"Cupertino {w['temp_f']}°F {w['summary']}, AQI {w['us_aqi']}")


def check_skies() -> Check:
    from .live.skies import fetch_skies

    sky = fetch_skies(*APPLE_PARK)
    return Check("Aircraft (ADS-B)", "ok", f"{sky['overhead']} overhead near Apple Park, {sky['bizjets']} business jets ({sky['source']})")


def check_traffic() -> Check:
    if not get_settings().tomtom_api_key:
        return Check("Traffic flow (TomTom)", "skip", "set SPT_TOMTOM_API_KEY (free tier: https://developer.tomtom.com)")
    from .live.traffic import fetch_traffic

    t = fetch_traffic(*APPLE_PARK)
    return Check("Traffic flow (TomTom)", "ok", f"{t['current_speed_mph']} mph vs {t['free_flow_speed_mph']} free-flow")


CHECKS: list[Callable[[], Check]] = [
    check_caltrans, check_wsdot, check_511pa, check_edgar, check_yfinance,
    check_overpass, check_nominatim, check_weather, check_skies, check_traffic, check_vision,
]


LABELS = {
    "check_caltrans": "Caltrans cameras", "check_wsdot": "WSDOT cameras", "check_511pa": "511PA cameras",
    "check_edgar": "SEC EDGAR", "check_yfinance": "Yahoo prices", "check_overpass": "OSM venues (Overpass)",
    "check_nominatim": "OSM geocoding (Nominatim)", "check_weather": "Weather + AQI (Open-Meteo)",
    "check_skies": "Aircraft (ADS-B)", "check_traffic": "Traffic flow (TomTom)", "check_vision": "YOLO vehicle counting",
}


def run_checks(checks: list[Callable[[], Check]] | None = None) -> list[Check]:
    results = []
    for fn in checks or CHECKS:
        name = LABELS.get(fn.__name__, fn.__name__.removeprefix("check_"))
        try:
            results.append(fn())
        except Exception as exc:  # report and keep going
            results.append(Check(name, "fail", explain(exc)))
    return results


def format_checks(results: list[Check]) -> str:
    mark = {"ok": "✓", "fail": "✗", "skip": "–"}
    width = max(len(r.name) for r in results)
    lines = [f" {mark[r.status]}  {r.name:<{width}}  {r.detail}" for r in results]
    ok = sum(r.status == "ok" for r in results)
    lines.append(f"\n{ok}/{len(results)} sources working. '–' = not configured yet; '✗' = configured but failing.")
    return "\n".join(lines)

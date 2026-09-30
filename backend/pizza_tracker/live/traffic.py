"""Road speed vs free-flow at the HQ from TomTom Flow Segment Data (free key, ~1 min fresh)."""
from __future__ import annotations

from ..collectors.http import PoliteClient
from ..config import get_settings
from .cache import ttl_cache

URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/12/json"
_client = PoliteClient(min_interval_s=0.5, cache_ttl_s=60)


def parse_flow(payload: dict) -> dict:
    f = payload.get("flowSegmentData", {})
    cur, free = f.get("currentTravelTime"), f.get("freeFlowTravelTime")
    delta = round(100 * (cur - free) / free) if cur and free else None
    return {
        "current_speed_mph": _kmh_to_mph(f.get("currentSpeed")),
        "free_flow_speed_mph": _kmh_to_mph(f.get("freeFlowSpeed")),
        "travel_time_s": cur, "free_flow_time_s": free, "vs_free_flow_pct": delta,
        "closed": bool(f.get("roadClosure")), "confidence": f.get("confidence"),
    }


def _kmh_to_mph(v):
    return round(v * 0.621371) if v is not None else None


@ttl_cache(120)
def fetch_traffic(lat: float, lon: float) -> dict:
    key = get_settings().tomtom_api_key
    if not key:
        raise LookupError("set SPT_TOMTOM_API_KEY (free tier: https://developer.tomtom.com)")
    return parse_flow(_client.get(URL, params={"point": f"{lat},{lon}", "unit": "KMPH", "key": key}).json())

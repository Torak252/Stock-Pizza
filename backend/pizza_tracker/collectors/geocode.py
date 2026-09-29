"""HQ address verification via OpenStreetMap Nominatim.

Nominatim's usage policy allows light automated use: at most 1 request/second, a real
User-Agent, and cached results. Ten HQs, run by hand, is well inside that.
"""
from __future__ import annotations

from dataclasses import dataclass

from .http import PoliteClient

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


@dataclass
class GeocodeResult:
    lat: float
    lon: float
    display_name: str
    osm_type: str | None


def parse_nominatim(payload: list) -> GeocodeResult | None:
    if not payload:
        return None
    top = payload[0]
    return GeocodeResult(float(top["lat"]), float(top["lon"]), top.get("display_name", ""), top.get("osm_type"))


def geocode(address: str, client: PoliteClient | None = None) -> GeocodeResult | None:
    client = client or PoliteClient(min_interval_s=1.1, cache_ttl_s=86400)
    resp = client.get(NOMINATIM_URL, params={"q": address, "format": "jsonv2", "limit": 1, "countrycodes": "us"})
    return parse_nominatim(resp.json())

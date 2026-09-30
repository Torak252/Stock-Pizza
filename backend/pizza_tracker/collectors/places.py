"""Discover late-night food venues near each HQ from OpenStreetMap (Overpass API).

OSM data is ODbL-licensed and Overpass explicitly allows automated queries at modest
volume, which makes it the right source for the one-time "mapping" step. Busyness for
these venues then comes from a licensed provider (see foot_traffic.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..geo import haversine_m
from .http import PoliteClient

# The main instance rate-limits hard and sometimes resets connections; mirrors run the same API.
OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
OVERPASS_URL = OVERPASS_URLS[0]
PIZZA_BRANDS = ("domino", "papa john", "pizza hut", "little caesars", "marco's", "jet's", "papa murphy")


@dataclass
class Venue:
    external_id: str
    name: str
    lat: float
    lon: float
    distance_m: float
    brand: str | None
    tags: dict


def build_query(lat: float, lon: float, radius_m: int) -> str:
    # Pizza places + anything tagged as delivery-capable fast food within the radius.
    return f"""
    [out:json][timeout:25];
    (
      node(around:{radius_m},{lat},{lon})["amenity"~"restaurant|fast_food"]["cuisine"~"pizza"];
      way(around:{radius_m},{lat},{lon})["amenity"~"restaurant|fast_food"]["cuisine"~"pizza"];
      node(around:{radius_m},{lat},{lon})["amenity"="fast_food"]["delivery"="yes"];
    );
    out center tags;
    """


def parse_overpass(payload: dict, lat: float, lon: float) -> list[Venue]:
    venues: dict[str, Venue] = {}
    for el in payload.get("elements", []):
        tags = el.get("tags", {})
        vlat = el.get("lat") or el.get("center", {}).get("lat")
        vlon = el.get("lon") or el.get("center", {}).get("lon")
        if vlat is None or vlon is None:
            continue
        name = tags.get("name", "Unnamed venue")
        brand_raw = (tags.get("brand") or name).lower()
        brand = next((b for b in PIZZA_BRANDS if b in brand_raw), None)
        ext_id = f"{el['type']}/{el['id']}"
        venues[ext_id] = Venue(ext_id, name, vlat, vlon, haversine_m(lat, lon, vlat, vlon), brand, tags)
    return sorted(venues.values(), key=lambda v: v.distance_m)


def find_venues(lat: float, lon: float, radius_m: int = 3000, client: PoliteClient | None = None) -> list[Venue]:
    # One retry per mirror: a struggling mirror should hand over quickly, not stall the whole map job.
    # Overpass queries run up to 25 s server-side ([timeout:25]), so the client must wait longer.
    client = client or PoliteClient(min_interval_s=5.0, cache_ttl_s=3600, max_retries=1, timeout_s=45)
    # GET, not POST: some proxies reset Overpass POSTs, and the query is well under URL limits.
    last_exc: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            resp = client.get(url, params={"data": build_query(lat, lon, radius_m)})
            return parse_overpass(resp.json(), lat, lon)
        except Exception as exc:
            last_exc = exc
    raise last_exc  # type: ignore[misc]

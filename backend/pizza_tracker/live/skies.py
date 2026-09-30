"""Aircraft near an HQ from community ADS-B aggregators (free, no key, ~1 s latency).

Business jets are the interesting part: a Gulfstream landing near HQ at 11 PM is a stronger
tell than any pizza order. Type designators are ICAO codes as reported by the aggregator.
"""
from __future__ import annotations

from ..collectors.http import PoliteClient
from ..geo import haversine_m
from .cache import ttl_cache

# readsb-compatible "point" endpoints; the first that answers wins.
HOSTS = ["https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}", "https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}"]

BIZJET_TYPES = {
    # Gulfstream
    "GLF2", "GLF3", "GLF4", "GLF5", "GLF6", "GA5C", "GA6C", "GA7C", "GA8C", "G150", "G280", "GALX",
    # Bombardier
    "GLEX", "GL5T", "GL7T", "GL8T", "CL30", "CL35", "CL60", "LJ31", "LJ35", "LJ40", "LJ45", "LJ55", "LJ60", "LJ70", "LJ75",
    # Cessna Citation
    "C500", "C501", "C510", "C525", "C25A", "C25B", "C25C", "C25M", "C550", "C551", "C55B", "C560", "C56X",
    "C650", "C680", "C68A", "C700", "C750",
    # Dassault Falcon
    "F2TH", "F900", "FA10", "FA20", "FA50", "FA6X", "FA7X", "FA8X",
    # Embraer, Hawker, others
    "E35L", "E50P", "E55P", "E545", "E550", "H25A", "H25B", "H25C", "HA4T", "BE40", "PRM1", "PC24", "HDJT", "EA50", "SF50",
}
TRAINER_TYPES = {"C152", "C172", "PA28", "P28A", "DA40", "DA20", "SR20", "SR22"}

_client = PoliteClient(min_interval_s=1.0, cache_ttl_s=10)


def classify(ac: dict, hq: tuple[float, float]) -> dict:
    alt = ac.get("alt_baro")
    on_ground = alt == "ground"
    alt_ft = None if on_ground or alt is None else int(alt)
    rate = ac.get("baro_rate") or ac.get("geom_rate") or 0
    t = (ac.get("t") or "").upper()
    kind = "bizjet" if t in BIZJET_TYPES else "trainer" if t in TRAINER_TYPES else "other"
    approaching = bool(alt_ft is not None and alt_ft < 8000 and rate < -300)
    dist_km = None
    if ac.get("lat") is not None and ac.get("lon") is not None:
        dist_km = round(haversine_m(hq[0], hq[1], ac["lat"], ac["lon"]) / 1000, 1)
    return {
        "hex": ac.get("hex"), "callsign": (ac.get("flight") or "").strip() or None, "reg": ac.get("r"),
        "type": t or None, "kind": kind, "lat": ac.get("lat"), "lon": ac.get("lon"), "alt_ft": alt_ft,
        "on_ground": on_ground, "track": ac.get("track"), "speed_kt": ac.get("gs"),
        "approaching": approaching, "dist_km": dist_km,
    }


def summarize(aircraft: list[dict]) -> dict:
    airborne = [a for a in aircraft if not a["on_ground"]]
    jets = [a for a in aircraft if a["kind"] == "bizjet"]
    return {
        "overhead": len(airborne),
        "bizjets": len(jets),
        "bizjets_approaching": sum(a["approaching"] for a in jets),
        "bizjets_on_ground": sum(a["on_ground"] for a in jets),
    }


@ttl_cache(20)
def fetch_skies(lat: float, lon: float, radius_nm: int = 25) -> dict:
    last_exc: Exception | None = None
    for tpl in HOSTS:
        try:
            payload = _client.get(tpl.format(lat=lat, lon=lon, nm=radius_nm)).json()
            aircraft = [classify(a, (lat, lon)) for a in payload.get("ac") or []]
            return {"source": tpl.split("/")[2], "radius_nm": radius_nm, "aircraft": aircraft, **summarize(aircraft)}
        except Exception as exc:
            last_exc = exc
    raise last_exc  # type: ignore[misc]

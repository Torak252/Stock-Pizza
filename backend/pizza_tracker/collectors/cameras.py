"""Public DOT traffic-camera discovery and snapshot fetching.

Each provider publishes an official, documented camera inventory with still-image URLs
that refresh every 1-5 minutes. We poll stills (not video) at or below that refresh rate,
which is both polite and all the resolution a vehicle-count signal needs.

Coverage for the Fortune 10 is uneven: Caltrans covers Cupertino/Mountain View and WSDOT
covers Seattle; TX, MN, AR, NE, RI and PA need their 511 / DOT feeds added as providers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..config import get_settings
from ..geo import haversine_m
from .http import PoliteClient


@dataclass
class Camera:
    provider: str
    external_id: str
    name: str
    lat: float
    lon: float
    image_url: str
    refresh_s: int = 120
    meta: dict = field(default_factory=dict)


class CameraProvider(ABC):
    name: str

    def __init__(self, client: PoliteClient | None = None):
        self.client = client or PoliteClient(cache_ttl_s=3600)

    @abstractmethod
    def fetch_inventory_payload(self) -> object: ...

    @abstractmethod
    def parse_inventory(self, payload: object) -> list[Camera]: ...

    def inventory(self) -> list[Camera]:
        return self.parse_inventory(self.fetch_inventory_payload())

    def nearest(self, lat: float, lon: float, radius_m: float = 5000, limit: int = 5) -> list[tuple[Camera, float]]:
        scored = [(c, haversine_m(lat, lon, c.lat, c.lon)) for c in self.inventory()]
        return sorted([s for s in scored if s[1] <= radius_m], key=lambda s: s[1])[:limit]


class CaltransProvider(CameraProvider):
    """Caltrans CWWP2 CCTV feed. District 4 = SF Bay Area (Apple, Alphabet)."""

    name = "caltrans"

    def __init__(self, district: int = 4, client: PoliteClient | None = None):
        super().__init__(client)
        self.district = district

    def fetch_inventory_payload(self) -> dict:
        d = f"{self.district:02d}"
        return self.client.get(f"https://cwwp2.dot.ca.gov/data/d{self.district}/cctv/cctvStatusD{d}.json").json()

    def parse_inventory(self, payload: dict) -> list[Camera]:
        cams = []
        for row in payload.get("data", []):
            c = row.get("cctv", {})
            loc = c.get("location", {})
            img = c.get("imageData", {}).get("static", {}).get("currentImageURL")
            if not img or str(c.get("inService", "true")).lower() != "true":
                continue
            try:
                lat, lon = float(loc["latitude"]), float(loc["longitude"])
            except (KeyError, ValueError):
                continue
            cams.append(
                Camera(
                    provider=self.name,
                    external_id=str(c.get("index", img)),
                    name=loc.get("locationName", "Caltrans camera"),
                    lat=lat,
                    lon=lon,
                    image_url=img,
                    refresh_s=int(c.get("imageData", {}).get("static", {}).get("currentImageUpdateFrequency", 5) or 5) * 60,
                    meta={"route": loc.get("route"), "district": self.district},
                )
            )
        return cams


class WSDOTProvider(CameraProvider):
    """WSDOT Traveler Information API (free access code required). Covers Seattle (Amazon)."""

    name = "wsdot"
    URL = "https://wsdot.wa.gov/Traffic/api/HighwayCameras/HighwayCamerasREST.svc/GetCamerasAsJson"

    def fetch_inventory_payload(self) -> list:
        code = get_settings().wsdot_access_code
        if not code:
            raise RuntimeError("SPT_WSDOT_ACCESS_CODE is not set")
        return self.client.get(self.URL, params={"AccessCode": code}).json()

    def parse_inventory(self, payload: list) -> list[Camera]:
        cams = []
        for c in payload:
            loc = c.get("CameraLocation") or {}
            if not c.get("IsActive", True) or not c.get("ImageURL"):
                continue
            cams.append(
                Camera(
                    provider=self.name,
                    external_id=str(c["CameraID"]),
                    name=c.get("Title", "WSDOT camera"),
                    lat=float(loc.get("Latitude", 0)),
                    lon=float(loc.get("Longitude", 0)),
                    image_url=c["ImageURL"],
                    meta={"road": loc.get("RoadName")},
                )
            )
        return cams


PROVIDERS_BY_STATE: dict[str, type[CameraProvider]] = {
    "CA": CaltransProvider,
    "WA": WSDOTProvider,
}


def fetch_snapshot(image_url: str, client: PoliteClient | None = None) -> bytes:
    """Fetch one still frame. Callers must not persist it unless store_camera_frames is on."""
    client = client or PoliteClient(min_interval_s=1.0, cache_ttl_s=55)
    return client.get(image_url).content

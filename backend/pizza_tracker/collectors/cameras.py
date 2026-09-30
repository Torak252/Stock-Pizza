"""Public DOT traffic-camera discovery and snapshot fetching.

Each provider publishes an official, documented camera inventory with still-image URLs
that refresh every 1-5 minutes. We poll stills (not video) at or below that refresh rate,
which is both polite and all the resolution a vehicle-count signal needs.

Providers by state (all free; only WSDOT's own API needs a key):
  CA Caltrans (stills + HLS) · WA Seattle city (SDOT, 1080p + HLS) and WSDOT · MN 511MN (HLS)
  NE Nebraska 511 · TX TxDOT Dallas/Houston (up to 1080p) · PA 511PA.
Arkansas (IDrive Arkansas) is deliberately absent: its terms forbid framing its camera images.
Anything else can be added by hand with `cli add-camera` or seed/cameras.json.
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


def _minutes(value, default: int = 5) -> int:
    """Caltrans reports refresh minutes as a string, occasionally "Not Reported"."""
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


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
                    refresh_s=_minutes(c.get("imageData", {}).get("static", {}).get("currentImageUpdateFrequency")) * 60,
                    meta={"route": loc.get("route"), "district": self.district, "direction": loc.get("direction"),
                          "video_url": c.get("imageData", {}).get("streamingVideoURL") or None},
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


class Atis511Provider(CameraProvider):
    """The '511' traveller-information platform several states share (511NY, 511PA, ...).

    GET https://{host}/api/getcameras?key=KEY&format=json. Older deployments return one image
    `Url` per camera; newer ones return a `Views` list. Both shapes are accepted.
    UNVERIFIED against 511PA from this codebase's CI: confirm the first `cli map` run finds cameras.
    """

    def __init__(self, host: str, key: str, name: str, client: PoliteClient | None = None):
        super().__init__(client)
        self.host, self.key, self.name = host, key, name

    def fetch_inventory_payload(self) -> list:
        return self.client.get(f"https://{self.host}/api/getcameras", params={"key": self.key, "format": "json"}).json()

    def parse_inventory(self, payload: list) -> list[Camera]:
        cams = []
        for c in payload:
            if c.get("Disabled") or c.get("Blocked"):
                continue
            views = [v for v in c.get("Views") or [] if v.get("Url") and str(v.get("Status", "Enabled")).lower() != "disabled"]
            url = c.get("Url") or (views[0]["Url"] if views else None)
            lat, lon = c.get("Latitude"), c.get("Longitude")
            if not url or lat is None or lon is None:
                continue
            cams.append(
                Camera(
                    provider=self.name,
                    external_id=str(c.get("ID") or c.get("Id") or url),
                    name=c.get("Name") or c.get("Location") or f"{self.name} camera",
                    lat=float(lat),
                    lon=float(lon),
                    image_url=url,
                    meta={"road": c.get("RoadwayName") or c.get("Roadway"), "direction": c.get("DirectionOfTravel")},
                )
            )
        return cams


class SeattleProvider(CameraProvider):
    """City of Seattle (SDOT) traveler map: ~650 street cameras, 720p-1080p stills plus live HLS video.

    No key. Street-level city cameras, unlike freeway DOT feeds, sit right next to campuses
    (Amazon's South Lake Union HQ has four within 300 m).
    """

    name = "sdot"
    LIST_URL = "https://web.seattle.gov/Travelers/api/Map/Data"  # zoomId=18: real positions, not cluster centroids
    VIDEO_TEMPLATE_URL = "https://web.seattle.gov/Travelers/api/Map/WowsaUrl"
    IMAGE_BASE = {"sdot": "https://www.seattle.gov/trafficcams/images/", "wsdot": "https://images.wsdot.wa.gov/nw/"}

    def fetch_inventory_payload(self) -> dict:
        payload = self.client.get(self.LIST_URL, params={"zoomId": 18, "type": 2}).json()
        try:
            payload["_video_template"] = self.client.get(self.VIDEO_TEMPLATE_URL).json()
        except Exception:
            payload["_video_template"] = None  # stills still work
        return payload

    def parse_inventory(self, payload: dict) -> list[Camera]:
        video_tpl = payload.get("_video_template")
        cams = []
        for feat in payload.get("Features") or []:
            lat, lon = feat.get("PointCoordinate") or (None, None)
            if lat is None:
                continue
            for c in feat.get("Cameras") or []:
                base = self.IMAGE_BASE.get(c.get("Type"))
                if not base or not c.get("ImageUrl"):
                    continue
                video = None
                if video_tpl and c["Type"] == "sdot" and "{stream}" in video_tpl:
                    video = video_tpl.replace("{stream}", c["ImageUrl"].rsplit(".", 1)[0] + ".stream")
                cams.append(Camera(provider=self.name, external_id=c["Id"], name=c.get("Description") or c["Id"],
                                   lat=float(lat), lon=float(lon), image_url=base + c["ImageUrl"], refresh_s=300,
                                   meta={"agency": c["Type"], "video_url": video}))
        return cams


TXDOT_ITS = "https://its.txdot.gov/its/DistrictIts"


class TxDOTProvider(CameraProvider):
    """TxDOT district ITS cameras (the system behind DriveTexas). Many are 1080p. No key.

    Snapshots come back as base64 inside JSON, so cameras get a `txdot://{district}/{id}` address
    that fetch_snapshot resolves; the API's /sources/{id}/still serves them to the browser.
    """

    def __init__(self, district: str, client: PoliteClient | None = None):
        super().__init__(client)
        self.district = district
        self.name = f"txdot-{district.lower()}"

    def fetch_inventory_payload(self) -> dict:
        return self.client.get(f"{TXDOT_ITS}/GetCctvStatusListByDistrict", params={"districtCode": self.district}).json()

    def parse_inventory(self, payload: dict) -> list[Camera]:
        from urllib.parse import quote

        cams = []
        for roadway in (payload.get("roadwayCctvStatuses") or {}).values():
            for c in roadway:
                if not c.get("hasSnapshot") or "offline" in str(c.get("statusDescription", "")).lower():
                    continue
                cams.append(Camera(provider=self.name, external_id=c["icd_Id"], name=c.get("name") or c["icd_Id"],
                                   lat=float(c["latitude"]), lon=float(c["longitude"]),
                                   image_url=f"txdot://{self.district}/{quote(c['icd_Id'], safe='')}", refresh_s=180,
                                   meta={"direction": (c.get("equipLoc") or {}).get("direction")}))
        return cams


class PA511MapProvider(CameraProvider):
    """511PA's public map list (the one its website uses): ~1,500 cameras, stills without a key.

    Video on 511PA needs an auth token, so only stills are used. Listed 100 per page.
    """

    name = "511pa"
    LIST_URL = "https://www.511pa.com/List/GetData/Cameras"

    def fetch_inventory_payload(self) -> list:
        import json

        rows, start = [], 0
        while True:
            query = {"columns": [{"data": None, "name": ""}, {"name": "sortOrder", "s": True}],
                     "order": [{"column": 1, "dir": "asc"}], "start": start, "length": 100, "search": {"value": ""}}
            page = self.client.get(self.LIST_URL, params={"lang": "en-US", "query": json.dumps(query)}).json()
            rows += page.get("data") or []
            start += 100
            if start >= int(page.get("recordsTotal") or 0) or not page.get("data"):
                return rows

    def parse_inventory(self, payload: list) -> list[Camera]:
        import re

        cams = []
        for c in payload:
            wkt = (((c.get("latLng") or {}).get("geography") or {}).get("wellKnownText")) or ""
            m = re.match(r"POINT \(([-\d.]+) ([-\d.]+)\)", wkt)
            img = next((i for i in c.get("images") or [] if not i.get("disabled") and not i.get("blocked")), None)
            if not m or not img:
                continue
            cams.append(Camera(provider=self.name, external_id=str(img["id"]),
                               name=f"{c.get('roadway') or ''} {c.get('location') or ''}".strip() or str(img["id"]),
                               lat=float(m.group(2)), lon=float(m.group(1)),
                               image_url=f"https://www.511pa.com/map/Cctv/{img['id']}", refresh_s=60,
                               meta={"direction": c.get("direction")}))
        return cams


class CastleRockProvider(CameraProvider):
    """511 sites on the Castle Rock platform (511MN, Nebraska 511, ...): public GraphQL, no key.

    Cameras are listed per bounding box; each camera's detail query adds its live HLS stream
    where the state publishes one (Minnesota does, Nebraska is stills only).
    """

    MAP_QUERY = """query MapFeatures($input: MapFeaturesArgs!) { mapFeaturesQuery(input: $input) {
      mapFeatures { title uri features { geometry } __typename
        ... on Camera { active views(limit: 5) { uri category ... on CameraView { url } } } } } }"""
    CAMERA_QUERY = """query($cameraId: ID!) { cameraQuery(cameraId: $cameraId) { camera {
      views { category ... on CameraView { url sources { type src } } } } } }"""

    def __init__(self, host: str, name: str, client: PoliteClient | None = None):
        super().__init__(client)
        self.host, self.name = host, name
        self._bbox: tuple[float, float, float, float] | None = None

    def _graphql(self, query: str, variables: dict) -> dict:
        resp = self.client.post(f"https://{self.host}/api/graphql", json=[{"query": query, "variables": variables}],
                                headers={"content-type": "application/json"})
        body = resp.json()
        return (body[0] if isinstance(body, list) else body).get("data") or {}

    def fetch_inventory_payload(self) -> dict:
        n, s_, e, w = self._bbox or (0, 0, 0, 0)
        return self._graphql(self.MAP_QUERY, {"input": {"north": n, "south": s_, "east": e, "west": w, "zoom": 15,
                                                         "layerSlugs": ["normalCameras"], "nonClusterableUris": ["dashboard"]}})

    def parse_inventory(self, payload: dict) -> list[Camera]:
        cams = []
        for f in (payload.get("mapFeaturesQuery") or {}).get("mapFeatures") or []:
            if f.get("__typename") != "Camera" or f.get("active") is False:
                continue
            still = next((v.get("url") for v in f.get("views") or [] if v.get("url")), None)
            still = still.split("?")[0] if still else None  # drop the baked-in timestamp so we always get the latest
            geom = ((f.get("features") or [{}])[0].get("geometry") or {}).get("coordinates")
            if not still or not geom:
                continue
            cams.append(Camera(provider=self.name, external_id=f["uri"].split("/")[-1], name=f.get("title") or f["uri"],
                               lat=float(geom[1]), lon=float(geom[0]), image_url=still, refresh_s=60))
        return cams

    def video_url(self, camera_id: str) -> str | None:
        data = self._graphql(self.CAMERA_QUERY, {"cameraId": camera_id})
        for v in (((data.get("cameraQuery") or {}).get("camera") or {}).get("views") or []):
            for src in v.get("sources") or []:
                if src.get("src") and "m3u8" in src["src"]:
                    return src["src"]
        return None

    def nearest(self, lat: float, lon: float, radius_m: float = 5000, limit: int = 5):
        pad = radius_m / 111_000 * 1.5
        self._bbox = (lat + pad, lat - pad, lon + pad * 1.4, lon - pad * 1.4)
        found = super().nearest(lat, lon, radius_m, limit)
        for cam, _ in found:  # one detail call per shortlisted camera, only to pick up live video
            try:
                cam.meta["video_url"] = self.video_url(cam.external_id)
            except Exception:
                pass
        return found


def providers_for_state(state: str) -> list[CameraProvider]:
    """Configured camera providers for a two-letter state; unconfigured ones are left out."""
    s = get_settings()
    if state == "CA":
        return [CaltransProvider()]
    if state == "WA":
        # City street cameras first (they're next to the campus); WSDOT freeway cameras if keyed.
        return [SeattleProvider()] + ([WSDOTProvider()] if s.wsdot_access_code else [])
    if state == "PA":
        return [Atis511Provider("www.511pa.com", s.pa511_api_key, "511pa")] if s.pa511_api_key else [PA511MapProvider()]
    if state == "TX":
        # TxDOT's Houston district already carries the Houston TranStar cameras, so no separate provider.
        return [TxDOTProvider("DAL"), TxDOTProvider("HOU")]
    if state == "MN":
        return [CastleRockProvider("511mn.org", "511mn")]
    if state == "NE":
        return [CastleRockProvider("511.nebraska.gov", "ne511")]
    return []


def fetch_snapshot(image_url: str, client: PoliteClient | None = None) -> bytes:
    """Fetch one still frame. Callers must not persist it unless store_camera_frames is on."""
    client = client or PoliteClient(min_interval_s=1.0, cache_ttl_s=55)
    if image_url.startswith("txdot://"):
        import base64
        from urllib.parse import unquote

        district, icd = image_url.removeprefix("txdot://").split("/", 1)
        data = client.get(f"{TXDOT_ITS}/GetCctvSnapshotByIcdId", params={"icdId": unquote(icd), "districtCode": district}).json()
        if not data.get("snippet"):
            raise ValueError(f"no TxDOT snapshot for {unquote(icd)}")
        return base64.b64decode(data["snippet"])
    return client.get(image_url).content


def fetch_stream_frames(playlist_url: str, count: int = 1, client: PoliteClient | None = None) -> list:
    """Decode frames from the start of the newest complete segment of an HLS stream.

    Caltrans/SDOT/MnDOT streams are 720p-1080p (vs 320x260 stills), which is what lets YOLO see
    distant cars. Segments are 0.6-5 MB, but the first keyframe sits at the start, so we fetch
    progressively larger byte ranges (96 KB is usually enough) instead of whole segments; that
    keeps a 24/7 worker to roughly 0.5 GB/day instead of ~25 GB. Requires PyAV (vision extra).
    """
    import io
    from urllib.parse import urljoin

    import av

    client = client or PoliteClient(min_interval_s=0.2, cache_ttl_s=5)

    def media_lines(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if ln and not ln.startswith("#")]

    def decode(data: bytes) -> list:
        try:
            return [f.to_ndarray(format="bgr24") for f in av.open(io.BytesIO(data)).decode(video=0)]
        except Exception:  # a truncated range can end mid-packet; whatever decoded before that is kept
            return []

    master = client.get(playlist_url)
    lines = media_lines(master.text)
    if not lines:
        raise ValueError("empty HLS playlist")
    chunklist = master
    if lines[-1].endswith(".m3u8"):  # master playlist -> variant chunklist
        chunklist = client.get(urljoin(str(master.url), lines[-1]))
    segments = media_lines(chunklist.text)
    # The newest segment may still be being written; start from the one before it.
    for seg in (segments[-2:-1] + segments[-1:] + segments[:-2][::-1]) if len(segments) > 1 else segments:
        url = urljoin(str(chunklist.url), seg)
        for size in (96 * 1024, 512 * 1024, None):
            headers = {"Range": f"bytes=0-{size - 1}"} if size else {}
            data = client._client.get(url, headers=headers).content  # bypass the response cache: ranges differ
            frames = decode(data) if data else []
            if frames:
                step = max(1, len(frames) // count)
                return frames[::step][:count]
            if not data or (size and len(data) < size):
                break  # server returned the whole (empty or short) segment already
    raise ValueError("no decodable segment in HLS stream")

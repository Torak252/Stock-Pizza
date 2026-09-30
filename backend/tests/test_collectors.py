from pizza_tracker.collectors.cameras import CaltransProvider, WSDOTProvider
from pizza_tracker.collectors.market import parse_submissions
from pizza_tracker.collectors.places import parse_overpass

APPLE = (37.3349, -122.0090)


def test_parse_overpass_dedupes_sorts_and_tags_brand():
    payload = {"elements": [
        {"type": "node", "id": 2, "lat": 37.36, "lon": -122.03, "tags": {"name": "Joe's Pizza"}},
        {"type": "way", "id": 1, "center": {"lat": 37.336, "lon": -122.010}, "tags": {"name": "Domino's", "brand": "Domino's"}},
        {"type": "node", "id": 3, "tags": {"name": "no coords"}},
    ]}
    venues = parse_overpass(payload, *APPLE)
    assert [v.name for v in venues] == ["Domino's", "Joe's Pizza"]
    assert venues[0].brand == "domino"
    assert venues[0].distance_m < venues[1].distance_m


def test_caltrans_inventory_skips_out_of_service():
    payload = {"data": [
        {"cctv": {"index": "1", "inService": "true",
                  "location": {"latitude": "37.33", "longitude": "-122.01", "locationName": "I-280 at De Anza", "route": "I-280"},
                  "imageData": {"static": {"currentImageURL": "https://example/1.jpg", "currentImageUpdateFrequency": "2"}}}},
        {"cctv": {"index": "3", "inService": "true",
                  "location": {"latitude": "37.35", "longitude": "-122.03", "locationName": "I-280 at Wolfe"},
                  "imageData": {"streamingVideoURL": "https://wzmedia.dot.ca.gov/D4/x.stream/playlist.m3u8",
                                "static": {"currentImageURL": "https://example/3.jpg", "currentImageUpdateFrequency": "Not Reported"}}}},
        {"cctv": {"index": "2", "inService": "false",
                  "location": {"latitude": "37.34", "longitude": "-122.02"},
                  "imageData": {"static": {"currentImageURL": "https://example/2.jpg"}}}},
    ]}
    cams = CaltransProvider(client=object()).parse_inventory(payload)
    assert len(cams) == 2 and cams[0].refresh_s == 120 and cams[0].meta["route"] == "I-280"
    assert cams[1].refresh_s == 300 and cams[1].meta["video_url"].endswith("playlist.m3u8")  # "Not Reported" -> default


def test_wsdot_inventory():
    payload = [{"CameraID": 9, "Title": "SR 99 at Denny", "IsActive": True, "ImageURL": "https://example/9.jpg",
                "CameraLocation": {"Latitude": 47.618, "Longitude": -122.34, "RoadName": "SR 99"}}]
    cams = WSDOTProvider(client=object()).parse_inventory(payload)
    assert cams[0].external_id == "9" and cams[0].meta["road"] == "SR 99"


def test_parse_submissions_filters_forms():
    payload = {"filings": {"recent": {
        "form": ["8-K", "4", "10-Q"],
        "accessionNumber": ["a", "b", "c"],
        "filingDate": ["2026-01-02", "2026-01-03", "2026-01-30"],
        "acceptanceDateTime": ["2026-01-02T16:05:00.000Z", "2026-01-03T10:00:00.000Z", "2026-01-30T21:30:00.000Z"],
    }}}
    out = parse_submissions(payload)
    assert [r["form"] for r in out] == ["8-K", "10-Q"]
    assert out[0]["ts"].hour == 16


def test_parse_nominatim():
    from pizza_tracker.collectors.geocode import parse_nominatim

    hit = parse_nominatim([{"lat": "37.3346", "lon": "-122.0090", "display_name": "Apple Park, Cupertino", "osm_type": "way"}])
    assert (hit.lat, hit.lon, hit.osm_type) == (37.3346, -122.009, "way")
    assert parse_nominatim([]) is None


def test_atis511_accepts_both_payload_shapes():
    from pizza_tracker.collectors.cameras import Atis511Provider

    payload = [
        {"ID": "A1", "Name": "I-476 at Conshohocken", "Latitude": 40.08, "Longitude": -75.30,
         "Url": "https://example/a1.jpg", "RoadwayName": "I-476", "DirectionOfTravel": "Northbound"},
        {"Id": 7, "Location": "I-76 at Gulph Mills", "Latitude": 40.07, "Longitude": -75.35,
         "Views": [{"Url": "https://example/off.jpg", "Status": "Disabled"}, {"Url": "https://example/b7.jpg", "Status": "Enabled"}]},
        {"ID": "gone", "Name": "disabled cam", "Latitude": 40, "Longitude": -75, "Url": "https://example/x.jpg", "Disabled": True},
        {"ID": "nocoords", "Name": "no coords", "Url": "https://example/y.jpg"},
    ]
    cams = Atis511Provider("www.511pa.com", "k", "511pa", client=object()).parse_inventory(payload)
    assert [(c.external_id, c.image_url) for c in cams] == [("A1", "https://example/a1.jpg"), ("7", "https://example/b7.jpg")]
    assert cams[0].meta == {"road": "I-476", "direction": "Northbound"} and cams[1].name == "I-76 at Gulph Mills"


def test_providers_only_when_configured(monkeypatch):
    from pizza_tracker.collectors import cameras

    keys = type("S", (), {"wsdot_access_code": "", "pa511_api_key": ""})()
    monkeypatch.setattr(cameras, "get_settings", lambda: keys)
    assert [p.name for p in cameras.providers_for_state("CA")] == ["caltrans"]
    assert [p.name for p in cameras.providers_for_state("WA")] == ["sdot"]
    assert [p.name for p in cameras.providers_for_state("PA")] == ["511pa"]  # keyless map list
    assert [p.name for p in cameras.providers_for_state("TX")] == ["txdot-dal", "txdot-hou"]
    assert [p.name for p in cameras.providers_for_state("MN")] == ["511mn"]
    keys.wsdot_access_code, keys.pa511_api_key = "w", "p"
    assert [p.name for p in cameras.providers_for_state("WA")] == ["sdot", "wsdot"]
    assert [p.name for p in cameras.providers_for_state("PA")] == ["511pa"]


def test_castle_rock_inventory_and_video():
    from pizza_tracker.collectors.cameras import CastleRockProvider

    payload = {"mapFeaturesQuery": {"mapFeatures": [
        {"__typename": "Camera", "uri": "camera/506465", "title": "US 169 SB @ Bren Rd", "active": True,
         "features": [{"geometry": {"type": "Point", "coordinates": [-93.40133, 44.89879]}}],
         "views": [{"uri": "v", "category": "VIDEO", "url": "https://public.carsprogram.org/cameras/MN/C324?1790"}]},
        {"__typename": "Camera", "uri": "camera/2", "title": "inactive", "active": False,
         "features": [{"geometry": {"coordinates": [-93.4, 44.9]}}], "views": [{"url": "https://x/2.jpg"}]},
        {"__typename": "Event", "uri": "event/9", "title": "crash"},
    ]}}
    p = CastleRockProvider("511mn.org", "511mn", client=object())
    cams = p.parse_inventory(payload)
    assert [(c.external_id, c.image_url) for c in cams] == [("506465", "https://public.carsprogram.org/cameras/MN/C324")]

    detail = {"cameraQuery": {"camera": {"views": [{"category": "VIDEO", "url": "u",
              "sources": [{"type": "application/x-mpegURL", "src": "https://video.dot.state.mn.us/public/C324.stream/playlist.m3u8"}]}]}}}
    p._graphql = lambda q, v: detail
    assert p.video_url("506465").endswith("C324.stream/playlist.m3u8")
    p._graphql = lambda q, v: {"cameraQuery": {"camera": {"views": [{"url": "x", "sources": None}]}}}
    assert p.video_url("689") is None  # Nebraska: stills only


def test_seattle_inventory():
    from pizza_tracker.collectors.cameras import SeattleProvider

    payload = {"_video_template": "https://x.streamlock.net:443/live/{stream}/playlist.m3u8", "Features": [
        {"PointCoordinate": [47.622041, -122.338456], "Cameras": [
            {"Id": "CMR-0260", "Description": "Westlake Ave N & Harrison St", "ImageUrl": "Westlake_N_Harrison_NS.jpg", "Type": "sdot"},
            {"Id": "WS-1", "Description": "I-5 @ Mercer", "ImageUrl": "005vc16678.jpg", "Type": "wsdot"}]},
        {"PointCoordinate": [47.6, -122.3], "Cameras": [{"Id": "odd", "ImageUrl": "a.jpg", "Type": "other"}]},
    ]}
    cams = SeattleProvider(client=object()).parse_inventory(payload)
    assert [c.external_id for c in cams] == ["CMR-0260", "WS-1"]
    assert cams[0].image_url == "https://www.seattle.gov/trafficcams/images/Westlake_N_Harrison_NS.jpg"
    assert cams[0].meta["video_url"] == "https://x.streamlock.net:443/live/Westlake_N_Harrison_NS.stream/playlist.m3u8"
    assert cams[1].image_url == "https://images.wsdot.wa.gov/nw/005vc16678.jpg" and cams[1].meta["video_url"] is None


def test_txdot_inventory_and_base64_snapshot(monkeypatch):
    import base64

    from pizza_tracker.collectors import cameras

    payload = {"roadwayCctvStatuses": {"SH114": [
        {"icd_Id": "SH114 @ PGBT (SH161)", "name": "SH114 @ PGBT (SH161)", "latitude": 32.893865, "longitude": -96.969583,
         "hasSnapshot": True, "statusDescription": "Device Online", "equipLoc": {"direction": "East"}},
        {"icd_Id": "SH114 @ Dead", "name": "dead", "latitude": 32.9, "longitude": -96.9, "hasSnapshot": True,
         "statusDescription": "Device Offline"},
    ]}}
    cams = cameras.TxDOTProvider("DAL", client=object()).parse_inventory(payload)
    assert [c.image_url for c in cams] == ["txdot://DAL/SH114%20%40%20PGBT%20%28SH161%29"]

    seen = {}

    class FakeClient:
        def get(self, url, params=None):
            seen.update(url=url, params=params)
            return type("R", (), {"json": lambda self: {"snippet": base64.b64encode(b"\xff\xd8jpeg").decode()}})()

    assert cameras.fetch_snapshot(cams[0].image_url, client=FakeClient()) == b"\xff\xd8jpeg"
    assert seen["params"] == {"icdId": "SH114 @ PGBT (SH161)", "districtCode": "DAL"}


def test_pa511_map_inventory():
    from pizza_tracker.collectors.cameras import PA511MapProvider

    rows = [
        {"roadway": "PA 23", "location": "PA 23 @ FAYETTE ST", "direction": "North",
         "latLng": {"geography": {"wellKnownText": "POINT (-75.31126 40.06895)"}},
         "images": [{"id": 5775, "disabled": False, "blocked": False}]},
        {"roadway": "I-76", "location": "blocked", "latLng": {"geography": {"wellKnownText": "POINT (-75.3 40.07)"}},
         "images": [{"id": 1, "blocked": True}]},
    ]
    cams = PA511MapProvider(client=object()).parse_inventory(rows)
    assert len(cams) == 1 and cams[0].image_url == "https://www.511pa.com/map/Cctv/5775"
    assert (cams[0].lat, cams[0].lon) == (40.06895, -75.31126)

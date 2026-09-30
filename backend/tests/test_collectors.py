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
    assert cameras.providers_for_state("WA") == [] and cameras.providers_for_state("PA") == []
    assert cameras.providers_for_state("TX") == []
    keys.wsdot_access_code, keys.pa511_api_key = "w", "p"
    assert [p.name for p in cameras.providers_for_state("WA")] == ["wsdot"]
    assert [p.name for p in cameras.providers_for_state("PA")] == ["511pa"]

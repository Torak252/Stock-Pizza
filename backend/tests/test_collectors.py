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
        {"cctv": {"index": "2", "inService": "false",
                  "location": {"latitude": "37.34", "longitude": "-122.02"},
                  "imageData": {"static": {"currentImageURL": "https://example/2.jpg"}}}},
    ]}
    cams = CaltransProvider(client=object()).parse_inventory(payload)
    assert len(cams) == 1 and cams[0].refresh_s == 120 and cams[0].meta["route"] == "I-280"


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

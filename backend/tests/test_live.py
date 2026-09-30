"""Live-panel parsers and logic, against payloads shaped like each upstream's documented format."""
from datetime import datetime, timezone

import pytest

from pizza_tracker.live.cache import ttl_cache
from pizza_tracker.live.filings import parse_wire
from pizza_tracker.live.skies import classify, summarize
from pizza_tracker.live.traffic import parse_flow
from pizza_tracker.live.weather import moon, parse_weather
from pizza_tracker.vision.stops import StopTracker, iou

HQ = (37.3349, -122.0090)


def test_parse_weather():
    fc = {"current": {"time": "2026-09-29T23:00", "temperature_2m": 61.2, "relative_humidity_2m": 88, "wind_speed_10m": 6.5,
                      "surface_pressure": 1013.9, "cloud_cover": 100, "weather_code": 3},
          "daily": {"sunrise": ["2026-09-29T07:02"], "sunset": ["2026-09-29T18:51"]}}
    w = parse_weather(fc, {"current": {"us_aqi": 21}})
    assert (w["summary"], w["temp_f"], w["us_aqi"], w["sunset"]) == ("Overcast", 61.2, 21, "2026-09-29T18:51")
    assert parse_weather(fc, None)["us_aqi"] is None


def test_moon_phase_known_dates():
    assert moon(datetime(2024, 4, 8, 18, 0, tzinfo=timezone.utc))["phase"] == "New moon"   # total eclipse day
    full = moon(datetime(2024, 9, 18, 2, 0, tzinfo=timezone.utc))
    assert full["phase"] == "Full moon" and full["illumination_pct"] >= 97


def test_skies_classifies_bizjets_and_approaches():
    ac = [
        {"hex": "a1", "flight": "EJA123  ", "t": "C68A", "lat": 37.36, "lon": -121.93, "alt_baro": 4200, "baro_rate": -900},
        {"hex": "a2", "flight": "UAL1", "t": "B738", "lat": 37.4, "lon": -122.0, "alt_baro": 30000, "baro_rate": 0},
        {"hex": "a3", "t": "GLF6", "lat": 37.36, "lon": -121.92, "alt_baro": "ground"},
        {"hex": "a4", "t": "C172", "alt_baro": 2500},
    ]
    out = [classify(a, HQ) for a in ac]
    assert [a["kind"] for a in out] == ["bizjet", "other", "bizjet", "trainer"]
    assert out[0]["approaching"] and out[0]["callsign"] == "EJA123" and out[0]["dist_km"] < 15
    assert out[2]["on_ground"] and not out[2]["approaching"]
    assert summarize(out) == {"overhead": 3, "bizjets": 2, "bizjets_approaching": 1, "bizjets_on_ground": 1}


def test_parse_flow():
    f = parse_flow({"flowSegmentData": {"currentSpeed": 40, "freeFlowSpeed": 64, "currentTravelTime": 140,
                                        "freeFlowTravelTime": 120, "confidence": 0.9, "roadClosure": False}})
    assert f["vs_free_flow_pct"] == 17 and f["current_speed_mph"] == 25 and not f["closed"]


def test_parse_wire():
    payload = {"filings": {"recent": {
        "form": ["4", "8-K", "10-Q", "8-K", "4"],
        "accessionNumber": ["0001-26-000005", "0001-26-000004", "0001-26-000003", "0001-26-000002", "0001-26-000001"],
        "filingDate": ["2026-09-28", "2026-09-24", "2026-08-01", "2026-07-30", "2026-07-01"],
        "acceptanceDateTime": ["2026-09-28T20:01:00.000Z", "2026-09-24T16:05:00.000Z", "2026-08-01T20:30:00.000Z",
                               "2026-07-30T20:30:00.000Z", "2026-07-01T20:00:00.000Z"],
        "primaryDocument": ["f4.xml", "ek.htm", "q.htm", "ek2.htm", "f4b.xml"],
    }}}
    w = parse_wire(payload, 320193, now=datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert w["last_8k"].startswith("2026-09-24") and w["insider_filings_7d"] == 1
    assert w["eightk_by_weekday"]["Thu"] == 2 and w["eightk_sample"] == 2
    assert w["wire"][1]["url"] == "https://www.sec.gov/Archives/edgar/data/320193/000126000004/ek.htm"


def test_ttl_cache_reuses_and_does_not_cache_errors():
    calls = []

    @ttl_cache(60)
    def f(x):
        calls.append(x)
        if x < 0:
            raise ValueError
        return x * 2

    assert f(2) == 4 and f(2) == 4 and calls == [2]
    for _ in range(2):
        with pytest.raises(ValueError):
            f(-1)
    assert calls == [2, -1, -1]


def test_short_stops():
    t = StopTracker(max_stop_s=900)
    car = ((0.1, 0.5, 0.3, 0.7), "car")
    passing = ((0.6, 0.5, 0.8, 0.7), "car")
    assert t.update([car, passing], 0) == 0    # both appear
    assert t.update([car], 120) == 0           # passer gone after one frame: not a stop
    assert t.update([car], 240) == 0           # delivery car still waiting
    assert t.update([], 360) == 1              # ...and leaves: one short stop
    parked = ((0.4, 0.1, 0.5, 0.2), "car")
    for ts in range(0, 1800, 120):
        t.update([parked], 1000 + ts)
    assert t.update([], 3000) == 0             # stayed 28 min: parked, not a drop-off
    assert iou(car[0], car[0]) == 1 and iou(car[0], passing[0]) == 0


def test_placeholder_frames_are_rejected():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from pizza_tracker.vision.detector import is_placeholder

    card = np.full((260, 320, 3), 255, np.uint8)  # "Temporarily Unavailable" style: white card, a line of text
    cv2.putText(card, "Temporarily", (40, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (80, 20, 20), 3)
    scene = np.random.default_rng(0).integers(0, 255, (260, 320, 3), dtype=np.uint8)  # textured everywhere
    assert is_placeholder(card) and is_placeholder(np.zeros((260, 320, 3), np.uint8))
    assert not is_placeholder(scene)
    assert is_placeholder(b"not an image")

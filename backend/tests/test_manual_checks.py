"""HQ verification and camera ROI editing, offline."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from pizza_tracker import db, pipeline
from pizza_tracker.api.main import app
from pizza_tracker.collectors.geocode import GeocodeResult
from pizza_tracker.models import Company, SignalSource
from pizza_tracker.seed import seed_companies


@pytest.fixture()
def Session(tmp_path):
    engine = db.make_engine(f"sqlite:///{tmp_path / 'v.db'}")
    db.init_db(engine)
    S = sessionmaker(bind=engine, expire_on_commit=False)
    with S() as s:
        seed_companies(s)
    return S


def fake_geocoder(address):
    if "Cupertino" in address:
        return GeocodeResult(37.3346, -122.0090, "Apple Park", "way")
    if "Omaha" in address:
        raise RuntimeError("timeout")
    return None


def test_verify_dry_run_does_not_write(Session):
    with Session() as s:
        rows = {r["ticker"]: r for r in pipeline.verify_hqs(s, geocoder=fake_geocoder)}
        assert rows["AAPL"]["shift_m"] == pytest.approx(33, abs=2)
        assert rows["BRK-B"]["geocoded"] is None and rows["WMT"]["geocoded"] is None
        assert not s.query(Company).filter_by(ticker="AAPL").one().coords_verified


def test_verify_apply_updates_coords_and_distances(Session):
    with Session() as s:
        apple = s.query(Company).filter_by(ticker="AAPL").one()
        s.add(SignalSource(company_id=apple.id, kind="camera", provider="caltrans", external_id="1", name="cam",
                           lat=37.3346, lon=-122.0190, distance_m=0, url="http://x/1.jpg", meta={}))
        s.commit()
        pipeline.verify_hqs(s, apply=True, geocoder=fake_geocoder)
    with Session() as s:
        apple = s.query(Company).filter_by(ticker="AAPL").one()
        assert apple.coords_verified and apple.lat == 37.3346
        assert s.query(SignalSource).one().distance_m == pytest.approx(885, abs=5)
        assert not s.query(Company).filter_by(ticker="WMT").one().coords_verified


def test_roi_roundtrip_and_validation(Session):
    with Session() as s:
        apple = s.query(Company).filter_by(ticker="AAPL").one()
        cam = SignalSource(company_id=apple.id, kind="camera", provider="caltrans", external_id="9", name="cam",
                           lat=37.33, lon=-122.01, distance_m=100, url="http://x/9.jpg", meta={"route": "I-280"})
        venue = SignalSource(company_id=apple.id, kind="venue", provider="osm", external_id="v", name="pizza",
                             lat=37.33, lon=-122.01, distance_m=100, meta={})
        s.add_all([cam, venue])
        s.commit()
        cam_id, venue_id = cam.id, venue.id

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[db.get_session] = override
    try:
        c = TestClient(app)
        assert c.put(f"/sources/{cam_id}/roi", json={"x1": 0.1, "y1": 0.5, "x2": 0.6, "y2": 0.9}).json()["roi"] == [0.1, 0.5, 0.6, 0.9]
        src = next(x for x in c.get("/companies/AAPL/sources").json() if x["id"] == cam_id)
        assert src["roi"] == [0.1, 0.5, 0.6, 0.9]
        assert c.put(f"/sources/{cam_id}/roi", json={"x1": 0.6, "y1": 0.5, "x2": 0.1, "y2": 0.9}).status_code == 422
        assert c.put(f"/sources/{cam_id}/roi", json={"x1": 0, "y1": 0, "x2": 1.5, "y2": 1}).status_code == 422
        assert c.put(f"/sources/{venue_id}/roi", json={"x1": 0, "y1": 0, "x2": 1, "y2": 1}).status_code == 404
        assert c.put(f"/sources/{cam_id}/roi").json()["roi"] is None  # no body clears it
        assert c.get(f"/sources/{cam_id}/preview").status_code == 501  # vision extra not installed here
        with Session() as s:
            assert s.get(SignalSource, cam_id).meta == {"route": "I-280"}  # other meta untouched
    finally:
        app.dependency_overrides.clear()


def test_add_manual_camera(Session):
    with Session() as s:
        src = pipeline.add_manual_camera(s, "xom", "I-45 at Rayford", "https://example/cam.jpg", 30.09, -95.43)
        assert src.provider == "manual" and 500 < src.distance_m < 1000
        same_place = pipeline.add_manual_camera(s, "MCK", "Gate cam", "https://example/gate.jpg")
        assert same_place.distance_m == 0  # defaults to the HQ point
        for args, msg in [
            (("XOM", "dup", "https://example/cam.jpg"), "already registered"),
            (("NOPE", "x", "https://example/z.jpg"), "unknown ticker"),
            (("XOM", "x", "ftp://example/z.jpg"), "http"),
        ]:
            with pytest.raises(ValueError, match=msg):
                pipeline.add_manual_camera(s, *args)


def test_disabled_cameras_are_skipped(Session, monkeypatch):
    import sys
    import types

    from pizza_tracker.collectors import cameras
    from pizza_tracker.models import ActivitySample
    from pizza_tracker.vision.detector import FrameCounts

    fake_detector = types.SimpleNamespace(count_vehicles=lambda img, roi=None: FrameCounts(4, 1, {"car": 3, "truck": 1}))
    monkeypatch.setitem(sys.modules, "pizza_tracker.vision.detector", fake_detector)
    monkeypatch.setattr(cameras, "fetch_snapshot", lambda url: b"jpeg")
    with Session() as s:
        on = pipeline.add_manual_camera(s, "XOM", "on", "https://example/on.jpg")
        off = pipeline.add_manual_camera(s, "XOM", "off", "https://example/off.jpg")
        off.meta = {"disabled": True}
        s.commit()
        assert pipeline.collect_camera_counts(s) == 1
        assert {r.source_id for r in s.query(ActivitySample)} == {on.id}


def test_enable_toggle_endpoint(Session):
    with Session() as s:
        cam_id = pipeline.add_manual_camera(s, "XOM", "c", "https://example/c.jpg").id

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[db.get_session] = override
    try:
        c = TestClient(app)
        assert c.put(f"/sources/{cam_id}/enabled", json={"enabled": False}).json() == {"id": cam_id, "enabled": False}
        assert c.get("/companies/XOM/sources").json()[0]["enabled"] is False
        c.put(f"/sources/{cam_id}/enabled", json={"enabled": True})
        assert c.get("/companies/XOM/sources").json()[0]["enabled"] is True
        with Session() as s:
            assert s.get(SignalSource, cam_id).meta == {}
    finally:
        app.dependency_overrides.clear()

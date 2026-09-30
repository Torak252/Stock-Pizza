"""End-to-end: seed -> synthetic history -> scoring -> API, on a throwaway SQLite DB."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from pizza_tracker import db, pipeline
from pizza_tracker.api.main import app
from pizza_tracker.seed import seed_companies


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    engine = db.make_engine(f"sqlite:///{tmp_path_factory.mktemp('db') / 't.db'}")
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db.init_db(engine)
    with Session() as s:
        assert seed_companies(s) == 10
        assert seed_companies(s) == 0  # idempotent
        pipeline.seed_demo(s, days=35, step_min=60, score_days=3)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[db.get_session] = override
    # No `with`: skip the startup hook, which would create tables in the default DB.
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_companies_have_latest_reading(client):
    rows = client.get("/companies").json()
    assert [r["ticker"] for r in rows][:3] == ["WMT", "AMZN", "UNH"]
    assert all(r["latest"] is not None for r in rows)


def test_readings_and_samples(client):
    assert len(client.get("/companies/AAPL/readings?hours=168").json()) >= 70
    assert len(client.get("/companies/AAPL/samples?hours=24").json()) >= 23
    assert client.get("/companies/NOPE/readings").status_code == 404


def test_spike_feed_only_off_hours_alerts(client):
    spikes = client.get("/spikes").json()
    assert all(s["off_hours"] and s["level"] != "normal" for s in spikes)


def test_market_ingest_and_study(tmp_path, monkeypatch):
    """Offline: stub yfinance/EDGAR, plant a price shock after each spike evening, check the report."""
    import numpy as np
    import pandas as pd

    from pizza_tracker.collectors import market
    from pizza_tracker.models import Company, IndexReading
    from pizza_tracker.study import format_report, run_study

    idx = pd.bdate_range("2025-01-01", periods=300, tz="America/New_York").tz_convert("UTC")
    rng = np.random.default_rng(3)
    rets = rng.normal(0, 0.004, len(idx))
    spike_days = idx[30:280:25]
    for d in spike_days:
        rets[idx.get_loc(d) + 1] = 0.05
    close = 100 * np.exp(np.cumsum(rets))
    bars = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1e6}, index=idx)

    monkeypatch.setattr(market, "fetch_daily_bars", lambda t, period="2y": bars)
    monkeypatch.setattr(market, "fetch_earnings_dates", lambda t, limit=12: [idx[100].to_pydatetime()])
    monkeypatch.setattr(pipeline, "get_settings", lambda: type("S", (), {"contact_email": ""})())

    engine = db.make_engine(f"sqlite:///{tmp_path / 'm.db'}")
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db.init_db(engine)
    with Session() as s:
        seed_companies(s)
        first = pipeline.ingest_market(s)
        assert first["bars"] == 300 * 10 and first["events"] == 10
        assert pipeline.ingest_market(s) == {"bars": 0, "events": 0}  # idempotent

        aapl = s.query(Company).filter_by(ticker="AAPL").one()
        for d in spike_days:  # 11 PM Cupertino time on each spike day
            day = d.tz_convert("America/New_York").date()  # the session date
            ts = pd.Timestamp(f"{day} 23:00", tz="America/Los_Angeles").tz_convert("UTC")
            s.add(IndexReading(ts=ts.to_pydatetime(), company_id=aapl.id, score=5, components={}, level="extreme", off_hours=True))
        s.commit()

        results = run_study(s, horizon=1)
        assert [r.ticker for r in results] == ["AAPL"]
        r = results[0]
        assert r.spike_evenings == len(spike_days)
        assert r.mean_abs_ret_spike > 3 * r.mean_abs_ret_all and r.p_value < 0.01
        assert "AAPL" in format_report(results, 1)


def test_overview_fields_and_status(client):
    from pizza_tracker.api.main import defcon_for

    rows = client.get("/companies").json()
    assert all({"last_night", "trend_24h", "sources"} <= r.keys() for r in rows)
    assert all(r["latest"]["pct_normal"] is not None for r in rows)
    assert all(r["sources"]["venues"] == 1 for r in rows)
    st = client.get("/status").json()
    assert st["mode"] == "demo" and 1 <= st["defcon"] <= 5
    assert defcon_for([]) == 5 and defcon_for(["normal", "elevated"]) == 4
    assert defcon_for(["high"]) == 3 and defcon_for(["extreme"]) == 2 and defcon_for(["extreme"] * 3) == 1


def test_init_db_adds_missing_columns(tmp_path):
    from sqlalchemy import inspect, text

    engine = db.make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:  # an index_readings table from before pct_normal existed
        conn.execute(text("CREATE TABLE index_readings (id INTEGER PRIMARY KEY, ts DATETIME, company_id INTEGER, "
                          "score FLOAT, components JSON, level VARCHAR(16), off_hours BOOLEAN)"))
    db.init_db(engine)
    assert "pct_normal" in {c["name"] for c in inspect(engine).get_columns("index_readings")}


def test_live_panel_errors_are_readable(client, monkeypatch):
    import httpx

    from pizza_tracker.live import weather

    def blocked(lat, lon):
        raise httpx.ConnectError("no", request=httpx.Request("GET", "https://api.open-meteo.com/v1/forecast"))

    monkeypatch.setattr(weather, "fetch_weather", blocked)
    r = client.get("/companies/AAPL/live/weather").json()
    assert r["ok"] is False and "api.open-meteo.com" in r["error"]
    traffic = client.get("/companies/AAPL/live/traffic").json()
    assert traffic["ok"] is False and traffic["setup"] and "SPT_TOMTOM_API_KEY" in traffic["error"]
    assert client.get("/companies/AAPL/live/nope").status_code == 404


def test_hourly_profile(client):
    h = client.get("/companies/AMZN/hourly").json()
    assert h["metric"] == "venue_busyness" and len(h["hours"]) == 24
    assert any(x["typical"] is not None for x in h["hours"])

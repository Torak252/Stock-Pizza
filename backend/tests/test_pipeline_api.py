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

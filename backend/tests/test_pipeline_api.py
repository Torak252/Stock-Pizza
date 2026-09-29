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

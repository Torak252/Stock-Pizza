"""Glue between collectors, storage and analytics. Each function is one scheduler job."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .analytics.baseline import add_local_calendar, build_baseline, pct_of_normal, robust_z
from .analytics.scoring import score_snapshot
from .collectors.foot_traffic import SyntheticProvider
from .config import get_settings
from .models import ActivitySample, Company, CorporateEvent, IndexReading, PriceBar, SignalSource

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- mapping (run rarely)
def _add_source_if_new(session: Session, src: SignalSource) -> bool:
    exists = session.scalar(select(SignalSource.id).where(
        SignalSource.company_id == src.company_id, SignalSource.kind == src.kind, SignalSource.external_id == src.external_id
    ))
    if not exists:
        session.add(src)
    return not exists


def map_venues(session: Session, radius_m: int = 3000, max_per_company: int = 8) -> int:
    from .collectors.places import find_venues

    added = 0
    for company in session.scalars(select(Company)):
        try:
            venues = find_venues(company.lat, company.lon, radius_m)
        except Exception as exc:  # one bad upstream must not stop the others
            log.warning("venue lookup failed for %s: %s", company.ticker, exc)
            continue
        for v in venues[:max_per_company]:
            added += _add_source_if_new(session, SignalSource(
                company_id=company.id, kind="venue", provider="osm", external_id=v.external_id, name=v.name,
                lat=v.lat, lon=v.lon, distance_m=round(v.distance_m), meta={"brand": v.brand, "addr": v.tags.get("addr:street")},
            ))
    session.commit()
    return added


def map_cameras(session: Session, radius_m: float = 5000) -> int:
    from .collectors.cameras import providers_for_state

    added = 0
    for company in session.scalars(select(Company)):
        state = company.hq_address.rsplit(",", 1)[-1].strip()[:2]
        for provider in providers_for_state(state):
            try:
                nearest = provider.nearest(company.lat, company.lon, radius_m)
            except Exception as exc:
                log.warning("%s camera lookup failed for %s: %s", provider.name, company.ticker, exc)
                continue
            for cam, dist in nearest:
                added += _add_source_if_new(session, SignalSource(
                    company_id=company.id, kind="camera", provider=cam.provider, external_id=cam.external_id, name=cam.name,
                    lat=cam.lat, lon=cam.lon, distance_m=round(dist), url=cam.image_url, meta=cam.meta,
                ))
    session.commit()
    return added


def add_manual_camera(session: Session, ticker: str, name: str, url: str,
                      lat: float | None = None, lon: float | None = None) -> SignalSource:
    """Register a public camera still found by hand (state DOT camera pages, city feeds, ...)."""
    import hashlib

    from .geo import haversine_m

    company = session.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise ValueError(f"unknown ticker {ticker}")
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must be an http(s) link to a still image")
    lat, lon = (company.lat, company.lon) if lat is None or lon is None else (lat, lon)
    src = SignalSource(
        company_id=company.id, kind="camera", provider="manual",
        external_id=hashlib.sha1(url.encode()).hexdigest()[:16], name=name, lat=lat, lon=lon,
        distance_m=round(haversine_m(company.lat, company.lon, lat, lon)), url=url, meta={},
    )
    if not _add_source_if_new(session, src):
        raise ValueError("that camera URL is already registered for this company")
    session.commit()
    return src


# ---------------------------------------------------------------- HQ verification (manual)
def verify_hqs(session: Session, apply: bool = False, geocoder=None) -> list[dict]:
    """Geocode each HQ address and compare it with the stored coordinates.

    With apply=True, geocoded coordinates replace the stored ones, the company is marked
    verified, and source distances are recomputed. Review the dry-run table first:
    geocoders sometimes pick a mailing address rather than the campus.
    """
    from .collectors.geocode import geocode
    from .geo import haversine_m

    geocoder = geocoder or geocode
    rows = []
    for company in session.scalars(select(Company).order_by(Company.fortune_rank)):
        try:
            hit = geocoder(company.hq_address)
        except Exception as exc:
            log.warning("geocode failed for %s: %s", company.ticker, exc)
            hit = None
        row = {"ticker": company.ticker, "address": company.hq_address, "stored": (company.lat, company.lon),
               "geocoded": None, "shift_m": None, "match": None}
        if hit:
            row.update(geocoded=(round(hit.lat, 5), round(hit.lon, 5)), match=hit.display_name,
                       shift_m=round(haversine_m(company.lat, company.lon, hit.lat, hit.lon)))
            if apply:
                company.lat, company.lon, company.coords_verified = round(hit.lat, 5), round(hit.lon, 5), True
                for src in company.sources:
                    src.distance_m = round(haversine_m(company.lat, company.lon, src.lat, src.lon))
        rows.append(row)
    session.commit()
    return rows


# ---------------------------------------------------------------- collection (every ~5 min)
# Short-stop trackers live as long as the worker process; a restart just forgets in-flight stops.
_stop_trackers: dict[int, "StopTracker"] = {}


def collect_camera_counts(session: Session, now: datetime | None = None) -> int:
    from .collectors.cameras import fetch_snapshot
    from .vision.detector import counts_from, detect_boxes
    from .vision.stops import StopTracker

    now = now or datetime.now(timezone.utc)
    n = 0
    for src in session.scalars(select(SignalSource).where(SignalSource.kind == "camera")):
        if (src.meta or {}).get("disabled"):
            continue
        try:
            detections = detect_boxes(fetch_snapshot(src.url), roi=(src.meta or {}).get("roi"))
        except Exception as exc:
            log.warning("camera %s failed: %s", src.external_id, exc)
            continue
        counts = counts_from(detections)
        stops = _stop_trackers.setdefault(src.id, StopTracker()).update(detections, now.timestamp())
        for metric, value in (("vehicle_count", counts.vehicle_count),
                              ("delivery_vehicle_count", counts.delivery_vehicle_count),
                              ("short_stops", stops)):
            session.add(ActivitySample(ts=now, company_id=src.company_id, source_id=src.id, metric=metric, value=value))
        n += 1
    session.commit()
    return n


def collect_skies(session: Session, now: datetime | None = None, radius_nm: int = 25) -> int:
    """Business jets near each HQ (ADS-B), recorded so they feed the index like any other signal."""
    from .live.skies import fetch_skies

    now = now or datetime.now(timezone.utc)
    n = 0
    for company in session.scalars(select(Company)):
        try:
            sky = fetch_skies(company.lat, company.lon, radius_nm)
        except Exception as exc:
            log.warning("skies failed for %s: %s", company.ticker, exc)
            continue
        session.add(ActivitySample(ts=now, company_id=company.id, metric="bizjet_count", value=sky["bizjets"]))
        n += 1
    session.commit()
    return n


# ---------------------------------------------------------------- scoring (every ~10 min)
def _samples_frame(session: Session, company_id: int, since: datetime) -> pd.DataFrame:
    rows = session.execute(
        select(ActivitySample.ts, ActivitySample.metric, ActivitySample.value)
        .where(ActivitySample.company_id == company_id, ActivitySample.ts >= since)
    ).all()
    return pd.DataFrame(rows, columns=["ts", "metric", "value"])


def _load_company_frame(session: Session, company: Company, since: datetime) -> pd.DataFrame:
    df = _samples_frame(session, company.id, since)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return add_local_calendar(df, company.timezone)


def _score_frame(df: pd.DataFrame, company: Company, now: datetime) -> IndexReading | None:
    """Score the current local clock hour (so far) against the same hour in past weeks."""
    s = get_settings()
    if df.empty:
        return None
    now_ts = pd.Timestamp(now)
    cutoff = now_ts.floor("h")
    local = now.astimezone(ZoneInfo(company.timezone))
    # Only the same local (weekday, hour) slot informs the baseline, and only the part of that
    # hour that has elapsed so far, so a partial hour is never compared with a full one.
    history = df[(df["ts"] < cutoff) & (df["ts"] >= now_ts - pd.Timedelta(weeks=s.baseline_weeks))
                 & (df["dow"] == local.weekday()) & (df["hour"] == local.hour) & (df["minute"] <= local.minute)]
    current = df[(df["ts"] >= cutoff) & (df["ts"] <= now_ts)]
    if current.empty or history.empty:
        return None

    # Aggregate history to one value per metric per hour so dense sources don't dominate the baseline.
    hourly = (history.assign(bucket=history["ts"].dt.floor("h"))
              .groupby(["metric", "bucket", "dow", "hour"], as_index=False)["value"].mean())
    baseline = build_baseline(hourly, min_samples=s.min_baseline_samples)
    latest = current.groupby("metric", as_index=False).agg(value=("value", "mean"))
    latest = latest.assign(dow=local.weekday(), hour=local.hour)
    scored = robust_z(latest, baseline).set_index("metric")
    z = scored["z"].to_dict()
    pcts = [pct_of_normal(m, row["value"], row["median"]) for m, row in scored.dropna(subset=["median"]).iterrows()]
    pct_normal = round(sum(pcts) / len(pcts), 1) if pcts else None

    reading = score_snapshot(z, local.hour, s.z_threshold, s.off_hours_start, s.off_hours_end)
    if reading.score is None:
        return None
    return IndexReading(ts=now, company_id=company.id, score=round(reading.score, 3),
                        components=reading.components, level=reading.level, off_hours=reading.off_hours,
                        pct_normal=pct_normal)


def score_company(session: Session, company: Company, now: datetime | None = None) -> IndexReading | None:
    now = now or datetime.now(timezone.utc)
    df = _load_company_frame(session, company, now - timedelta(weeks=get_settings().baseline_weeks))
    row = _score_frame(df, company, now)
    if row is not None:
        session.add(row)
        session.commit()
    return row


def score_all(session: Session, now: datetime | None = None) -> list[IndexReading]:
    return [r for c in session.scalars(select(Company)) if (r := score_company(session, c, now))]


# ---------------------------------------------------------------- market data (daily)
# Filings that are expected on a calendar; everything else (8-K, M&A forms) counts as a surprise.
SCHEDULED_FORMS = {"10-Q", "10-K"}


def _add_event_if_new(session: Session, ticker: str, ts: datetime, kind: str, scheduled: bool, url: str | None = None) -> bool:
    exists = session.scalar(select(CorporateEvent.id).where(
        CorporateEvent.ticker == ticker, CorporateEvent.kind == kind, CorporateEvent.ts == ts
    ))
    if not exists:
        session.add(CorporateEvent(ticker=ticker, ts=ts, kind=kind, scheduled=scheduled, url=url))
    return not exists


def ingest_market(session: Session, period: str = "2y") -> dict[str, int]:
    """Daily bars + earnings dates (yfinance) and filings (SEC EDGAR, if SPT_CONTACT_EMAIL is set)."""
    from .collectors import market

    edgar = market.EdgarClient() if get_settings().contact_email else None
    if edgar is None:
        log.info("SPT_CONTACT_EMAIL not set; skipping SEC EDGAR filings")
    counts = {"bars": 0, "events": 0}
    for company in session.scalars(select(Company)):
        t = company.ticker
        try:
            bars = market.fetch_daily_bars(t, period)
            have = set(session.scalars(select(PriceBar.ts).where(PriceBar.ticker == t, PriceBar.interval == "1d")))
            have = {h.replace(tzinfo=None) for h in have}
            for ts, row in bars.iterrows():
                ts = ts.to_pydatetime()
                if ts.replace(tzinfo=None) in have:
                    continue
                session.add(PriceBar(ticker=t, ts=ts, interval="1d", open=row.open, high=row.high,
                                     low=row.low, close=row.close, volume=row.volume))
                counts["bars"] += 1
            for ts in market.fetch_earnings_dates(t):
                counts["events"] += _add_event_if_new(session, t, ts, "earnings", scheduled=True)
        except Exception as exc:
            log.warning("yfinance failed for %s: %s", t, exc)
        if edgar:
            try:
                for f in edgar.recent_filings(t):
                    counts["events"] += _add_event_if_new(session, t, f["ts"], f["form"], f["form"] in SCHEDULED_FORMS)
            except Exception as exc:
                log.warning("EDGAR failed for %s: %s", t, exc)
        session.commit()
    return counts


# ---------------------------------------------------------------- demo data
def seed_demo(session: Session, days: int = 42, step_min: int = 30, seed: int = 7, score_days: int = 7) -> int:
    """Fill the DB with synthetic venues + history + scored readings so the UI works offline."""
    session.execute(delete(IndexReading))
    session.execute(delete(ActivitySample))
    session.commit()
    provider = SyntheticProvider(seed=seed)

    for company in session.scalars(select(Company)):
        if not any(src.kind == "venue" for src in company.sources):
            session.add(SignalSource(
                company_id=company.id, kind="venue", provider="synthetic", external_id=f"demo-{company.ticker}",
                name=f"Demo Pizza near {company.name}", lat=company.lat + 0.004, lon=company.lon + 0.004, distance_m=560,
            ))
    session.commit()

    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    t = end - timedelta(days=days)
    n = 0
    sources = list(session.scalars(select(SignalSource).where(SignalSource.kind == "venue")))
    while t <= end:
        for src in sources:
            local = t.astimezone(ZoneInfo(src.company.timezone))
            session.add(ActivitySample(ts=t, company_id=src.company_id, source_id=src.id, metric="venue_busyness",
                                       value=round(provider.live_busyness(src.name, "", local), 2)))
            n += 1
        t += timedelta(minutes=step_min)
    session.commit()

    # Score the most recent days hour-by-hour so the spike feed and charts have history.
    for company in session.scalars(select(Company)):
        df = _load_company_frame(session, company, end - timedelta(days=days))
        t = end - timedelta(days=score_days)
        while t <= end:
            if (row := _score_frame(df, company, t)) is not None:
                session.add(row)
            t += timedelta(hours=1)
    session.commit()
    return n

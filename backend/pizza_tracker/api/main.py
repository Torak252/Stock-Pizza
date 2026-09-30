"""REST API for the Next.js dashboard.

Everything is read-only except camera ROI editing. The API has no auth and is meant to stay on
localhost (uvicorn's default bind); don't expose it on a public interface.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session, init_db
from ..models import ActivitySample, Company, IndexReading, SignalSource


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Stock Pizza Tracker", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "PUT"], allow_headers=["*"])


def _latest_readings(session: Session) -> dict[int, IndexReading]:
    latest = select(IndexReading.company_id, func.max(IndexReading.ts).label("ts")).group_by(IndexReading.company_id).subquery()
    rows = session.scalars(select(IndexReading).join(
        latest, (IndexReading.company_id == latest.c.company_id) & (IndexReading.ts == latest.c.ts)
    ))
    return {r.company_id: r for r in rows}


def _iso_utc(ts: datetime) -> str:
    # SQLite drops tzinfo on the way back out; everything is stored as UTC.
    return (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)).isoformat()


def _reading_dict(r: IndexReading | None) -> dict | None:
    if r is None:
        return None
    return {"ts": _iso_utc(r.ts), "score": r.score, "level": r.level, "off_hours": r.off_hours,
            "pct_normal": r.pct_normal, "components": r.components}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


LEVEL_RANK = {"normal": 0, "elevated": 1, "high": 2, "extreme": 3}


def _last_night_peaks(session: Session, since: datetime) -> dict[int, IndexReading]:
    """Highest-scoring off-hours reading per company since `since`."""
    peaks: dict[int, IndexReading] = {}
    rows = session.scalars(select(IndexReading).where(IndexReading.ts >= since, IndexReading.off_hours.is_(True)))
    for r in rows:
        if r.company_id not in peaks or r.score > peaks[r.company_id].score:
            peaks[r.company_id] = r
    return peaks


def _trends(session: Session, since: datetime) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    rows = session.execute(
        select(IndexReading.company_id, IndexReading.ts, IndexReading.score, IndexReading.off_hours)
        .where(IndexReading.ts >= since).order_by(IndexReading.ts)
    ).all()
    for cid, ts, score, off in rows:
        out.setdefault(cid, []).append({"ts": _iso_utc(ts), "score": round(score, 2), "off_hours": off})
    return out


@app.get("/companies")
def companies(session: Session = Depends(get_session)) -> list[dict]:
    """Every HQ with its latest reading, last night's peak, a 24 h trend and source counts."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    latest, peaks, trends = _latest_readings(session), _last_night_peaks(session, since), _trends(session, since)
    counts: dict[tuple[int, str], int] = {
        (cid, kind): n for cid, kind, n in session.execute(
            select(SignalSource.company_id, SignalSource.kind, func.count()).group_by(SignalSource.company_id, SignalSource.kind)
        ).all()
    }
    return [
        {
            "ticker": c.ticker, "name": c.name, "rank": c.fortune_rank, "hq_address": c.hq_address,
            "lat": c.lat, "lon": c.lon, "timezone": c.timezone, "coords_verified": c.coords_verified,
            "latest": _reading_dict(latest.get(c.id)),
            "last_night": _reading_dict(peaks.get(c.id)),
            "trend_24h": trends.get(c.id, []),
            "sources": {"cameras": counts.get((c.id, "camera"), 0), "venues": counts.get((c.id, "venue"), 0)},
        }
        for c in session.scalars(select(Company).order_by(Company.fortune_rank))
    ]


def defcon_for(levels: list[str]) -> int:
    """5 = quiet everywhere ... 1 = several HQs at 'extreme' in the same 24 h."""
    extreme = sum(lv == "extreme" for lv in levels)
    top = max((LEVEL_RANK[lv] for lv in levels), default=0)
    if extreme >= 3:
        return 1
    return 5 - top


@app.get("/status")
def status(session: Session = Depends(get_session)) -> dict:
    """Headline state for the dashboard: DEFCON-style level and whether the data is synthetic."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    peaks = _last_night_peaks(session, since)
    demo = session.scalar(select(SignalSource.id).where(SignalSource.provider == "synthetic").limit(1)) is not None
    return {
        "mode": "demo" if demo else "live",
        "defcon": defcon_for([r.level for r in peaks.values()]),
        "hqs_elevated": sum(r.level != "normal" for r in peaks.values()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _company_or_404(session: Session, ticker: str) -> Company:
    c = session.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not c:
        raise HTTPException(404, f"unknown ticker {ticker}")
    return c


@app.get("/companies/{ticker}/sources")
def sources(ticker: str, session: Session = Depends(get_session)) -> list[dict]:
    c = _company_or_404(session, ticker)
    return [
        {"id": s.id, "kind": s.kind, "provider": s.provider, "name": s.name, "lat": s.lat, "lon": s.lon,
         "distance_m": s.distance_m, "url": s.url, "roi": (s.meta or {}).get("roi"), "video_url": (s.meta or {}).get("video_url"),
         "enabled": not (s.meta or {}).get("disabled", False)}
        for s in session.scalars(select(SignalSource).where(SignalSource.company_id == c.id).order_by(SignalSource.distance_m))
    ]


@app.get("/companies/{ticker}/readings")
def readings(ticker: str, hours: int = Query(168, le=24 * 90), session: Session = Depends(get_session)) -> list[dict]:
    c = _company_or_404(session, ticker)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = session.scalars(select(IndexReading).where(IndexReading.company_id == c.id, IndexReading.ts >= since).order_by(IndexReading.ts))
    return [_reading_dict(r) for r in rows]


@app.get("/companies/{ticker}/samples")
def samples(ticker: str, metric: str = "venue_busyness", hours: int = Query(48, le=24 * 30),
            session: Session = Depends(get_session)) -> list[dict]:
    c = _company_or_404(session, ticker)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = session.execute(
        select(ActivitySample.ts, func.avg(ActivitySample.value))
        .where(ActivitySample.company_id == c.id, ActivitySample.metric == metric, ActivitySample.ts >= since)
        .group_by(ActivitySample.ts).order_by(ActivitySample.ts)
    ).all()
    return [{"ts": _iso_utc(ts), "value": round(v, 2)} for ts, v in rows]


@app.get("/spikes")
def spikes(limit: int = Query(50, le=500), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.execute(
        select(IndexReading, Company.ticker, Company.name, Company.timezone)
        .join(Company, Company.id == IndexReading.company_id)
        .where(IndexReading.off_hours.is_(True), IndexReading.level != "normal")
        .order_by(IndexReading.ts.desc()).limit(limit)
    ).all()
    return [{"ticker": t, "name": n, "timezone": tz, **_reading_dict(r)} for r, t, n, tz in rows]


class Roi(BaseModel):
    """Gate-lane box as fractions of the frame; null clears it."""

    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self):
        if self.x2 - self.x1 < 0.02 or self.y2 - self.y1 < 0.02:
            raise ValueError("ROI must have x1 < x2 and y1 < y2, and be at least 2% of the frame on each side")
        return self


def _camera_or_404(session: Session, source_id: int) -> SignalSource:
    src = session.get(SignalSource, source_id)
    if not src or src.kind != "camera":
        raise HTTPException(404, f"no camera source {source_id}")
    return src


@app.put("/sources/{source_id}/roi")
def set_roi(source_id: int, roi: Roi | None = None, session: Session = Depends(get_session)) -> dict:
    src = _camera_or_404(session, source_id)
    meta = dict(src.meta or {})  # new dict so SQLAlchemy notices the JSON change
    if roi is None:
        meta.pop("roi", None)
    else:
        meta["roi"] = [round(v, 4) for v in (roi.x1, roi.y1, roi.x2, roi.y2)]
    src.meta = meta
    session.commit()
    return {"id": src.id, "roi": meta.get("roi")}


class Enabled(BaseModel):
    enabled: bool


@app.put("/sources/{source_id}/enabled")
def set_enabled(source_id: int, body: Enabled, session: Session = Depends(get_session)) -> dict:
    """Turn counting off for a camera that doesn't show a campus entrance (history is kept)."""
    src = _camera_or_404(session, source_id)
    meta = dict(src.meta or {})
    if body.enabled:
        meta.pop("disabled", None)
    else:
        meta["disabled"] = True
    src.meta = meta
    session.commit()
    return {"id": src.id, "enabled": body.enabled}


@app.get("/sources/{source_id}/preview", responses={200: {"content": {"image/jpeg": {}}}})
def preview(source_id: int, session: Session = Depends(get_session)) -> Response:
    """Live frame with YOLO detections and the ROI drawn, plus counts in X-Counts headers."""
    import importlib.util

    from ..pipeline import camera_frames
    from ..vision.detector import annotate

    src = _camera_or_404(session, source_id)
    if not all(importlib.util.find_spec(m) for m in ("cv2", "ultralytics")):
        raise HTTPException(501, 'preview needs the vision extra: pip install -e ".[vision]"')
    try:
        jpg, counts = annotate(camera_frames(src)[-1], roi=(src.meta or {}).get("roi"))
    except Exception as exc:
        raise HTTPException(502, f"camera fetch or detection failed: {exc}")
    return Response(jpg, media_type="image/jpeg", headers={
        "X-Vehicle-Count": str(counts.vehicle_count),
        "X-Delivery-Count": str(counts.delivery_vehicle_count),
        "Access-Control-Expose-Headers": "X-Vehicle-Count, X-Delivery-Count",
    })


# ---------------------------------------------------------------- live panels (per-HQ page)
LIVE_PANELS = ("weather", "skies", "traffic", "wire", "quote")


@app.get("/companies/{ticker}/live/{panel}")
def live_panel(ticker: str, panel: str, session: Session = Depends(get_session)) -> dict:
    """Near-real-time panel data. Upstream failures come back as ok=false with a readable reason."""
    from ..doctor import explain

    if panel not in LIVE_PANELS:
        raise HTTPException(404, f"unknown panel {panel}; one of {', '.join(LIVE_PANELS)}")
    c = _company_or_404(session, ticker)
    fetched = datetime.now(timezone.utc).isoformat()
    try:
        if panel == "weather":
            from ..live.weather import fetch_weather, moon

            data = {**fetch_weather(c.lat, c.lon), "moon": moon()}
        elif panel == "skies":
            from ..live.skies import fetch_skies

            data = fetch_skies(c.lat, c.lon)
        elif panel == "traffic":
            from ..live.traffic import fetch_traffic

            data = fetch_traffic(c.lat, c.lon)
        elif panel == "wire":
            from ..live.filings import fetch_wire

            data = fetch_wire(c.ticker)
        else:
            from ..live.quote import fetch_quote

            data = fetch_quote(c.ticker)
        return {"ok": True, "fetched_at": fetched, "data": data}
    except LookupError as exc:  # not configured
        return {"ok": False, "fetched_at": fetched, "setup": True, "error": str(exc).strip("'\"")}
    except ImportError as exc:  # optional dependency missing
        return {"ok": False, "fetched_at": fetched, "setup": True, "error": f"pip install {exc.name or 'the missing package'}"}
    except Exception as exc:
        return {"ok": False, "fetched_at": fetched, "error": explain(exc)}


HOURLY_METRICS = ("short_stops", "delivery_vehicle_count", "vehicle_count", "venue_busyness")


@app.get("/companies/{ticker}/hourly")
def hourly(ticker: str, metric: str | None = None, session: Session = Depends(get_session)) -> dict:
    """Today's activity by local hour next to the typical level for this weekday and hour."""
    import pandas as pd
    from zoneinfo import ZoneInfo

    c = _company_or_404(session, ticker)
    since = datetime.now(timezone.utc) - timedelta(weeks=8)
    # Only metrics that have ever been non-zero: a brand-new short_stops series of zeros says nothing yet.
    have = set(session.scalars(select(ActivitySample.metric).where(
        ActivitySample.company_id == c.id, ActivitySample.ts >= since, ActivitySample.value > 0).distinct()))
    metric = metric or next((m for m in HOURLY_METRICS if m in have), None)
    if metric is None:
        return {"metric": None, "hours": []}
    rows = session.execute(select(ActivitySample.ts, ActivitySample.value).where(
        ActivitySample.company_id == c.id, ActivitySample.metric == metric, ActivitySample.ts >= since)).all()
    df = pd.DataFrame(rows, columns=["ts", "value"])
    local = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(c.timezone)
    df = df.assign(date=local.dt.date, dow=local.dt.dayofweek, hour=local.dt.hour)
    today = datetime.now(ZoneInfo(c.timezone))
    cur = df[df["date"] == today.date()].groupby("hour")["value"].mean()
    past = df[(df["date"] != today.date()) & (df["dow"] == today.weekday())]
    typical = past.groupby(["date", "hour"])["value"].mean().groupby("hour").median()
    return {
        "metric": metric,
        "now_hour": today.hour,
        "hours": [{"hour": h, "today": None if h not in cur else round(float(cur[h]), 2),
                   "typical": None if h not in typical else round(float(typical[h]), 2)} for h in range(24)],
    }

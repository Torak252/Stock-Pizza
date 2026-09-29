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
    return {"ts": _iso_utc(r.ts), "score": r.score, "level": r.level, "off_hours": r.off_hours, "components": r.components}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


@app.get("/companies")
def companies(session: Session = Depends(get_session)) -> list[dict]:
    latest = _latest_readings(session)
    return [
        {
            "ticker": c.ticker, "name": c.name, "rank": c.fortune_rank, "hq_address": c.hq_address,
            "lat": c.lat, "lon": c.lon, "timezone": c.timezone, "coords_verified": c.coords_verified,
            "latest": _reading_dict(latest.get(c.id)),
        }
        for c in session.scalars(select(Company).order_by(Company.fortune_rank))
    ]


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
         "distance_m": s.distance_m, "url": s.url, "roi": (s.meta or {}).get("roi")}
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


@app.get("/sources/{source_id}/preview", responses={200: {"content": {"image/jpeg": {}}}})
def preview(source_id: int, session: Session = Depends(get_session)) -> Response:
    """Live frame with YOLO detections and the ROI drawn, plus counts in X-Counts headers."""
    import importlib.util

    from ..collectors.cameras import fetch_snapshot
    from ..vision.detector import annotate

    src = _camera_or_404(session, source_id)
    if not all(importlib.util.find_spec(m) for m in ("cv2", "ultralytics")):
        raise HTTPException(501, 'preview needs the vision extra: pip install -e ".[vision]"')
    try:
        jpg, counts = annotate(fetch_snapshot(src.url), roi=(src.meta or {}).get("roi"))
    except Exception as exc:
        raise HTTPException(502, f"camera fetch or detection failed: {exc}")
    return Response(jpg, media_type="image/jpeg", headers={
        "X-Vehicle-Count": str(counts.vehicle_count),
        "X-Delivery-Count": str(counts.delivery_vehicle_count),
        "Access-Control-Expose-Headers": "X-Vehicle-Count, X-Delivery-Count",
    })

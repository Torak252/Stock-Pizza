"""Relational schema.

`activity_samples` and `price_bars` are the high-volume tables; on Postgres they are
converted to TimescaleDB hypertables by infra/timescale_init.sql.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    fortune_rank: Mapped[int | None] = mapped_column(Integer)
    hq_address: Mapped[str] = mapped_column(String(256))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(64))
    coords_verified: Mapped[bool] = mapped_column(default=False)

    sources: Mapped[list["SignalSource"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class SignalSource(Base):
    """Anything near an HQ that we can sample: a pizza place, a DOT camera, a road segment."""

    __tablename__ = "signal_sources"
    __table_args__ = (UniqueConstraint("company_id", "kind", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # "venue" | "camera" | "traffic"
    provider: Mapped[str] = mapped_column(String(32))  # "osm" | "caltrans" | "wsdot" | "synthetic" ...
    external_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(256))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    distance_m: Mapped[float] = mapped_column(Float)
    url: Mapped[str | None] = mapped_column(String(512))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    company: Mapped[Company] = relationship(back_populates="sources")


class ActivitySample(Base):
    """One observation of one metric from one source at one time (UTC)."""

    __tablename__ = "activity_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("signal_sources.id"))
    # e.g. "venue_busyness" (0-100), "vehicle_count", "delivery_vehicle_count", "parking_occupancy"
    metric: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[float] = mapped_column(Float)


class IndexReading(Base):
    """One Pizza & Overtime Index computation. Spikes are readings with off_hours and level != normal."""

    __tablename__ = "index_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    score: Mapped[float] = mapped_column(Float)  # composite Pizza & Overtime Index (z units)
    components: Mapped[dict] = mapped_column(JSON, default=dict)  # per-metric z-scores
    level: Mapped[str] = mapped_column(String(16))  # "normal" | "elevated" | "high" | "extreme"
    off_hours: Mapped[bool] = mapped_column(default=False)


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("ticker", "ts", "interval"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    interval: Mapped[str] = mapped_column(String(8), default="1d")
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)


class CorporateEvent(Base):
    """Earnings dates, SEC filings (8-K, 10-Q, 10-K), announced M&A — the 'ground truth' labels."""

    __tablename__ = "corporate_events"
    __table_args__ = (UniqueConstraint("ticker", "kind", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # "earnings" | "8-K" | "10-Q" | "10-K" ...
    scheduled: Mapped[bool] = mapped_column(default=False)  # known in advance (earnings) vs surprise
    url: Mapped[str | None] = mapped_column(String(512))

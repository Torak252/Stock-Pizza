"""Research report: do off-hours spikes precede price moves or surprise filings?

Spikes are grouped into "spike evenings" in HQ local time (a 1 AM reading belongs to the
previous evening), then tested per ticker against that ticker's own history.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics.correlation import precedence_rate, volatility_study
from .config import get_settings
from .models import Company, CorporateEvent, IndexReading, PriceBar


@dataclass
class TickerStudy:
    ticker: str
    spike_evenings: int
    unexplained: int  # evenings with no scheduled event (earnings/10-Q/10-K) within the window
    mean_abs_ret_spike: float
    mean_abs_ret_all: float
    p_value: float
    surprise_rate: float  # share of spike evenings followed by a surprise filing
    surprise_base_rate: float  # same share for every trading day


def spike_evenings(session: Session, company: Company) -> pd.DatetimeIndex:
    rows = session.scalars(select(IndexReading.ts).where(
        IndexReading.company_id == company.id, IndexReading.off_hours.is_(True), IndexReading.level != "normal"
    )).all()
    if not rows:
        return pd.DatetimeIndex([])
    local = pd.to_datetime(rows, utc=True).tz_convert(company.timezone)
    # Shift past the end of the off-hours window so 1 AM counts toward the previous evening.
    evening = (local - timedelta(hours=get_settings().off_hours_end + 1)).tz_localize(None).normalize()
    return pd.DatetimeIndex(sorted(set(evening)))


def _event_dates(session: Session, ticker: str, scheduled: bool) -> pd.DatetimeIndex:
    rows = session.scalars(select(CorporateEvent.ts).where(
        CorporateEvent.ticker == ticker, CorporateEvent.scheduled.is_(scheduled)
    )).all()
    return pd.DatetimeIndex(pd.to_datetime(rows, utc=True).tz_localize(None).normalize()) if rows else pd.DatetimeIndex([])


def study_ticker(session: Session, company: Company, horizon: int = 5, within_days: int = 10) -> TickerStudy | None:
    bars = session.execute(select(PriceBar.ts, PriceBar.close).where(
        PriceBar.ticker == company.ticker, PriceBar.interval == "1d"
    ).order_by(PriceBar.ts)).all()
    spikes = spike_evenings(session, company)
    if len(bars) < horizon + 20 or len(spikes) == 0:
        return None
    close = pd.Series([c for _, c in bars], index=pd.to_datetime([t for t, _ in bars], utc=True).tz_localize(None).normalize())
    close = close[~close.index.duplicated(keep="last")]

    scheduled = _event_dates(session, company.ticker, scheduled=True)
    surprise = _event_dates(session, company.ticker, scheduled=False)
    explained = pd.Series([len(scheduled) > 0 and bool(((scheduled >= d) & (scheduled <= d + timedelta(days=within_days))).any())
                           for d in spikes], dtype=bool)
    vol = volatility_study(close, spikes, horizon=horizon)
    return TickerStudy(
        ticker=company.ticker,
        spike_evenings=len(spikes),
        unexplained=int((~explained).sum()),
        mean_abs_ret_spike=vol.mean_abs_ret_spike,
        mean_abs_ret_all=vol.mean_abs_ret_all,
        p_value=vol.p_value,
        surprise_rate=precedence_rate(spikes, surprise, within_days),
        surprise_base_rate=precedence_rate(close.index, surprise, within_days),
    )


def run_study(session: Session, horizon: int = 5, within_days: int = 10) -> list[TickerStudy]:
    return [r for c in session.scalars(select(Company).order_by(Company.fortune_rank))
            if (r := study_ticker(session, c, horizon, within_days))]


def format_report(results: list[TickerStudy], horizon: int) -> str:
    if not results:
        return "Not enough data yet: need price bars (cli market) and at least one off-hours spike per ticker."
    head = f"{'ticker':<7}{'nights':>7}{'unexpl':>7}{f'|r{horizon}d| spike':>14}{'|r| all':>9}{'p':>7}{'8-K after':>11}{'base':>7}"
    lines = [head, "-" * len(head)]
    for r in results:
        lines.append(f"{r.ticker:<7}{r.spike_evenings:>7}{r.unexplained:>7}{r.mean_abs_ret_spike:>14.4f}"
                     f"{r.mean_abs_ret_all:>9.4f}{r.p_value:>7.3f}{r.surprise_rate:>11.2f}{r.surprise_base_rate:>7.2f}")
    lines.append("p = permutation test vs random days. With 10 tickers, expect ~1 p < 0.1 by chance alone.")
    return "\n".join(lines)

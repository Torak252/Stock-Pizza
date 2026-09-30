"""Last price and next earnings date (Yahoo via yfinance; research use)."""
from __future__ import annotations

from datetime import datetime, timezone

from .cache import ttl_cache


@ttl_cache(60)
def fetch_quote(ticker: str) -> dict:
    import yfinance as yf

    t = yf.Ticker(ticker)
    fi = t.fast_info
    last, prev = fi.get("lastPrice"), fi.get("previousClose")
    nxt = None
    try:
        dates = t.get_earnings_dates(limit=8)
        now = datetime.now(timezone.utc)
        future = sorted(d.to_pydatetime() for d in dates.index if d.to_pydatetime() > now) if dates is not None else []
        past = sorted(d.to_pydatetime() for d in dates.index if d.to_pydatetime() <= now) if dates is not None else []
        nxt = {"next": future[0].isoformat() if future else None, "last": past[-1].isoformat() if past else None}
    except Exception:
        pass
    return {
        "last": round(last, 2) if last else None,
        "change_pct": round(100 * (last - prev) / prev, 2) if last and prev else None,
        "earnings": nxt,
    }

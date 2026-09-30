"""Market data and corporate-event labels.

Prices: yfinance (unofficial, fine for research; swap to Polygon/Alpaca for production).
Filings: SEC EDGAR submissions API — official, free, requires a descriptive User-Agent
with contact email and <= 10 requests/second.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..config import get_settings
from .http import PoliteClient

EDGAR_TICKERS = "https://www.sec.gov/files/company_tickers.json"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
TRACKED_FORMS = {"8-K", "10-Q", "10-K", "SC 13D", "S-4", "DEFM14A"}


def fetch_daily_bars(ticker: str, period: str = "2y") -> pd.DataFrame:
    import yfinance as yf  # imported lazily: heavy, and only the worker needs it

    df = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
    # The current session's bar can be all-NaN until Yahoo fills it in.
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    df.index = df.index.tz_convert("UTC")
    return df


def fetch_earnings_dates(ticker: str, limit: int = 12) -> list[datetime]:
    import yfinance as yf

    df = yf.Ticker(ticker).get_earnings_dates(limit=limit)
    if df is None or df.empty:
        return []
    return [ts.tz_convert("UTC").to_pydatetime() for ts in df.index]


class EdgarClient:
    def __init__(self, client: PoliteClient | None = None):
        if not get_settings().contact_email:
            raise RuntimeError("SEC requires a contact email: set SPT_CONTACT_EMAIL")
        # 0.15s spacing keeps us under the SEC's 10 req/s fair-access limit.
        self.client = client or PoliteClient(min_interval_s=0.15, cache_ttl_s=600)
        self._cik_map: dict[str, int] | None = None

    def cik_for(self, ticker: str) -> int:
        if self._cik_map is None:
            data = self.client.get(EDGAR_TICKERS).json()
            self._cik_map = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
        t = ticker.upper()
        for candidate in (t, t.replace("-", "."), t.replace(".", "-")):  # Yahoo "BRK-B" vs SEC spellings
            if candidate in self._cik_map:
                return self._cik_map[candidate]
        raise KeyError(f"{ticker} not in SEC ticker list")

    def recent_filings(self, ticker: str) -> list[dict]:
        return parse_submissions(self.client.get(EDGAR_SUBMISSIONS.format(cik=self.cik_for(ticker))).json())


def parse_submissions(payload: dict) -> list[dict]:
    recent = payload.get("filings", {}).get("recent", {})
    out = []
    for form, acc, filed, accepted in zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("filingDate", []),
        recent.get("acceptanceDateTime", recent.get("filingDate", [])),
    ):
        if form not in TRACKED_FORMS:
            continue
        ts = pd.Timestamp(accepted or filed)
        ts = ts.tz_localize(timezone.utc) if ts.tzinfo is None else ts.tz_convert(timezone.utc)
        out.append({"form": form, "accession": acc, "ts": ts.to_pydatetime()})
    return out

"""SEC EDGAR as a live wire: recent filings, insider (Form 4) activity, and filing-day habits.

EDGAR's submissions JSON updates within minutes of acceptance. Fair access: <= 10 req/s with
a contact email in the User-Agent (handled by EdgarClient).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

import pandas as pd

from ..collectors.market import EdgarClient
from .cache import ttl_cache

WIRE_FORMS = {"8-K", "10-Q", "10-K", "4", "SC 13D", "SC 13G", "S-4", "DEFM14A", "425", "8-K/A"}
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
_edgar: EdgarClient | None = None


def _client() -> EdgarClient:
    global _edgar
    if _edgar is None:
        _edgar = EdgarClient()
    return _edgar


def parse_wire(payload: dict, cik: int, now: datetime | None = None, limit: int = 25) -> dict:
    now = now or datetime.now(timezone.utc)
    r = payload.get("filings", {}).get("recent", {})
    rows = []
    for form, acc, filed, accepted, doc in zip(
        r.get("form", []), r.get("accessionNumber", []), r.get("filingDate", []),
        r.get("acceptanceDateTime", r.get("filingDate", [])), r.get("primaryDocument", [""] * len(r.get("form", []))),
    ):
        ts = pd.Timestamp(accepted or filed)
        ts = (ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")).to_pydatetime()
        rows.append({"form": form, "ts": ts, "url": ARCHIVE.format(cik=cik, acc=acc.replace("-", ""), doc=doc) if doc else None})

    eightk = [x for x in rows if x["form"] in ("8-K", "8-K/A")]
    week = now - timedelta(days=7)
    weekday = Counter(x["ts"].strftime("%a") for x in eightk)
    return {
        "wire": [{**x, "ts": x["ts"].isoformat()} for x in rows if x["form"] in WIRE_FORMS][:limit],
        "last_8k": eightk[0]["ts"].isoformat() if eightk else None,
        "insider_filings_7d": sum(1 for x in rows if x["form"] == "4" and x["ts"] >= week),
        "eightk_by_weekday": {d: weekday.get(d, 0) for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
        "eightk_sample": len(eightk),
    }


@ttl_cache(300)
def fetch_wire(ticker: str) -> dict:
    c = _client()
    cik = c.cik_for(ticker)
    from ..collectors.market import EDGAR_SUBMISSIONS

    return parse_wire(c.client.get(EDGAR_SUBMISSIONS.format(cik=cik)).json(), cik)

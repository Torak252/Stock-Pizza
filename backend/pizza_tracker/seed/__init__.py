"""Load the Fortune 10 starter set.

Ranks follow the 2025 Fortune 500 list. Coordinates were checked against OpenStreetMap on
2026-09-30; each row records its source, and anything unconfirmed ships with coords_verified=false.
"""
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Company

SEED_FILE = Path(__file__).with_name("fortune10.json")


def seed_companies(session: Session) -> int:
    rows = json.loads(SEED_FILE.read_text())
    added = 0
    for row in rows:
        if session.scalar(select(Company).where(Company.ticker == row["ticker"])):
            continue
        session.add(
            Company(
                ticker=row["ticker"],
                name=row["name"],
                fortune_rank=row["rank"],
                hq_address=row["hq_address"],
                lat=row["lat"],
                lon=row["lon"],
                timezone=row["timezone"],
                coords_verified=row.get("coords_verified", False),
            )
        )
        added += 1
    session.commit()
    return added

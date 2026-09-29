"""Load the Fortune 10 starter set.

Ranks follow the 2025 Fortune 500 list; coordinates are approximate campus centroids and
are stored with coords_verified=False until someone checks them against the real entrances.
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
            )
        )
        added += 1
    session.commit()
    return added

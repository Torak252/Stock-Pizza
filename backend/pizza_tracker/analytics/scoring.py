"""Pizza & Overtime Index (POI).

Per-metric robust z-scores are fused with a weighted Stouffer combination so that several
moderately elevated signals (busy pizza place + more cars at the gate + delivery vans)
outrank one noisy sensor. Only off-hours observations (local 19:00-03:00 by default) can
raise an alert; daytime values are still scored so the dashboard can show them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# How much we trust each signal. Delivery vehicles at the gate are the most specific.
DEFAULT_WEIGHTS = {
    "delivery_vehicle_count": 1.5,
    "venue_busyness": 1.0,
    "vehicle_count": 0.8,
    "parking_occupancy": 1.2,
}

LEVELS = ((4.0, "extreme"), (3.0, "high"), (2.0, "elevated"))


def is_off_hours(local_hour: int, start: int = 19, end: int = 3) -> bool:
    """True inside [start, end) where the window may wrap past midnight."""
    if start <= end:
        return start <= local_hour < end
    return local_hour >= start or local_hour < end


def combine_z(z_by_metric: dict[str, float], weights: dict[str, float] | None = None) -> float | None:
    weights = weights or DEFAULT_WEIGHTS
    pairs = [(z, weights.get(m, 1.0)) for m, z in z_by_metric.items() if z is not None and not math.isnan(z)]
    if not pairs:
        return None
    num = sum(w * z for z, w in pairs)
    den = math.sqrt(sum(w * w for _, w in pairs))
    return num / den


def level_for(score: float | None, threshold: float = 2.0) -> str:
    if score is None or score < threshold:
        return "normal"
    for cutoff, name in LEVELS:
        if score >= max(cutoff, threshold):
            return name
    return "elevated"


@dataclass
class IndexReading:
    score: float | None
    level: str
    off_hours: bool
    components: dict[str, float]

    @property
    def is_alert(self) -> bool:
        return self.off_hours and self.level != "normal"


def score_snapshot(
    z_by_metric: dict[str, float],
    local_hour: int,
    threshold: float = 2.0,
    off_start: int = 19,
    off_end: int = 3,
    weights: dict[str, float] | None = None,
) -> IndexReading:
    score = combine_z(z_by_metric, weights)
    return IndexReading(
        score=score,
        level=level_for(score, threshold),
        off_hours=is_off_hours(local_hour, off_start, off_end),
        components={k: round(v, 3) for k, v in z_by_metric.items() if v is not None and not math.isnan(v)},
    )

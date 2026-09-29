"""Per-company 'Normal Activity Index': robust seasonal baselines.

Each observation is compared only with past observations of the same company, metric,
local day-of-week and local hour. We use median / MAD rather than mean / std so that the
very spikes we are hunting for do not inflate the baseline and mask themselves.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MAD_TO_SIGMA = 1.4826

# Smallest believable noise level per metric, in the metric's own units. Busyness is a 0-100
# score whose providers quantise to ~5 points; camera counts jitter by a couple of vehicles.
METRIC_SCALE_FLOORS = {"venue_busyness": 5.0, "vehicle_count": 2.0, "delivery_vehicle_count": 1.0, "parking_occupancy": 3.0}


def add_local_calendar(df: pd.DataFrame, tz: str) -> pd.DataFrame:
    """Expects a UTC `ts` column; adds local `dow`, `hour` and `minute`."""
    local = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(tz)
    return df.assign(dow=local.dt.dayofweek, hour=local.dt.hour, minute=local.dt.minute)


def build_baseline(
    history: pd.DataFrame, min_samples: int = 4, scale_floor: float = 1.0, rel_floor: float = 0.1,
    metric_floors: dict[str, float] | None = None,
) -> pd.DataFrame:
    """history: columns [metric, dow, hour, value] -> baseline indexed by (metric, dow, hour).

    With only a few weeks of history the MAD of a slot can be tiny by chance, so the scale is
    floored at both an absolute value and a fraction of the median; otherwise ordinary noise
    would read as z > 2. `metric_floors` overrides `scale_floor` per metric.
    """
    keys = ["metric", "dow", "hour"]
    g = history.groupby(keys)["value"]
    abs_dev = (history["value"] - g.transform("median")).abs()
    mad = abs_dev.groupby([history[k] for k in keys]).median()
    med = g.median()
    floors = METRIC_SCALE_FLOORS if metric_floors is None else metric_floors
    abs_floor = med.index.get_level_values("metric").map(lambda m: floors.get(m, scale_floor)).to_numpy()
    scale = np.maximum(np.maximum(mad * MAD_TO_SIGMA, abs_floor), rel_floor * med.abs())
    out = pd.DataFrame({"median": med, "scale": scale, "n": g.size()})
    return out[out["n"] >= min_samples]


def robust_z(current: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """current: columns [metric, dow, hour, value] -> same rows plus `z` (NaN when no baseline)."""
    merged = current.join(baseline, on=["metric", "dow", "hour"])
    return merged.assign(z=(merged["value"] - merged["median"]) / merged["scale"])

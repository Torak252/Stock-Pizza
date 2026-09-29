"""Event study: do off-hours spikes precede price moves or corporate events?

Two questions, each answered against a permutation null so we don't fool ourselves:

1. Volatility: is |forward return| after spike nights larger than after random nights?
2. Precedence: are spikes followed by an 8-K / M&A filing within k days more often than
   random nights are?

Scheduled earnings are reported separately: late nights before a known earnings date are
expected and already priced in, so the interesting signal is spikes *not* explained by one.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StudyResult:
    n_spikes: int
    horizon_days: int
    mean_abs_ret_spike: float
    mean_abs_ret_all: float
    p_value: float


def forward_abs_returns(close: pd.Series, horizon: int) -> pd.Series:
    """|log(close[t+h] / close[t])| indexed by trading date t."""
    return np.log(close.shift(-horizon) / close).abs().dropna()


def align_to_trading_days(spike_dates: pd.DatetimeIndex, trading_days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Map each spike evening to the last session that closed before it.

    Forward returns are then measured from a price nobody could have traded on the spike yet:
    a Monday-night spike is measured from Monday's close, a Saturday spike from Friday's.
    """
    pos = trading_days.searchsorted(spike_dates.normalize(), side="right") - 1
    pos = pos[pos >= 0]
    return trading_days[np.unique(pos)]


def volatility_study(
    close: pd.Series, spike_dates: pd.DatetimeIndex, horizon: int = 5, n_perm: int = 5000, seed: int = 0
) -> StudyResult:
    fwd = forward_abs_returns(close, horizon)
    days = align_to_trading_days(spike_dates, fwd.index)
    if len(days) == 0:
        return StudyResult(0, horizon, float("nan"), float(fwd.mean()), float("nan"))
    observed = fwd.loc[days].mean()
    rng = np.random.default_rng(seed)
    values = fwd.to_numpy()
    null = np.array([rng.choice(values, size=len(days), replace=False).mean() for _ in range(n_perm)])
    p = (np.sum(null >= observed) + 1) / (n_perm + 1)
    return StudyResult(len(days), horizon, float(observed), float(fwd.mean()), float(p))


def precedence_rate(
    spike_dates: pd.DatetimeIndex, event_dates: pd.DatetimeIndex, within_days: int = 10
) -> float:
    """Fraction of spikes followed by at least one event within `within_days` calendar days."""
    if len(spike_dates) == 0:
        return float("nan")
    if len(event_dates) == 0:
        return 0.0
    ev = event_dates.normalize().sort_values()
    spk = spike_dates.normalize()
    idx = np.minimum(ev.searchsorted(spk, side="left"), len(ev) - 1)
    nxt = ev[idx]
    hit = (nxt >= spk) & (nxt - spk <= pd.Timedelta(days=within_days))
    return float(np.asarray(hit).mean())

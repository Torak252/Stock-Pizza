import math

import numpy as np
import pandas as pd
import pytest

from pizza_tracker.analytics.baseline import add_local_calendar, build_baseline, robust_z
from pizza_tracker.analytics.correlation import align_to_trading_days, precedence_rate, volatility_study
from pizza_tracker.analytics.scoring import combine_z, is_off_hours, level_for, score_snapshot


@pytest.mark.parametrize("hour,expected", [(18, False), (19, True), (23, True), (0, True), (2, True), (3, False), (12, False)])
def test_off_hours_wraps_midnight(hour, expected):
    assert is_off_hours(hour, 19, 3) is expected


def test_combine_z_stouffer():
    assert combine_z({"a": 2.0, "b": 2.0}, {"a": 1, "b": 1}) == pytest.approx(4 / math.sqrt(2))
    assert combine_z({"a": float("nan")}) is None
    assert combine_z({}) is None


def test_levels():
    assert level_for(1.9) == "normal"
    assert level_for(2.1) == "elevated"
    assert level_for(3.5) == "high"
    assert level_for(4.2) == "extreme"
    assert level_for(None) == "normal"


def test_daytime_spike_is_not_an_alert():
    assert not score_snapshot({"venue_busyness": 5.0}, local_hour=13).is_alert
    assert score_snapshot({"venue_busyness": 5.0}, local_hour=23).is_alert


def test_local_calendar_uses_hq_timezone():
    df = pd.DataFrame({"ts": [pd.Timestamp("2026-01-06 05:00", tz="UTC")]})  # Tue 05:00 UTC
    out = add_local_calendar(df, "America/Los_Angeles")  # -> Mon 21:00 PST
    assert (out["dow"].iloc[0], out["hour"].iloc[0]) == (0, 21)


def test_robust_baseline_flags_spike_and_ignores_outlier_in_history():
    hist = pd.DataFrame({
        "metric": ["venue_busyness"] * 8, "dow": [4] * 8, "hour": [22] * 8,
        "value": [10, 11, 9, 10, 12, 10, 95, 11],  # one past crunch shouldn't blow up the baseline
    })
    base = build_baseline(hist, min_samples=4, metric_floors={})
    cur = pd.DataFrame({"metric": ["venue_busyness", "venue_busyness"], "dow": [4, 4], "hour": [22, 22], "value": [10.5, 40]})
    z = robust_z(cur, base)["z"].tolist()
    assert abs(z[0]) < 1
    assert z[1] > 10


def test_baseline_requires_min_samples():
    hist = pd.DataFrame({"metric": ["m"] * 2, "dow": [0, 0], "hour": [1, 1], "value": [1, 2]})
    assert build_baseline(hist, min_samples=4).empty


def test_spike_maps_to_last_close_before_it():
    days = pd.bdate_range("2026-03-02", periods=10, tz="UTC")
    sat, tue = pd.Timestamp("2026-03-07", tz="UTC"), pd.Timestamp("2026-03-10", tz="UTC")
    out = align_to_trading_days(pd.DatetimeIndex([sat, tue]), days)
    assert list(out) == [pd.Timestamp("2026-03-06", tz="UTC"), tue]  # Friday, and Tuesday itself


def test_volatility_study_detects_planted_effect():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2024-01-01", periods=400, tz="UTC")
    rets = rng.normal(0, 0.005, len(idx))
    spikes = idx[20:380:30]
    for d in spikes:  # plant a big move in the session right after each spike evening
        rets[idx.get_loc(d) + 1] = 0.06
    close = pd.Series(100 * np.exp(np.cumsum(rets)), index=idx)
    res = volatility_study(close, spikes, horizon=2, n_perm=2000)
    assert res.n_spikes == len(spikes)
    assert res.mean_abs_ret_spike > 3 * res.mean_abs_ret_all
    assert res.p_value < 0.01


def test_precedence_rate():
    spikes = pd.DatetimeIndex(["2026-01-01", "2026-02-01", "2026-03-01"], tz="UTC")
    events = pd.DatetimeIndex(["2026-01-05", "2026-03-30"], tz="UTC")
    assert precedence_rate(spikes, events, within_days=10) == pytest.approx(1 / 3)


def test_metric_floor_stops_near_zero_noise_from_spiking():
    hist = pd.DataFrame({"metric": ["venue_busyness"] * 6, "dow": [1] * 6, "hour": [6] * 6, "value": [0, 1, 0, 2, 0, 1]})
    cur = pd.DataFrame({"metric": ["venue_busyness"], "dow": [1], "hour": [6], "value": [8.0]})
    assert robust_z(cur, build_baseline(hist))["z"].iloc[0] < 2

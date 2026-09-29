"""Venue busyness providers.

Google Popular Times has no public API and scraping Maps violates Google's ToS, so it is
intentionally NOT implemented. Use a licensed provider instead:

  * BestTimeProvider — BestTime.app live + forecast busyness per venue (paid, per-call).
  * SyntheticProvider — deterministic fake data so the pipeline and UI run end-to-end
    before any paid key exists. Never mix its output with real data in the same DB.
"""
from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from datetime import datetime

from ..config import get_settings
from .http import PoliteClient


class FootTrafficProvider(ABC):
    name: str

    @abstractmethod
    def live_busyness(self, venue_name: str, venue_address: str, at: datetime) -> float | None:
        """Return busyness on a 0-100 scale, or None if unavailable."""


class BestTimeProvider(FootTrafficProvider):
    name = "besttime"
    URL = "https://besttime.app/api/v1/forecasts/live"

    def __init__(self, client: PoliteClient | None = None):
        self.key = get_settings().besttime_api_key
        if not self.key:
            raise RuntimeError("SPT_BESTTIME_API_KEY is not set")
        self.client = client or PoliteClient(min_interval_s=1.0)

    def live_busyness(self, venue_name: str, venue_address: str, at: datetime) -> float | None:
        resp = self.client.post(
            self.URL,
            params={"api_key_private": self.key, "venue_name": venue_name, "venue_address": venue_address},
        )
        analysis = resp.json().get("analysis", {})
        if not analysis.get("venue_live_busyness_available"):
            return None
        return float(analysis.get("venue_live_busyness", 0))


class SyntheticProvider(FootTrafficProvider):
    """Diurnal curve + noise, with an optional late-night 'crunch' injected for demos."""

    name = "synthetic"

    def __init__(self, seed: int = 7, crunch_prob: float = 0.03):
        self.rng = random.Random(seed)
        self.crunch_prob = crunch_prob

    def live_busyness(self, venue_name: str, venue_address: str, at: datetime) -> float:
        h = at.hour + at.minute / 60
        lunch = 45 * math.exp(-((h - 12.5) ** 2) / 2)
        dinner = 55 * math.exp(-((h - 18.5) ** 2) / 3)
        base = 5 + lunch + dinner
        if at.weekday() >= 5:
            base *= 0.8
        if (h >= 20 or h < 2) and self.rng.random() < self.crunch_prob:
            base += 35
        return max(0.0, min(100.0, base + self.rng.gauss(0, 4)))

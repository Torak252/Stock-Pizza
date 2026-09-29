"""Venue busyness: synthetic only.

There is no free, terms-compliant source of live venue busyness. Google Popular Times has no
API and scraping Maps violates Google's ToS; BestTime / Advan are paid. The live pipeline
therefore relies on DOT camera counts, and this module exists only so `cli demo` can
exercise the pipeline and dashboard. Never write its output into a database of real data.
"""
from __future__ import annotations

import math
import random
from datetime import datetime


class SyntheticProvider:
    """Diurnal curve + noise, with an occasional late-night 'crunch' injected for demos."""

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

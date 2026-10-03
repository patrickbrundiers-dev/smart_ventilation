"""Pure forecast scoring helpers for Smart Ventilation.

No Home Assistant dependency. Keeps forecast ranking deterministic and easy to test.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ForecastWindow:
    """Normalized forecast candidate used by the coordinator and frontend."""

    timestamp: str
    gain: float
    wind: float = 0.0
    rain_probability: float = 0.0
    rain_amount: float = 0.0
    temperature_delta: float = 0.0
    score: float = 0.0


def score_forecast_window(
    *,
    humidity_gain: float | None,
    wind: float | None,
    temperature_delta: float | None,
    rain_probability: float | None = None,
    rain_amount: float | None = None,
    min_gain: float = 1.0,
    max_rain_probability: float = 50.0,
    max_rain_amount: float = 0.2,
) -> float:
    """Score a forecast candidate from 0..100.

    Hard rain limits are applied first. The remaining score rewards drier air,
    useful wind and a moderate temperature advantage while avoiding excessive
    weighting of any single input.
    """
    gain = max(0.0, float(humidity_gain or 0.0))
    rain_prob = max(0.0, float(rain_probability or 0.0))
    rain_amount = max(0.0, float(rain_amount or 0.0))
    if gain < min_gain:
        return 0.0
    if rain_prob > max_rain_probability or rain_amount > max_rain_amount:
        return 0.0

    wind_value = max(0.0, float(wind or 0.0))
    temp_delta = float(temperature_delta or 0.0)

    score = min(60.0, gain * 20.0)
    score += min(20.0, wind_value * 1.5)
    score += min(15.0, max(0.0, temp_delta) * 3.0)
    score -= min(10.0, rain_prob / 10.0)
    return max(0.0, min(100.0, score))


def choose_best_window(
    windows: Iterable[ForecastWindow],
) -> ForecastWindow | None:
    """Return the highest-scoring usable window, preserving input order on ties."""
    best: ForecastWindow | None = None
    for window in windows:
        if best is None or window.score > best.score:
            best = window
    return best

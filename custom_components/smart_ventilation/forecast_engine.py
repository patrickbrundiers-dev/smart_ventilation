"""Pure forecast scoring helpers for Smart Ventilation.

No Home Assistant dependency. Keeps forecast ranking deterministic and easy to test.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
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
    try:
        gain = float(humidity_gain or 0.0)
        rain_prob = float(rain_probability or 0.0)
        rain_amount = float(rain_amount or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not all(math.isfinite(v) for v in (gain, rain_prob, rain_amount)):
        return 0.0
    gain = max(0.0, gain)
    rain_prob = max(0.0, min(100.0, rain_prob))
    rain_amount = max(0.0, rain_amount)
    if gain < min_gain:
        return 0.0
    if rain_prob >= max_rain_probability or rain_amount > max_rain_amount:
        return 0.0

    try:
        wind_value = max(0.0, float(wind or 0.0))
        temp_delta = float(temperature_delta or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(wind_value) or not math.isfinite(temp_delta):
        return 0.0

    score = min(60.0, gain * 20.0)
    score += min(20.0, wind_value * 1.5)
    score += min(15.0, max(0.0, temp_delta) * 3.0)
    score -= min(10.0, rain_prob / 10.0)
    return max(0.0, min(100.0, score))


def build_forecast_windows(
    candidates: Iterable[ForecastWindow],
    *,
    max_gap_minutes: int = 90,
    limit: int = 6,
) -> list[dict]:
    """Turn usable hourly candidates into contiguous ventilation windows."""
    import datetime as _dt

    ordered = sorted(candidates, key=lambda item: item.timestamp)
    groups: list[list[ForecastWindow]] = []
    for item in ordered:
        try:
            when = _dt.datetime.fromisoformat(item.timestamp)
        except (TypeError, ValueError):
            continue
        if not groups:
            groups.append([item])
            continue
        try:
            previous = _dt.datetime.fromisoformat(groups[-1][-1].timestamp)
            gap = (when - previous).total_seconds() / 60
        except (TypeError, ValueError):
            gap = max_gap_minutes + 1
        if gap <= max_gap_minutes:
            groups[-1].append(item)
        else:
            groups.append([item])

    result: list[dict] = []
    for group in groups:
        try:
            start = _dt.datetime.fromisoformat(group[0].timestamp)
            end = _dt.datetime.fromisoformat(group[-1].timestamp) + _dt.timedelta(hours=1)
        except (TypeError, ValueError):
            continue
        result.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "score": round(max(item.score for item in group), 1),
            "gain": round(sum(item.gain for item in group) / len(group), 1),
            "wind": round(sum(item.wind for item in group) / len(group), 1),
            "rain_probability": round(max(item.rain_probability for item in group), 1),
            "rain_amount": round(max(item.rain_amount for item in group), 2),
            "temperature_delta": round(sum(item.temperature_delta for item in group) / len(group), 1),
            "hours": len(group),
        })
    result.sort(key=lambda item: (-item["score"], item["start"]))
    return result[:max(1, limit)]


def choose_best_window(
    windows: Iterable[ForecastWindow],
) -> ForecastWindow | None:
    """Return the highest-scoring usable window, preserving input order on ties."""
    best: ForecastWindow | None = None
    for window in windows:
        if best is None or window.score > best.score:
            best = window
    return best

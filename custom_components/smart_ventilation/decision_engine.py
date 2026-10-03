"""Pure decision and learning helpers for Smart Ventilation.

The module intentionally has no Home Assistant dependency so the safety-critical
math can be tested quickly and independently from the HA test matrix.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
import math
from typing import Any


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def ventilation_utility_score(
    *,
    humidity_gain: float | None,
    wind: float | None = None,
    wind_factor: float = 1.0,
    temperature_delta: float | None,
    cloud_cover: float | None = None,
    solar_radiation: float | None = None,
    co2: float | None = None,
    mold_risk: str = "niedrig",
    wall_rh: float | None = None,
    dewpoint_margin: float | None = None,
    forecast_score: float | None = None,
) -> tuple[int, str]:
    """Calculate a transparent 0..100 usefulness score for ventilation.

    The score answers only "how useful is ventilation now/at this time?".
    Hard safety gates such as rain, thunderstorms and excessive outdoor
    temperature remain outside this function and always take precedence.
    """
    score = 0.0
    reasons: list[str] = []

    if humidity_gain is not None:
        gain = max(0.0, float(humidity_gain))
        score += min(40.0, gain * 12.0)
        if gain >= 2.0:
            reasons.append(f"{gain:.1f} g/m³ trockener")
        elif gain >= 1.0:
            reasons.append("Außenluft trockener")

    if wind is not None:
        effective_wind = max(0.0, float(wind)) * max(0.0, min(1.0, float(wind_factor)))
        score += min(15.0, effective_wind / 2.0)
        if effective_wind >= 10:
            reasons.append("günstiger Wind")

    if temperature_delta is not None:
        td = float(temperature_delta)
        score += min(12.0, max(0.0, td) * 2.0)
        if td >= 3:
            reasons.append("Temperatur günstig")

    if co2 is not None:
        value = float(co2)
        if value >= 1400:
            score += 20.0
            reasons.append("CO₂ sehr hoch")
        elif value >= 1000:
            score += 10.0
            reasons.append("CO₂ erhöht")

    if mold_risk == "kritisch":
        score += 30.0
        reasons.append("Schimmelrisiko kritisch")
    elif mold_risk == "hoch":
        score += 20.0
        reasons.append("Schimmelrisiko hoch")
    elif mold_risk == "erhöht":
        score += 10.0
        reasons.append("Wandfeuchte erhöht")

    if wall_rh is not None:
        wrh = float(wall_rh)
        if wrh >= 90:
            score += 15.0
        elif wrh >= 80:
            score += 10.0
        elif wrh >= 70:
            score += 4.0

    if dewpoint_margin is not None:
        margin = float(dewpoint_margin)
        if margin <= 0:
            score += 20.0
            reasons.append("Kondensation möglich")
        elif margin <= 0.5:
            score += 15.0
            reasons.append("Wand sehr nah am Taupunkt")
        elif margin <= 2:
            score += 6.0

    if forecast_score is not None:
        score += max(-10.0, min(10.0, (float(forecast_score) - 50.0) * 0.2))

    score = int(round(max(0.0, min(100.0, score))))
    return score, (" · ".join(reasons) if reasons else "geringer Lüftungsnutzen")


def adaptive_ventilation_score(
    *,
    humidity_gain: float | None,
    wind: float | None,
    wind_factor: float = 1.0,
    temperature_delta: float | None,
    cloud_cover: float | None,
    solar_radiation: float | None,
    rain: bool = False,
    co2: float | None = None,
    mold_risk: str = "niedrig",
) -> tuple[int, str]:
    """Return 0..100 usefulness score and a human-readable reason.

    The score is a decision aid, not a replacement for the hard safety gates
    (rain, thunderstorm, unavailable sensors, excessive outdoor temperature).
    """
    if rain:
        return 0, "Regen blockiert"
    score = 0.0
    reasons: list[str] = []

    if humidity_gain is not None:
        gain = max(0.0, humidity_gain)
        score += min(45.0, gain * 12.0)
        if gain >= 2.0:
            reasons.append(f"{gain:.1f} g/m³ trockener")
        elif gain >= 1.0:
            reasons.append("Außenluft merklich trockener")

    if temperature_delta is not None:
        score += min(15.0, max(0.0, temperature_delta) * 2.0)

    if wind is not None:
        effective_wind = max(0.0, wind) * max(0.0, min(1.0, wind_factor))
        score += min(15.0, effective_wind / 2.0)
        if effective_wind >= 10:
            reasons.append("günstiger Wind")

    if cloud_cover is not None:
        if cloud_cover >= 80:
            score -= 10
        elif cloud_cover >= 45:
            if solar_radiation is None:
                score -= 5
            elif solar_radiation >= 180:
                score += 6
                reasons.append("ausreichende Einstrahlung trotz Wolken")
            else:
                score -= 6
        elif solar_radiation is not None and solar_radiation >= 180:
            score += 5

    if solar_radiation is not None:
        score += min(10.0, max(0.0, solar_radiation - 120.0) / 80.0)

    if co2 is not None:
        if co2 >= 1400:
            score += 20
            reasons.append("CO₂ sehr hoch")
        elif co2 >= 1000:
            score += 10
            reasons.append("CO₂ erhöht")

    if mold_risk == "hoch":
        score += 15
        reasons.append("Schimmelrisiko hoch")
    elif mold_risk == "erhöht":
        score += 8
        reasons.append("Schimmelrisiko erhöht")

    score = int(round(max(0.0, min(100.0, score))))
    return score, (" · ".join(reasons) if reasons else "geringer Lüftungseffekt")


def robust_ach_update(
    model: dict[str, Any] | None,
    ach: float,
    *,
    now: datetime | None = None,
    trust_samples: int = 5,
    max_history: int = 12,
) -> tuple[dict[str, Any], bool]:
    """Update one learning bucket while rejecting clear outliers.

    Returns (model, accepted). Early observations are averaged; after the
    trust threshold, exponential smoothing reacts to real changes. A compact
    history makes outlier rejection auditable and bounded.
    """
    try:
        ach = float(ach)
    except (TypeError, ValueError):
        return model or {}, False
    if not math.isfinite(ach) or not 0.2 <= ach <= 40:
        return model or {}, False

    current = dict(model or {})
    raw_history = current.get("history", [])
    history: list[float] = []
    if isinstance(raw_history, (list, tuple)):
        for value in raw_history:
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                continue
            if 0.2 <= parsed <= 40:
                history.append(parsed)
    if len(history) >= trust_samples:
        med = median(history)
        deviations = [abs(v - med) for v in history]
        mad = median(deviations) if deviations else 0.0
        tolerance = max(2.0, med * 0.35, mad * 4.0)
        if abs(ach - med) > tolerance:
            return current, False

    try:
        old_ach = float(current.get("ach", ach))
    except (TypeError, ValueError):
        old_ach = ach
    try:
        count = max(0, int(current.get("samples", len(history))))
    except (TypeError, ValueError):
        count = len(history)
    if count < trust_samples:
        new_ach = (old_ach * count + ach) / (count + 1)
    else:
        new_ach = old_ach * 0.8 + ach * 0.2

    history.append(float(ach))
    history = history[-max_history:]
    current.update(
        ach=max(0.5, min(40.0, new_ach)),
        samples=count + 1,
        last_observed_ach=float(ach),
        history=history,
        last_updated=_now_iso(now),
    )
    return current, True


def context_bucket(
    *,
    wind: float | None,
    temperature_delta: float | None,
    cross_ventilation: bool = False,
) -> str:
    """Build a stable learning bucket from physical ventilation context.

    The bucket intentionally stays coarse so learning does not fragment into
    hundreds of sparsely populated combinations.
    """
    w = max(0.0, float(wind or 0.0))
    td = float(temperature_delta or 0.0)
    wind_bucket = "still" if w < 3 else "light" if w < 10 else "strong"
    temp_bucket = "colder" if td < -3 else "neutral" if td <= 3 else "warmer"
    cross = "cross" if cross_ventilation else "single"
    return f"{wind_bucket}:{temp_bucket}:{cross}"


def stale_adjusted_ach(
    model: dict[str, Any],
    fallback: float,
    *,
    now: datetime | None = None,
    stale_days: int = 45,
) -> float:
    """Blend stale bucket data back toward the global model."""
    value = float(model.get("ach", fallback))
    stamp = model.get("last_updated")
    if not stamp:
        # Legacy buckets from pre-2.17 have no timestamp. Treat them conservatively
        # as stale rather than allowing old learned values to override the global model forever.
        return max(0.5, value * 0.5 + float(fallback) * 0.5)
    try:
        updated = datetime.fromisoformat(str(stamp))
        current = now or datetime.now(updated.tzinfo)
        if updated.tzinfo is None:
            if current.tzinfo is not None:
                current = current.replace(tzinfo=None)
        elif current.tzinfo is None:
            current = current.replace(tzinfo=updated.tzinfo)
        age_days = max(0.0, (current - updated).total_seconds() / 86400)
    except (TypeError, ValueError):
        # Corrupt/unknown timestamps must not be treated as permanently fresh.
        # Fall back conservatively just like legacy timestamp-less buckets.
        return max(0.5, value * 0.5 + float(fallback) * 0.5)
    if age_days <= stale_days:
        return max(0.5, value)
    decay = min(0.7, (age_days - stale_days) / stale_days * 0.25)
    return max(0.5, value * (1 - decay) + float(fallback) * decay)


def robust_global_update(history: list[float], ach: float, *, max_history: int = 24) -> tuple[list[float], float]:
    """Maintain a bounded global observation history and robust mean."""
    values: list[float] = []
    for value in history:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if 0.2 <= parsed <= 40:
            values.append(parsed)
    try:
        candidate = float(ach)
    except (TypeError, ValueError):
        return values[-max_history:], sum(values) / len(values) if values else 8.0
    if not 0.2 <= candidate <= 40:
        return values[-max_history:], sum(values) / len(values) if values else 8.0
    if len(values) >= 5:
        med = median(values)
        mad = median(abs(v - med) for v in values)
        if abs(candidate - med) > max(2.0, med * 0.35, mad * 4.0):
            return values[-max_history:], sum(values) / len(values)
    values.append(candidate)
    values = values[-max_history:]
    ordered = sorted(values)
    trim = 1 if len(ordered) >= 7 else 0
    core = ordered[trim: len(ordered) - trim] if trim else ordered
    return values, sum(core) / len(core)

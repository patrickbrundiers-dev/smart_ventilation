"""Pure decision and learning helpers for Smart Ventilation.

The module intentionally has no Home Assistant dependency so the safety-critical
math can be tested quickly and independently from the HA test matrix.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


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
    if not 0.2 <= ach <= 40:
        return model or {}, False

    current = dict(model or {})
    history = [float(v) for v in current.get("history", []) if 0.2 <= float(v) <= 40]
    if len(history) >= 5:
        med = median(history)
        deviations = [abs(v - med) for v in history]
        mad = median(deviations) if deviations else 0.0
        tolerance = max(2.0, med * 0.35, mad * 4.0)
        if abs(ach - med) > tolerance:
            return current, False

    old_ach = float(current.get("ach", ach))
    count = int(current.get("samples", len(history)))
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
        return max(0.5, value)
    try:
        updated = datetime.fromisoformat(str(stamp))
        current = now or datetime.now(updated.tzinfo)
        age_days = max(0.0, (current - updated).total_seconds() / 86400)
    except (TypeError, ValueError):
        return max(0.5, value)
    if age_days <= stale_days:
        return max(0.5, value)
    decay = min(0.7, (age_days - stale_days) / stale_days * 0.25)
    return max(0.5, value * (1 - decay) + float(fallback) * decay)


def robust_global_update(history: list[float], ach: float, *, max_history: int = 24) -> tuple[list[float], float]:
    """Maintain a bounded global observation history and robust mean."""
    values = [float(v) for v in history if 0.2 <= float(v) <= 40]
    if len(values) >= 5:
        med = median(values)
        mad = median(abs(v - med) for v in values)
        if abs(ach - med) > max(2.0, med * 0.35, mad * 4.0):
            return values[-max_history:], sum(values) / len(values)
    values.append(float(ach))
    values = values[-max_history:]
    ordered = sorted(values)
    trim = 1 if len(ordered) >= 7 else 0
    core = ordered[trim: len(ordered) - trim] if trim else ordered
    return values, sum(core) / len(core)

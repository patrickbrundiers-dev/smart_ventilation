from __future__ import annotations

import math

from homeassistant.core import HomeAssistant

from .const import LOW_RISK_STATES, OFF_STATES, ON_STATES


def _float_state(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Return a finite numeric state, safely handling optional/missing entities."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _is_on(hass: HomeAssistant, entity_id: str | None) -> bool:
    if not entity_id:
        return False
    state = hass.states.get(entity_id)
    return state is not None and state.state in ON_STATES


def _is_raining(hass: HomeAssistant, entity_id: str | None) -> bool:
    """Support binary rain sensors and numeric precipitation sensors."""
    if _is_on(hass, entity_id):
        return True
    value = _float_state(hass, entity_id)
    return value is not None and value > 0


def _has_risk(hass: HomeAssistant, entity_id: str | None) -> bool:
    """Treat unknown/non-standard risk states conservatively."""
    if not entity_id:
        return False
    if _is_on(hass, entity_id):
        return True
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", ""):
        return False
    if state.state in OFF_STATES:
        return False
    return str(state.state).strip().lower() not in LOW_RISK_STATES


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def _wind_kmh(hass: HomeAssistant, entity_id: str | None) -> float | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    value = _float_state(hass, entity_id)
    if value is None:
        return None
    unit = state.attributes.get("unit_of_measurement", "") if state else ""
    return value * 3.6 if unit in ("m/s", "mps") else value


def _relative_humidity_from_absolute(
    absolute_humidity: float | None, temperature_c: float | None
) -> float | None:
    """Approximate RH from absolute humidity in g/m³ and temperature in °C."""
    if absolute_humidity is None or temperature_c is None:
        return None
    tk = temperature_c + 273.15
    vapor_pressure = absolute_humidity * tk / 216.7
    saturation = 6.112 * math.exp((17.62 * temperature_c) / (243.12 + temperature_c))
    if saturation <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * vapor_pressure / saturation))


def _absolute_humidity(
    temperature_c: float | None, rh: float | None = None, dew_point: float | None = None
) -> float | None:
    """Absolute humidity in g/m³ from dew point or temperature + RH."""
    if temperature_c is None:
        return None
    if dew_point is not None:
        vapor = 6.112 * math.exp((17.62 * dew_point) / (243.12 + dew_point))
    elif rh is not None:
        vapor = rh / 100.0 * 6.112 * math.exp(
            (17.62 * temperature_c) / (243.12 + temperature_c)
        )
    else:
        return None
    return 216.7 * vapor / (273.15 + temperature_c)


def _num(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _dew_point(temperature_c: float | None, rh: float | None) -> float | None:
    if temperature_c is None or rh is None or rh <= 0:
        return None
    gamma = math.log(rh / 100.0) + (17.62 * temperature_c) / (243.12 + temperature_c)
    return (243.12 * gamma) / (17.62 - gamma)

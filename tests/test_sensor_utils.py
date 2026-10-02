from unittest.mock import MagicMock

import pytest

from custom_components.smart_ventilation.sensor_utils import (
    _absolute_humidity,
    _dew_point,
    _float_state,
    _relative_humidity_from_absolute,
)


def test_float_state_handles_missing_optional_entity():
    hass = MagicMock()
    assert _float_state(hass, None) is None
    hass.states.get.assert_not_called()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("21.5", 21.5),
        ("unknown", None),
        ("unavailable", None),
        ("not-a-number", None),
    ],
)
def test_float_state_parses_finite_values(value, expected):
    hass = MagicMock()
    state = MagicMock(state=value)
    hass.states.get.return_value = state
    assert _float_state(hass, "sensor.test") == expected


def test_float_state_rejects_non_finite_value():
    hass = MagicMock()
    hass.states.get.return_value = MagicMock(state="nan")
    assert _float_state(hass, "sensor.test") is None


def test_absolute_humidity_round_trip():
    absolute = _absolute_humidity(20.0, rh=50.0)
    assert absolute is not None
    assert _relative_humidity_from_absolute(absolute, 20.0) == pytest.approx(50.0, abs=0.2)


def test_absolute_humidity_from_dew_point():
    absolute = _absolute_humidity(20.0, dew_point=10.0)
    assert absolute is not None
    assert 8.0 < absolute < 10.0


def test_dew_point_round_trip():
    dew_point = _dew_point(20.0, 50.0)
    assert dew_point is not None
    assert dew_point == pytest.approx(9.26, abs=0.1)

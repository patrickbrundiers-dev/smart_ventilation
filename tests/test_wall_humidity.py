from custom_components.smart_ventilation.sensor_utils import _relative_humidity_at_surface


def test_surface_humidity_rises_on_colder_wall():
    result = _relative_humidity_at_surface(20, 60, 16.36)
    assert result is not None
    assert 75.0 < result < 76.0


def test_surface_humidity_is_lower_on_warm_wall():
    cold = _relative_humidity_at_surface(20, 60, 16.0)
    warm = _relative_humidity_at_surface(20, 60, 19.0)
    assert cold is not None
    assert warm is not None
    assert warm < cold


def test_surface_humidity_handles_missing_inputs():
    assert _relative_humidity_at_surface(None, 60, 16) is None
    assert _relative_humidity_at_surface(20, None, 16) is None
    assert _relative_humidity_at_surface(20, 60, None) is None


def test_surface_humidity_is_bounded():
    result = _relative_humidity_at_surface(20, 100, 10)
    assert result == 100.0

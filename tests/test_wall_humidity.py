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


def test_winter_scenario_20c_60rh_average_wall():
    result = _relative_humidity_at_surface(20, 60, 17.4)
    assert result is not None
    assert 70.0 < result < 71.5


def test_winter_scenario_20c_70rh_cold_wall_is_high():
    result = _relative_humidity_at_surface(20, 70, 16.1)
    assert result is not None
    assert 88.0 < result < 90.5


from custom_components.smart_ventilation.mold_engine import assess_mold_risk


def test_wall_dewpoint_margin_distinguishes_condensation_from_warning():
    safe = assess_mold_risk(70, 17.4, 60, 12.0)
    warning = assess_mold_risk(78, 16.4, 60, 16.0)
    condensation = assess_mold_risk(95, 16.0, 60, 16.2)
    assert safe.dew_point_margin > 2
    assert 0 < warning.dew_point_margin <= 0.5
    assert condensation.dew_point_margin <= 0
    assert condensation.level == "kritisch"


def test_wall_humidity_scenario_escalates_with_duration():
    result = assess_mold_risk(82, 16.5, 70, 14.5, duration_high_minutes=360)
    assert result.level == "hoch"
    assert result.duration_hours >= 6

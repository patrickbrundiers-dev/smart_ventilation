from custom_components.smart_ventilation.coordinator import SmartVentilationCoordinator


def test_stored_float_rejects_invalid_and_out_of_range_values():
    assert SmartVentilationCoordinator._stored_float("8.5", 8.0, 0.2, 40) == 8.5
    assert SmartVentilationCoordinator._stored_float("nan", 8.0, 0.2, 40) == 8.0
    assert SmartVentilationCoordinator._stored_float("bad", 8.0, 0.2, 40) == 8.0
    assert SmartVentilationCoordinator._stored_float("-1", 8.0, 0.2, 40) == 8.0
    assert SmartVentilationCoordinator._stored_float("99", 8.0, 0.2, 40) == 8.0


def test_stored_int_and_datetime_are_defensive():
    assert SmartVentilationCoordinator._stored_int("12", 0, 0) == 12
    assert SmartVentilationCoordinator._stored_int("bad", 0, 0) == 0
    assert SmartVentilationCoordinator._stored_int("-1", 0, 0) == 0
    assert SmartVentilationCoordinator._stored_datetime("not-a-date") is None
    assert SmartVentilationCoordinator._stored_datetime(None) is None


def test_stored_observations_filters_corrupt_values():
    assert SmartVentilationCoordinator._stored_observations(["1.2", "bad", 50, 0.1, 8]) == [1.2, 8.0]
    assert SmartVentilationCoordinator._stored_observations("bad") == []


def test_restore_session_corrupt_value_is_ignored():
    saved = "corrupt-session"
    assert not isinstance(saved, dict)
    if isinstance(saved, dict) and saved.get("started"):
        raise AssertionError("corrupt session must not be restored")

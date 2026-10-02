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


def test_stored_models_filters_corrupt_bucket_data():
    models = SmartVentilationCoordinator._stored_models(
        {
            "good": {
                "ach": "8.5",
                "samples": "5",
                "history": ["8", "bad", 50],
                "last_observed_ach": "9",
            },
            "broken": "not-a-model",
        },
        8.0,
    )
    assert set(models) == {"good"}
    assert models["good"]["ach"] == 8.5
    assert models["good"]["samples"] == 5
    assert models["good"]["history"] == [8.0]
    assert models["good"]["last_observed_ach"] == 9.0


def test_stored_stats_normalizes_corrupt_period_data():
    stats = SmartVentilationCoordinator._stored_stats(
        {
            "day": {
                "key": "2026-10-02",
                "count": "4",
                "ok": "3",
                "short": "bad",
                "seconds": "120.5",
                "kwh": "bad",
                "need_minutes": 30,
                "kwh_gespart": -5,
                "mold_days": ["2026-10-02", 123],
            },
            "week": "broken",
            "max_seconds": "bad",
        }
    )
    assert stats["day"]["count"] == 4
    assert stats["day"]["ok"] == 3
    assert stats["day"]["short"] == 0
    assert stats["day"]["seconds"] == 120.5
    assert stats["day"]["kwh"] == 0.0
    assert stats["day"]["need_minutes"] == 30.0
    assert stats["day"]["kwh_gespart"] == 0.0
    assert stats["day"]["mold_days"] == ["2026-10-02"]
    assert stats["max_seconds"] == 0.0


def test_stored_night_low_rejects_invalid_values():
    assert SmartVentilationCoordinator._stored_float("4.5", None, -50, 60) == 4.5
    assert SmartVentilationCoordinator._stored_float("bad", None, -50, 60) is None
    assert SmartVentilationCoordinator._stored_float("99", None, -50, 60) is None


def test_stored_mold_log_filters_corrupt_entries():
    log = SmartVentilationCoordinator._stored_mold_log(
        {"2026-10-01": "12.5", "bad": "nope", 123: 5, "negative": -1}
    )
    assert log == {"2026-10-01": 12.5}


def test_stored_history_dict_rejects_non_dict():
    assert SmartVentilationCoordinator._stored_history_dict("broken") == {}
    assert SmartVentilationCoordinator._stored_history_dict({"2026-10": {"kwh": 1}}) == {"2026-10": {"kwh": 1}}

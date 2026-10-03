from datetime import datetime, timezone

from custom_components.smart_ventilation.decision_engine import (
    adaptive_ventilation_score,
    robust_ach_update,
    robust_global_update,
    stale_adjusted_ach,
)


def test_adaptive_score_rewards_dry_outdoor_air_and_good_wind():
    score, reason = adaptive_ventilation_score(
        humidity_gain=4.0,
        wind=18,
        wind_factor=1.0,
        temperature_delta=5,
        cloud_cover=20,
        solar_radiation=300,
    )
    assert score >= 70
    assert "trockener" in reason


def test_adaptive_score_penalizes_heavy_cloud():
    clear, _ = adaptive_ventilation_score(
        humidity_gain=1.5, wind=5, wind_factor=1, temperature_delta=2,
        cloud_cover=10, solar_radiation=300,
    )
    cloudy, _ = adaptive_ventilation_score(
        humidity_gain=1.5, wind=5, wind_factor=1, temperature_delta=2,
        cloud_cover=90, solar_radiation=20,
    )
    assert cloudy < clear


def test_adaptive_score_medium_cloud_requires_real_radiation():
    low, _ = adaptive_ventilation_score(
        humidity_gain=1.5, wind=5, wind_factor=1, temperature_delta=2,
        cloud_cover=60, solar_radiation=80,
    )
    high, reason = adaptive_ventilation_score(
        humidity_gain=1.5, wind=5, wind_factor=1, temperature_delta=2,
        cloud_cover=60, solar_radiation=250,
    )
    assert high > low
    assert "Einstrahlung" in reason


def test_rain_is_hard_block():
    score, reason = adaptive_ventilation_score(
        humidity_gain=10, wind=30, wind_factor=1, temperature_delta=10,
        cloud_cover=0, solar_radiation=800, rain=True,
    )
    assert score == 0
    assert reason == "Regen blockiert"


def test_robust_bucket_builds_average_before_trust():
    model, accepted = robust_ach_update({"ach": 8, "samples": 0}, 10)
    assert accepted
    assert model["samples"] == 1
    assert model["ach"] == 10


def test_robust_bucket_rejects_clear_outlier():
    model = {"ach": 8, "samples": 6, "history": [7, 8, 8, 9, 8, 8]}
    updated, accepted = robust_ach_update(model, 30)
    assert not accepted
    assert updated["ach"] == 8


def test_robust_bucket_keeps_bounded_history():
    model = {"ach": 8, "samples": 12, "history": list(range(1, 13))}
    updated, accepted = robust_ach_update(model, 10)
    assert accepted
    assert len(updated["history"]) == 12


def test_stale_bucket_blends_back_to_global_model():
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    model = {"ach": 20, "last_updated": old.isoformat()}
    value = stale_adjusted_ach(model, 8, now=now)
    assert 8 < value < 20


def test_recent_bucket_is_not_changed_by_staleness():
    old = datetime(2026, 2, 20, tzinfo=timezone.utc)
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    model = {"ach": 20, "last_updated": old.isoformat()}
    assert stale_adjusted_ach(model, 8, now=now) == 20


def test_invalid_timestamp_is_treated_conservatively():
    model = {"ach": 20, "last_updated": "not-a-date"}
    value = stale_adjusted_ach(model, 8)
    assert 8 < value < 20


def test_global_learning_rejects_outlier():
    history, mean = robust_global_update([7, 8, 8, 9, 8, 8], 35)
    assert 35 not in history
    assert mean < 10


def test_global_learning_history_is_bounded():
    history, _ = robust_global_update(list(range(1, 25)), 10)
    assert len(history) == 24


def test_robust_bucket_ignores_malformed_history_values():
    model = {"ach": 8, "samples": 5, "history": [8, "bad", None, 9]}
    updated, accepted = robust_ach_update(model, 10)
    assert accepted
    assert updated["samples"] == 6
    assert all(0.2 <= value <= 40 for value in updated["history"])


def test_robust_bucket_uses_configured_trust_threshold():
    model = {"ach": 8, "samples": 4, "history": [7, 8, 8, 9]}
    updated, accepted = robust_ach_update(model, 10, trust_samples=4)
    assert accepted
    assert updated["samples"] == 5


def test_global_learning_ignores_malformed_values_and_candidates():
    history, mean = robust_global_update([7, "bad", None, 8, 9], 10)
    assert history[-1] == 10
    assert all(0.2 <= value <= 40 for value in history)
    assert mean > 0

    unchanged, fallback = robust_global_update([7, "bad"], "invalid")
    assert unchanged == [7.0]
    assert fallback == 7.0


def test_stale_bucket_handles_naive_model_timestamp_with_aware_now():
    model = {"ach": 20, "last_updated": "2026-01-01T00:00:00"}
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    value = stale_adjusted_ach(model, 8, now=now)
    assert 8 < value < 20


def test_stale_bucket_handles_aware_model_timestamp_with_naive_now():
    model = {"ach": 20, "last_updated": "2026-01-01T00:00:00+00:00"}
    now = datetime(2026, 4, 1)
    value = stale_adjusted_ach(model, 8, now=now)
    assert 8 < value < 20


def test_robust_ach_rejects_non_finite_values():
    model, accepted = robust_ach_update(None, float("nan"))
    assert not accepted
    assert model == {}


from custom_components.smart_ventilation.decision_engine import ventilation_utility_score


def test_ventilation_utility_increases_with_drier_air():
    low, _ = ventilation_utility_score(
        humidity_gain=0.5, wind=3, temperature_delta=1, mold_risk="niedrig"
    )
    high, reason = ventilation_utility_score(
        humidity_gain=3.0, wind=8, temperature_delta=3, mold_risk="erhöht"
    )
    assert high > low
    assert "g/m³" in reason


def test_ventilation_utility_reacts_to_wall_condensation_risk():
    safe, _ = ventilation_utility_score(
        humidity_gain=1.0, temperature_delta=1, dewpoint_margin=4
    )
    critical, reason = ventilation_utility_score(
        humidity_gain=1.0, temperature_delta=1, dewpoint_margin=0
    )
    assert critical > safe
    assert "Kondensation" in reason


def test_ventilation_utility_is_bounded():
    score, _ = ventilation_utility_score(
        humidity_gain=100, wind=100, temperature_delta=100,
        co2=5000, mold_risk="kritisch", wall_rh=100, dewpoint_margin=-10
    )
    assert 0 <= score <= 100


def test_ventilation_utility_penalizes_heavy_cloud_without_radiation():
    clear, _ = ventilation_utility_score(
        humidity_gain=2.0, wind=5, temperature_delta=2,
        cloud_cover=10, solar_radiation=300,
    )
    cloudy, reason = ventilation_utility_score(
        humidity_gain=2.0, wind=5, temperature_delta=2,
        cloud_cover=90, solar_radiation=20,
    )
    assert cloudy < clear
    assert "bewölkt" in reason or "stark bewölkt" in reason


def test_ventilation_utility_rewards_real_solar_radiation():
    low, _ = ventilation_utility_score(
        humidity_gain=2.0, wind=5, temperature_delta=2,
        cloud_cover=60, solar_radiation=80,
    )
    high, reason = ventilation_utility_score(
        humidity_gain=2.0, wind=5, temperature_delta=2,
        cloud_cover=60, solar_radiation=250,
    )
    assert high > low
    assert "Einstrahlung" in reason


def test_ventilation_utility_ignores_non_finite_sensor_values():
    baseline, _ = ventilation_utility_score(
        humidity_gain=2.0, wind=5, wind_factor=1.0, temperature_delta=2,
        cloud_cover=20, solar_radiation=250, co2=1200, wall_rh=70,
        dewpoint_margin=2, forecast_score=60,
    )
    guarded, reason = ventilation_utility_score(
        humidity_gain=float("nan"), wind=float("inf"), wind_factor=float("nan"),
        temperature_delta=float("nan"), cloud_cover=float("nan"),
        solar_radiation=float("nan"), co2=float("nan"), wall_rh=float("nan"),
        dewpoint_margin=float("nan"), forecast_score=float("nan"),
    )
    assert guarded == 0
    assert "geringer Lüftungsnutzen" in reason
    assert baseline > guarded


def test_ventilation_utility_keeps_valid_values_when_optional_inputs_are_invalid():
    score, reason = ventilation_utility_score(
        humidity_gain=3.0, wind=8, wind_factor=1.0, temperature_delta=3,
        cloud_cover=float("nan"), solar_radiation=float("nan"),
        co2=float("nan"), wall_rh=float("nan"), dewpoint_margin=float("nan"),
    )
    assert score > 0
    assert "g/m³" in reason

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


def test_global_learning_rejects_outlier():
    history, mean = robust_global_update([7, 8, 8, 9, 8, 8], 35)
    assert 35 not in history
    assert mean < 10


def test_global_learning_history_is_bounded():
    history, _ = robust_global_update(list(range(1, 25)), 10)
    assert len(history) == 24

from datetime import datetime, timezone

from custom_components.smart_ventilation.decision_engine import context_bucket
from custom_components.smart_ventilation.forecast_engine import (
    ForecastWindow,
    choose_best_window,
    score_forecast_window,
)


def test_context_bucket_is_coarse_and_stable():
    assert context_bucket(wind=1, temperature_delta=-5, cross_ventilation=False) == "still:colder:single"
    assert context_bucket(wind=12, temperature_delta=1, cross_ventilation=True) == "strong:neutral:cross"


def test_forecast_score_rejects_rain_and_low_gain():
    assert score_forecast_window(
        humidity_gain=0.5, wind=10, temperature_delta=-2
    ) == 0
    assert score_forecast_window(
        humidity_gain=3, wind=10, temperature_delta=-2, rain_probability=70
    ) == 0


def test_forecast_score_rewards_drier_air_and_wind():
    low = score_forecast_window(humidity_gain=1.2, wind=2, temperature_delta=0)
    high = score_forecast_window(humidity_gain=3.0, wind=15, temperature_delta=-2)
    assert high > low > 0


def test_choose_best_forecast_window_preserves_order_on_tie():
    first = ForecastWindow("10:00", gain=2, score=50)
    second = ForecastWindow("11:00", gain=3, score=50)
    assert choose_best_window([first, second]) is first


def test_forecast_window_datetime_values_can_be_external_timestamps():
    now = datetime.now(timezone.utc).isoformat()
    window = ForecastWindow(now, gain=2.0)
    assert window.timestamp == now

def test_forecast_score_rejects_rain_at_probability_limit():
    assert score_forecast_window(
        humidity_gain=3, wind=10, temperature_delta=0, rain_probability=50
    ) == 0


def test_forecast_score_rejects_rain_above_amount_limit():
    assert score_forecast_window(
        humidity_gain=3, wind=10, temperature_delta=0, rain_amount=0.21
    ) == 0


def test_forecast_score_rejects_rain_at_amount_limit():
    """rain_amount am Grenzwert selbst muss genauso blockieren wie rain_probability am
    Grenzwert (siehe test_forecast_score_rejects_rain_at_probability_limit) - vorher war
    rain_amount beim Grenzwert selbst noch NICHT blockiert (">" statt ">="), eine unbegründete
    Asymmetrie zwischen zwei gleichartigen Sicherheits-Schwellen."""
    assert score_forecast_window(
        humidity_gain=3, wind=10, temperature_delta=0, rain_amount=0.2
    ) == 0


def test_forecast_rejects_non_finite_inputs():
    assert score_forecast_window(humidity_gain=float("nan"), wind=5, temperature_delta=1) == 0.0
    assert score_forecast_window(humidity_gain=2, wind=float("inf"), temperature_delta=1) == 0.0


def test_forecast_clamps_rain_probability():
    assert score_forecast_window(humidity_gain=2, wind=5, temperature_delta=1, rain_probability=150) == 0.0


from custom_components.smart_ventilation.forecast_engine import ForecastWindow, build_forecast_windows


def test_build_forecast_windows_merges_adjacent_hours():
    candidates = [
        ForecastWindow("2026-10-03T10:00:00+02:00", 2.0, score=70),
        ForecastWindow("2026-10-03T11:00:00+02:00", 2.5, score=90),
        ForecastWindow("2026-10-03T14:00:00+02:00", 3.0, score=60),
    ]
    windows = build_forecast_windows(candidates)
    assert len(windows) == 2
    assert windows[0]["hours"] == 2
    # Durchschnitt (70+90)/2=80, nicht das Maximum (90) - konsistent mit gain/wind/
    # temperature_delta, die ebenfalls den typischen Wert über das Fenster abbilden (siehe
    # test_build_forecast_windows_score_is_average_not_best_hour für die Begründung).
    assert windows[0]["score"] == 80.0
    assert windows[1]["hours"] == 1


def test_build_forecast_windows_score_is_average_not_best_hour():
    """Vorher war "score" das Maximum der Gruppe, rain_probability/rain_amount aber das Maximum
    der (womöglich anderen!) schlechtesten Stunde - ein in sich widersprüchliches Ergebnis (hoher
    Score neben hohem Regenrisiko aus zwei verschiedenen Stunden). Score muss wie gain/wind/
    temperature_delta der Durchschnitt sein, rain_probability/rain_amount bleiben bewusst das
    (konservative) Maximum."""
    candidates = [
        ForecastWindow("2026-10-03T10:00:00+02:00", gain=3.0, rain_probability=5, score=90),
        ForecastWindow("2026-10-03T11:00:00+02:00", gain=0.2, rain_probability=48, score=20),
    ]
    windows = build_forecast_windows(candidates)
    assert len(windows) == 1
    assert windows[0]["score"] == 55.0
    assert windows[0]["rain_probability"] == 48


def test_build_forecast_windows_limits_results():
    candidates = [
        ForecastWindow(f"2026-10-03T{h:02d}:00:00+02:00", 2.0, score=float(h))
        for h in range(7, 15, 2)
    ]
    windows = build_forecast_windows(candidates, limit=2)
    assert len(windows) == 2

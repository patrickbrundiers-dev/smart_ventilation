from custom_components.smart_ventilation.mold_engine import assess_mold_risk


def test_mold_low_below_watch_threshold():
    result = assess_mold_risk(60, 18, 60, 10)
    assert result.level == "niedrig"


def test_mold_watch_at_65_percent():
    result = assess_mold_risk(65, 18, 65, 11)
    assert result.level == "beobachten"


def test_mold_elevated_at_70_percent():
    result = assess_mold_risk(70, 18, 70, 12)
    assert result.level == "erhöht"


def test_mold_high_at_80_percent():
    result = assess_mold_risk(80, 18, 70, 12)
    assert result.level == "hoch"


def test_mold_high_explains_long_duration():
    result = assess_mold_risk(80, 18, 70, 12, duration_high_minutes=360)
    assert result.level == "hoch"
    assert "6 Stunden" in result.reason


def test_mold_critical_above_90_percent():
    result = assess_mold_risk(90, 18, 75, 13)
    assert result.level == "kritisch"


def test_mold_critical_near_condensation():
    result = assess_mold_risk(82, 16, 75, 15.6)
    assert result.level == "kritisch"
    assert "sehr nah" in result.reason


def test_mold_critical_at_condensation_point():
    result = assess_mold_risk(82, 16, 75, 16)
    assert result.level == "kritisch"
    assert "Kondensation" in result.reason


def test_mold_rising_trend_adds_urgency():
    result = assess_mold_risk(78, 18, 68, 12, trend_rh_per_hour=2.5)
    assert result.level == "erhöht"
    assert "steigend" in result.reason


def test_mold_missing_wall_data_uses_room_air():
    result = assess_mold_risk(None, None, 65, 12)
    assert result.level == "beobachten"
    assert "Wanddaten fehlen" in result.reason


def test_mold_uses_room_air_fallback_when_wall_data_is_missing():
    result = assess_mold_risk(None, None, 76, 14)
    assert result.level == "hoch"
    assert "Wanddaten fehlen" in result.reason


def test_mold_score_increases_with_condensation_risk():
    result = assess_mold_risk(82, 16, 75, 15.6, trend_rh_per_hour=2.5)
    assert result.score >= 95


def test_mold_score_is_bounded():
    result = assess_mold_risk(95, 15, 90, 14, duration_high_minutes=720, trend_rh_per_hour=10)
    assert 0 <= result.score <= 100


def test_mold_unknown_when_all_humidity_data_is_missing():
    """Fehlen sowohl Wand- als auch Raumluftfeuchte komplett, gibt es keine Grundlage für eine
    Einschätzung - das muss "unbekannt" bleiben statt z. B. optimistisch "niedrig" zu raten."""
    result = assess_mold_risk(None, None, None, None)
    assert result.level == "unbekannt"
    assert "fehlen" in result.reason


def test_mold_critical_from_dewpoint_margin_even_without_wall_humidity_sensor():
    """Auch ohne Wandfeuchte-Sensor: Ist (z. B. über einen reinen Wandtemperatur-Sensor) bekannt,
    dass die Wandoberfläche sehr nah am Taupunkt liegt, muss das trotzdem als "kritisch" statt
    nur anhand der Raumluftfeuchte (hier 60 % - für sich allein nur "niedrig") bewertet werden."""
    result = assess_mold_risk(None, 16.0, 60, 15.6)
    assert result.level == "kritisch"
    assert "Taupunkt" in result.reason


def test_mold_unknown_when_wall_humidity_known_but_wall_temperature_missing():
    """Eine Wandfeuchte ohne zugehörige Wandtemperatur lässt sich nicht einordnen (Taupunkt-Marge
    unberechenbar) - muss "unbekannt" bleiben statt die Wandfeuchte isoliert zu bewerten."""
    result = assess_mold_risk(70, None, 60, 12)
    assert result.level == "unbekannt"
    assert "Wandtemperatur" in result.reason


def test_mold_elevated_explains_long_duration():
    result = assess_mold_risk(72, 18, 60, 12, duration_elevated_minutes=400)
    assert result.level == "erhöht"
    assert "über längere Zeit" in result.reason


def test_mold_score_is_monotonic_across_dewpoint_margin_critical_threshold():
    """Eine minimal SICHERERE Taupunkt-Marge (weiter weg vom Taupunkt) darf nie einen HÖHEREN
    Score liefern als eine knappere Marge - vorher kippte die Formel an der Schwelle
    MOLD_DEWPOINT_MARGIN_CRITICAL (0,5 °C) von "max(score, 95)" auf eine additive Formel, die an
    0,51 °C kurzzeitig über 95 hinausschießen konnte."""
    from custom_components.smart_ventilation.mold_engine import MoldAssessment

    margins = [0.3, 0.5, 0.51, 0.8, 1.0, 1.5, 1.9, 2.0, 2.5]
    for level, base in (("kritisch", 92), ("hoch", 72), ("erhöht", 50)):
        scores = [
            MoldAssessment(
                level=level, reason="", action="", wall_rh=None, wall_temperature=None,
                dew_point_margin=margin, duration_hours=0, trend_rh_per_hour=None,
            ).score
            for margin in margins
        ]
        assert scores == sorted(scores, reverse=True), (level, margins, scores)

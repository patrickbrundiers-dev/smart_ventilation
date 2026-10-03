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
    assert "Taupunkt" in result.reason


def test_mold_rising_trend_adds_urgency():
    result = assess_mold_risk(78, 18, 68, 12, trend_rh_per_hour=2.5)
    assert result.level == "erhöht"
    assert "steigend" in result.reason


def test_mold_missing_wall_data_is_unknown():
    result = assess_mold_risk(None, None, 65, 12)
    assert result.level == "unbekannt"

def test_mold_uses_room_air_fallback_when_wall_data_is_missing():
    result = assess_mold_risk(None, None, 76, 14)
    assert result.level == "hoch"
    assert "Wanddaten fehlen" in result.reason

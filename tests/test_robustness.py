"""Robustheit im Alltag: ausgefallener Gewitterdienst, ruhiger Empfehlungszustand,
geglättete Schimmelstufe und wiederholte Erinnerung bei sehr langem Lüften im Winter."""
from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.smart_ventilation.const import (
    DOMAIN,
    MOLD_LEVEL_DOWNGRADE_MINUTES,
    THUNDERSTORM_FALLBACK_NOTE,
    THUNDERSTORM_UNAVAILABLE_GRACE_MINUTES,
)

from .conftest import eid, setup_room


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_long_thunderstorm_outage_falls_back_to_rain_sensor(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Gewitterdienst tagelang weg (21.-28.10.2026 bei KachelmannWetter): kurz sicher sperren,
    danach nach dem lokalen Regensensor entscheiden und den Ausfall in der Empfehlung nennen."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    hass.states.async_set("binary_sensor.gewitter_erwartet", "off")
    entry = await setup_room(hass, thunderstorm_entity="binary_sensor.gewitter_erwartet")
    rec = eid(hass, "sensor", entry, "recommendation")
    assert hass.states.get(rec).attributes["karte"]["minuten"] > 0

    hass.states.async_set("binary_sensor.gewitter_erwartet", "unavailable")
    await _tick(hass, freezer, 1)
    assert hass.states.get(rec).state == "Nicht lüften – Gewittersensor nicht verfügbar"

    await _tick(hass, freezer, THUNDERSTORM_UNAVAILABLE_GRACE_MINUTES)
    state = hass.states.get(rec)
    assert state.attributes["karte"]["minuten"] > 0
    assert state.state.endswith(THUNDERSTORM_FALLBACK_NOTE)
    assert not state.attributes["karte"]["blockiert"]

    # Der Regensensor bleibt das Sicherheitsnetz.
    hass.states.async_set("sensor.regen", 1.5)
    await _tick(hass, freezer, 1)
    assert hass.states.get(rec).state == "Nicht lüften – Regen"
    hass.states.async_set("sensor.regen", 0)
    await _tick(hass, freezer, 1)
    assert hass.states.get(rec).attributes["karte"]["minuten"] > 0

    # Dienst wieder da: Hinweis verschwindet, ein neuer Ausfall startet die Karenzzeit neu.
    hass.states.async_set("binary_sensor.gewitter_erwartet", "off")
    await _tick(hass, freezer, 1)
    assert THUNDERSTORM_FALLBACK_NOTE not in hass.states.get(rec).state
    hass.states.async_set("binary_sensor.gewitter_erwartet", "unavailable")
    await _tick(hass, freezer, 1)
    assert hass.states.get(rec).state == "Nicht lüften – Gewittersensor nicht verfügbar"


async def test_thunderstorm_outage_without_rain_sensor_keeps_blocking(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Ohne Regensensor gibt es kein Ersatz-Sicherheitssignal - dann bleibt es bei der Sperre."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    hass.states.async_set("binary_sensor.gewitter_erwartet", "unavailable")
    entry = await setup_room(
        hass, rain="", thunderstorm_entity="binary_sensor.gewitter_erwartet"
    )
    rec = eid(hass, "sensor", entry, "recommendation")
    await _tick(hass, freezer, THUNDERSTORM_UNAVAILABLE_GRACE_MINUTES + 30)
    assert hass.states.get(rec).state == "Nicht lüften – Gewittersensor nicht verfügbar"


async def test_grace_counts_from_outage_not_from_ventilation_need(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Die Karenzzeit läuft ab dem Ausfall, auch wenn zu dem Zeitpunkt noch kein Bedarf bestand."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    hass.states.async_set("binary_sensor.gewitter_erwartet", "off")
    entry = await setup_room(hass, thunderstorm_entity="binary_sensor.gewitter_erwartet")
    rec = eid(hass, "sensor", entry, "recommendation")
    hass.states.async_set("sensor.innen_ah", 6.0)  # trocken, kein Bedarf
    hass.states.async_set("binary_sensor.gewitter_erwartet", "unavailable")
    await _tick(hass, freezer, THUNDERSTORM_UNAVAILABLE_GRACE_MINUTES + 5)
    assert hass.states.get(rec).state == "Keine Lüftung erforderlich"

    hass.states.async_set("sensor.innen_ah", 10.5)  # jetzt Bedarf
    await _tick(hass, freezer, 1)
    assert hass.states.get(rec).attributes["karte"]["minuten"] > 0


async def test_recommendation_state_has_no_minutes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Die Minuten schwankten minütlich und erzeugten hunderte Zustandswechsel pro Tag. Der
    Zustand nennt nur noch die Art des Lüftens, die Minuten stehen im Attribut "text" und im
    Sensor "Empfohlene Dauer"."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    entry = await setup_room(hass)
    rec = eid(hass, "sensor", entry, "recommendation")
    state = hass.states.get(rec)
    minutes = state.attributes["karte"]["minuten"]
    assert minutes > 0
    assert "Min." not in state.state
    assert state.attributes["text"] == f"{state.state.split(' – ')[0]} – ca. {minutes} Min."

    coordinator = hass.data[DOMAIN][entry.entry_id]
    for text, expected in (
        ("Stoßlüften – ca. 14 Min.", "Stoßlüften"),
        ("Stoßlüften (Querlüften) – ca. 8 Min. – bald Regen, lieber jetzt lüften",
         "Stoßlüften (Querlüften) – bald Regen, lieber jetzt lüften"),
        ("Vorheizen – warme Luft reinlassen bis ca. 20 °C (ca. 12 Min.)",
         "Vorheizen – warme Luft reinlassen bis ca. 20 °C"),
        ("Nicht lüften – Regen", "Nicht lüften – Regen"),
    ):
        coordinator.recommendation = text
        assert coordinator.recommendation_state == expected


async def test_mold_risk_display_waits_before_stepping_down(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin, monkeypatch
) -> None:
    """Höhere Stufe sofort, niedrigere erst nach MOLD_LEVEL_DOWNGRADE_MINUTES stabil darunter;
    ein kurzer Rückfall startet die Wartezeit neu. Die Entscheidung bleibt ungeglättet."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    entry = await setup_room(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    level = {"value": "niedrig"}
    monkeypatch.setattr(type(coordinator), "mold_risk", property(lambda self: level["value"]))
    coordinator._mold_level_shown = None  # Stand aus dem Setup verwerfen

    assert coordinator.mold_risk_display == "niedrig"
    level["value"] = "beobachten"
    assert coordinator.mold_risk_display == "beobachten"

    level["value"] = "niedrig"
    freezer.tick(timedelta(minutes=MOLD_LEVEL_DOWNGRADE_MINUTES - 1))
    assert coordinator.mold_risk_display == "beobachten"
    level["value"] = "beobachten"
    assert coordinator.mold_risk_display == "beobachten"
    level["value"] = "niedrig"
    assert coordinator.mold_risk_display == "beobachten"
    freezer.tick(timedelta(minutes=MOLD_LEVEL_DOWNGRADE_MINUTES - 1))
    assert coordinator.mold_risk_display == "beobachten"
    freezer.tick(timedelta(minutes=1))
    assert coordinator.mold_risk_display == "niedrig"
    assert coordinator.mold_risk == "niedrig"


async def test_long_open_window_in_winter_is_reminded_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Fenster blieben trotz der einen Warnung bis zu 32 Stunden offen: nach 1, 2 und 4
    Stunden erneut erinnern, zusätzlich als HA-Benachrichtigung, die beim Schließen verschwindet."""
    freezer.move_to("2026-12-05 09:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    notification_id = f"smart_ventilation_{entry.entry_id}_overtime"

    def overtime():
        return [c for c in pushes if c.data["title"].startswith("Fenster noch offen")]

    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    limit = coordinator._winter_max_minutes()
    await _tick(hass, freezer, limit + 6)
    assert len(overtime()) == 1
    assert notification_id in hass.data["persistent_notification"]

    for minute in range(int(limit + 6), 62):
        await _tick(hass, freezer, 1)
    assert len(overtime()) == 2
    assert "seit 1 Stunde offen" in overtime()[-1].data["message"]

    await _tick(hass, freezer, 60)
    assert len(overtime()) == 3
    assert "seit 2 Stunden offen" in overtime()[-1].data["message"]
    await _tick(hass, freezer, 5)
    assert len(overtime()) == 3

    hass.states.async_set("binary_sensor.fenster_1", "off")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)
    assert notification_id not in hass.data["persistent_notification"]


async def test_overtime_repeat_is_silent_during_quiet_hours(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Nachts (z. B. Bad bewusst gekippt) keine wiederholte Push-/Sprachnachricht, nur die
    HA-Benachrichtigung."""
    freezer.move_to("2026-12-05 21:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass)
    notification_id = f"smart_ventilation_{entry.entry_id}_overtime"
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 30)
    first = [c for c in pushes if c.data["title"].startswith("Fenster noch offen")]
    assert len(first) == 1
    await _tick(hass, freezer, 70)  # 22:40, Ruhezeit
    assert len([c for c in pushes if c.data["title"].startswith("Fenster noch offen")]) == 1
    assert hass.data["persistent_notification"][notification_id]["message"].startswith(
        "Das Fenster ist seit"
    )

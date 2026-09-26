"""Schimmel-Frühwarnung über mehrere Tage und Monats-/Jahresvergleich."""
from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed, async_mock_service

from custom_components.smart_ventilation.const import DOMAIN

from .conftest import eid, setup_room


async def _tick(hass, freezer, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _titles(calls, prefix):
    return [c for c in calls if c.data["title"].startswith(prefix)]


async def test_critical_wall_minutes_are_counted(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    entry = await setup_room(hass, building_standard="old")
    hass.states.async_set("sensor.aussen_t", -5)      # kalte Wand
    hass.states.async_set("sensor.innen_ah", 11.0)    # feuchte Luft -> Wand > 80 %
    for _ in range(4):
        await _tick(hass, freezer, 5)
    room = hass.data[DOMAIN][entry.entry_id]
    assert room.mold_log["2026-12-05"] >= 15
    assert float(hass.states.get(eid(hass, "sensor", entry, "mold_streak")).state) == 0


async def test_three_critical_days_warn_once(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 23:00:00+01:00")      # Ruhezeit
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass)
    room = hass.data[DOMAIN][entry.entry_id]
    room.mold_log.update({"2026-12-02": 400, "2026-12-03": 500, "2026-12-04": 420})

    await _tick(hass, freezer, 1)
    assert not _titles(pushes, "Schimmelgefahr")       # nicht in der Ruhezeit

    freezer.move_to("2026-12-05 08:00:00+01:00")
    room.mold_log["2026-12-04"] = 420
    await _tick(hass, freezer, 1)
    await _tick(hass, freezer, 1)
    warnings = _titles(pushes, "Schimmelgefahr")
    assert len(warnings) == 1
    assert "Seit 3 Tagen" in warnings[0].data["message"]
    assert hass.states.get(eid(hass, "binary_sensor", entry, "mold_alarm")).state == "on"
    assert float(hass.states.get(eid(hass, "sensor", entry, "mold_streak")).state) == 3


async def test_two_days_do_not_warn(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass)
    room = hass.data[DOMAIN][entry.entry_id]
    room.mold_log.update({"2026-12-03": 100, "2026-12-04": 500, "2026-12-02": 500})  # 03. unkritisch
    await _tick(hass, freezer, 1)
    assert not _titles(pushes, "Schimmelgefahr")


async def test_month_archive_and_report(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-10-31 20:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass, monthly_report=True)
    room = hass.data[DOMAIN][entry.entry_id]
    room.history["2026-09"] = {"lueftungen": 10, "erfolgreich": 8, "minuten": 60, "bedarf_h": 1.0,
                               "kwh": 1.0, "kosten": 0.12, "schimmeltage": 0}
    for _ in range(6):                                 # 30 Min. Lüftungsbedarf im Oktober
        await _tick(hass, freezer, 5)
    assert room.period_stats("month")["need_hours"] >= 0.4

    freezer.move_to("2026-11-01 09:05:00+01:00")
    await _tick(hass, freezer, 0.5)
    await _tick(hass, freezer, 0.5)

    assert "2026-10" in room.history
    reports = _titles(pushes, "Monatsbericht")
    assert len(reports) == 1
    text = reports[0].data["message"]
    assert text.startswith("Oktober 2026")
    assert "weniger Bedarf als im September" in text   # 0,5 h statt 1,0 h

    need = hass.states.get(eid(hass, "sensor", entry, "need_month"))
    assert need.attributes["letzter_monat"]["monat"] == "Oktober 2026"

"""Schimmel-Frühwarnung über mehrere Tage und Monats-/Jahresvergleich."""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

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
    freezer.move_to("2026-12-05 06:30:00+01:00")      # Ruhezeit (bis 7 Uhr)
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass)
    room = hass.data[DOMAIN][entry.entry_id]
    room.mold_log.update({"2026-12-02": 400, "2026-12-03": 500, "2026-12-04": 420})

    await _tick(hass, freezer, 1)
    assert not _titles(pushes, "Schimmelgefahr")       # nicht in der Ruhezeit

    freezer.move_to("2026-12-05 08:00:00+01:00")      # nach der Ruhezeit nachholen
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


async def test_history_load_sanitizes_corrupt_state_and_measurement_edges(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    entry = await setup_room(hass)
    room = hass.data[DOMAIN][entry.entry_id]

    room._history_load({
        "mold_log": {"2026-12-01": 20},
        "history": {"2026-11": {"bedarf_h": 1}},
        "day_log": {"2026-12-04": {"minuten": 10}},
        "mold_warned": "corrupt",
        "last_anomaly_check": "not-a-date",
    })
    assert room.mold_log["2026-12-01"] == 20
    assert room._mold_warned is None
    assert room._last_anomaly_check is None

    now = __import__("homeassistant.util.dt", fromlist=["now"]).now()
    with patch("custom_components.smart_ventilation.coordinator.SmartVentilationCoordinator.wall_rh", new_callable=PropertyMock, return_value=85):
        room.recommended_minutes = 10
        room._last_measure = None
        room._measure(now)
        assert room.mold_log["2026-12-05"] == 0.5

    room._measure(now - timedelta(minutes=1))
    assert room.mold_log["2026-12-05"] == 0.5


async def test_history_day_archive_and_anomaly_notification(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-10 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass)
    room = hass.data[DOMAIN][entry.entry_id]

    with patch("custom_components.smart_ventilation.coordinator.SmartVentilationCoordinator.energy_price", new_callable=PropertyMock, return_value=0.4):
        room._archive_day({
        "key": "2026-12-09",
        "ok": 3,
        "seconds": 7200,
        "kwh": 2.0,
            "kwh_gespart": 0.5,
        })
        assert room.day_log["2026-12-09"]["kosten"] == 0.8
        assert room.day_log["2026-12-09"]["kwh_netto"] == 1.5
        assert room.day_log["2026-12-09"]["kosten_netto"] == 0.6

    for i in range(1, 8):
        room.day_log[(__import__("datetime").date(2026, 12, 10) - timedelta(days=i)).isoformat()] = {"minuten": 10}
    room.day_log["2026-12-09"]["minuten"] = 120
    await room._anomaly_check(__import__("homeassistant.util.dt", fromlist=["now"]).now())
    assert any(c.data["title"].startswith("Ungewöhnlich viel Lüftungsbedarf") for c in pushes)
    assert room._last_anomaly_check is not None


async def test_history_mold_warning_retry_and_monthly_overview_suppression(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    entry = await setup_room(hass, monthly_report=True)
    room = hass.data[DOMAIN][entry.entry_id]
    room.mold_log.update({"2026-12-02": 500, "2026-12-03": 500, "2026-12-04": 500})
    room._save = AsyncMock()
    room._send = AsyncMock(return_value=False)
    await room._mold_early_warning(__import__("homeassistant.util.dt", fromlist=["now"]).now())
    assert room._mold_warned is None

    room.history["2026-11"] = {
        "lueftungen": 2, "erfolgreich": 2, "minuten": 60, "bedarf_h": 1.0,
        "kwh": 1.0, "kosten": 0.4, "schimmeltage": 0,
    }
    room._last_month_report = None
    room.hass.data[DOMAIN]["overview"] = SimpleNamespace(is_overview=True, monthly_report=True)
    await room._monthly_report(__import__("homeassistant.util.dt", fromlist=["now"]).now().replace(day=1, hour=9))
    assert room._last_month_report == "2026-11"

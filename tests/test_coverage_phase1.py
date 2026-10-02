"""Gezielte Coverage-Tests für Export, Übersicht und Dashboard-Karte."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ventilation.const import CONF_NAME, DOMAIN
from custom_components.smart_ventilation.export import _rows, _rooms, _write_csv, async_setup_export
from custom_components.smart_ventilation.overview import OverviewCoordinator
from custom_components.smart_ventilation import card


def _room(name="Wohnzimmer", *, overview=False):
    stats = {
        "day": {"count": 2, "ok": 1, "minutes": 18, "kwh": 0.4, "cost": 0.12, "kwh_gespart": 0.1, "kosten_gespart": 0.03},
        "week": {"count": 5, "ok": 4, "minutes": 52, "kwh": 1.1, "cost": 0.33, "kwh_gespart": 0.3, "kosten_gespart": 0.09},
        "month": {"count": 12, "ok": 10, "minutes": 140, "kwh": 3.2, "cost": 0.96, "kwh_gespart": 0.8, "kosten_gespart": 0.24},
        "total": {"count": 30, "ok": 25, "minutes": 360, "kwh": 8.0, "cost": 2.4, "kwh_gespart": 2.0, "kosten_gespart": 0.6},
    }
    return SimpleNamespace(
        is_overview=overview,
        data={CONF_NAME: name, "name": name},
        period_stats=lambda period: stats[period],
        humidity_difference=2.0,
        mold_risk="erhöht",
        co2=1200,
        _rain_soon=False,
        recommended_minutes=15,
        recommendation="Lüften",
        pause_reason=lambda: None,
        air_quality="mittel",
        session=None,
        own_entity=lambda domain, key: f"{domain}.test_{key}",
        dehumidifier_active=True,
        shutter_recommended=True,
        shutter_closed=False,
        day_trend=lambda days: [
            {"datum": "2026-10-01", "anzahl": 2, "kwh": 0.4, "kosten": 0.12, "kwh_netto": 0.3, "kosten_netto": 0.09},
            {"datum": "2026-10-02", "anzahl": 1, "kwh": 0.2, "kosten": 0.06, "kwh_netto": 0.15, "kosten_netto": 0.045},
        ],
    )


def test_export_rooms_rows_and_csv(hass: HomeAssistant):
    room = _room()
    overview = _room("Übersicht", overview=True)
    hass.data[DOMAIN] = {"room": room, "overview": overview}

    assert _rooms(hass) == [room]
    rows = _rows(hass)
    assert len(rows) == 4
    assert rows[0]["raum"] == "Wohnzimmer"
    assert rows[0]["zeitraum"] == "Heute"
    assert rows[-1]["zeitraum"] == "Gesamt"

    filename, write = _write_csv(hass, rows)
    write()
    path = Path(hass.config.path("www", filename))
    assert path.is_file()
    text = path.read_text(encoding="utf-8-sig")
    assert "raum;zeitraum;anzahl" in text
    assert "Wohnzimmer;Heute;2;1" in text


async def test_export_service_is_idempotent_and_returns_result(hass: HomeAssistant):
    hass.data[DOMAIN] = {"room": _room()}
    await async_setup_export(hass)
    await async_setup_export(hass)

    result = await hass.services.async_call(
        DOMAIN, "export_statistics", {}, blocking=True, return_response=True
    )
    assert result["zeilen"] == 4
    assert result["url"].startswith("/local/smart_ventilation_export_")
    assert hass.services.has_service(DOMAIN, "export_statistics")


def test_overview_properties_rooms_and_totals(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="overview-test",
        data={
            "entry_type": "overview",
            "name": "Übersicht",
            "combine_notifications": True,
            "notify_services": ["notify.mobile_app_test", "light.foo"],
            "persons": ["person.patrick", ""],
        },
    )
    entry.add_to_hass(hass)
    room1 = _room("Bad")
    room2 = _room("Wohnzimmer")
    hass.data[DOMAIN] = {"r1": room1, "r2": room2, "o": SimpleNamespace(is_overview=True)}

    coordinator = OverviewCoordinator(hass, entry)
    assert coordinator.combine is True
    assert coordinator.monthly_report is False
    assert coordinator.weekly_report is False
    assert coordinator.persons == ["person.patrick"]
    assert coordinator.notify_targets == ["notify.mobile_app_test"]
    assert coordinator.rooms() == [room1, room2]

    totals = coordinator.totals()
    assert totals["heute_kwh"] == 0.8
    assert totals["heute_eur_netto"] == 0.18

    trend = coordinator.day_trend(7)
    assert trend[0]["anzahl"] == 4
    assert trend[0]["kwh"] == 0.8
    assert trend[1]["kosten_netto"] == 0.09


def test_overview_room_list_and_urgency(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, entry_id="overview-test", data={"entry_type": "overview"})
    entry.add_to_hass(hass)
    room = _room("Bad")
    hass.data[DOMAIN] = {"r1": room}
    coordinator = OverviewCoordinator(hass, entry)

    urgency = coordinator.urgency(room)
    assert urgency == 6.5
    result = coordinator.room_list()
    assert result[0]["raum"] == "Bad"
    assert result[0]["entfeuchter"] is True
    assert result[0]["rollo_empfehlung"] is True
    assert result[0]["heute_kwh_netto"] == 0.3
    assert coordinator.rooms_needing()[0]["raum"] == "Bad"
    assert coordinator.most_urgent == "Bad"

    room.recommended_minutes = 0
    assert coordinator.rooms_needing() == []
    assert coordinator.most_urgent == "Keiner"


async def test_overview_action_snooze_and_skip(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, entry_id="overview-actions", data={"entry_type": "overview"})
    entry.add_to_hass(hass)
    coordinator = OverviewCoordinator(hass, entry)
    coordinator._save = AsyncMock()

    coordinator._handle_action(SimpleNamespace(data={"action": f"__invalid__"}))
    assert coordinator._snooze_until is None
    assert coordinator._skip_date is None

    coordinator._handle_action(SimpleNamespace(data={"action": f"lueften_snooze_{entry.entry_id}"}))
    assert coordinator._snooze_until is not None
    coordinator._save.assert_awaited_once()

    coordinator._save.reset_mock()
    coordinator._handle_action(SimpleNamespace(data={"action": f"lueften_skip_{entry.entry_id}"}))
    assert coordinator._skip_date is not None
    coordinator._save.assert_awaited_once()


def test_card_helpers_and_copy(tmp_path: Path):
    src = tmp_path / "source.js"
    dest = tmp_path / "nested" / "card.js"
    src.write_text("console.log('test');", encoding="utf-8")

    assert card._base("/local/smart_ventilation/card.js?v=2") == "/local/smart_ventilation/card.js"
    assert card._base(None) == ""
    assert card._copy_to_www(src, dest) is True
    assert dest.read_text(encoding="utf-8") == "console.log('test');"
    assert card._copy_to_www(src, dest) is True


async def test_card_resource_registration_paths(hass: HomeAssistant):
    resources = MagicMock()
    resources.async_get_info = AsyncMock()
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()
    resources.async_delete_item = AsyncMock()
    resources.async_items.return_value = []

    with patch.object(card, "_lovelace_resources", return_value=resources):
        assert await card._async_register_resource(hass) is True
        resources.async_create_item.assert_awaited_once()

    resources.async_items.return_value = [
        {"id": "keep", "url": card.CARD_URL + "?old=1", "type": "js"},
        {"id": "duplicate", "url": card.LOCAL_URL, "type": "module"},
    ]
    resources.async_update_item.reset_mock()
    resources.async_delete_item.reset_mock()
    with patch.object(card, "_lovelace_resources", return_value=resources):
        assert await card._async_register_resource(hass) is True
        resources.async_update_item.assert_awaited_once()
        resources.async_delete_item.assert_awaited_once_with("duplicate")


async def test_card_resource_and_extra_module_edge_cases(hass: HomeAssistant):
    with patch.object(card, "_lovelace_resources", return_value=None):
        assert await card._async_register_resource(hass) is False
        await card.async_remove_resource(hass)

    with patch("homeassistant.components.frontend.add_extra_js_url", side_effect=KeyError):
        assert card._add_extra_module(hass, card.CARD_URL_VERSIONED) is False

    with patch("homeassistant.components.frontend.add_extra_js_url"):
        assert card._add_extra_module(hass, card.CARD_URL_VERSIONED) is True


@pytest.mark.asyncio
async def test_card_register_skips_without_http(hass: HomeAssistant):
    hass.data.pop(card.DATA_URL, None)
    hass.http = None
    await card.async_register_card(hass)
    assert card.DATA_URL not in hass.data

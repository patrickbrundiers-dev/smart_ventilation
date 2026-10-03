"""Gezielte Coverage-Tests für Export, Übersicht und Dashboard-Karte."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ventilation.const import (
    ACTION_SKIP,
    ACTION_SNOOZE,
    CAT_WARNING,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMP,
    CONF_NAME,
    CONF_NOTIFY_TARGETS_WARNING,
    DOMAIN,
)
from custom_components.smart_ventilation.export import _rows, _rooms, _write_csv, async_setup_export
from custom_components.smart_ventilation.overview import OverviewCoordinator
from custom_components.smart_ventilation import card, notify_util
from custom_components.smart_ventilation.extras import de_num, _num_state, _week_key


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
    assert urgency == 5.0
    result = coordinator.room_list()
    assert result[0]["raum"] == "Bad"
    assert result[0]["entfeuchter"] is True
    assert result[0]["rollo_empfehlung"] is True
    assert result[0]["heute_kwh_netto"] == 0.3
    assert coordinator.rooms_needing()[0]["raum"] == "Bad"
    assert coordinator.most_urgent == "Bad"


def test_urgency_ranks_critical_mold_above_high_mold(hass: HomeAssistant):
    """MOLD_WEIGHT kannte "kritisch" bisher nicht -> .get(..., 0.0) gab einem Raum mit akutem
    Schimmelrisiko denselben (Null-)Dringlichkeits-Bonus wie einem Raum ganz ohne Risiko. Ein
    Raum mit "kritisch" muss dringender sein als einer mit "hoch", nicht gleich dringend wie
    einer ganz ohne Schimmelrisiko."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="overview-test", data={"entry_type": "overview"})
    entry.add_to_hass(hass)
    hoch = _room("Hoch-Risiko")
    hoch.mold_risk = "hoch"
    kritisch = _room("Kritisch-Risiko")
    kritisch.mold_risk = "kritisch"
    kein_risiko = _room("Kein-Risiko")
    kein_risiko.mold_risk = "niedrig"
    hass.data[DOMAIN] = {"hoch": hoch, "kritisch": kritisch, "kein_risiko": kein_risiko}
    coordinator = OverviewCoordinator(hass, entry)

    assert coordinator.urgency(kritisch) > coordinator.urgency(hoch)
    assert coordinator.urgency(kritisch) > coordinator.urgency(kein_risiko)


async def test_overview_action_snooze_and_skip(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, entry_id="overview-actions", data={"entry_type": "overview"})
    entry.add_to_hass(hass)
    coordinator = OverviewCoordinator(hass, entry)
    coordinator._save = AsyncMock()

    coordinator._handle_action(SimpleNamespace(data={"action": f"__invalid__"}))
    assert coordinator._snooze_until is None
    assert coordinator._skip_date is None

    coordinator._handle_action(SimpleNamespace(data={"action": f"{ACTION_SNOOZE}{entry.entry_id}"}))
    assert coordinator._snooze_until is not None
    coordinator._save.assert_awaited_once()

    coordinator._save.reset_mock()
    coordinator._handle_action(SimpleNamespace(data={"action": f"{ACTION_SKIP}{entry.entry_id}"}))
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


async def test_overview_setup_loads_state_and_unload(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, entry_id="overview-setup", data={"entry_type": "overview"})
    entry.add_to_hass(hass)
    coordinator = OverviewCoordinator(hass, entry)
    coordinator.store.async_load = AsyncMock(return_value={
        "last_notification_at": "2026-10-02T12:00:00+00:00",
        "skip_date": "not-a-date",
        "snooze_until": "2026-10-02T12:05:00+00:00",
        "last_report": "2026-W40",
        "last_month_report": "2026-09",
    })
    unsub_tick = MagicMock()
    unsub_bus = MagicMock()
    with patch("custom_components.smart_ventilation.overview.async_track_time_interval", return_value=unsub_tick), patch("homeassistant.core.EventBus.async_listen", return_value=unsub_bus) as listen_mock:
        await coordinator.async_setup()

    assert coordinator.last_notification_at is not None
    assert coordinator._skip_date is None
    assert coordinator._snooze_until is not None
    assert coordinator._last_report == "2026-W40"
    assert coordinator._last_month_report == "2026-09"
    assert len(coordinator._unsubs) == 2

    callback = MagicMock()
    remove = coordinator.async_add_listener(callback)
    callback()
    remove()
    coordinator.async_unload()
    unsub_tick.assert_called_once()
    listen_mock.assert_called_once()
    assert coordinator._unsubs == []


async def test_overview_tick_respects_combine_and_calls_reports(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, entry_id="overview-tick", data={"entry_type": "overview"})
    entry.add_to_hass(hass)
    coordinator = OverviewCoordinator(hass, entry)
    listener = MagicMock()
    coordinator._listeners = [listener]
    coordinator._send_combined = AsyncMock()
    coordinator._send_weekly_report = AsyncMock()
    coordinator._send_monthly_report = AsyncMock()

    await coordinator._tick()
    listener.assert_called_once()
    coordinator._send_combined.assert_awaited_once()
    coordinator._send_weekly_report.assert_awaited_once()
    coordinator._send_monthly_report.assert_awaited_once()

    coordinator.data["combine_notifications"] = False
    coordinator._send_combined.reset_mock()
    await coordinator._tick()
    coordinator._send_combined.assert_not_awaited()


async def test_overview_combined_notification_success_and_failure(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="overview-send",
        data={
            "entry_type": "overview",
            "notify_services": ["notify.mobile_app_test"],
            "combine_notifications": True,
            "notification_cooldown": 0,
        },
    )
    entry.add_to_hass(hass)
    coordinator = OverviewCoordinator(hass, entry)
    room = _room("Bad")
    room.reminder_allowed = MagicMock(return_value=True)
    hass.data[DOMAIN] = {"room": room}

    with patch("custom_components.smart_ventilation.overview.notify_util.anyone_home", return_value=True), patch(
        "custom_components.smart_ventilation.overview.notify_util.in_quiet_hours", return_value=False
    ), patch(
        "custom_components.smart_ventilation.overview.notify_util.targets_for_category", return_value=["notify.mobile_app_test"]
    ), patch(
        "custom_components.smart_ventilation.overview.notify_util.filter_targets", return_value=["notify.mobile_app_test"]
    ), patch(
        "custom_components.smart_ventilation.overview.notify_util.send", new=AsyncMock(return_value=True)
    ) as send:
        coordinator._save = AsyncMock()
        await coordinator._send_combined()
        send.assert_awaited_once()
        assert coordinator.last_notification_at is not None
        assert coordinator._save.await_count == 1

    coordinator.last_notification_at = None
    coordinator._save = AsyncMock()
    with patch("custom_components.smart_ventilation.overview.notify_util.anyone_home", return_value=True), patch(
        "custom_components.smart_ventilation.overview.notify_util.in_quiet_hours", return_value=False
    ), patch(
        "custom_components.smart_ventilation.overview.notify_util.targets_for_category", return_value=["notify.mobile_app_test"]
    ), patch(
        "custom_components.smart_ventilation.overview.notify_util.filter_targets", return_value=["notify.mobile_app_test"]
    ), patch(
        "custom_components.smart_ventilation.overview.notify_util.send", new=AsyncMock(return_value=False)
    ):
        await coordinator._send_combined()
    assert coordinator.last_notification_at is None


async def test_overview_combined_notification_blockers_and_snooze(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="overview-blockers",
        data={"entry_type": "overview", "notify_services": ["notify.test"], "notification_cooldown": 60},
    )
    entry.add_to_hass(hass)
    coordinator = OverviewCoordinator(hass, entry)
    room = _room("Bad")
    room.reminder_allowed = MagicMock(return_value=True)
    hass.data[DOMAIN] = {"room": room}

    coordinator._snooze_until = __import__("homeassistant.util.dt", fromlist=["now"]).now() + timedelta(minutes=10)
    with patch("custom_components.smart_ventilation.overview.notify_util.anyone_home", return_value=False):
        await coordinator._send_combined()
    coordinator._snooze_until = None

    coordinator.last_notification_at = __import__("homeassistant.util.dt", fromlist=["now"]).now()
    with patch("custom_components.smart_ventilation.overview.notify_util.anyone_home", return_value=True), patch(
        "custom_components.smart_ventilation.overview.notify_util.in_quiet_hours", return_value=False
    ):
        await coordinator._send_combined()
    assert coordinator.last_notification_at is not None


async def test_overview_weekly_report_branches(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="overview-weekly",
        data={"entry_type": "overview", "notify_services": ["notify.test"], "weekly_report": True},
    )
    entry.add_to_hass(hass)
    coordinator = OverviewCoordinator(hass, entry)

    with patch("custom_components.smart_ventilation.overview.dt_util.now", return_value=__import__("datetime").datetime(2026, 10, 4, 20, 0, tzinfo=__import__("datetime").timezone.utc)), patch(
        "custom_components.smart_ventilation.overview.notify_util.send", new=AsyncMock()
    ):
        hass.data[DOMAIN] = {}
        await coordinator._send_weekly_report()
        assert coordinator._last_report is None

    room = _room("Bad")
    room.weekly_summary = MagicMock(return_value={"raum": "Bad", "anzahl": 3, "kwh": 1.2, "kosten": 0.34, "schimmeltage": 2})
    hass.data[DOMAIN] = {"room": room}
    coordinator._save = AsyncMock()
    with patch("custom_components.smart_ventilation.overview.dt_util.now", return_value=__import__("datetime").datetime(2026, 10, 4, 20, 0, tzinfo=__import__("datetime").timezone.utc)), patch(
        "custom_components.smart_ventilation.overview.notify_util.targets_for_category", return_value=["notify.test"]
    ), patch(
        "custom_components.smart_ventilation.overview.notify_util.send", new=AsyncMock(return_value=True)
    ) as send:
        await coordinator._send_weekly_report()
        send.assert_awaited_once()
    assert coordinator._last_report is not None


async def test_overview_monthly_report_with_comparison(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="overview-monthly",
        data={"entry_type": "overview", "notify_services": ["notify.test"], "monthly_report": True},
    )
    entry.add_to_hass(hass)
    room = _room("Bad")
    room.history = {"2026-09": {}}
    room.month_comparison = MagicMock(return_value={
        "bedarf_h": 3.0,
        "vormonat": {"bedarf_h": 2.0},
        "kwh": 1.5,
        "kosten": 0.45,
        "schimmeltage": 1,
        "lueftungen": 4,
    })
    hass.data[DOMAIN] = {"room": room}
    coordinator = OverviewCoordinator(hass, entry)
    coordinator._save = AsyncMock()

    with patch("custom_components.smart_ventilation.overview.dt_util.now", return_value=__import__("datetime").datetime(2026, 10, 1, 20, 0, tzinfo=__import__("datetime").timezone.utc)), patch(
        "custom_components.smart_ventilation.overview.notify_util.targets_for_category", return_value=["notify.test"]
    ), patch(
        "custom_components.smart_ventilation.overview.notify_util.send", new=AsyncMock(return_value=True)
    ) as send:
        await coordinator._send_monthly_report()
        send.assert_awaited_once()
        assert "mehr" in send.await_args.args[3]

    await coordinator._send_monthly_report()
    assert coordinator._last_month_report == "2026-09"


async def test_card_registers_static_path_and_local_url(hass: HomeAssistant, tmp_path: Path):
    hass.data.pop(card.DATA_URL, None)
    hass.state = "running"
    http = MagicMock()
    http.async_register_static_paths = AsyncMock()
    hass.http = http
    with patch.object(card, "CARD_FILE", tmp_path / "card.js"), patch.object(
        card, "_copy_to_www", return_value=True
    ), patch.object(card, "_local_file", return_value=tmp_path / "www" / "card.js"), patch.object(
        card, "_local_served", return_value=True
    ), patch.object(card, "_add_extra_module", return_value=True), patch.object(
        card, "_async_register_resource", new=AsyncMock(return_value=True)
    ):
        (tmp_path / "card.js").write_text("x", encoding="utf-8")
        await card.async_register_card(hass)

    assert hass.data[card.DATA_URL] == card.LOCAL_URL_VERSIONED
    http.async_register_static_paths.assert_awaited_once()


async def test_card_registers_fallback_and_retry_when_not_running(hass: HomeAssistant, tmp_path: Path):
    hass.data.pop(card.DATA_URL, None)
    hass.state = "not_running"
    http = MagicMock()
    http.async_register_static_paths = AsyncMock()
    hass.http = http

    retry_listener = MagicMock()
    with patch.object(card, "CARD_FILE", tmp_path / "card.js"), patch.object(
        card, "_copy_to_www", return_value=False
    ), patch.object(card, "_local_served", return_value=False), patch.object(
        card, "_add_extra_module", return_value=False
    ), patch.object(card, "_async_register_resource", new=AsyncMock(return_value=False)), patch("homeassistant.core.EventBus.async_listen_once", return_value=retry_listener) as listen_once_mock:
        (tmp_path / "card.js").write_text("x", encoding="utf-8")
        await card.async_register_card(hass)

    assert hass.data[card.DATA_URL] == card.CARD_URL_VERSIONED
    listen_once_mock.assert_called_once()


async def test_card_register_static_path_failure_does_not_mark_ready(hass: HomeAssistant, tmp_path: Path):
    hass.data.pop(card.DATA_URL, None)
    http = MagicMock()
    http.async_register_static_paths = AsyncMock(side_effect=RuntimeError("boom"))
    hass.http = http

    with patch.object(card, "CARD_FILE", tmp_path / "card.js"):
        (tmp_path / "card.js").write_text("x", encoding="utf-8")
        await card.async_register_card(hass)

    assert card.DATA_URL not in hass.data


async def test_card_remove_resource_tolerates_resource_failure(hass: HomeAssistant):
    resources = MagicMock()
    resources.async_get_info = AsyncMock(side_effect=RuntimeError("boom"))
    resources.async_items.return_value = []
    with patch.object(card, "_lovelace_resources", return_value=resources), patch.object(
        hass, "async_add_executor_job", new=AsyncMock()
    ) as executor:
        await card.async_remove_resource(hass)
        executor.assert_awaited_once()


def test_notify_time_category_and_presence_filters(hass: HomeAssistant):
    from datetime import datetime, timezone

    saturday = datetime(2026, 10, 3, 23, 30, tzinfo=timezone.utc)
    data = {
        "quiet_weekend_different": True,
        "quiet_start_weekend": "22:00",
        "quiet_end_weekend": "07:00",
        "quiet_start": "23:00",
        "quiet_end": "06:00",
    }
    assert notify_util.parse_time("22:30:00", "00:00") == 1350
    assert notify_util.parse_time("invalid", "01:30") == 90
    assert notify_util.in_quiet_hours(saturday, data, "23:00", "06:00")
    assert notify_util.quiet_hours_range(saturday, data) == ("22:00", "07:00")

    targets = ["notify.mobile_app_p", "notify.mobile_app_j"]
    assert notify_util.targets_for_category({}, "unknown", targets) == targets
    assert notify_util.targets_for_category({CONF_NOTIFY_TARGETS_WARNING: []}, CAT_WARNING, targets) == []
    assert notify_util.targets_for_category({CONF_NOTIFY_TARGETS_WARNING: ["notify.mobile_app_p"]}, CAT_WARNING, targets) == [
        "notify.mobile_app_p"
    ]

    hass.states.async_set("person.patrick", "home", {"device_trackers": ["device_tracker.p"]})
    hass.states.async_set("person.jenny", "not_home", {"device_trackers": ["device_tracker.j"]})
    assert notify_util.anyone_home(hass, ["person.patrick", "person.jenny"])
    assert notify_util.filter_targets(hass, targets, ["person.patrick", "person.jenny"]) == [
        "notify.mobile_app_p"
    ]
    assert notify_util.filter_targets(hass, targets, ["person.patrick"], only_home=False) == targets
    assert notify_util.filter_targets(hass, targets, ["person.patrick"], only_person="person.patrick") == [
        "notify.mobile_app_p"
    ]
    assert notify_util.filter_targets(hass, targets, [], only_person="person.patrick") == []
    assert notify_util.owner_map(hass, ["person.unknown"]) == {}


async def test_notify_send_voice_normal_and_failed_services(hass: HomeAssistant):
    from pytest_homeassistant_custom_component.common import async_mock_service

    async_mock_service(hass, "notify", "mobile_app_test")
    async_mock_service(hass, "notify", "alexa_media_test")
    normal = await notify_util.send(
        hass,
        ["notify.mobile_app_test", "notify.alexa_media_test"],
        "Lüften fertig: Bad",
        "4.2 °C, 10 %",
        "tag",
        actions=[{"action": "SV_SNOOZE"}],
    )
    assert normal is True

    with patch(
        "homeassistant.core.ServiceRegistry.has_service",
        side_effect=lambda domain, service: service == "broken",
    ), patch(
        "homeassistant.core.ServiceRegistry.async_call",
        new=AsyncMock(side_effect=RuntimeError("offline")),
    ):
        assert await notify_util.send(hass, ["notify.broken"], "Titel", "Text", "tag") is False


def test_extras_helpers_and_trace(hass: HomeAssistant):
    assert de_num(1.25, 2) == "1,25"
    assert _week_key(__import__("datetime").datetime(2026, 10, 2)) == "2026-W40"

    hass.states.async_set("sensor.test", "12.5")
    assert _num_state(hass, "sensor.test") == 12.5
    hass.states.async_set("sensor.test", "not-a-number")
    assert _num_state(hass, "sensor.test") is None
    hass.states.async_set("sensor.test", "nan")
    assert _num_state(hass, "sensor.test") is None

    from custom_components.smart_ventilation.extras import RoomExtrasMixin
    class TraceRoom(RoomExtrasMixin):
        pass

    room = TraceRoom()
    room.hass = hass
    room.data = {CONF_INDOOR_HUMIDITY: "sensor.test", CONF_INDOOR_TEMP: "sensor.temp"}
    room.session = {"trace": []}
    room.current_duration_seconds = 30
    room.last_trace = None
    hass.states.async_set("sensor.test", "10")
    hass.states.async_set("sensor.temp", "20")
    room._init_extras()
    room._trace_add()
    assert room.session["trace"]
    room.session = None
    room.last_trace = {"ende": "now", "punkte": [[i, 10, 20] for i in range(70)]}
    card_data = RoomExtrasMixin.trace_for_card(room)
    assert card_data["laeuft"] is False
    assert len(card_data["punkte"]) == 61

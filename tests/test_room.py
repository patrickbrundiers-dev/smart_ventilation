"""Ein Raum im echten Home Assistant: Entitäten, Lüftung, Heizung, Warnungen, Reparaturen."""
from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.smart_ventilation.const import DOMAIN

from .conftest import eid, setup_entry, setup_room, set_room_states, ROOM_DATA


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_entities_and_recommendation(hass: HomeAssistant, berlin) -> None:
    entry = await setup_room(hass)
    rec = hass.states.get(eid(hass, "sensor", entry, "recommendation"))
    assert rec is not None
    assert "Stoßlüften" in rec.state and "Querlüften" in rec.state  # Winter + 2 Fenster
    assert "karte" in rec.attributes
    assert hass.states.get(eid(hass, "binary_sensor", entry, "recommended")).state == "on"
    assert hass.states.get(eid(hass, "sensor", entry, "season")).state == "winter"
    wall = float(hass.states.get(eid(hass, "sensor", entry, "wall_temperature")).state)
    assert 10 < wall < 20.5
    assert hass.states.get(eid(hass, "button", entry, "reset_learning")) is not None


async def test_ventilation_session(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("climate.wz", "heat", {"hvac_modes": ["heat", "off"], "temperature": 21})
    entry = await setup_room(hass, climate_entities=["climate.wz"])

    # Fenster auf -> nach 1 Min. Heizung aus
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 2)
    assert [c.data["hvac_mode"] for c in hvac] == ["off"]
    assert hass.states.get(eid(hass, "sensor", entry, "ventilation_running")).state == "running"

    # Feuchte sinkt deutlich -> "Lüften fertig"
    hass.states.async_set("sensor.innen_ah", 5.5)
    await _tick(hass, freezer, 1)
    assert any("fertig" in c.data["title"] for c in pushes)

    # Fenster zu -> Heizung zurück, Statistik zählt eine erfolgreiche Lüftung
    hass.states.async_set("binary_sensor.fenster_1", "off")
    await hass.async_block_till_done()
    assert [c.data["hvac_mode"] for c in hvac] == ["off", "heat"]
    today = hass.states.get(eid(hass, "sensor", entry, "stats_day"))
    assert today.state == "1"
    assert today.attributes["erfolgreich"] == 1
    assert today.attributes["waermeverlust_kwh"] > 0
    assert hass.states.get(eid(hass, "binary_sensor", entry, "ventilated_today")).state == "on"


async def test_cooling_warning(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass)
    hass.states.async_set("binary_sensor.fenster_1", "on")
    hass.states.async_set("sensor.innen_t", 17.2)
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)
    await _tick(hass, freezer, 1)
    warnings = [c for c in pushes if "kühlt aus" in c.data["title"]]
    assert len(warnings) == 1
    assert hass.states.get(eid(hass, "binary_sensor", entry, "cooling_down")).state == "on"


async def test_reminder_has_buttons_and_quiet_hours(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 23:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    await setup_room(hass)
    await _tick(hass, freezer, 1)
    assert not [c for c in pushes if c.data["title"].startswith("Lüften:")]  # Ruhezeit

    freezer.move_to("2026-12-06 08:00:00+01:00")
    await _tick(hass, freezer, 1)
    reminders = [c for c in pushes if c.data["title"].startswith("Lüften:")]
    assert len(reminders) == 1
    assert len(reminders[0].data["data"]["actions"]) == 2


async def test_best_time_from_forecast(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 08:10:00+01:00")
    now = dt_util.now().replace(minute=0, second=0, microsecond=0)
    forecast = [
        {"datetime": (now + timedelta(hours=h)).isoformat(), "temperature": t, "humidity": rh,
         "precipitation": rain, "precipitation_probability": prob, "wind_speed": 10}
        for h, t, rh, rain, prob in [(1, 1, 92, 0, 0), (6, 6, 70, 0, 10), (7, 7, 65, 2, 80)]
    ]
    async_mock_service(
        hass, "weather", "get_forecasts",
        response={"weather.home": {"forecast": forecast}},
        supports_response=SupportsResponse.ONLY,
    )
    entry = await setup_room(hass, weather_entity="weather.home")
    await _tick(hass, freezer, 0.5)
    best = hass.states.get(eid(hass, "sensor", entry, "best_time"))
    assert best.attributes["text"] == "Heute 14:00 Uhr"  # 14 Uhr mild & trocken, 15 Uhr Regen


async def test_repair_issue_for_missing_sensor(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    entry = await setup_room(hass)
    issue_id = f"unavailable_{entry.entry_id}_sensor_innen_ah"
    hass.states.async_set("sensor.innen_ah", "unavailable")
    await _tick(hass, freezer, 0.5)
    await _tick(hass, freezer, 11)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    hass.states.async_set("sensor.innen_ah", 9.0)
    await _tick(hass, freezer, 0.5)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_legacy_entry_still_loads(hass: HomeAssistant, berlin) -> None:
    """Einträge aus älteren Versionen: ein Fenster als Text, altes notify-Feld, kein entry_type."""
    set_room_states(hass)
    legacy = {k: v for k, v in ROOM_DATA.items() if k not in (
        "entry_type", "notify_services", "persons", "co2_sensor", "climate_entities", "building_standard")}
    legacy.update(window="binary_sensor.fenster_1", notify_service="notify.mobile_app_test")
    entry = await setup_entry(hass, legacy, "alt", "Alt")
    assert hass.states.get(eid(hass, "sensor", entry, "recommendation")) is not None


async def test_overview_most_urgent(hass: HomeAssistant, berlin) -> None:
    await setup_room(hass)
    overview = await setup_entry(
        hass, {"entry_type": "overview", "name": "Lüften Übersicht", "combine_notifications": True,
               "notify_services": [], "persons": []}, "overview", "Lüften Übersicht")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()
    urgent = hass.states.get(eid(hass, "sensor", overview, "most_urgent"))
    assert urgent.state == "Schlafzimmer"
    assert urgent.attributes["raeume"][0]["lueften"] is True


async def test_unload(hass: HomeAssistant, berlin) -> None:
    entry = await setup_room(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def _heating_setup(hass, bt_window=False, cgh_window=False):
    """Wie beim Nutzer: 2 Thermostate -> Climate Group Helper -> Better Thermostat."""
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    reg = er.async_get(hass)
    cgh_entry = MockConfigEntry(
        domain="climate_group_helper",
        options={"window_mode": "enabled", "room_sensor": "binary_sensor.fenster_1"} if cgh_window else {},
    )
    cgh_entry.add_to_hass(hass)
    reg.async_get_or_create("climate", "climate_group_helper", "g1", config_entry=cgh_entry, suggested_object_id="gr_bad")
    bt_entry = MockConfigEntry(
        domain="better_thermostat",
        data={"thermostat": [{"trv": "climate.gr_bad"}], "window_sensors": "binary_sensor.fenster_1" if bt_window else None},
    )
    bt_entry.add_to_hass(hass)
    reg.async_get_or_create("climate", "better_thermostat", "bt1", config_entry=bt_entry, suggested_object_id="bad_bt")
    modes = {"hvac_modes": ["heat", "off"], "temperature": 21}
    hass.states.async_set("climate.trv_1", "heat", modes)
    hass.states.async_set("climate.trv_2", "heat", modes)
    hass.states.async_set("climate.gr_bad", "heat", {**modes, "entity_id": ["climate.trv_1", "climate.trv_2"]})
    hass.states.async_set("climate.bad_bt", "heat", modes)


async def _open_window(hass, freezer):
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 2)


async def test_heating_switches_better_thermostat_on_top(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    """Gruppe oder einzelnes Thermostat gewählt -> geschaltet wird das Better Thermostat darüber."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    _heating_setup(hass)
    await setup_room(hass, climate_entities=["climate.gr_bad", "climate.trv_1"])
    await _open_window(hass, freezer)
    assert [(c.data["entity_id"], c.data["hvac_mode"]) for c in hvac] == [("climate.bad_bt", "off")]
    hass.states.async_set("binary_sensor.fenster_1", "off")
    await hass.async_block_till_done()
    assert [(c.data["entity_id"], c.data["hvac_mode"]) for c in hvac][-1] == ("climate.bad_bt", "heat")


async def test_heating_left_to_better_thermostat_window(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    _heating_setup(hass, bt_window=True)
    entry = await setup_room(hass, climate_entities=["climate.bad_bt"])
    await _open_window(hass, freezer)
    await _tick(hass, freezer, 1)
    assert not hvac
    running = hass.states.get(eid(hass, "sensor", entry, "ventilation_running"))
    assert running.attributes["heizung_selbst_geregelt"] == {"climate.bad_bt": "Better Thermostat"}


async def test_heating_left_to_climate_group_helper_window(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    _heating_setup(hass, cgh_window=True)
    entry = await setup_room(hass, climate_entities=["climate.bad_bt"])
    await _open_window(hass, freezer)
    await _tick(hass, freezer, 1)
    assert not hvac
    running = hass.states.get(eid(hass, "sensor", entry, "ventilation_running"))
    assert running.attributes["heizung_selbst_geregelt"] == {"climate.bad_bt": "Climate Group Helper"}


async def test_card_shows_pause_after_ventilation(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    """Nach dem Lüften: Karte zeigt „Pausiert“ statt erneut „Lüften“ – wie bei den Benachrichtigungen."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    entry = await setup_room(hass)
    rec = eid(hass, "sensor", entry, "recommendation")
    assert hass.states.get(rec).attributes["karte"]["pausiert"] is None
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 3)
    hass.states.async_set("binary_sensor.fenster_1", "off")
    # Feuchte nach dem Lüften realistisch gesunken, aber Schimmelrisiko noch nicht "niedrig"
    # (bleibt "erhöht", nicht "hoch") – die Pause soll normal gelten, siehe Extrem-Test unten.
    hass.states.async_set("sensor.innen_ah", 9.0)
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)
    karte = hass.states.get(rec).attributes["karte"]
    assert karte["minuten"] > 0
    assert karte["schimmel"] == "erhöht"
    assert karte["pausiert"].startswith("Pause nach dem Lüften bis 11:0")
    await _tick(hass, freezer, 61)
    assert hass.states.get(rec).attributes["karte"]["pausiert"] is None


async def test_card_shows_heating_lowered(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    """Die Karte zeigt, wenn beim Lüften die Heizung abgesenkt wird."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    hass.states.async_set(
        "climate.wz", "heat",
        {"hvac_modes": ["heat", "off"], "temperature": 21, "friendly_name": "Wohnzimmer Heizung"},
    )
    async_mock_service(hass, "climate", "set_hvac_mode")
    entry = await setup_room(hass, climate_entities=["climate.wz"])
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 2)
    karte = hass.states.get(eid(hass, "sensor", entry, "recommendation")).attributes["karte"]
    assert karte["heizung_ab"] == ["Wohnzimmer Heizung"]
    assert karte["heizung_extern"] == []


async def test_post_vent_pause_uses_forecast_and_extreme_override(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Pause nach dem Lüften: nutzt den nächsten günstigen Zeitpunkt statt fix 60 Minuten,
    aber nicht mehr als 4 Std. voraus, und bei Schimmelalarm gilt sie gar nicht."""
    freezer.move_to("2026-12-05 08:00:00+01:00")
    now = dt_util.now().replace(minute=0, second=0, microsecond=0)
    forecast = [
        {"datetime": (now + timedelta(hours=h)).isoformat(), "temperature": 5, "humidity": rh,
         "precipitation": 0, "precipitation_probability": 0, "wind_speed": 10}
        for h, rh in [(2, 20), (7, 60)]           # günstigster Punkt (trockenste Luft): in 2 Std.
    ]
    async_mock_service(
        hass, "weather", "get_forecasts",
        response={"weather.home": {"forecast": forecast}},
        supports_response=SupportsResponse.ONLY,
    )
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass, weather_entity="weather.home")
    rec = eid(hass, "sensor", entry, "recommendation")
    await _tick(hass, freezer, 0.5)                # Vorhersage laden

    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 3)
    hass.states.async_set("binary_sensor.fenster_1", "off")
    # Feuchte nach dem Lüften gesunken, aber noch nicht "niedrig" (erhöht, nicht hoch) –
    # sonst würde die neue Extrem-Ausnahme schon hier statt erst unten greifen.
    hass.states.async_set("sensor.innen_ah", 9.0)
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)

    karte = hass.states.get(rec).attributes["karte"]
    assert karte["schimmel"] == "erhöht"
    assert "nächster günstiger Zeitpunkt" in karte["pausiert"]
    assert karte["pausiert"].startswith("Pause nach dem Lüften bis 10:0")   # in ca. 2 Std., nicht 60 Min.

    # nach 61 Minuten wäre die alte feste Pause vorbei, die Wetter-Pause aber noch nicht
    before = len([c for c in pushes if c.data["title"].startswith("Lüften:")])
    await _tick(hass, freezer, 61)
    assert hass.states.get(rec).attributes["karte"]["pausiert"] is not None
    assert len([c for c in pushes if c.data["title"].startswith("Lüften:")]) == before

    # jetzt wird es extrem (Schimmelrisiko hoch) -> Pause gilt nicht mehr, auch wenn die Zeit noch nicht da ist
    hass.states.async_set("sensor.innen_ah", 13.0)
    hass.states.async_set("sensor.aussen_ah", 4.0)
    await _tick(hass, freezer, 1)
    karte = hass.states.get(rec).attributes["karte"]
    assert karte["schimmel"] == "hoch"
    assert karte["pausiert"] is None

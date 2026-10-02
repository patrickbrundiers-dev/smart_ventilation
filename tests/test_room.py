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


async def test_auto_season_uses_calendar_month(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Automatik-Modus: Dezember-Februar/Juni-August gelten fest, unabhängig von der
    Außentemperatur. Nur in den Übergangsmonaten entscheidet die Temperatur - und zwar erst,
    wenn sie mehrere Stunden ununterbrochen deutlich über/unter der Schwelle liegt (sonst
    würde z. B. eine kalte Nacht gefolgt von einem warmen Nachmittag den Modus am selben Tag
    mehrfach hin- und herspringen lassen)."""
    freezer.move_to("2026-07-15 12:00:00+02:00")  # Juli -> fester Sommer
    entry = await setup_room(hass, season_mode="auto")
    season = eid(hass, "sensor", entry, "season")
    hass.states.async_set("sensor.aussen_t", 5.0)  # kalt - würde ohne Monat "Winter" ergeben
    await hass.async_block_till_done()
    assert hass.states.get(season).state == "summer"

    freezer.move_to("2026-12-15 12:00:00+01:00")  # Dezember -> fester Winter
    hass.states.async_set("sensor.aussen_t", 22.0)  # warm - würde ohne Monat "Sommer" ergeben
    await hass.async_block_till_done()
    assert hass.states.get(season).state == "winter"

    freezer.move_to("2026-04-15 06:00:00+02:00")  # April -> Übergangsmonat, Temperatur entscheidet
    hass.states.async_set("sensor.aussen_t", 20.0)  # deutlich über der Schwelle (15 °C)
    await hass.async_block_till_done()
    assert hass.states.get(season).state == "winter"  # noch nicht lange genug warm -> bleibt zunächst

    await _tick(hass, freezer, 7 * 60)  # 7 h ununterbrochen warm -> Wechsel wird bestätigt
    assert hass.states.get(season).state == "summer"

    hass.states.async_set("sensor.aussen_t", 5.0)  # deutlich darunter
    await hass.async_block_till_done()
    assert hass.states.get(season).state == "summer"  # noch nicht lange genug kalt

    await _tick(hass, freezer, 7 * 60)  # 7 h ununterbrochen kalt -> Wechsel wird bestätigt
    assert hass.states.get(season).state == "winter"


async def test_season_does_not_flap_within_a_single_day(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Regression: ein Tag mit kalter Nacht und warmem Nachmittag (typisch im Herbst/Frühling)
    durfte den Automatik-Modus nicht kurzzeitig auf Sommer springen lassen, nur um Stunden
    später wieder auf Winter zurückzufallen - dafür reicht ein paar Stunden Wärme nicht."""
    freezer.move_to("2026-04-10 06:00:00+02:00")  # April -> Übergangsmonat
    entry = await setup_room(hass, season_mode="auto")
    season = eid(hass, "sensor", entry, "season")

    hass.states.async_set("sensor.aussen_t", 9.0)  # kalter Morgen
    await hass.async_block_till_done()
    assert hass.states.get(season).state == "winter"

    hass.states.async_set("sensor.aussen_t", 20.0)  # warmer Nachmittag, nur ein paar Stunden
    await hass.async_block_till_done()
    assert hass.states.get(season).state == "winter"  # kurze Wärmephase reicht nicht
    await _tick(hass, freezer, 3 * 60)
    assert hass.states.get(season).state == "winter"

    hass.states.async_set("sensor.aussen_t", 10.0)  # kühlt abends wieder ab, bevor bestätigt wurde
    await _tick(hass, freezer, 12 * 60)
    assert hass.states.get(season).state == "winter"  # nie wirklich auf Sommer gesprungen


async def test_season_uses_daily_forecast_trend_without_waiting(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Zeigt die mehrtägige Vorhersage schon einen eindeutigen Trend (Hoch UND Tief mehrere
    Tage am Stück klar unter der Heizgrenze), wird das sofort als Winter übernommen - ohne
    erst SEASON_CONFIRM_HOURS auf lokale Bestätigung zu warten. Das ist ein verlässlicheres
    Signal, gerade für die längerfristige Einordnung."""
    freezer.move_to("2026-09-27 12:00:00+02:00")  # Übergangsmonat
    forecast_holder: dict = {"daily": []}

    async def _handle_get_forecasts(call):
        if call.data.get("type") == "daily":
            return {"weather.home": {"forecast": forecast_holder["daily"]}}
        return {"weather.home": {"forecast": []}}

    hass.services.async_register(
        "weather", "get_forecasts", _handle_get_forecasts,
        supports_response=SupportsResponse.ONLY,
    )
    entry = await setup_room(hass, season_mode="auto", weather_entity="weather.home")
    room = hass.data[DOMAIN][entry.entry_id]
    room._auto_season = "summer"  # simuliert: bisher als Sommer eingestuft
    room._season_pending = None
    room._season_pending_since = None

    hass.states.async_set("sensor.aussen_t", 20.0)  # aktuell noch warm
    await hass.async_block_till_done()

    now = dt_util.now()
    forecast_holder["daily"] = [
        {"datetime": (now + timedelta(days=d)).isoformat(), "temperature": high, "templow": low}
        for d, (high, low) in enumerate([(12.0, 4.0), (11.0, 3.0), (13.0, 5.0)])
    ]
    await _tick(hass, freezer, 6)  # über die Retry-Zeit hinaus -> neue Vorhersage wird geholt

    # Trotz aktuell warmer Außenluft (würde sonst Richtung Sommer bleiben bzw. erst nach
    # Stunden umschalten) übernimmt der eindeutige mehrtägige Vorhersage-Trend sofort "Winter".
    assert hass.states.get(eid(hass, "sensor", entry, "season")).state == "winter"


async def test_no_venting_when_warmer_outside_even_in_winter(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Auch im Winter nicht lüften, wenn es draußen deutlich wärmer ist als drinnen (z. B.
    milder Herbsttag) - vorher wurde die Wärme-Sperre im Winter komplett übersprungen und
    trotz feuchter Raumluft trotzdem „Lüften“ empfohlen."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass)  # season_mode="winter" per ROOM_DATA-Fixture
    rec = eid(hass, "sensor", entry, "recommendation")
    assert hass.states.get(rec).attributes["karte"]["minuten"] > 0  # Ausgangslage: feucht genug

    hass.states.async_set("sensor.aussen_t", 24.0)  # > 3 °C wärmer als innen (20,5 °C)
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)
    state = hass.states.get(rec)
    assert state.state == "Nicht lüften – draußen zu warm"
    assert state.attributes["karte"]["minuten"] == 0
    assert "wärmer" in state.attributes["karte"]["blockiert"]

    # Ist trotzdem schon gelüftet worden (Fenster offen) und wird es dabei wärmer,
    # kommt zusätzlich der Hinweis zum Schließen - auch im Winter.
    hass.states.async_set("sensor.aussen_t", 20.5)
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.aussen_t", 24.0)
    await _tick(hass, freezer, 1)
    assert any(t.startswith("Fenster schließen") for t in [c.data["title"] for c in pushes])


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


async def test_humid_outdoor_warning_when_window_opened_anyway(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Öffnet man trotz „Raumluft feucht – Außenluft aktuell nicht trockener" das Fenster
    (Lüften hilft hier ja gerade nicht, weil draußen nicht trockener ist), soll einmalig eine
    Erinnerung kommen, es wieder zu schließen - sonst bleibt es unbemerkt offen und die Feuchte
    verschlechtert sich eher, statt sich zu verbessern."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass)
    rec = eid(hass, "sensor", entry, "recommendation")

    # Innen (10,5) über dem Zielwert (10,0), aber draußen (9,9) nicht trockener genug -> Karte
    # zeigt "nicht in Ordnung, aber Lüften hilft gerade nicht" statt "Lüften".
    hass.states.async_set("sensor.aussen_ah", 9.9)
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)
    assert hass.states.get(rec).attributes["karte"]["minuten"] == 0
    assert hass.states.get(rec).state == "Raumluft feucht – Außenluft aktuell nicht trockener"

    # Trotzdem geöffnet -> einmalige Erinnerung, wieder zu schließen.
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)
    await _tick(hass, freezer, 1)
    warnings = [c for c in pushes if "Außenluft nicht trockener" in c.data["title"]]
    assert len(warnings) == 1


async def test_thunderstorm_blocks_venting(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    """Ein Text-Enum-Sensor (z. B. KachelmannWetter "Gewitter erwartet") mit einem Wert außerhalb
    von LOW_RISK_STATES (hier "Sicher") soll das Lüften genauso blockieren wie Regen."""
    freezer.move_to("2026-09-27 10:00:00+02:00")
    entry = await setup_room(
        hass, season_mode="summer", thunderstorm_entity="sensor.gewitter"
    )
    rec = eid(hass, "sensor", entry, "recommendation")
    hass.states.async_set("sensor.gewitter", "Unwahrscheinlich")
    hass.states.async_set("sensor.innen_ah", 12.5)  # eigentlich klarer Lüftungsbedarf
    await _tick(hass, freezer, 1)
    assert hass.states.get(rec).attributes["karte"]["minuten"] > 0

    hass.states.async_set("sensor.gewitter", "Sicher")
    await _tick(hass, freezer, 1)
    assert hass.states.get(rec).attributes["karte"]["minuten"] == 0
    assert hass.states.get(rec).state == "Nicht lüften – Gewitter erwartet"
    assert hass.states.get(rec).attributes["karte"]["blockiert"] == "Gewitter erwartet"


async def test_wind_gust_warning_when_window_open(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Windböen-Vorhersage über der Schwelle (50 km/h) und offenes Fenster -> einmalige Warnung,
    das Kippfenster zu sichern/schließen."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    await setup_room(hass, wind_gust_entity="sensor.boeen")
    hass.states.async_set("sensor.boeen", 65)
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)
    await _tick(hass, freezer, 1)
    warnings = [c for c in pushes if "Windböen" in c.data["title"]]
    assert len(warnings) == 1


async def test_frost_warning_when_window_open(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Frost-Sensor auf einem Risiko-Wert (nicht in LOW_RISK_STATES) und offenes Fenster ->
    einmalige Erinnerung, es nicht offen zu vergessen."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    await setup_room(hass, frost_entity="sensor.frost")
    hass.states.async_set("sensor.frost", "Erhöht")
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)
    await _tick(hass, freezer, 1)
    warnings = [c for c in pushes if "Frost" in c.data["title"]]
    assert len(warnings) == 1


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


async def test_overview_room_list_includes_dehumidifier_shutter_and_air_quality(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """room_list() (Grundlage der Übersichtskarte) soll Entfeuchter-Status, Rollo-Empfehlung und
    CO2-Luftqualität pro Raum liefern - sonst müsste man dafür jede Raumkarte einzeln öffnen,
    statt es auf der Übersicht auf einen Blick zu sehen."""
    freezer.move_to("2026-06-15 12:00:00+02:00")
    dehum_calls = async_mock_service(hass, "switch", "turn_on")  # sonst schlägt der Service-Call fehl (kein "switch" geladen)
    hass.states.async_set("switch.entfeuchter", "off")
    hass.states.async_set("sensor.co2", 1500)
    await setup_room(
        hass, use_sun=True, season_mode="summer",
        dehumidifier_entity="switch.entfeuchter", co2_sensor="sensor.co2",
    )
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 40, "azimuth": 106})  # = Fensterausrichtung
    hass.states.async_set("sensor.regen", 1.2)     # Regen -> Lüften blockiert -> Entfeuchter darf ran
    hass.states.async_set("sensor.innen_ah", 12.5)  # feucht genug für den Entfeuchter
    await _tick(hass, freezer, 0.5)
    assert any(call.data.get("entity_id") == ["switch.entfeuchter"] for call in dehum_calls)

    overview = await setup_entry(
        hass, {"entry_type": "overview", "name": "Lüften Übersicht", "combine_notifications": True,
               "notify_services": [], "persons": []}, "overview", "Lüften Übersicht")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()
    urgent = hass.states.get(eid(hass, "sensor", overview, "most_urgent"))
    room = urgent.attributes["raeume"][0]
    assert room["entfeuchter"] is True
    assert room["rollo_empfehlung"] is True
    assert room["rollo_geschlossen"] is False  # kein Rollo-Entity konfiguriert -> nie "von uns" zu
    assert room["luft"] == "schlecht"


async def test_shutter_recommendation_ignores_heavy_clouds(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Bei bedecktem Himmel darf ein passender Sonnenwinkel allein kein Rollo-Schließen auslösen."""
    freezer.move_to("2026-06-15 12:00:00+02:00")
    entry = await setup_room(hass, use_sun=True, season_mode="summer", weather_entity="weather.home")
    hass.states.async_set(
        "weather.home", "cloudy", {"cloud_coverage": 90, "temperature": 22}
    )
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 40, "azimuth": 106})
    await hass.async_block_till_done()

    room = hass.data[DOMAIN][entry.entry_id]
    assert room.shutter_recommended is False


async def test_shutter_recommendation_reacts_to_weather_entity_changes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Ein Wechsel der Wetterlage muss die Rollo-Empfehlung sofort neu berechnen."""
    freezer.move_to("2026-06-15 12:00:00+02:00")
    entry = await setup_room(hass, use_sun=True, season_mode="summer", weather_entity="weather.home")
    hass.states.async_set(
        "weather.home", "sunny", {"cloud_coverage": 5, "temperature": 24}
    )
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 40, "azimuth": 106})
    await hass.async_block_till_done()
    room = hass.data[DOMAIN][entry.entry_id]
    assert room.shutter_recommended is True

    hass.states.async_set(
        "weather.home", "overcast", {"cloud_coverage": 95, "temperature": 22}
    )
    await hass.async_block_till_done()
    assert room.shutter_recommended is False


async def test_unload(hass: HomeAssistant, berlin) -> None:
    entry = await setup_room(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_restored_session_does_not_use_stale_sensor_values(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Fenster öffnet sich, HA startet neu (Fenster schließt währenddessen, unbemerkt),
    und beim Wiederhochfahren liegen Stunden dazwischen. Die Erfolgsprüfung darf dann NICHT
    die aktuellen (längst nicht mehr aussagekräftigen) Sensorwerte heranziehen - sonst zählt
    eine tatsächlich wirkungslose Lüftung fälschlich als „Ziel erreicht“, nur weil der Raum
    Stunden später zufällig trocken ist."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    entry = await setup_room(hass)  # innen 10,5 / außen 4,0 g/m³, Tagesziel 10,0

    hass.states.async_set("binary_sensor.fenster_1", "on")  # Lüftung beginnt
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)  # "HA fährt runter"

    # Während der Auszeit: Fenster schließt sich nach 3 Minuten (echte Lüftungsdauer,
    # Feuchte damals unverändert hoch - das Ziel wurde nie erreicht).
    freezer.tick(timedelta(minutes=3))
    hass.states.async_set("binary_sensor.fenster_1", "off")

    # Erst Stunden später kommt HA wieder hoch. Der Raum ist inzwischen aus anderen Gründen
    # trocken (z. B. Heizung lief durch) - das darf nicht rückwirkend als Erfolg gewertet werden.
    freezer.tick(timedelta(hours=4))
    hass.states.async_set("sensor.innen_ah", 9.0)  # jetzt unter dem Tagesziel (10,0)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    today = hass.states.get(eid(hass, "sensor", entry, "stats_day"))
    assert today.state == "1"
    assert today.attributes["erfolgreich"] == 0
    assert today.attributes["ohne_ziel"] == 1


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
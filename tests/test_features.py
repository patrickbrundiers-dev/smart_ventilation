"""Bad-Modus, Verlassen, Urlaub, Kühlen, Entfeuchter, Wochenbericht, Verlauf, Sprachsteuerung."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import intent
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed, async_mock_service

from custom_components.smart_ventilation.const import DOMAIN

from .conftest import eid, setup_room


async def _tick(hass, freezer, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _titles(calls):
    return [c.data["title"] for c in calls]


async def test_shower_sensor_and_followup(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("binary_sensor.dusche", "off")
    await setup_room(hass, shower_sensor="binary_sensor.dusche")
    hass.states.async_set("binary_sensor.dusche", "on")
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.dusche", "off")
    await hass.async_block_till_done()
    assert any(t.startswith("Nach dem Duschen") for t in _titles(pushes))

    hass.states.async_set("sensor.innen_ah", 12.5)
    await _tick(hass, freezer, 31)
    assert any(t.startswith("Noch feucht") for t in _titles(pushes))


async def test_shower_detected_by_humidity_jump(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    await setup_room(hass, shower_detect=True)
    await _tick(hass, freezer, 1)
    hass.states.async_set("sensor.innen_ah", 12.6)
    await _tick(hass, freezer, 1)
    assert sum(t.startswith("Nach dem Duschen") for t in _titles(pushes)) == 1


async def test_everyone_left_with_window_open(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("person.patrick", "home")
    await setup_room(hass, persons=["person.patrick"])
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    hass.states.async_set("person.patrick", "not_home")
    await hass.async_block_till_done()
    assert any(t.startswith("Fenster offen") for t in _titles(pushes))


async def test_vacation_silences_reminders_and_watches_mold(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("input_boolean.urlaub", "on")
    entry = await setup_room(hass, vacation_entity="input_boolean.urlaub", building_standard="old")
    await _tick(hass, freezer, 1)
    assert not [t for t in _titles(pushes) if t.startswith("Lüften:")]

    hass.states.async_set("sensor.aussen_t", -5)
    hass.states.async_set("sensor.innen_ah", 11.5)
    await _tick(hass, freezer, 1)
    await _tick(hass, freezer, 1)
    assert sum(t.startswith("Urlaub – Schimmelrisiko") for t in _titles(pushes)) == 1
    assert hass.states.get(eid(hass, "sensor", entry, "recommendation")).attributes["karte"]["urlaub"] is True


async def test_summer_cooling_and_warm_outside(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-07-10 21:00:00+02:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass, season_mode="summer")
    for eid_, val in (("sensor.innen_t", 26), ("sensor.aussen_t", 18), ("sensor.innen_ah", 10), ("sensor.aussen_ah", 9.8)):
        hass.states.async_set(eid_, val)
    await _tick(hass, freezer, 0.5)
    rec = hass.states.get(eid(hass, "sensor", entry, "recommendation"))
    assert rec.state.startswith("Kühlen")
    assert rec.attributes["grund"] == "Kühlen"

    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.aussen_t", 27.5)
    await _tick(hass, freezer, 1)
    assert any(t.startswith("Fenster schließen") for t in _titles(pushes))


async def test_preheat_after_cold_night_overrides_warm_outside_block(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Nach einer kalten Nacht (Tiefstwert unter der Heizgrenze) darf tagsüber trotz wärmerer
    Außenluft gelüftet werden, um den Raum ohne Heizung aufzuwärmen - die Wärme-Sperre aus
    2.3.14 gilt hier ausnahmsweise nicht, weil die Wärme hier ja das Ziel ist."""
    freezer.move_to("2026-12-05 23:00:00+01:00")  # innerhalb des Nachtfensters (22-9 Uhr)
    entry = await setup_room(hass)  # season_mode="winter" per ROOM_DATA-Fixture
    hass.states.async_set("sensor.aussen_t", -2.0)  # kalte Nacht, deutlich unter der Heizgrenze
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)  # Nacht-Tiefsttemperatur wird mitgeschrieben

    freezer.move_to("2026-12-06 09:30:00+01:00")  # Nachtfenster vorbei -> Tiefstwert wird übernommen
    await _tick(hass, freezer, 1)

    # Tagsüber: Raum kalt (unter der Vorheiz-Schwelle), draußen deutlich wärmer als drinnen,
    # Luftfeuchte unauffällig (damit nur „Vorheizen“ als Grund übrig bleibt)
    hass.states.async_set("sensor.innen_t", 15.0)
    hass.states.async_set("sensor.aussen_t", 19.0)  # 4 °C wärmer -> würde sonst die Wärme-Sperre auslösen
    hass.states.async_set("sensor.innen_ah", 6.0)
    hass.states.async_set("sensor.aussen_ah", 5.8)
    await _tick(hass, freezer, 1)

    rec = hass.states.get(eid(hass, "sensor", entry, "recommendation"))
    assert rec.attributes["grund"] == "Vorheizen"
    assert rec.attributes["karte"]["minuten"] > 0
    assert "Vorheizen" in rec.state


async def test_preheat_ignores_slow_auto_label_but_respects_manual_summer(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Vorheizen soll nur in der Heizsaison passieren, nicht unnötig Wärme in den echten Sommer
    holen. Dafür zählt aber nicht die automatisch ERKANNTE Saison - die reagiert seit 2.3.19
    bewusst erst nach Stunden Trend (gegen Flackern) und kann in der Übergangszeit deshalb noch
    tagelang „Sommer“ zeigen, obwohl es nachts schon unter die Heizgrenze fällt (z. B. Herbst-Tag
    mit 9 °C morgens/nachts, 26 °C mittags). Genau dann soll Vorheizen trotzdem funktionieren.
    Stellt der Nutzer den Raum dagegen bewusst manuell auf "Sommer", wird respektiert, dass hier
    keine Heizsaison gewünscht ist."""
    freezer.move_to("2026-09-27 23:00:00+02:00")  # innerhalb des Nachtfensters (22-9 Uhr)
    entry = await setup_room(hass, season_mode="auto")
    room = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set("sensor.aussen_t", 9.0)  # kühle Nacht, unter der Heizgrenze (15 °C)
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)  # Nacht-Tiefsttemperatur wird mitgeschrieben

    freezer.move_to("2026-09-28 09:30:00+02:00")  # Nachtfenster vorbei -> Tiefstwert übernommen
    await _tick(hass, freezer, 1)

    # Automatik-Label simuliert absichtlich den Fall, dass es (weil die letzten Tage vorher
    # warm waren) noch nicht auf "winter" umgesprungen ist - genau das kann seit 2.3.19 einige
    # Tage dauern, obwohl es nachts längst kalt genug ist.
    room._auto_season = "summer"
    room._season_pending = None
    room._season_pending_since = None

    hass.states.async_set("sensor.innen_t", 17.0)
    hass.states.async_set("sensor.aussen_t", 21.0)  # spürbar wärmer als drinnen
    hass.states.async_set("sensor.innen_ah", 6.0)
    hass.states.async_set("sensor.aussen_ah", 5.8)
    await _tick(hass, freezer, 1)

    rec = hass.states.get(eid(hass, "sensor", entry, "recommendation"))
    # Automatik-Label ist (bewusst träge) noch nicht auf "winter" umgesprungen ...
    assert hass.states.get(eid(hass, "sensor", entry, "season")).state == "summer"
    # ... trotzdem wird vorgeheizt, weil es nachts tatsächlich unter die Heizgrenze fiel.
    assert rec.attributes["grund"] == "Vorheizen"
    assert rec.attributes["karte"]["minuten"] > 0

    # Stellt der Nutzer den Raum jetzt bewusst manuell auf "Sommer" ...
    room.data["season_mode"] = "summer"
    await _tick(hass, freezer, 1)
    rec = hass.states.get(eid(hass, "sensor", entry, "recommendation"))
    # ... wird das respektiert, auch wenn die Nacht-Bedingung weiter erfüllt wäre.
    assert "Vorheizen" not in rec.attributes["grund"]


async def test_preheat_uses_forecast_for_rain_and_upcoming_window(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Die Vorhersage fließt beim Vorheizen mit ein: droht in Kürze Regen, wird trotz aktuell
    passender Werte nicht vorgeheizt; außerdem zeigt die Karte an, ab wann es laut Vorhersage
    warm genug wird."""
    freezer.move_to("2026-12-05 23:00:00+01:00")  # innerhalb des Nachtfensters (22-9 Uhr)
    forecast_holder: dict = {"data": []}

    async def _handle_get_forecasts(call):
        return {"weather.home": {"forecast": forecast_holder["data"]}}

    hass.services.async_register(
        "weather", "get_forecasts", _handle_get_forecasts,
        supports_response=SupportsResponse.ONLY,
    )
    entry = await setup_room(hass, weather_entity="weather.home")

    hass.states.async_set("sensor.aussen_t", -2.0)  # kalte Nacht
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)  # Nacht-Tiefsttemperatur wird mitgeschrieben

    freezer.move_to("2026-12-06 09:30:00+01:00")  # Nachtfenster vorbei -> Tiefstwert übernommen
    await _tick(hass, freezer, 1)

    # Tagsüber: Raum kalt, draußen aktuell warm genug, Luftfeuchte unauffällig -
    # ohne Vorhersage würde jetzt "Vorheizen" empfohlen.
    hass.states.async_set("sensor.innen_t", 15.0)
    hass.states.async_set("sensor.aussen_t", 19.0)
    hass.states.async_set("sensor.innen_ah", 6.0)
    hass.states.async_set("sensor.aussen_ah", 5.8)
    await hass.async_block_till_done()

    now = dt_util.now().replace(minute=0, second=0, microsecond=0)
    forecast_holder["data"] = [
        {"datetime": (now + timedelta(hours=h)).isoformat(), "temperature": t,
         "humidity": 80, "precipitation": rain, "precipitation_probability": prob, "wind_speed": 5}
        for h, t, rain, prob in [(1, 19, 3.0, 90), (5, 19, 0, 5), (6, 19, 0, 5), (7, 10, 0, 5)]
    ]
    await _tick(hass, freezer, 31)  # über die Auffrischungszeit hinaus -> neue Vorhersage wird geholt

    rec = hass.states.get(eid(hass, "sensor", entry, "recommendation"))
    # Regen in den nächsten 2 h -> kein Vorheizen, obwohl es gerade noch trocken und warm genug ist
    assert "Vorheizen" not in rec.attributes["grund"]
    # Vorhersage zeigt trotzdem an, wann es (nach dem Regen) warm genug werden soll
    plan = rec.attributes["karte"]["vorheizen_plan"]
    assert plan is not None and "Heute" in plan


async def test_preheat_blocked_when_outside_much_more_humid(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Ist die Luft draußen deutlich feuchter als drinnen, würde Vorheizen sich zugleich ein
    Feuchteproblem einhandeln - dann lohnt sich das Öffnen trotz der Wärme nicht (spiegelbildlich
    zu COOL_MAX_EXTRA_HUMIDITY beim Kühlen)."""
    freezer.move_to("2026-12-05 23:00:00+01:00")  # innerhalb des Nachtfensters (22-9 Uhr)
    entry = await setup_room(hass)
    hass.states.async_set("sensor.aussen_t", -2.0)  # kalte Nacht
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)  # Nacht-Tiefsttemperatur wird mitgeschrieben

    freezer.move_to("2026-12-06 09:30:00+01:00")  # Nachtfenster vorbei -> Tiefstwert übernommen
    await _tick(hass, freezer, 1)

    # Sonst würde jetzt vorgeheizt: kalt genug drinnen, draußen deutlich wärmer ...
    hass.states.async_set("sensor.innen_t", 15.0)
    hass.states.async_set("sensor.aussen_t", 19.0)
    # ... aber draußen auch deutlich feuchter als drinnen
    hass.states.async_set("sensor.innen_ah", 5.0)
    hass.states.async_set("sensor.aussen_ah", 7.0)
    await _tick(hass, freezer, 1)

    rec = hass.states.get(eid(hass, "sensor", entry, "recommendation"))
    assert "Vorheizen" not in rec.attributes["grund"]
    room = hass.data[DOMAIN][entry.entry_id]
    assert room.preheat_minutes() == 0


async def test_preheat_wind_plan_prefers_favorable_wind_direction(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Liefert die Vorhersage eine Windrichtung, wird eine an sich warme/trockene Stunde
    übersprungen, wenn der Wind ungünstig vom Fenster weg bläst - die nächste Stunde mit
    günstigem Wind wird stattdessen als Vorheiz-Beginn angezeigt."""
    freezer.move_to("2026-12-05 23:00:00+01:00")
    forecast_holder: dict = {"data": []}

    async def _handle_get_forecasts(call):
        return {"weather.home": {"forecast": forecast_holder["data"]}}

    hass.services.async_register(
        "weather", "get_forecasts", _handle_get_forecasts,
        supports_response=SupportsResponse.ONLY,
    )
    # window_direction=106.0, wind_is_from=True (ROOM_DATA)
    entry = await setup_room(hass, weather_entity="weather.home")

    hass.states.async_set("sensor.aussen_t", -2.0)  # kalte Nacht
    await hass.async_block_till_done()
    await _tick(hass, freezer, 1)

    freezer.move_to("2026-12-06 09:30:00+01:00")
    await _tick(hass, freezer, 1)

    hass.states.async_set("sensor.innen_t", 15.0)
    hass.states.async_set("sensor.aussen_t", 15.5)  # noch nicht warm genug für Vorheizen jetzt
    hass.states.async_set("sensor.innen_ah", 6.0)
    hass.states.async_set("sensor.aussen_ah", 5.8)
    await hass.async_block_till_done()

    now = dt_util.now().replace(minute=0, second=0, microsecond=0)
    forecast_holder["data"] = [
        # Stunde 1: warm & trocken genug, aber Wind bläst klar vom Fenster weg (Winkel ~176°)
        {"datetime": (now + timedelta(hours=1)).isoformat(), "temperature": 19,
         "precipitation": 0, "precipitation_probability": 5, "wind_speed": 10, "wind_bearing": 290},
        # Stunde 2: ebenso warm & trocken, Wind steht günstig zum Fenster (Winkel ~4°)
        {"datetime": (now + timedelta(hours=2)).isoformat(), "temperature": 19,
         "precipitation": 0, "precipitation_probability": 5, "wind_speed": 10, "wind_bearing": 110},
        {"datetime": (now + timedelta(hours=3)).isoformat(), "temperature": 10,
         "precipitation": 0, "precipitation_probability": 5, "wind_speed": 10, "wind_bearing": 110},
    ]
    await _tick(hass, freezer, 31)

    rec = hass.states.get(eid(hass, "sensor", entry, "recommendation"))
    plan = rec.attributes["karte"]["vorheizen_plan"]
    assert plan is not None
    expected_start = (now + timedelta(hours=2)).strftime("%H:%M")
    skipped_start = (now + timedelta(hours=1)).strftime("%H:%M")
    assert expected_start in plan
    assert skipped_start not in plan


async def test_cooling_and_preheat_use_bucketed_ach_model(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Kühlen und Vorheizen nutzen (wie die normale Lüftungsdauer) das nach Wind/Winkel/
    Temperaturdifferenz gebuckete Modell, statt nur den groben globalen Durchschnitt - ist für
    die aktuellen Bedingungen schon genug gelernt worden, wird das bevorzugt."""
    freezer.move_to("2026-07-10 21:00:00+02:00")
    entry = await setup_room(hass, season_mode="summer")
    room = hass.data[DOMAIN][entry.entry_id]

    for eid_, val in (
        ("sensor.innen_t", 26), ("sensor.aussen_t", 18),
        ("sensor.innen_ah", 10), ("sensor.aussen_ah", 9.8),
    ):
        hass.states.async_set(eid_, val)
    await hass.async_block_till_done()

    wind, angle, temp_diff = room._context()
    key = room._bucket(wind, angle, temp_diff)

    room.learned_ach = 0.5  # sehr langsamer globaler Durchschnitt
    minutes_flat = room.cooling_minutes()
    assert minutes_flat > 30  # bei so langsamem ACH dauert es lange

    room.models[key] = {"ach": 20.0, "samples": 5}  # für genau diese Bedingungen viel schneller gelernt
    minutes_bucketed = room.cooling_minutes()
    assert minutes_bucketed < minutes_flat
    assert minutes_bucketed == 10  # bei so schnellem ACH greift die Mindestdauer


async def test_preheat_session_records_heating_savings(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Eine als Vorheizen erkannte Lüftung soll in der Statistik nicht nur (wie normales
    Lüften) als Wärmeverlust, sondern als eingesparte Heizenergie auftauchen - die wärmere
    Außenluft ersetzt hier ja Heizenergie, statt Wärme zu kosten. Die Sitzung wird direkt
    konstruiert (statt über den vollen Fenster-auf/zu-Ablauf), um die Berechnung isoliert und
    ohne Timing-Abhängigkeiten zu prüfen."""
    freezer.move_to("2026-12-05 10:00:00+01:00")
    entry = await setup_room(hass)
    room = hass.data[DOMAIN][entry.entry_id]

    session = {
        "started": dt_util.now() - timedelta(seconds=90),
        "initial_diff": 0.2,
        "initial_indoor": 6.0,
        "initial_co2": None,
        "dT": -4.0,  # draußen 4 °C wärmer als drinnen zu Sitzungsbeginn
        "wind": 8.0,
        "angle": 4.0,
        "temp_diff": 4.0,
        "target_reached": False,
        "cross": False,
        "notified": False,
        "cool_warned": False,
        "overtime_warned": False,
        "heating": None,
        "cooling": False,
        "preheat": True,
        "trace": [],
    }

    # DEBUG: Berechnung isoliert prüfen, bevor der volle _finish_session()-Ablauf läuft
    direct_kwh = room._session_preheat_savings_kwh(dict(session), 90.0)
    assert direct_kwh > 0, (
        f"direct_kwh={direct_kwh!r} learned_ach={room.learned_ach!r} "
        f"models={room.models!r} volume={room.data.get('volume')!r}"
    )

    room.session = session
    await room._finish_session()

    stats = room.period_stats("day")
    assert stats["kwh_gespart"] > 0, f"stats={stats!r}"
    assert stats["kosten_gespart"] > 0
    card = room.card_data()
    assert card["heute_kwh_gespart"] > 0
    assert card["heute_eur_gespart"] > 0


async def test_dehumidifier_runs_when_rain_blocks(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    on = async_mock_service(hass, "switch", "turn_on")
    off = async_mock_service(hass, "switch", "turn_off")
    hass.states.async_set("switch.entfeuchter", "off")
    await setup_room(hass, dehumidifier_entity="switch.entfeuchter")
    hass.states.async_set("sensor.regen", 1.2)           # Regen -> Lüften blockiert
    hass.states.async_set("sensor.innen_ah", 12.5)        # ~70 % rel. Feuchte
    await _tick(hass, freezer, 0.5)
    assert len(on) == 1

    hass.states.async_set("sensor.innen_ah", 8.0)         # trocken genug
    await _tick(hass, freezer, 16)
    assert len(off) == 1


async def test_weekly_report(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-06 19:05:00+01:00")  # Sonntag
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    await setup_room(hass, weekly_report=True)
    await _tick(hass, freezer, 0.5)
    await _tick(hass, freezer, 0.5)
    assert sum(t.startswith("Wochenbericht") for t in _titles(pushes)) == 1


async def test_trace_for_card(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    freezer.move_to("2026-12-05 10:00:00+01:00")
    entry = await setup_room(hass)
    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    for value in (9.5, 8.0, 7.0):
        hass.states.async_set("sensor.innen_ah", value)
        await _tick(hass, freezer, 1)
    hass.states.async_set("binary_sensor.fenster_1", "off")
    await hass.async_block_till_done()
    trace = hass.states.get(eid(hass, "sensor", entry, "recommendation")).attributes["karte"]["verlauf"]
    assert trace["laeuft"] is False
    assert len(trace["punkte"]) >= 3
    assert trace["punkte"][0][1] == 10.5 and trace["punkte"][-1][1] == 7.0


async def test_assist_intent_and_service(hass: HomeAssistant, berlin) -> None:
    await setup_room(hass)
    response = await intent.async_handle(hass, "test", "SmartVentilationStatus")
    speech = response.speech["plain"]["speech"]
    assert speech.startswith("Ja") and "Schlafzimmer" in speech

    result = await hass.services.async_call(DOMAIN, "status", {}, blocking=True, return_response=True)
    assert result["raeume"][0]["raum"] == "Schlafzimmer"

    sentences = Path(hass.config.path("custom_sentences", "de", "smart_ventilation.yaml"))
    assert sentences.exists()


async def test_no_humidity_nag_when_room_is_dry_enough(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    """Innen 10,1 / außen 9,2 g/m³ bei 20 °C: Lüften bringt kaum etwas -> keine Aufforderung."""
    freezer.move_to("2026-09-27 10:00:00+02:00")
    entry = await setup_room(hass, season_mode="summer")
    for eid_, val in (("sensor.innen_t", 20.4), ("sensor.aussen_t", 20), ("sensor.innen_ah", 10.1), ("sensor.aussen_ah", 9.2)):
        hass.states.async_set(eid_, val)
    await _tick(hass, freezer, 1)
    assert hass.states.get(eid(hass, "sensor", entry, "recommendation")).state == "Keine Lüftung erforderlich"
    hass.states.async_set("sensor.innen_ah", 12.5)        # jetzt wirklich zu feucht
    await _tick(hass, freezer, 1)
    assert hass.states.get(eid(hass, "sensor", entry, "recommendation")).state != "Keine Lüftung erforderlich"


async def test_humidity_airing_not_contradicted_by_warm_warning(hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin) -> None:
    """Wegen Feuchte empfohlen, draußen 0,6 °C wärmer -> kein „Fenster schließen“; erst ab Sommer-Grenze."""
    freezer.move_to("2026-09-27 10:00:00+02:00")
    pushes = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await setup_room(hass, season_mode="summer")
    for eid_, val in (("sensor.innen_t", 20.4), ("sensor.aussen_t", 21.0), ("sensor.innen_ah", 12.5), ("sensor.aussen_ah", 9.2)):
        hass.states.async_set(eid_, val)
    await _tick(hass, freezer, 1)
    rec = hass.states.get(eid(hass, "sensor", entry, "recommendation"))
    assert rec.attributes["grund"] == "Feuchte"

    hass.states.async_set("binary_sensor.fenster_1", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, 2)
    assert not any(t.startswith("Fenster schließen") for t in _titles(pushes))

    hass.states.async_set("sensor.aussen_t", 24.0)          # > 3 °C wärmer -> jetzt schließen
    await _tick(hass, freezer, 1)
    assert any(t.startswith("Fenster schließen") for t in _titles(pushes))

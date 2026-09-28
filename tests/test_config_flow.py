"""Einrichtungs-Assistent und Optionen-Menü."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.smart_ventilation.const import DOMAIN

from .conftest import ROOM_DATA, set_room_states, setup_room

ROOM_INPUT = {
    "room": {"name": "Schlafzimmer", "window": ["binary_sensor.fenster_1"]},
    "indoor": {"indoor_temperature": "sensor.innen_t", "indoor_absolute_humidity": "sensor.innen_ah"},
    "outdoor": {
        "outdoor_temperature": "sensor.aussen_t",
        "outdoor_absolute_humidity": "sensor.aussen_ah",
        "rain": "sensor.regen",
        "wind_speed": "sensor.wind",
        "wind_direction": "sensor.windrichtung",
    },
    "behavior": {},
    "notify": {},
    "devices": {},
}


async def test_room_form_with_sections(hass: HomeAssistant) -> None:
    """Ein Formular mit Bereichen – einmal absenden, fertig."""
    set_room_states(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "room"})
    assert result["step_id"] == "room"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ROOM_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["entry_type"] == "room"
    assert data["name"] == "Schlafzimmer"
    assert data["window"] == ["binary_sensor.fenster_1"]
    assert data["indoor_temperature"] == "sensor.innen_t"
    assert data["season_mode"] == "auto"          # Standard aus zugeklapptem Bereich
    assert data["co2_sensor"] == ""
    assert data["climate_entities"] == []
    assert "room" not in data and "behavior" not in data  # flach gespeichert
    await hass.async_block_till_done()


async def test_room_form_accepts_optional_rh_sensors(hass: HomeAssistant) -> None:
    """Die optionalen RH-Sensoren (indoor/outdoor) lassen sich beim Einrichten mit angeben und
    werden wie die anderen optionalen Felder (z. B. CO₂-Sensor) flach gespeichert; werden sie
    weggelassen, bleiben sie leer statt das Speichern zu blockieren (wie bei co2_sensor)."""
    set_room_states(hass)
    room_input = {
        **ROOM_INPUT,
        "indoor": {**ROOM_INPUT["indoor"], "indoor_relative_humidity": "sensor.innen_rh"},
        "outdoor": {**ROOM_INPUT["outdoor"], "outdoor_relative_humidity": "sensor.aussen_rh"},
    }
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "room"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], room_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["indoor_relative_humidity"] == "sensor.innen_rh"
    assert data["outdoor_relative_humidity"] == "sensor.aussen_rh"
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "room"})
    room_input_2 = {
        **ROOM_INPUT,
        "room": {**ROOM_INPUT["room"], "name": "Büro", "window": ["binary_sensor.fenster_2"]},
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], room_input_2)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["indoor_relative_humidity"] == ""
    assert result["data"]["outdoor_relative_humidity"] == ""


async def test_room_type_suggests_target_humidity(hass: HomeAssistant) -> None:
    """Raumtyp „Schlafzimmer“ gewählt, Tagesziel unangetastet -> passender Richtwert statt
    des allgemeinen Vorschlags (siehe ROOM_TYPE_TARGET_ABS)."""
    set_room_states(hass)
    room_input = {
        **ROOM_INPUT,
        "room": {**ROOM_INPUT["room"], "room_type": "bedroom"},
    }
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "room"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], room_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["room_type"] == "bedroom"
    assert result["data"]["target_absolute_humidity"] == 8.5


async def test_room_type_does_not_override_manual_target_humidity(hass: HomeAssistant) -> None:
    """Wurde das Tagesziel bewusst gesetzt, darf der Raumtyp-Vorschlag es nicht überschreiben."""
    set_room_states(hass)
    room_input = {
        **ROOM_INPUT,
        "room": {**ROOM_INPUT["room"], "room_type": "bedroom"},
        "behavior": {"target_absolute_humidity": 12.0},
    }
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "room"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], room_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["target_absolute_humidity"] == 12.0


async def test_room_twice_aborts(hass: HomeAssistant) -> None:
    await setup_room(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "room"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ROOM_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_overview_wizard(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "overview"})
    assert result["step_id"] == "overview"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"messages": {"combine_notifications": True}, "reports": {}}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["entry_type"] == "overview"
    await hass.async_block_till_done()


def _options_input(entry, **changes):
    """Aktuelle Werte als Bereichs-Eingabe (wie das Formular sie abschickt)."""
    from custom_components.smart_ventilation.config_flow import SECTIONS, _section_fields
    current = {**entry.data, **entry.options}
    user_input = {}
    for name in SECTIONS:
        keys = [str(k) for k in _section_fields(name, None, current, with_name=False) if name != "notify"] \
            if name != "notify" else ["notify_services", "persons", "quiet_start", "quiet_end",
                                      "weekly_report", "monthly_report",
                                      "vacation_entity", "vacation_keyword"]
        user_input[name] = {k: current[k] for k in keys if k in current and current[k] not in ("", None)}
        user_input[name].update({k: v for k, v in changes.items() if k in keys})
    return user_input


async def test_options_one_form_saves_all(hass: HomeAssistant) -> None:
    entry = await setup_room(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _options_input(entry, season_mode="summer", cool_limit=17.0, energy_price=0.3)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["season_mode"] == "summer"
    assert entry.options["cool_limit"] == 17.0
    assert entry.options["energy_price"] == 0.3


async def test_options_clear_optional_field(hass: HomeAssistant) -> None:
    """Entfernte optionale Felder (z. B. Thermostate) müssen wirklich leer gespeichert werden."""
    entry = await setup_room(hass, climate_entities=["climate.wz"])
    user_input = _options_input(entry)
    user_input["devices"].pop("climate_entities", None)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["climate_entities"] == []


def _frontend_input(schema) -> dict:
    """Formular so befüllen wie die HA-Oberfläche: Defaults und vorgeschlagene Werte übernehmen."""
    result = {}
    for marker, value in schema.schema.items():
        inner = getattr(value, "schema", None)
        if inner is not None and hasattr(inner, "schema"):   # Bereich (section)
            result[str(marker)] = _frontend_input(inner)
            continue
        default = getattr(marker, "default", None)
        if callable(default):
            default = default()
        if default is not None and not (type(default).__name__ == "Undefined"):
            result[str(marker)] = default
            continue
        suggested = (getattr(marker, "description", None) or {}).get("suggested_value")
        if suggested is not None:
            result[str(marker)] = suggested
    return result


async def test_options_save_unchanged_like_frontend(hass: HomeAssistant) -> None:
    """Regression 2.1.1: leere optionale Felder (CO₂-Sensor "") ließen das Speichern scheitern."""
    entry = await setup_room(hass, co2_sensor="", weather_entity="", vacation_entity="")
    result = await hass.config_entries.options.async_init(entry.entry_id)
    user_input = _frontend_input(result["data_schema"])
    assert "co2_sensor" not in user_input["indoor"]
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["co2_sensor"] == ""
    assert entry.options["window"] == ["binary_sensor.fenster_1", "binary_sensor.fenster_2"]

"""Einrichtungs-Assistent und Optionen-Menü."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.smart_ventilation.const import DOMAIN

from .conftest import ROOM_DATA, set_room_states, setup_room

SENSOR_INPUT = {
    "name": "Schlafzimmer",
    "window": ["binary_sensor.fenster_1"],
    "indoor_absolute_humidity": "sensor.innen_ah",
    "indoor_temperature": "sensor.innen_t",
    "outdoor_absolute_humidity": "sensor.aussen_ah",
    "outdoor_temperature": "sensor.aussen_t",
    "wind_speed": "sensor.wind",
    "wind_direction": "sensor.windrichtung",
    "rain": "sensor.regen",
}


async def test_room_wizard(hass: HomeAssistant) -> None:
    set_room_states(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "sensors"})
    assert result["step_id"] == "sensors"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SENSOR_INPUT)
    assert result["step_id"] == "behavior"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "notify"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "heating"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["entry_type"] == "room"
    assert data["window"] == ["binary_sensor.fenster_1"]
    assert data["season_mode"] == "auto"
    assert data["co2_sensor"] == ""
    assert data["climate_entities"] == []
    await hass.async_block_till_done()


async def test_room_twice_aborts(hass: HomeAssistant) -> None:
    await setup_room(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "sensors"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SENSOR_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_overview_wizard(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "overview"})
    assert result["step_id"] == "overview"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"combine_notifications": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["entry_type"] == "overview"
    await hass.async_block_till_done()


async def test_options_menu_saves_section(hass: HomeAssistant) -> None:
    entry = await setup_room(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "behavior"})
    assert result["step_id"] == "behavior"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"season_mode": "summer", "cool_limit": 17.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["season_mode"] == "summer"
    assert entry.options["cool_limit"] == 17.0


async def test_options_clear_optional_field(hass: HomeAssistant) -> None:
    """Entfernte optionale Felder (z. B. Thermostate) müssen wirklich leer gespeichert werden."""
    entry = await setup_room(hass, climate_entities=["climate.wz"])
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "heating"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"energy_price": 0.1})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["climate_entities"] == []

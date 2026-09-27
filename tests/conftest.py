"""Gemeinsame Test-Hilfen: echte Home-Assistant-Instanz über pytest-homeassistant-custom-component."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ventilation.const import DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"

ROOM_DATA = {
    "entry_type": "room",
    "name": "Schlafzimmer",
    "window": ["binary_sensor.fenster_1", "binary_sensor.fenster_2"],
    "indoor_absolute_humidity": "sensor.innen_ah",
    "indoor_temperature": "sensor.innen_t",
    "outdoor_absolute_humidity": "sensor.aussen_ah",
    "outdoor_temperature": "sensor.aussen_t",
    "wind_speed": "sensor.wind",
    "wind_direction": "sensor.windrichtung",
    "wind_is_from": True,
    "rain": "sensor.regen",
    "co2_sensor": "",
    "weather_entity": "",
    "volume": 45.0,
    "window_direction": 106.0,
    "target_absolute_humidity": 10.0,
    "season_mode": "winter",
    "season_threshold": 15.0,
    "max_temperature_difference": 3.0,
    "building_standard": "average",
    "cool_limit": 18.0,
    "use_sun": False,
    "min_sun_elevation": 15.0,
    "sun_entity": "sun.sun",
    "notify_services": ["notify.mobile_app_test"],
    "persons": [],
    "notification_cooldown": 180,
    "quiet_start": "22:00:00",
    "quiet_end": "07:00:00",
    "climate_entities": [],
    "energy_price": 0.12,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Custom Components in allen Tests zulassen."""
    yield


@pytest.fixture
async def berlin(hass: HomeAssistant):
    await hass.config.async_set_time_zone("Europe/Berlin")


def set_room_states(hass: HomeAssistant, **values) -> None:
    """Typischer Wintertag: innen feucht, außen kalt und trocken."""
    defaults = {
        "sensor.innen_ah": 10.5,
        "sensor.innen_t": 20.5,
        "sensor.aussen_ah": 4.0,
        "sensor.aussen_t": 3.0,
        "sensor.wind": 8,
        "sensor.windrichtung": 110,
        "sensor.regen": 0,
        "binary_sensor.fenster_1": "off",
        "binary_sensor.fenster_2": "off",
    }
    defaults.update(values)
    for entity_id, value in defaults.items():
        hass.states.async_set(entity_id, value)


async def setup_entry(hass: HomeAssistant, data: dict, unique_id: str, title: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=data, unique_id=unique_id, title=title)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def setup_room(hass: HomeAssistant, **overrides) -> MockConfigEntry:
    set_room_states(hass)
    return await setup_entry(hass, {**ROOM_DATA, **overrides}, "schlafzimmer", "Schlafzimmer")


def eid(hass: HomeAssistant, platform: str, entry: MockConfigEntry, key: str) -> str:
    """Entity-ID über die unique_id finden – unabhängig von der Namens-Slug-Bildung."""
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, f"{platform} {key} nicht gefunden"
    return entity_id

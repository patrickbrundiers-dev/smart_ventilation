from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_OVERVIEW
from .coordinator import SmartVentilationCoordinator
from .card import async_register_card
from .overview import OverviewCoordinator

PLATFORMS = ["sensor", "binary_sensor", "button"]
OVERVIEW_PLATFORMS = ["sensor"]

# Nur über die Oberfläche einrichtbar (kein YAML)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _platforms(entry: ConfigEntry) -> list[str]:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_OVERVIEW:
        return OVERVIEW_PLATFORMS
    return PLATFORMS


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_OVERVIEW:
        coordinator = OverviewCoordinator(hass, entry)
    else:
        coordinator = SmartVentilationCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))
    # Nach Änderung der Optionen neu laden (Lerndaten liegen im Storage und bleiben)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _platforms(entry))
    coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
    if coordinator:
        coordinator.async_unload()
    return unload_ok

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_OVERVIEW
from .coordinator import SmartVentilationCoordinator
from .assist import async_setup_assist
from .card import DATA_URL as CARD_DATA_URL, async_register_card, async_remove_resource
from .export import async_setup_export
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
    await async_setup_assist(hass)
    await async_setup_export(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # async_setup() (Domain-Ebene) läuft pro HA-Prozess nur einmal. Wurde die Karten-Ressource
    # zwischenzeitlich beim Entfernen des letzten Eintrags ausgetragen (siehe async_remove_entry),
    # würde sie ohne diesen erneuten (idempotenten) Aufruf hier für einen danach neu hinzugefügten
    # Eintrag nie wieder registriert, solange Home Assistant nicht neu startet.
    await async_register_card(hass)
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


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Letzten Eintrag entfernt: Dashboard-Ressource der Karte wieder austragen."""
    remaining = [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]
    if not remaining:
        # Flag VOR dem (mehrere await-Schritte umfassenden) Aufräumen zurücksetzen, nicht danach:
        # würde currently gleichzeitig ein anderer Eintrag hinzugefügt (async_setup_entry ruft
        # async_register_card auf), während dieses Aufräumen hier noch läuft, und das Flag erst
        # danach gelöscht, könnte der andere Aufruf das (noch gesetzte) Flag sehen und sich für
        # "schon registriert" halten - die Ressource bliebe dann bis zum HA-Neustart fehlend. So
        # herum registriert der andere Aufruf im schlimmsten Fall einmal zu viel (harmlos, da
        # idempotent), statt gar nicht mehr.
        hass.data.pop(CARD_DATA_URL, None)
        await async_remove_resource(hass)

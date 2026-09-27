"""Liefert die Dashboard-Karte mit der Integration aus.

Zwei Wege, damit die Karte zuverlässig geladen wird:
1. als Dashboard-Ressource (wie HACS es für Karten macht) – wird bei jedem Dashboard-Aufruf geladen
2. zusätzlich als Frontend-Modul (Fallback, z. B. für Dashboards im YAML-Modus)
Beide nutzen dieselbe Adresse, der Browser lädt die Datei daher nur einmal.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

CARD_URL = f"/{DOMAIN}/smart-ventilation-card.js"
CARD_URL_VERSIONED = f"{CARD_URL}?v={VERSION}"
CARD_FILE = Path(__file__).parent / "www" / "smart-ventilation-card.js"


def _lovelace_resources(hass: HomeAssistant):
    """Ressourcen-Sammlung der Dashboards – None im YAML-Modus oder wenn nicht verfügbar."""
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
    except ImportError:
        return None
    data = hass.data.get(LOVELACE_DATA)
    resources = getattr(data, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return None
    return resources


async def _async_register_resource(hass: HomeAssistant) -> bool:
    """Karte als Dashboard-Ressource eintragen bzw. die Version aktualisieren."""
    resources = _lovelace_resources(hass)
    if resources is None:
        return False
    await resources.async_get_info()  # lädt die gespeicherten Ressourcen
    for item in resources.async_items():
        if str(item.get("url", "")).split("?")[0] == CARD_URL:
            if item.get("url") != CARD_URL_VERSIONED:
                await resources.async_update_item(
                    item["id"], {"res_type": "module", "url": CARD_URL_VERSIONED}
                )
            return True
    await resources.async_create_item({"res_type": "module", "url": CARD_URL_VERSIONED})
    _LOGGER.info("Dashboard-Karte als Ressource eingetragen: %s", CARD_URL_VERSIONED)
    return True


async def async_remove_resource(hass: HomeAssistant) -> None:
    """Beim Entfernen der Integration die Ressource wieder austragen."""
    resources = _lovelace_resources(hass)
    if resources is None:
        return
    try:
        await resources.async_get_info()
        for item in list(resources.async_items()):
            if str(item.get("url", "")).split("?")[0] == CARD_URL:
                await resources.async_delete_item(item["id"])
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Ressource der Karte konnte nicht entfernt werden", exc_info=True)


def _add_extra_module(hass: HomeAssistant) -> bool:
    from homeassistant.components.frontend import add_extra_js_url

    try:
        add_extra_js_url(hass, CARD_URL_VERSIONED)
    except KeyError:
        return False  # Frontend noch nicht bereit
    return True


async def async_register_card(hass: HomeAssistant) -> None:
    """Karte als statische Datei bereitstellen und im Frontend registrieren."""
    flag = f"{DOMAIN}_card_registered"
    if hass.data.get(flag) or getattr(hass, "http", None) is None:
        return  # schon erledigt oder kein Webserver (z. B. in Tests)
    hass.data[flag] = True

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
        )
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard-Karte konnte nicht bereitgestellt werden")
        return

    async def _register(_event: Event | None = None) -> None:
        module_ok = _add_extra_module(hass)
        try:
            resource_ok = await _async_register_resource(hass)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Dashboard-Ressource der Karte konnte nicht eingetragen werden", exc_info=True)
            resource_ok = False
        if not module_ok and not resource_ok:
            _LOGGER.warning(
                "Dashboard-Karte konnte nicht registriert werden. Bitte unter Einstellungen → "
                "Dashboards → Ressourcen %s als JavaScript-Modul hinzufügen.",
                CARD_URL_VERSIONED,
            )

    # Dashboards und Frontend sind erst nach dem Start sicher bereit
    if hass.state is CoreState.running:
        await _register()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register)

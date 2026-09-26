"""Liefert die Dashboard-Karte mit der Integration aus."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

CARD_URL = f"/{DOMAIN}/smart-ventilation-card.js"
CARD_FILE = Path(__file__).parent / "www" / "smart-ventilation-card.js"


def _add_to_frontend(hass: HomeAssistant) -> bool:
    """Karte beim Laden des Frontends mitladen lassen; False, wenn das Frontend noch nicht bereit ist."""
    from homeassistant.components.frontend import add_extra_js_url

    try:
        # ?v= sorgt dafür, dass Browser und App nach Updates die neue Version laden
        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    except KeyError:
        return False
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

    if _add_to_frontend(hass):
        _LOGGER.debug("Dashboard-Karte registriert: %s", CARD_URL)
        return

    # Frontend lädt noch – nach dem Start erneut versuchen
    async def _retry(_event: Event) -> None:
        if not _add_to_frontend(hass):
            _LOGGER.warning(
                "Dashboard-Karte konnte nicht im Frontend registriert werden. "
                "Alternativ unter Einstellungen → Dashboards → Ressourcen %s als JavaScript-Modul hinzufügen.",
                CARD_URL,
            )

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _retry)

"""Liefert die Dashboard-Karte mit der Integration aus."""
from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

CARD_URL = f"/{DOMAIN}/smart-ventilation-card.js"
CARD_FILE = Path(__file__).parent / "www" / "smart-ventilation-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    """Karte als statische Datei bereitstellen und im Frontend laden lassen."""
    flag = f"{DOMAIN}_card_registered"
    if hass.data.get(flag) or getattr(hass, "http", None) is None:
        return
    try:
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
        )
        # ?v= sorgt dafür, dass Browser nach Updates die neue Version laden
        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    except Exception:  # noqa: BLE001 – ohne Frontend (z. B. in Tests) einfach keine Karte
        return
    hass.data[flag] = True

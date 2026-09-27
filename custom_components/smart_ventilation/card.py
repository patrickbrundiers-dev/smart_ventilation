"""Liefert die Dashboard-Karte mit der Integration aus.

Damit die Karte auch direkt nach einem Neustart zuverlässig lädt:
1. Die Datei wird nach /config/www/smart_ventilation/ kopiert und über /local/ ausgeliefert.
   /local/ stellt Home Assistant schon ganz am Anfang des Starts bereit (lange bevor diese
   Integration geladen ist) und mit Cache-Headern, das Handy behält die Datei also.
2. Sie wird als Dashboard-Ressource eingetragen (wie HACS es für Karten macht) –
   das Dashboard lädt sie bei jedem Aufruf.
3. Zusätzlich als Frontend-Modul (Fallback, z. B. für Dashboards im YAML-Modus).
Alle Wege nutzen dieselbe Adresse, der Browser lädt die Datei daher nur einmal.
Gibt es /local/ noch nicht (Ordner www fehlte beim Start), wird die eigene Adresse
/smart_ventilation/… genutzt – ab dem nächsten Neustart dann /local/.
"""
from __future__ import annotations

import logging
from pathlib import Path
import shutil

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

FILE_NAME = "smart-ventilation-card.js"
CARD_URL = f"/{DOMAIN}/{FILE_NAME}"            # eigene Adresse (erst verfügbar, wenn die Integration lädt)
LOCAL_URL = f"/local/{DOMAIN}/{FILE_NAME}"      # /config/www/… (ab Start von HA verfügbar)
OUR_URLS = (CARD_URL, LOCAL_URL)
CARD_URL_VERSIONED = f"{CARD_URL}?v={VERSION}"
LOCAL_URL_VERSIONED = f"{LOCAL_URL}?v={VERSION}"
CARD_FILE = Path(__file__).parent / "www" / FILE_NAME
DATA_URL = f"{DOMAIN}_card_url"


def _base(url: object) -> str:
    return str(url or "").split("?")[0]


def _local_file(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("www", DOMAIN, FILE_NAME))


def _copy_to_www(src: Path, dest: Path) -> bool:
    """Karte nach /config/www kopieren (nur wenn sich der Inhalt geändert hat)."""
    try:
        data = src.read_bytes()
        if dest.is_file() and dest.read_bytes() == data:
            return True
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
        return True
    except OSError:
        _LOGGER.warning("Karte konnte nicht nach %s kopiert werden", dest, exc_info=True)
        return False


def _local_served(hass: HomeAssistant) -> bool:
    """Liefert Home Assistant /local/ aus? (nur wenn der Ordner www beim Start existierte)"""
    try:
        return any(
            getattr(res, "canonical", None) == "/local"
            for res in hass.http.app.router.resources()
        )
    except Exception:  # noqa: BLE001
        return False


def _lovelace_resources(hass: HomeAssistant):
    """Ressourcen-Sammlung der Dashboards – None im YAML-Modus oder wenn nicht verfügbar."""
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
    except ImportError:
        LOVELACE_DATA = "lovelace"
    data = hass.data.get(LOVELACE_DATA)
    resources = getattr(data, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return None
    return resources


async def _async_register_resource(hass: HomeAssistant, url: str = CARD_URL_VERSIONED) -> bool:
    """Karte als Dashboard-Ressource eintragen, Adresse/Version aktualisieren, Doppelte entfernen."""
    resources = _lovelace_resources(hass)
    if resources is None:
        return False
    await resources.async_get_info()  # lädt die gespeicherten Ressourcen
    ours = [i for i in resources.async_items() if _base(i.get("url")) in OUR_URLS]
    if not ours:
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Dashboard-Karte als Ressource eingetragen: %s", url)
        return True
    keep, *duplicates = ours
    if keep.get("url") != url or keep.get("type") != "module":
        await resources.async_update_item(keep["id"], {"res_type": "module", "url": url})
    for item in duplicates:
        await resources.async_delete_item(item["id"])
    return True


async def async_remove_resource(hass: HomeAssistant) -> None:
    """Beim Entfernen der Integration Ressource und kopierte Datei wieder entfernen."""
    resources = _lovelace_resources(hass)
    if resources is not None:
        try:
            await resources.async_get_info()
            for item in list(resources.async_items()):
                if _base(item.get("url")) in OUR_URLS:
                    await resources.async_delete_item(item["id"])
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Ressource der Karte konnte nicht entfernt werden", exc_info=True)

    def _delete(path: Path) -> None:
        if path.parent.is_dir() and path.parent.name == DOMAIN:
            shutil.rmtree(path.parent, ignore_errors=True)

    await hass.async_add_executor_job(_delete, _local_file(hass))


def _add_extra_module(hass: HomeAssistant, url: str) -> bool:
    from homeassistant.components.frontend import add_extra_js_url

    try:
        add_extra_js_url(hass, url)
    except KeyError:
        return False  # Frontend noch nicht bereit
    return True


async def async_register_card(hass: HomeAssistant) -> None:
    """Karte bereitstellen und im Frontend registrieren."""
    if hass.data.get(DATA_URL) or getattr(hass, "http", None) is None:
        return  # schon erledigt oder kein Webserver (z. B. in Tests)

    # Eigene Adresse immer bereitstellen (Fallback, ältere Einträge); versioniert -> darf gecacht werden
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=True)]
        )
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard-Karte konnte nicht bereitgestellt werden")
        return

    copied = await hass.async_add_executor_job(_copy_to_www, CARD_FILE, _local_file(hass))
    url = LOCAL_URL_VERSIONED if copied and _local_served(hass) else CARD_URL_VERSIONED
    hass.data[DATA_URL] = url
    _LOGGER.debug("Dashboard-Karte wird geladen von %s", url)

    async def _register(final: bool) -> bool:
        # Bewusst andere Adresse als die Ressource: schlägt ein Weg fehl (z. B. Laden während HA
        # neu startet), merkt sich der Browser den Fehler nur für diese Adresse – der andere Weg lädt trotzdem.
        # Doppeltes Laden ist harmlos, die Karte meldet sich nur einmal an.
        module_ok = _add_extra_module(hass, CARD_URL_VERSIONED)
        try:
            resource_ok = await _async_register_resource(hass, url)
        except Exception:  # noqa: BLE001
            if final:
                _LOGGER.warning("Dashboard-Ressource der Karte konnte nicht eingetragen werden", exc_info=True)
            resource_ok = False
        if final and not module_ok and not resource_ok:
            _LOGGER.warning(
                "Dashboard-Karte konnte nicht registriert werden. Bitte unter Einstellungen → "
                "Dashboards → Ressourcen %s als JavaScript-Modul hinzufügen.",
                url,
            )
        return module_ok and resource_ok

    # So früh wie möglich eintragen; falls Frontend/Dashboards noch nicht bereit sind, nach dem Start erneut
    running = hass.state is CoreState.running
    if not await _register(final=running) and not running:

        async def _retry(_event: Event) -> None:
            await _register(final=True)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _retry)

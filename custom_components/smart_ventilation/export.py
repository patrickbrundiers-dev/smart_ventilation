"""Dienst zum Exportieren der Statistiken als CSV-Datei (Woche/Monat/Gesamt je Raum)."""
from __future__ import annotations

import csv
import io

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import CONF_NAME, DOMAIN

SERVICE_EXPORT = "export_statistics"
PERIODS = ("day", "week", "month", "total")
PERIOD_LABEL = {"day": "Heute", "week": "Woche", "month": "Monat", "total": "Gesamt"}

FIELDS = [
    "raum", "zeitraum", "anzahl", "erfolgreich", "minuten",
    "kwh", "kosten_eur", "kwh_gespart", "kosten_gespart_eur",
]


def _rooms(hass: HomeAssistant):
    return [
        c for c in hass.data.get(DOMAIN, {}).values()
        if not getattr(c, "is_overview", False)
    ]


def _rows(hass: HomeAssistant) -> list[dict]:
    rows = []
    for room in _rooms(hass):
        name = room.data.get(CONF_NAME)
        for period in PERIODS:
            s = room.period_stats(period)
            rows.append({
                "raum": name,
                "zeitraum": PERIOD_LABEL[period],
                "anzahl": s["count"],
                "erfolgreich": s["ok"],
                "minuten": s["minutes"],
                "kwh": s["kwh"],
                "kosten_eur": s["cost"],
                "kwh_gespart": s["kwh_gespart"],
                "kosten_gespart_eur": s["kosten_gespart"],
            })
    return rows


def _write_csv(hass: HomeAssistant, rows: list[dict]):
    """Schreibt die CSV nach www/, damit sie ohne weiteren Zugriff über /local/... abrufbar ist."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, delimiter=";")
    writer.writeheader()
    writer.writerows(rows)

    www_dir = hass.config.path("www")
    filename = f"smart_ventilation_export_{dt_util.now().strftime('%Y%m%d_%H%M%S')}.csv"

    def _write():
        import os
        try:
            os.makedirs(www_dir, exist_ok=True)
            with open(f"{www_dir}/{filename}", "w", encoding="utf-8-sig", newline="") as f:
                f.write(buffer.getvalue())
        except OSError as err:
            # Ohne das würde ein Schreibfehler (z. B. www/ nicht anlegbar, Platte voll) als
            # unklarer interner Fehler im Log landen statt als verständliche Service-Fehlermeldung.
            raise HomeAssistantError(f"Export konnte nicht geschrieben werden: {err}") from err

    return filename, _write


async def async_setup_export(hass: HomeAssistant) -> None:
    flag = f"{DOMAIN}_export"
    if hass.data.get(flag):
        return
    hass.data[flag] = True

    async def _export(call: ServiceCall) -> dict:
        rows = _rows(hass)
        filename, write = _write_csv(hass, rows)
        await hass.async_add_executor_job(write)
        url = f"/local/{filename}"
        persistent_notification.async_create(
            hass,
            f"Statistik-Export bereit: [{filename}]({url})",
            title="Lüften – Export",
            notification_id=f"{DOMAIN}_export",
        )
        return {"pfad": f"www/{filename}", "url": url, "zeilen": len(rows)}

    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT, _export, supports_response=SupportsResponse.OPTIONAL
    )

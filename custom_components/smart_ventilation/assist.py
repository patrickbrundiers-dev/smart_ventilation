"""Sprachsteuerung: „Muss ich lüften?“ – Intent, mitgelieferte Sätze und Dienst mit Antwort."""
from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import intent

from .const import DOMAIN

INTENT_STATUS = "SmartVentilationStatus"
SERVICE_STATUS = "status"

SENTENCES_DE = """\
# Automatisch von Smart Ventilation angelegt – darf angepasst werden.
language: "de"
intents:
  SmartVentilationStatus:
    data:
      - sentences:
          - "(muss|soll|sollte) ich [jetzt] lüften"
          - "(muss|soll|sollte) [jetzt] gelüftet werden"
          - "wo (muss|soll|sollte) ich [jetzt] lüften"
          - "(wie ist|was sagt) die lüftung[sempfehlung]"
          - "lüftungsstatus"
"""


def _rooms(hass: HomeAssistant):
    return [
        c for c in hass.data.get(DOMAIN, {}).values()
        if not getattr(c, "is_overview", False)
    ]


def status_text(hass: HomeAssistant) -> str:
    rooms = _rooms(hass)
    if not rooms:
        return "Es ist noch kein Raum für die Lüftung eingerichtet."
    running = [r.data.get("name") for r in rooms if r.session]
    due = [r for r in rooms if r.recommended_minutes > 0 and not r.session]
    parts = []
    if due:
        due.sort(key=lambda r: -r.recommended_minutes)
        items = [f"{r.data.get('name')} etwa {r.recommended_minutes} Minuten" for r in due]
        parts.append("Ja, bitte lüften: " + _join(items) + ".")
    else:
        parts.append("Nein, gerade muss nirgends gelüftet werden.")
    if running:
        parts.append(f"Gerade gelüftet wird: {_join(running)}.")
    cold = [r.data.get("name") for r in rooms if r.cooling_down]
    if cold:
        parts.append(f"Achtung, {_join(cold)} kühlt aus.")
    return " ".join(parts)


def _join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " und " + items[-1]


class VentilationStatusIntent(intent.IntentHandler):
    intent_type = INTENT_STATUS
    description = "Sagt, ob und wo gelüftet werden sollte."

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent_obj.create_response()
        response.async_set_speech(status_text(intent_obj.hass))
        return response


def _write_sentences(path: Path) -> None:
    if path.exists():
        return  # eigene Anpassungen nie überschreiben
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SENTENCES_DE, encoding="utf-8")


async def async_setup_assist(hass: HomeAssistant) -> None:
    flag = f"{DOMAIN}_assist"
    if hass.data.get(flag):
        return
    hass.data[flag] = True

    intent.async_register(hass, VentilationStatusIntent())

    async def _status(call: ServiceCall) -> dict:
        return {
            "text": status_text(hass),
            "raeume": [
                {
                    "raum": r.data.get("name"),
                    "empfehlung": r.recommendation,
                    "minuten": r.recommended_minutes,
                    "laeuft": r.session is not None,
                }
                for r in _rooms(hass)
            ],
        }

    hass.services.async_register(
        DOMAIN, SERVICE_STATUS, _status, supports_response=SupportsResponse.ONLY
    )

    try:
        await hass.async_add_executor_job(
            _write_sentences, Path(hass.config.path("custom_sentences", "de", "smart_ventilation.yaml"))
        )
    except OSError:
        pass  # z. B. schreibgeschützt – Intent und Dienst funktionieren trotzdem

"""Gemeinsame Benachrichtigungs-Logik für Räume und Übersicht."""
from __future__ import annotations

import re

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CATEGORY_CONF_KEYS, CONF_QUIET_END, CONF_QUIET_END_WEEKEND, CONF_QUIET_START,
    CONF_QUIET_START_WEEKEND, CONF_QUIET_WEEKEND_DIFFERENT,
)


def parse_time(value, fallback):
    """'22:00' oder '22:00:00' -> Minuten seit Mitternacht."""
    try:
        parts = str(value or fallback).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return parse_time(fallback, "00:00")


def _time_in_range(now, start, end, default_start, default_end) -> bool:
    start_min = parse_time(start, default_start)
    end_min = parse_time(end, default_end)
    minute = now.hour * 60 + now.minute
    if start_min == end_min:
        return False
    if start_min < end_min:
        return start_min <= minute < end_min
    return minute >= start_min or minute < end_min  # über Mitternacht


def quiet_hours_range(now, data):
    """(Anfang, Ende) der für 'now' geltenden Ruhezeit - je nach Wochentag."""
    if now.weekday() >= 5 and data.get(CONF_QUIET_WEEKEND_DIFFERENT):
        return data.get(CONF_QUIET_START_WEEKEND), data.get(CONF_QUIET_END_WEEKEND)
    return data.get(CONF_QUIET_START), data.get(CONF_QUIET_END)


def in_quiet_hours(now, data, default_start, default_end) -> bool:
    """Ruhezeit für 'now' - am Wochenende (Sa/So) mit eigener Ruhezeit, sofern aktiviert."""
    start, end = quiet_hours_range(now, data)
    return _time_in_range(now, start, end, default_start, default_end)


def targets_for_category(data, category, targets):
    """Nur die Ziele, die diese Benachrichtigungsart abonniert haben.

    Ist die Kategorie noch nicht konfiguriert (alter Eintrag oder frisch hinzugefügtes Ziel -
    der Schlüssel fehlt dann komplett in `data`), bekommen weiterhin alle übergebenen `targets`
    diese Kategorie - das Verhalten ändert sich ohne bewusste Einschränkung durch den Nutzer
    nicht. Hat der Nutzer die Auswahl dagegen bewusst geleert (Schlüssel vorhanden, aber []),
    heißt das "niemand" und muss auch so respektiert werden - nicht mit "nicht konfiguriert"
    verwechseln, sonst kommt trotz bewusst leerer Auswahl wieder an alle Ziele eine Nachricht.
    """
    if not category:
        return list(targets)
    key = CATEGORY_CONF_KEYS.get(category)
    if not key or key not in data:
        return list(targets)
    allowed = set(data.get(key) or [])
    return [t for t in targets if t in allowed]



# ---------------------------------------------------------------------------
# Persistente Benachrichtigungs-Sperre
# ---------------------------------------------------------------------------
def notification_guard_key(category, title):
    """Stabiler Schlüssel für dieselbe Benachrichtigungsart eines Ziels."""
    return f"{str(category or 'generic')}|{str(title or '').strip()}"


def load_notification_guard(value):
    """Bereinigt persistierte Sperrdaten defensiv."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, dict):
            continue
        at = item.get("at")
        try:
            priority = int(item.get("priority", 0))
        except (TypeError, ValueError):
            priority = 0
        if isinstance(at, str):
            result[key] = {"at": at, "priority": priority}
    return result


def reserve_notification(guard, key, now, cooldown_seconds, priority=0):
    """Reserviert eine Benachrichtigung vor dem asynchronen Versand."""
    item = guard.get(key)
    if item:
        previous = dt_util.parse_datetime(item.get("at"))
        if previous is not None:
            elapsed = (now - previous).total_seconds()
            if elapsed < max(0, cooldown_seconds) and int(item.get("priority", 0)) >= priority:
                return False
    guard[key] = {"at": now.isoformat(), "priority": int(priority)}
    return True


def release_notification(guard, key):
    """Hebt eine Reservierung bei fehlgeschlagenem Versand wieder auf."""
    guard.pop(key, None)


def owner_map(hass: HomeAssistant, persons: list[str]) -> dict[str, str]:
    """notify.mobile_app_<gerät> -> person.<name>, über die Geräte-Tracker der Person.

    Die Companion-App legt device_tracker.<gerät> und notify.mobile_app_<gerät>
    mit demselben Namen an – darüber lässt sich das Handy seiner Person zuordnen.
    """
    owners: dict[str, str] = {}
    for person in persons:
        state = hass.states.get(person)
        if state is None:
            continue
        for tracker in state.attributes.get("device_trackers") or []:
            object_id = str(tracker).partition(".")[2]
            if object_id:
                owners[f"notify.mobile_app_{object_id}"] = person
    return owners


def anyone_home(hass: HomeAssistant, persons: list[str]) -> bool:
    """Ohne ausgewählte Personen gilt: immer jemand da."""
    if not persons:
        return True
    return any(
        (state := hass.states.get(p)) is not None and state.state == "home"
        for p in persons
    )


def filter_targets(hass, targets, persons, only_home=True, only_person=None):
    """Nur Handys von Anwesenden (oder einer bestimmten Person).

    Handys, die keiner Person zugeordnet werden können, bekommen bei der Anwesenheits-Filterung
    (only_home) immer Nachrichten. Bei einer an eine bestimmte Person gerichteten Nachricht
    (only_person gesetzt, z. B. „Willkommen zu Hause“) dagegen nicht - sie ist ja nur für diese
    eine Person gedacht.
    """
    if not persons:
        return list(targets) if only_person is None else []
    owners = owner_map(hass, persons)
    result = []
    for target in targets:
        person = owners.get(target)
        if only_person is not None:
            if person == only_person:
                result.append(target)
            continue
        if person is None or not only_home:
            result.append(target)
            continue
        state = hass.states.get(person)
        if state is not None and state.state == "home":
            result.append(target)
    return result


# Sprachausgabe (Alexa Media Player): liest nur den Nachrichtentext vor, nicht den Titel
VOICE_PREFIXES = ("alexa_media",)

_SPEECH_RULES = [
    (r"\s*\n+\s*•?\s*", ". "),            # Zeilen und Aufzählungen -> Sätze
    (r"•\s*", ""),
    (r"(\d)\.(\d)", r"\1,\2"),             # 4.2 -> 4,2
    (r"\s?g/m³", " Gramm pro Kubikmeter"),
    (r"\s?°C", " Grad"),
    (r"\s?%", " Prozent"),
    (r"\s?kWh", " Kilowattstunden"),
    (r"\s?€", " Euro"),
    (r"≈", "etwa"),
    (r"(\d)\s?×", r"\1 mal"),
    (r"\s?→\s?", " auf "),
    (r"CO₂", "CO2"),
    (r"\bca\.", "circa"),
    (r"\bMin\.", "Minuten"),
    (r"(\d) T\.", r"\1 Tage"),
    (r"(\d) h\b", r"\1 Stunden"),
    (r"\s*\(\s*", ", "),
    (r"\s*\)", ""),
    (r"\s+[–-]\s+", ", "),                 # Gedankenstrich
    (r":\s+", ", "),
    (r"\s{2,}", " "),
    (r"\s+([.,])", r"\1"),
    (r",\s*\.", "."),
    (r"\.(\s*\.)+", "."),
]


def is_voice(service_name: str) -> bool:
    return str(service_name).startswith(VOICE_PREFIXES)


def speech_text(title: str, message: str) -> str:
    """Titel + Nachricht als vorlesbarer Text (Raum steht meist im Titel)."""
    title = str(title or "")
    head, sep, room = title.partition(": ")
    if sep and room and not room[0].isdigit():
        title = f"{room}, {head}"        # „Lüften fertig: Bad“ -> „Bad, Lüften fertig“
    text = f"{title}. {message}" if title else str(message)
    for pattern, repl in _SPEECH_RULES:
        text = re.sub(pattern, repl, text)
    text = text.strip(" ,")
    return text if text.endswith((".", "!", "?")) else f"{text}."


async def send(hass: HomeAssistant, targets, title, message, tag, actions=None) -> bool:
    """An alle Empfänger senden; ein fehlerhafter Dienst stoppt die anderen nicht."""
    sent = False
    for target in targets:
        service_name = str(target).partition(".")[2]
        if not service_name or not hass.services.has_service("notify", service_name):
            continue
        if is_voice(service_name):
            payload = {"message": speech_text(title, message), "data": {"type": "tts"}}
        else:
            payload = {
                "title": title,
                "message": message,
                "data": {"tag": tag, **({"actions": actions} if actions else {})},
            }
        try:
            await hass.services.async_call("notify", service_name, payload, blocking=False)
            sent = True
        except Exception:  # noqa: BLE001 – ein Handy offline darf nichts blockieren
            continue
    return sent

"""Gemeinsame Benachrichtigungs-Logik für Räume und Übersicht."""
from __future__ import annotations

from homeassistant.core import HomeAssistant


def parse_time(value, fallback):
    """'22:00' oder '22:00:00' -> Minuten seit Mitternacht."""
    try:
        parts = str(value or fallback).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return parse_time(fallback, "00:00")


def in_quiet_hours(now, start, end, default_start, default_end) -> bool:
    start_min = parse_time(start, default_start)
    end_min = parse_time(end, default_end)
    minute = now.hour * 60 + now.minute
    if start_min == end_min:
        return False
    if start_min < end_min:
        return start_min <= minute < end_min
    return minute >= start_min or minute < end_min  # über Mitternacht


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

    Handys, die keiner Person zugeordnet werden können, bekommen immer Nachrichten.
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


async def send(hass: HomeAssistant, targets, title, message, tag, actions=None) -> bool:
    """An alle Empfänger senden; ein fehlerhafter Dienst stoppt die anderen nicht."""
    sent = False
    for target in targets:
        service_name = str(target).partition(".")[2]
        if not service_name or not hass.services.has_service("notify", service_name):
            continue
        try:
            await hass.services.async_call(
                "notify",
                service_name,
                {
                    "title": title,
                    "message": message,
                    "data": {"tag": tag, **({"actions": actions} if actions else {})},
                },
                blocking=False,
            )
            sent = True
        except Exception:  # noqa: BLE001 – ein Handy offline darf nichts blockieren
            continue
    return sent

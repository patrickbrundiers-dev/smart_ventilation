"""Übersicht über alle Räume: dringendster Raum und Sammel-Benachrichtigung."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_SKIP, ACTION_SNOOZE, CO2_ELEVATED, CO2_HIGH, CONF_COMBINE,
    CONF_NOTIFICATION_COOLDOWN, CONF_NOTIFY_SERVICES, CONF_PERSONS,
    CONF_QUIET_END, CONF_QUIET_START, DEFAULT_NOTIFICATION_COOLDOWN,
    DEFAULT_QUIET_END, DEFAULT_QUIET_START, DOMAIN, SNOOZE_MINUTES, STORE_KEY,
    STORE_VERSION,
)
from . import notify_util

MOLD_WEIGHT = {"hoch": 3.0, "erhöht": 1.5}


class OverviewCoordinator:
    is_overview = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        self.data = {**entry.data, **entry.options}
        self.store = Store(hass, STORE_VERSION, f"{STORE_KEY}_{entry.entry_id}")
        self._listeners = []
        self._unsubs = []
        self.last_notification_at = None
        self._snooze_until = None
        self._skip_date = None

    # ------------------------------------------------------------------
    @property
    def combine(self):
        return bool(self.data.get(CONF_COMBINE, True))

    @property
    def persons(self):
        return [p for p in (self.data.get(CONF_PERSONS) or []) if p]

    @property
    def notify_targets(self):
        return [t for t in (self.data.get(CONF_NOTIFY_SERVICES) or []) if str(t).startswith("notify.")]

    def rooms(self):
        return [
            c for c in self.hass.data.get(DOMAIN, {}).values()
            if not getattr(c, "is_overview", False)
        ]

    @staticmethod
    def urgency(room):
        """Je höher, desto dringender: Feuchteunterschied + Schimmel + CO₂."""
        score = max(0.0, room.humidity_difference or 0.0)
        score += MOLD_WEIGHT.get(room.mold_risk, 0.0)
        co2 = room.co2
        if co2 is not None:
            score += 3.0 if co2 >= CO2_HIGH else 1.5 if co2 >= CO2_ELEVATED else 0.0
        return round(score, 2)

    def room_list(self):
        rooms = []
        for room in self.rooms():
            rooms.append({
                "raum": room.data.get("name"),
                "lueften": room.recommended_minutes > 0,
                "empfehlung": room.recommendation,
                "minuten": room.recommended_minutes,
                "feuchteunterschied": room.humidity_difference,
                "schimmelrisiko": room.mold_risk,
                "co2": room.co2,
                "laeuft": room.session is not None,
                "dringlichkeit": self.urgency(room),
            })
        rooms.sort(key=lambda r: (not r["lueften"], -r["dringlichkeit"]))
        return rooms

    def rooms_needing(self):
        return [r for r in self.room_list() if r["lueften"]]

    @property
    def most_urgent(self):
        needing = self.rooms_needing()
        return needing[0]["raum"] if needing else "Keiner"

    # ------------------------------------------------------------------
    async def async_setup(self):
        stored = await self.store.async_load() or {}
        if stored.get("last_notification_at"):
            self.last_notification_at = dt_util.parse_datetime(stored["last_notification_at"])
        self._unsubs.append(
            async_track_time_interval(self.hass, self._tick, timedelta(seconds=60))
        )
        self._unsubs.append(
            self.hass.bus.async_listen("mobile_app_notification_action", self._handle_action)
        )

    def async_unload(self):
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def async_add_listener(self, update_callback):
        self._listeners.append(update_callback)

        @callback
        def remove():
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)
        return remove

    @callback
    def _handle_action(self, event):
        action = event.data.get("action", "")
        if action == f"{ACTION_SNOOZE}{self.entry.entry_id}":
            self._snooze_until = dt_util.now() + timedelta(minutes=SNOOZE_MINUTES)
        elif action == f"{ACTION_SKIP}{self.entry.entry_id}":
            self._skip_date = dt_util.now().date()

    async def _tick(self, _now=None):
        for update_callback in list(self._listeners):
            update_callback()
        if self.combine:
            await self._send_combined()

    async def _send_combined(self):
        now = dt_util.now()
        due = [r for r in self.rooms() if r.reminder_allowed(now)]
        if not due or not self.notify_targets:
            return
        if not notify_util.anyone_home(self.hass, self.persons):
            return
        if self._skip_date == now.date() or notify_util.in_quiet_hours(
            now, self.data.get(CONF_QUIET_START), self.data.get(CONF_QUIET_END),
            DEFAULT_QUIET_START, DEFAULT_QUIET_END,
        ):
            return

        snooze_over = False
        if self._snooze_until is not None:
            if now < self._snooze_until:
                return
            self._snooze_until = None
            snooze_over = True

        cooldown = int(self.data.get(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN)) * 60
        if (
            not snooze_over
            and self.last_notification_at is not None
            and (now - self.last_notification_at).total_seconds() < cooldown
        ):
            return

        due.sort(key=self.urgency, reverse=True)
        lines = [f"• {r.data.get('name')}: {r.recommendation}" for r in due]
        title = (
            f"Lüften: {due[0].data.get('name')}" if len(due) == 1
            else f"Lüften: {len(due)} Räume"
        )
        sent = await notify_util.send(
            self.hass,
            notify_util.filter_targets(self.hass, self.notify_targets, self.persons),
            title,
            "\n".join(lines),
            f"smart_ventilation_{self.entry.entry_id}",
            actions=[
                {"action": f"{ACTION_SNOOZE}{self.entry.entry_id}",
                 "title": f"In {SNOOZE_MINUTES} Min. erinnern"},
                {"action": f"{ACTION_SKIP}{self.entry.entry_id}", "title": "Heute nicht mehr"},
            ],
        )
        if sent:
            self.last_notification_at = now
            await self.store.async_save({"last_notification_at": now.isoformat()})

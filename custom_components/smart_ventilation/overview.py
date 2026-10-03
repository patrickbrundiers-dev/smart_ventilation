"""Übersicht über alle Räume: dringendster Raum und Sammel-Benachrichtigung."""
from __future__ import annotations

from datetime import date, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_SKIP, ACTION_SNOOZE, CAT_REMINDER, CAT_REPORT, CO2_ELEVATED, CO2_HIGH,
    CONF_COMBINE, CONF_NOTIFICATION_COOLDOWN, CONF_NOTIFY_SERVICES, CONF_PERSONS,
    DEFAULT_NOTIFICATION_COOLDOWN, DEFAULT_QUIET_END, DEFAULT_QUIET_START, DOMAIN,
    RAIN_SOON_URGENCY_BOOST, SNOOZE_MINUTES, STORE_KEY, STORE_VERSION,
)
from . import notify_util
from .const import CONF_WEEKLY_REPORT, REPORT_HOUR, REPORT_WEEKDAY
from .extras import _week_key, de_num
from .const import CONF_MONTHLY_REPORT, MONTHLY_REPORT_HOUR
from .history import change_percent, de, month_name

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
        self._notification_guard = {}
        self._snooze_until = None
        self._skip_date = None
        self._last_report = None
        self._last_month_report = None

    # ------------------------------------------------------------------
    @property
    def combine(self):
        return bool(self.data.get(CONF_COMBINE, True))

    @property
    def monthly_report(self):
        return bool(self.data.get(CONF_MONTHLY_REPORT))

    @property
    def weekly_report(self):
        return bool(self.data.get(CONF_WEEKLY_REPORT))

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
        if getattr(room, "_rain_soon", False) and room.recommended_minutes > 0:
            score += RAIN_SOON_URGENCY_BOOST  # bald Regen -> jetzt lüften hat Vorrang
        return round(score, 2)

    def room_list(self):
        rooms = []
        for room in self.rooms():
            s = room.period_stats("day")
            rooms.append({
                "raum": room.data.get("name"),
                "lueften": room.recommended_minutes > 0,
                "pausiert": room.pause_reason(),
                "empfehlung": room.recommendation,
                "minuten": room.recommended_minutes,
                "feuchteunterschied": room.humidity_difference,
                "schimmelrisiko": room.mold_risk,
                "co2": room.co2,
                "luft": room.air_quality,
                "laeuft": room.session is not None,
                "dringlichkeit": self.urgency(room),
                "entity_id": room.own_entity("sensor", "recommendation"),
                # Für die Entfeuchter-/Rollo-Symbole in der Raumzeile der Übersichtskarte - dieselben
                # Werte wie auf der Einzelraum-Karte (card_data()), nur hier zusätzlich über alle
                # Räume hinweg auf einen Blick statt erst jede Raumkarte einzeln öffnen zu müssen.
                "entfeuchter": room.dehumidifier_active,
                "rollo_empfehlung": room.shutter_recommended,
                "rollo_geschlossen": room.shutter_closed,
                # Für die umschaltbare Sortierung und die Aufschlüsselung des Netto-Chips auf der
                # Übersichtskarte - dieselbe Rechnung wie in totals(), nur pro Raum statt aufsummiert.
                "heute_kwh_netto": round(s["kwh"] - s["kwh_gespart"], 2),
                "heute_eur_netto": round(s["cost"] - s["kosten_gespart"], 2),
            })
        rooms.sort(key=lambda r: (not r["lueften"], bool(r["pausiert"]), -r["dringlichkeit"]))
        return rooms

    def rooms_needing(self):
        return [r for r in self.room_list() if r["lueften"]]

    def totals(self):
        """Aufsummierte Heizkosten-Bilanz durchs Lüften heute, über alle Räume."""
        kwh = cost = kwh_saved = cost_saved = 0.0
        for room in self.rooms():
            s = room.period_stats("day")
            kwh += s["kwh"]
            cost += s["cost"]
            kwh_saved += s["kwh_gespart"]
            cost_saved += s["kosten_gespart"]
        return {
            "heute_kwh": round(kwh, 2),
            "heute_eur": round(cost, 2),
            "heute_kwh_gespart": round(kwh_saved, 2),
            "heute_eur_gespart": round(cost_saved, 2),
            "heute_kwh_netto": round(kwh - kwh_saved, 2),
            "heute_eur_netto": round(cost - cost_saved, 2),
        }

    def day_trend(self, days=7):
        """7-Tage-Trend über alle Räume aufsummiert, für die Sparkline auf der Übersichtskarte."""
        out = None
        for room in self.rooms():
            trend = room.day_trend(days)
            if out is None:
                out = [dict(t) for t in trend]
                continue
            for total, t in zip(out, trend):
                total["anzahl"] += t["anzahl"]
                total["kwh"] = round(total["kwh"] + t["kwh"], 2)
                total["kosten"] = round(total["kosten"] + t["kosten"], 2)
                total["kwh_netto"] = round(total["kwh_netto"] + t["kwh_netto"], 2)
                total["kosten_netto"] = round(total["kosten_netto"] + t["kosten_netto"], 2)
        return out or []

    @property
    def most_urgent(self):
        needing = self.rooms_needing()
        return needing[0]["raum"] if needing else "Keiner"

    # ------------------------------------------------------------------
    async def async_setup(self):
        stored = await self.store.async_load() or {}
        if stored.get("last_notification_at"):
            self.last_notification_at = dt_util.parse_datetime(stored["last_notification_at"])
        self._notification_guard = notify_util.load_notification_guard(stored.get("notification_guard", {}))
        if stored.get("skip_date"):
            try:
                self._skip_date = date.fromisoformat(stored["skip_date"])
            except ValueError:
                self._skip_date = None
        if stored.get("snooze_until"):
            self._snooze_until = dt_util.parse_datetime(stored["snooze_until"])
        self._last_report = stored.get("last_report")
        self._last_month_report = stored.get("last_month_report")
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
            self.hass.async_create_task(self._save())
        elif action == f"{ACTION_SKIP}{self.entry.entry_id}":
            self._skip_date = dt_util.now().date()
            self.hass.async_create_task(self._save())

    async def _tick(self, _now=None):
        for update_callback in list(self._listeners):
            update_callback()
        if self.combine:
            await self._send_combined()
        await self._send_weekly_report()
        await self._send_monthly_report()

    async def _send_combined(self):
        now = dt_util.now()
        due = [r for r in self.rooms() if r.reminder_allowed(now)]
        if not due or not self.notify_targets:
            return
        if not notify_util.anyone_home(self.hass, self.persons):
            return
        if self._skip_date == now.date() or notify_util.in_quiet_hours(
            now, self.data, DEFAULT_QUIET_START, DEFAULT_QUIET_END,
        ):
            return

        snooze_over = False
        if self._snooze_until is not None:
            if now < self._snooze_until:
                return
            self._snooze_until = None
            snooze_over = True
            await self._save()

        cooldown = int(self.data.get(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN)) * 60

        due.sort(key=self.urgency, reverse=True)
        lines = [f"• {r.data.get('name')}: {r.recommendation}" for r in due]
        title = (
            f"Lüften: {due[0].data.get('name')}" if len(due) == 1
            else f"Lüften: {len(due)} Räume"
        )
        targets = notify_util.targets_for_category(self.data, CAT_REMINDER, self.notify_targets)
        targets = notify_util.filter_targets(self.hass, targets, self.persons)

        key = notify_util.notification_guard_key(CAT_REMINDER, title)
        if not notify_util.reserve_notification(
            self._notification_guard, key, now, 0 if snooze_over else cooldown
        ):
            return
        self.last_notification_at = now
        await self._save()

        sent = await notify_util.send(
            self.hass,
            targets,
            title,
            "\n".join(lines),
            f"smart_ventilation_{self.entry.entry_id}",
            actions=[
                {"action": f"{ACTION_SNOOZE}{self.entry.entry_id}",
                 "title": f"In {SNOOZE_MINUTES} Min. erinnern"},
                {"action": f"{ACTION_SKIP}{self.entry.entry_id}", "title": "Heute nicht mehr"},
            ],
        )
        if not sent:
            notify_util.release_notification(self._notification_guard, key)
            self.last_notification_at = None
            await self._save()

    async def _save(self):
        await self.store.async_save({
            "last_notification_at": self.last_notification_at.isoformat() if self.last_notification_at else None,
            "notification_guard": self._notification_guard,
            "skip_date": self._skip_date.isoformat() if self._skip_date else None,
            "snooze_until": self._snooze_until.isoformat() if self._snooze_until else None,
            "last_report": self._last_report,
            "last_month_report": self._last_month_report,
        })

    async def _send_weekly_report(self):
        """Sonntagabend: eine Nachricht mit allen Räumen."""
        now = dt_util.now()
        if not self.weekly_report or not self.notify_targets:
            return
        if not (now.weekday() == REPORT_WEEKDAY and now.hour >= REPORT_HOUR and self._last_report != _week_key(now)):
            return
        rooms = [r.weekly_summary() for r in self.rooms()]
        if not rooms:
            # Noch keine Räume registriert (z. B. Startup-Race, in der die Übersicht schon läuft,
            # aber die Raum-Einträge noch nicht) - NICHT als "diese Woche schon berichtet"
            # vermerken, sonst gäbe es für diese Woche nie mehr einen Bericht.
            return
        self._last_report = _week_key(now)
        await self._save()
        total = sum(r["anzahl"] for r in rooms)
        kwh = sum(r["kwh"] for r in rooms)
        cost = sum(r["kosten"] for r in rooms)
        lines = [f"Gesamt: {total}× gelüftet, {de_num(kwh, 1)} kWh ≈ {de_num(cost, 2)} €"]
        for r in sorted(rooms, key=lambda x: (-x["schimmeltage"], -x["anzahl"])):
            mold = f", Schimmelrisiko {r['schimmeltage']} T." if r["schimmeltage"] else ""
            lines.append(f"• {r['raum']}: {r['anzahl']}×{mold}")
        worst = max(rooms, key=lambda x: (x["schimmeltage"], x["anzahl"]))
        if worst["schimmeltage"]:
            lines.append(f"Am meisten Bedarf: {worst['raum']}")
        targets = notify_util.targets_for_category(self.data, CAT_REPORT, self.notify_targets)
        await notify_util.send(
            self.hass, targets, "Lüften – Wochenbericht", "\n".join(lines),
            f"smart_ventilation_{self.entry.entry_id}_report",
        )

    async def _send_monthly_report(self):
        """Am 1. des Monats: alle Räume im Vergleich, mit Rangfolge nach Lüftungsbedarf."""
        now = dt_util.now()
        if not self.monthly_report or not self.notify_targets:
            return
        if now.day != 1 or now.hour < MONTHLY_REPORT_HOUR:
            return
        comparisons = [(r.data.get("name"), r.month_comparison()) for r in self.rooms()]
        comparisons = [(n, c) for n, c in comparisons if c]
        if not comparisons:
            return
        month_key = max(r_key for r in self.rooms() for r_key in r.history) if any(r.history for r in self.rooms()) else None
        if month_key is None or self._last_month_report == month_key:
            return
        self._last_month_report = month_key
        await self._save()

        need = sum(c["bedarf_h"] for _, c in comparisons)
        prev = [c["vormonat"]["bedarf_h"] for _, c in comparisons if c["vormonat"]]
        kwh = sum(c["kwh"] for _, c in comparisons)
        cost = sum(c["kosten"] for _, c in comparisons)
        lines = [f"{month_name(month_key)}: Lüftungsbedarf {de(need)} h, {de(kwh)} kWh ≈ {de(cost, 2)} €"]
        change = change_percent(need, sum(prev)) if len(prev) == len(comparisons) else None
        if change is not None:
            # "change" kann 0 sein (unveränderter Bedarf) - das ist ein echtes Ergebnis und darf
            # nicht wie "kein Vergleich möglich" (None) stillschweigend übersprungen werden, siehe
            # history.py::monthly_text() für dieselbe Fallunterscheidung im Pro-Raum-Bericht.
            lines.append(
                f"{abs(change)} % {'mehr' if change > 0 else 'weniger'} Bedarf als im Vormonat"
                if change else "Bedarf wie im Vormonat"
            )
        for name, c in sorted(comparisons, key=lambda x: -x[1]["bedarf_h"]):
            mold = f", {c['schimmeltage']} Schimmeltage" if c["schimmeltage"] else ""
            lines.append(f"• {name}: {de(c['bedarf_h'])} h Bedarf, {c['lueftungen']}× gelüftet{mold}")
        top = max(comparisons, key=lambda x: x[1]["bedarf_h"])
        if top[1]["bedarf_h"] > 0:
            lines.append(f"Am häufigsten Lüftungsbedarf: {top[0]}")
        targets = notify_util.targets_for_category(self.data, CAT_REPORT, self.notify_targets)
        await notify_util.send(
            self.hass, targets, "Lüften – Monatsbericht", "\n".join(lines),
            f"smart_ventilation_{self.entry.entry_id}_month",
        )
